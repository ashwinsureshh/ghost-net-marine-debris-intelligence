"""FR-3 — Drift Agent: backward/forward trajectories with an uncertainty envelope.

Particle advection through a surface-current field, integrated with RK4. Two
things the PRD asks for that shape the design:

* **FR-3.3 — an envelope, not a path.** Every run is an ensemble. Members are
  perturbed in the two places the physics is genuinely uncertain: the current
  field itself (OSCAR is a coarse gridded product, so a member samples a
  velocity error) and windage (the fraction of wind speed a partly-submerged
  raft picks up, which depends on how it floats). The reported track is the
  ensemble mean and the envelope is its 90th-percentile spread.
* **PRD §8 — reproducibility.** The ensemble is seeded. Same detection, same
  field, same seed gives the same envelope, which is what makes the drifter
  backtest in PRD §12 a real comparison rather than a re-roll.

The current field is behind a Protocol so the agent is testable with a uniform
or synthetic field. The OSCAR loader is the only part that needs downloaded
data, and it raises with the fetch instructions when that data is not on this
machine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

import numpy as np

from ghostnet.config import DataUnavailableError, dataset_path
from ghostnet.geo import mean_position, metres_to_degrees, spread_km
from ghostnet.schemas import Detection, Evidence, Trajectory, TrajectoryPoint

DEFAULT_ENSEMBLE = 64
DEFAULT_STEP_HOURS = 6.0
DEFAULT_SEED = 20260814
# Fractional 1-sigma error applied to the sampled current velocity per member.
DEFAULT_VELOCITY_SIGMA = 0.25
# Windage: floating debris typically advects at 0–3% of wind speed on top of the
# current. With no wind field loaded this widens the ensemble rather than biasing
# it, which is the honest treatment of an unmodelled term.
DEFAULT_WINDAGE_SIGMA_MS = 0.03


@runtime_checkable
class CurrentField(Protocol):
    """Anything that can report a surface velocity in m/s at a point in time."""

    name: str

    def velocity(self, lon: float, lat: float, when: datetime) -> tuple[float, float]:
        """Return (eastward, northward) velocity in m/s."""


@dataclass
class UniformCurrentField:
    """Constant current — for unit tests and analytic sanity checks."""

    u_ms: float
    v_ms: float
    name: str = "uniform"

    def velocity(self, lon: float, lat: float, when: datetime) -> tuple[float, float]:
        return self.u_ms, self.v_ms


@dataclass
class GriddedCurrentField:
    """Bilinearly interpolated lon/lat velocity grid.

    This is the in-memory shape the OSCAR loader produces, so an agent written
    against it works identically on synthetic fixtures and on real NetCDF.
    ``u``/``v`` are indexed ``[lat, lon]``; positions outside the grid clamp to
    the edge rather than raising, so a trajectory leaving the domain decays to
    the boundary current instead of terminating mid-run.
    """

    lons: np.ndarray
    lats: np.ndarray
    u: np.ndarray
    v: np.ndarray
    name: str = "gridded"

    def __post_init__(self) -> None:
        expected = (len(self.lats), len(self.lons))
        if self.u.shape != expected or self.v.shape != expected:
            raise ValueError(
                f"Current field u/v must be shaped {expected} (lat, lon); got "
                f"{self.u.shape} and {self.v.shape}."
            )

    def velocity(self, lon: float, lat: float, when: datetime) -> tuple[float, float]:
        return (
            float(self._interp(self.u, lon, lat)),
            float(self._interp(self.v, lon, lat)),
        )

    def _interp(self, grid: np.ndarray, lon: float, lat: float) -> float:
        x = np.clip(np.interp(lon, self.lons, np.arange(len(self.lons))), 0, len(self.lons) - 1)
        y = np.clip(np.interp(lat, self.lats, np.arange(len(self.lats))), 0, len(self.lats) - 1)
        x0, y0 = int(np.floor(x)), int(np.floor(y))
        x1 = min(x0 + 1, len(self.lons) - 1)
        y1 = min(y0 + 1, len(self.lats) - 1)
        fx, fy = x - x0, y - y0
        top = grid[y0, x0] * (1 - fx) + grid[y0, x1] * fx
        bottom = grid[y1, x0] * (1 - fx) + grid[y1, x1] * fx
        return top * (1 - fy) + bottom * fy


def load_oscar_field(start: datetime, end: datetime) -> GriddedCurrentField:
    """Load NOAA OSCAR surface currents for a window from ``data/oscar``.

    Raises :class:`DataUnavailableError` when the NetCDF files are not on this
    machine — per MACHINE-WORKFLOW.md, never assume the other machine's copy is
    here.
    """
    path = dataset_path(
        "oscar", required=True, purpose="Drift trajectory modelling (FR-3.1)."
    )
    files = sorted(path.glob("*.nc"))
    if not files:
        raise DataUnavailableError(
            "oscar", path, "No NetCDF (.nc) current files found in the directory."
        )
    raise NotImplementedError(
        f"Found {len(files)} OSCAR file(s) at {path}, but the NetCDF -> "
        "GriddedCurrentField reader (time-slicing and variable naming for "
        "OSCAR_L4_OC_NRT_V2.0) is not written yet. Build it against the "
        "GriddedCurrentField contract above; the integrator needs no changes."
    )


def _rk4_step(
    field: CurrentField,
    lon: float,
    lat: float,
    when: datetime,
    dt_s: float,
    sign: int,
    velocity_scale: float,
    windage: tuple[float, float],
) -> tuple[float, float]:
    """One classical RK4 step in (lon, lat) degrees."""

    def deriv(plon: float, plat: float, t: datetime) -> tuple[float, float]:
        u, v = field.velocity(plon, plat, t)
        u = u * velocity_scale + windage[0]
        v = v * velocity_scale + windage[1]
        return metres_to_degrees(sign * u, sign * v, plat)

    half = timedelta(seconds=dt_s / 2)
    full = timedelta(seconds=dt_s)

    k1 = deriv(lon, lat, when)
    k2 = deriv(lon + k1[0] * dt_s / 2, lat + k1[1] * dt_s / 2, when + half)
    k3 = deriv(lon + k2[0] * dt_s / 2, lat + k2[1] * dt_s / 2, when + half)
    k4 = deriv(lon + k3[0] * dt_s, lat + k3[1] * dt_s, when + full)

    dlon = (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]) * dt_s / 6
    dlat = (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]) * dt_s / 6
    return lon + dlon, max(-89.9, min(89.9, lat + dlat))


def run_trajectory(
    detection: Detection,
    field: CurrentField,
    *,
    direction: str = "backward",
    horizon_days: float = 5.0,
    step_hours: float = DEFAULT_STEP_HOURS,
    ensemble_size: int = DEFAULT_ENSEMBLE,
    seed: int = DEFAULT_SEED,
    velocity_sigma: float = DEFAULT_VELOCITY_SIGMA,
    windage_sigma_ms: float = DEFAULT_WINDAGE_SIGMA_MS,
) -> Trajectory:
    """Advect an ensemble from a detection and return the mean track + envelope.

    ``direction="backward"`` estimates probable origin (FR-3.1);
    ``"forward"`` projects the next ``horizon_days`` (FR-3.2).
    """
    if direction not in {"backward", "forward"}:
        raise ValueError(f"direction must be 'backward' or 'forward', got {direction!r}")
    if ensemble_size < 1:
        raise ValueError("ensemble_size must be >= 1")

    sign = -1 if direction == "backward" else 1
    dt_s = step_hours * 3600.0
    n_steps = max(1, int(round(horizon_days * 24.0 / step_hours)))

    rng = np.random.default_rng(seed)
    scales = 1.0 + rng.normal(0.0, velocity_sigma, ensemble_size)
    wind_u = rng.normal(0.0, windage_sigma_ms, ensemble_size)
    wind_v = rng.normal(0.0, windage_sigma_ms, ensemble_size)

    members = [(detection.lon, detection.lat) for _ in range(ensemble_size)]
    points = [
        TrajectoryPoint(
            t=detection.acquired_at, lon=detection.lon, lat=detection.lat, uncertainty_km=0.0
        )
    ]

    when = detection.acquired_at
    for _ in range(n_steps):
        stepped: list[tuple[float, float]] = []
        for i, (lon, lat) in enumerate(members):
            stepped.append(
                _rk4_step(
                    field,
                    lon,
                    lat,
                    when,
                    dt_s,
                    sign,
                    float(scales[i]),
                    (float(wind_u[i]), float(wind_v[i])),
                )
            )
        members = stepped
        when = when + timedelta(seconds=sign * dt_s)
        centre = mean_position(members)
        points.append(
            TrajectoryPoint(
                t=when,
                lon=round(centre[0], 6),
                lat=round(centre[1], 6),
                uncertainty_km=round(spread_km(members, centre), 3),
            )
        )

    return Trajectory(
        detection_id=detection.id,
        direction=direction,
        horizon_days=horizon_days,
        points=points,
        ensemble_size=ensemble_size,
        seed=seed,
        current_field=getattr(field, "name", type(field).__name__),
        evidence=[
            Evidence(
                kind="current_field",
                ref=getattr(field, "name", type(field).__name__),
                detail=(
                    f"{ensemble_size}-member RK4 ensemble, {step_hours}h steps, "
                    f"seed {seed}, velocity sigma {velocity_sigma}"
                ),
            )
        ],
    )


def mean_track_error_km(
    predicted: Trajectory, observed: list[tuple[datetime, float, float]]
) -> dict[str, float]:
    """Validate a predicted track against a real drifter path (PRD §3, §12).

    ``observed`` is (time, lon, lat) from the NOAA Global Drifter Program. Each
    observation is compared to the predicted position nearest in time, and the
    result reports what fraction fell inside the uncertainty envelope — an
    envelope that never contains the truth is worse than useless, and one that
    always does is probably too wide.
    """
    from ghostnet.geo import haversine_km

    if not observed:
        raise ValueError("No drifter observations supplied")

    errors: list[float] = []
    inside = 0
    for t, lon, lat in observed:
        nearest = min(predicted.points, key=lambda p: abs((p.t - t).total_seconds()))
        error = haversine_km(nearest.lon, nearest.lat, lon, lat)
        errors.append(error)
        if error <= nearest.uncertainty_km:
            inside += 1

    return {
        "n_observations": float(len(errors)),
        "mean_error_km": round(float(np.mean(errors)), 3),
        "median_error_km": round(float(np.median(errors)), 3),
        "max_error_km": round(float(np.max(errors)), 3),
        "fraction_within_envelope": round(inside / len(errors), 4),
    }


def implied_speed_ms(field: CurrentField, lon: float, lat: float, when: datetime) -> float:
    """Local current speed — used by the verification agent's coherence check."""
    u, v = field.velocity(lon, lat, when)
    return math.hypot(u, v)
