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
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

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


@dataclass
class TimeVaryingCurrentField:
    """Linear interpolation between spatial grids; never extrapolate in time.

    Sparse observations are explicit: intervals beyond max_gap_days fail rather
    than silently bridging seasons. Spatial boundary/land behaviour matches the
    historical gridded baseline and remains an approximation.
    """

    times: np.ndarray
    fields: list[GriddedCurrentField]
    name: str = "time-varying"
    max_gap_days: float = 7.0

    def __post_init__(self) -> None:
        self.times = np.asarray(self.times, dtype="datetime64[ns]")
        if len(self.times) < 2 or len(self.times) != len(self.fields):
            raise ValueError("Time-varying currents need at least two matching grids")
        if np.isnat(self.times).any() or np.any(np.diff(self.times.astype('int64')) <= 0):
            raise ValueError("Current timestamps must be unique and strictly increasing")
        if not math.isfinite(self.max_gap_days) or self.max_gap_days <= 0:
            raise ValueError("max_gap_days must be finite and positive")

    def velocity(self, lon: float, lat: float, when: datetime) -> tuple[float, float]:
        moment = np.datetime64(_as_naive_utc(when), "ns")
        if moment < self.times[0] or moment > self.times[-1]:
            raise ValueError("Trajectory time outside available current observations")
        right = int(np.searchsorted(self.times, moment))
        if self.times[right] == moment:
            return self.fields[right].velocity(lon, lat, when)
        left = right - 1
        gap = self.times[right] - self.times[left]
        if gap / np.timedelta64(1, 'D') > self.max_gap_days:
            raise ValueError("Current observations exceed the allowed temporal gap")
        fraction = float((moment - self.times[left]) / gap)
        before = self.fields[left].velocity(lon, lat, when)
        after = self.fields[right].velocity(lon, lat, when)
        return tuple(a + fraction * (b - a) for a, b in zip(before, after, strict=True))


#: OSCAR distributions disagree on names. Total surface current first — the
#: geostrophic-only pair is a documented last resort, not an equivalent.
_U_NAMES = ("u", "uo", "u_current", "eastward_sea_water_velocity")
_V_NAMES = ("v", "vo", "v_current", "northward_sea_water_velocity")
_U_GEOSTROPHIC = ("ug", "u_geostrophic")
_V_GEOSTROPHIC = ("vg", "v_geostrophic")
_LAT_NAMES = ("lat", "latitude", "nlat", "y")
_LON_NAMES = ("lon", "longitude", "nlon", "x")

#: Padding applied when a bbox is given, so a trajectory leaving the region
#: still finds real current instead of clamping to the subset edge.
#: `GriddedCurrentField._interp` clamps rather than raising, so too tight a
#: subset degrades silently into a constant boundary current.
OSCAR_BBOX_PAD_DEG = 5.0


def _pick(names: tuple[str, ...], available: Any) -> str | None:
    lowered = {str(n).lower(): str(n) for n in available}
    for candidate in names:
        if candidate in lowered:
            return lowered[candidate]
    return None


def _as_naive_utc(moment: datetime) -> datetime:
    """Drop the timezone after converting to UTC.

    xarray decodes NetCDF times to tz-naive ``datetime64``, and pandas refuses
    to compare those against tz-aware datetimes — so slicing a window with the
    aware datetimes this codebase uses everywhere else raises `TypeError:
    Cannot compare tz-naive and tz-aware datetime-like objects`. Converting
    first (rather than just stripping tzinfo) means a non-UTC input still
    selects the right steps instead of being silently offset by its own
    UTC offset.
    """
    if moment.tzinfo is not None:
        return moment.astimezone(UTC).replace(tzinfo=None)
    return moment


def _standard_calendar(dataset):
    """Normalise a non-standard NetCDF calendar to datetime64.

    **Trap 6, found on the first real download (2026-09-04).** OSCAR's FINAL
    product declares ``calendar: julian``, so xarray decodes its time axis to
    ``cftime.DatetimeJulian`` rather than ``datetime64``. Selecting a window
    then raises ``TypeError: cannot compare ... (different calendars)`` — which
    at least fails loudly, unlike traps 1-4. Synthetic fixtures decode as
    datetime64, so no test could have caught this before real data existed.

    The conversion is by date COMPONENTS, not by absolute instant: Julian and
    Gregorian differ by ~13 days for modern dates, and reinterpreting the
    instant would silently shift every field almost a fortnight and quietly
    select the wrong days. Verified against the granule filenames — decoded
    2018-09-13 converts to 2018-09-13, matching ``..._20180913.nc`` — before
    this was relied on.
    """
    time = dataset.coords.get("time")
    if time is None or time.dtype.kind == "M":  # already datetime64
        return dataset
    try:
        return dataset.convert_calendar("standard", use_cftime=False)
    except (AttributeError, ValueError):
        # Old xarray, or a calendar it cannot map. Leave it; the window
        # selection below will raise with the real reason rather than here.
        return dataset


def load_oscar_field(
    start: datetime,
    end: datetime,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    time_varying: bool = False,
) -> GriddedCurrentField | TimeVaryingCurrentField:
    """Load NOAA OSCAR surface currents for a window from ``data/oscar``.

    Raises :class:`DataUnavailableError` when the NetCDF files are not on this
    machine — per MACHINE-WORKFLOW.md, never assume the other machine's copy is
    here.

    By default this returns the historical time-MEAN field. The experimental
    ``time_varying=True`` option retains timestamps and linearly interpolates
    between observations; extrapolation and gaps beyond seven days fail.

    **The default is a time-MEAN field, and that is a real approximation.**
    :class:`GriddedCurrentField` has no time axis — its ``velocity()`` accepts
    ``when`` and ignores it — so a months-long window collapses to one mean
    field and seasonal reversals average out. For the Gulf of Honduras window
    (Feb–Oct) that is a genuine loss of signal, and it is the first thing to
    revisit if drift validation against the Global Drifter Program disappoints.
    The returned ``name`` records the window and step count so the artefact
    shows what was averaged.

    Five traps this handles. The first four fail silently — the field loads,
    interpolates, and moves debris to the wrong place — which is why each has
    its own test in ``tests/test_oscar.py``:

    1. **Descending latitude.** OSCAR ships lat 90 -> -90. ``_interp`` uses
       ``np.interp``, which requires an ascending coordinate and returns
       plausible-looking garbage otherwise — a 1.5 lookup on a descending axis
       returns the last index, not the midpoint. Rows are flipped to ascending.
    2. **Longitude convention.** Some OSCAR distributions run 0–360 (V1 was
       stranger still, 20E–420E). The Gulf of Honduras sits at −88, which
       simply does not exist in a 0–360 grid, so every lookup would clamp to a
       Pacific edge value. Longitudes are wrapped to −180..180 and re-sorted.
    3. **Land is NaN.** One NaN corner poisons the whole bilinear interpolation
       and the trajectory integrates to NaN from that step on. Land is filled
       with zero velocity, and the fraction filled is reported in ``name`` so a
       field that is mostly land is visible rather than assumed.
    4. **Geostrophic-only files.** ``ug``/``vg`` omit the wind-driven Ekman
       component, which is much of the surface drift that actually moves
       debris. They are accepted only if the total current is absent, and the
       field is renamed to say so.
    5. **Timezone mismatch.** This one does fail loudly, but confusingly:
       NetCDF times decode tz-naive while the rest of this codebase passes
       tz-aware datetimes, and pandas refuses to compare the two. Window bounds
       are converted in :func:`_as_naive_utc` rather than at the call sites.
    """
    path = dataset_path(
        "oscar", required=True, purpose="Drift trajectory modelling (FR-3.1)."
    )
    files = sorted(path.glob("*.nc"))
    if not files:
        raise DataUnavailableError(
            "oscar", path, "No NetCDF (.nc) current files found in the directory."
        )

    # Lazy, like ghostnet.ingest's readers: drift.py sits in the deployed
    # server's import graph, and requirements-deploy.txt deliberately has no
    # xarray. Moving this to module level breaks the container build.
    import xarray as xr

    # Opened and concatenated by hand rather than with `open_mfdataset`, which
    # requires dask — a heavy dependency to add for stitching a handful of
    # files whose only shared dimension is time.
    opened = [_standard_calendar(xr.open_dataset(f, decode_times=True)) for f in files]
    try:
        if len(opened) == 1:
            dataset = opened[0]
        elif all("time" in d.dims for d in opened):
            dataset = xr.concat(opened, dim="time").sortby("time")
        else:
            dataset = xr.merge(opened)
        u_name = _pick(_U_NAMES, dataset.data_vars)
        v_name = _pick(_V_NAMES, dataset.data_vars)
        geostrophic_only = False
        if not (u_name and v_name):
            u_name = _pick(_U_GEOSTROPHIC, dataset.data_vars)
            v_name = _pick(_V_GEOSTROPHIC, dataset.data_vars)
            geostrophic_only = bool(u_name and v_name)
        if not (u_name and v_name):
            raise ValueError(
                f"No current velocity variables in {[f.name for f in files]}. "
                f"Looked for {_U_NAMES + _U_GEOSTROPHIC} / "
                f"{_V_NAMES + _V_GEOSTROPHIC}; the file has "
                f"{sorted(map(str, dataset.data_vars))}."
            )

        lat_name = _pick(_LAT_NAMES, dataset.coords)
        lon_name = _pick(_LON_NAMES, dataset.coords)
        if not (lat_name and lon_name):
            raise ValueError(
                f"No lat/lon coordinates in {[f.name for f in files]}; found "
                f"{sorted(map(str, dataset.coords))}."
            )

        subset = dataset[[u_name, v_name]]

        steps = 1
        times = None
        if "time" in subset.dims:
            # Trap 5 — NetCDF times decode tz-naive; comparing them against the
            # aware datetimes used elsewhere in this codebase raises.
            window = subset.sel(time=slice(_as_naive_utc(start), _as_naive_utc(end)))
            steps = int(window.sizes.get("time", 0))
            if steps == 0:
                available = dataset["time"].values
                raise ValueError(
                    f"No OSCAR time steps between {start:%Y-%m-%d} and "
                    f"{end:%Y-%m-%d}. The files cover "
                    f"{np.datetime_as_string(available.min(), unit='D')} to "
                    f"{np.datetime_as_string(available.max(), unit='D')} — "
                    "download the window the region actually needs."
                )
            if time_varying:
                times = np.asarray(window.time.values, dtype="datetime64[ns]")
                subset = window
            else:
                subset = window.mean(dim="time", skipna=True)

        if time_varying and (times is None or len(times) < 2):
            raise ValueError("Time-varying OSCAR requires at least two timestamps")

        # Depth is a singleton on OSCAR; drop any other leftover degenerate dim.
        subset = subset.squeeze(drop=True)
        if time_varying:
            lat_dim = subset[lat_name].dims[0]
            lon_dim = subset[lon_name].dims[0]
            subset = subset.transpose("time", lat_dim, lon_dim)
            # Subset lazily before materialising every time slice of the globe.
            if bbox is not None:
                west, south, east, north = bbox
                latitude = np.asarray(subset[lat_name].values)
                longitude = ((np.asarray(subset[lon_name].values) + 180) % 360) - 180
                yi = np.flatnonzero((latitude >= south - OSCAR_BBOX_PAD_DEG)
                                    & (latitude <= north + OSCAR_BBOX_PAD_DEG))
                xi = np.flatnonzero((longitude >= west - OSCAR_BBOX_PAD_DEG)
                                    & (longitude <= east + OSCAR_BBOX_PAD_DEG))
                if len(yi) >= 2 and len(xi) >= 2:
                    subset = subset.isel({lat_dim: yi, lon_dim: xi})

        lats = np.asarray(subset[lat_name].values, dtype=float)
        lons = np.asarray(subset[lon_name].values, dtype=float)
        u = np.asarray(subset[u_name].values, dtype=float)
        v = np.asarray(subset[v_name].values, dtype=float)
    finally:
        for handle in opened:
            handle.close()

    if not time_varying and u.shape != (len(lats), len(lons)):
        # Some distributions store [lon, lat]; transposing beats failing.
        if u.shape == (len(lons), len(lats)):
            u, v = u.T, v.T
        else:
            raise ValueError(
                f"OSCAR u has shape {u.shape}, which matches neither "
                f"(lat, lon) = {(len(lats), len(lons))} nor its transpose."
            )

    # Trap 2 — wrap longitudes before sorting, or the seam lands mid-array.
    if float(lons.max()) > 180.0:
        lons = ((lons + 180.0) % 360.0) - 180.0
    order = np.argsort(lons)
    lons, u, v = lons[order], u[..., order], v[..., order]

    # Trap 1 — np.interp needs ascending; descending returns garbage in silence.
    if len(lats) > 1 and lats[0] > lats[-1]:
        lats, u, v = lats[::-1], u[..., ::-1, :], v[..., ::-1, :]

    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        lat_mask = (lats >= min_lat - OSCAR_BBOX_PAD_DEG) & (
            lats <= max_lat + OSCAR_BBOX_PAD_DEG
        )
        lon_mask = (lons >= min_lon - OSCAR_BBOX_PAD_DEG) & (
            lons <= max_lon + OSCAR_BBOX_PAD_DEG
        )
        if lat_mask.sum() >= 2 and lon_mask.sum() >= 2:
            lats, lons = lats[lat_mask], lons[lon_mask]
            u = u[..., lat_mask, :][..., lon_mask]
            v = v[..., lat_mask, :][..., lon_mask]

    # Trap 3 — one NaN corner poisons the bilinear interpolation downstream.
    land = ~np.isfinite(u) | ~np.isfinite(v)
    land_fraction = float(land.mean()) if land.size else 0.0
    u = np.where(land, 0.0, u)
    v = np.where(land, 0.0, v)

    kind = "oscar-geostrophic" if geostrophic_only else "oscar"
    if time_varying:
        return TimeVaryingCurrentField(
            times=times,
            fields=[GriddedCurrentField(lons, lats, ui, vi)
                    for ui, vi in zip(u, v, strict=True)],
            name=f"{kind} time-varying {start:%Y-%m-%d}..{end:%Y-%m-%d} "
                 f"({steps} steps, {land_fraction:.0%} land; max gap 7 days)",
        )
    name = (
        f"{kind} mean {start:%Y-%m-%d}..{end:%Y-%m-%d} "
        f"({steps} step(s), {len(files)} file(s), {land_fraction:.0%} land)"
    )
    return GriddedCurrentField(lons=lons, lats=lats, u=u, v=v, name=name)


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

    half = timedelta(seconds=sign * dt_s / 2)
    full = timedelta(seconds=sign * dt_s)

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
    diffusivity_m2s: float = 0.0,
) -> Trajectory:
    """Advect an ensemble from a detection and return the mean track + envelope.

    ``diffusivity_m2s`` (opt-in, default 0) adds a random walk with horizontal
    eddy diffusivity K after every RK4 step: a zero-mean Gaussian displacement
    of standard deviation sqrt(2 K dt) per axis, drawn from a separate seeded
    stream. It represents dispersion by currents the field does not resolve,
    so spread grows as sqrt(t). At 0 no extra draws are made and the result is
    bit-identical to the unmodified ensemble. Experimental; see
    docs/drift-diffusivity-protocol.md.

    ``direction="backward"`` estimates probable origin (FR-3.1);
    ``"forward"`` projects the next ``horizon_days`` (FR-3.2).
    """
    if direction not in {"backward", "forward"}:
        raise ValueError(f"direction must be 'backward' or 'forward', got {direction!r}")
    if ensemble_size < 1:
        raise ValueError("ensemble_size must be >= 1")
    if not math.isfinite(diffusivity_m2s) or diffusivity_m2s < 0:
        raise ValueError("diffusivity_m2s must be finite and >= 0")

    sign = -1 if direction == "backward" else 1
    dt_s = step_hours * 3600.0
    n_steps = max(1, int(round(horizon_days * 24.0 / step_hours)))

    rng = np.random.default_rng(seed)
    scales = 1.0 + rng.normal(0.0, velocity_sigma, ensemble_size)
    wind_u = rng.normal(0.0, windage_sigma_ms, ensemble_size)
    wind_v = rng.normal(0.0, windage_sigma_ms, ensemble_size)
    # Separate stream: enabling diffusion must not change the draws above.
    walk_rng = np.random.default_rng([seed, 1]) if diffusivity_m2s > 0 else None
    walk_sigma_m = math.sqrt(2.0 * diffusivity_m2s * dt_s)

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
        if walk_rng is not None:
            kicks = walk_rng.normal(0.0, walk_sigma_m, (ensemble_size, 2))
            walked = []
            for (lon, lat), (dx, dy) in zip(stepped, kicks, strict=True):
                dlon, dlat = metres_to_degrees(float(dx), float(dy), lat)
                walked.append((lon + dlon, max(-89.9, min(89.9, lat + dlat))))
            stepped = walked
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
                    + (f", eddy diffusivity {diffusivity_m2s} m2/s" if diffusivity_m2s else "")
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
