"""Opt-in eddy diffusivity in the drift ensemble (docs/drift-diffusivity-protocol.md)."""

from __future__ import annotations

import math

import pytest

from ghostnet.agents.drift import UniformCurrentField, run_trajectory
from ghostnet.schemas import Detection
from tests.conftest import BASE_TIME


def _det() -> Detection:
    return Detection(id="d", tile_id="t", acquired_at=BASE_TIME, lon=-88.5, lat=16.0,
                     area_px=1, area_km2=0, fdi_mean=0, ndvi_mean=0, confidence=1)


def _radius(traj, hours):
    return min(traj.points, key=lambda p: abs((p.t - BASE_TIME).total_seconds() / 3600 - hours))


def test_zero_diffusivity_is_bit_identical_to_the_baseline():
    field = UniformCurrentField(0.2, -0.1)
    base = run_trajectory(_det(), field, direction="forward", horizon_days=3)
    zero = run_trajectory(_det(), field, direction="forward", horizon_days=3, diffusivity_m2s=0.0)
    assert [(p.lon, p.lat, p.uncertainty_km) for p in base.points] == \
        [(p.lon, p.lat, p.uncertainty_km) for p in zero.points]


def test_diffusion_alone_spreads_as_sqrt_t_with_the_rayleigh_quantile():
    # No current, no windage: all spread is the random walk. The 90th
    # percentile of a 2-D isotropic Gaussian radius is sigma*sqrt(-2 ln 0.1),
    # with sigma = sqrt(2 K t) per axis.
    k = 1000.0
    traj = run_trajectory(_det(), UniformCurrentField(0.0, 0.0), direction="forward",
                          horizon_days=4, ensemble_size=3000, windage_sigma_ms=0.0,
                          diffusivity_m2s=k)
    for hours in (24, 96):
        expected_km = math.sqrt(2 * k * hours * 3600) * math.sqrt(-2 * math.log(0.1)) / 1000
        assert _radius(traj, hours).uncertainty_km == pytest.approx(expected_km, rel=0.08)
    ratio = _radius(traj, 96).uncertainty_km / _radius(traj, 24).uncertainty_km
    assert ratio == pytest.approx(2.0, rel=0.08)  # sqrt(4)


def test_diffusion_does_not_bias_the_mean_path():
    field = UniformCurrentField(0.3, 0.0)
    base = run_trajectory(_det(), field, direction="forward", horizon_days=2,
                          ensemble_size=2000, windage_sigma_ms=0.0, velocity_sigma=0.0)
    diffused = run_trajectory(_det(), field, direction="forward", horizon_days=2,
                              ensemble_size=2000, windage_sigma_ms=0.0, velocity_sigma=0.0,
                              diffusivity_m2s=1000.0)
    shift_km = math.hypot((base.points[-1].lon - diffused.points[-1].lon) * 107,
                          (base.points[-1].lat - diffused.points[-1].lat) * 111)
    # A zero-mean walk moves the ensemble mean only by sampling noise: per-axis
    # standard error sqrt(2 K t)/sqrt(n). A Rayleigh radius beyond 3.5 standard
    # errors has probability exp(-6.1) ~ 0.2%; a real bias would exceed it.
    standard_error_km = math.sqrt(2 * 1000.0 * 2 * 86400) / math.sqrt(2000) / 1000
    assert shift_km < 3.5 * standard_error_km


def test_same_seed_same_result_and_invalid_values_refused():
    field = UniformCurrentField(0.1, 0.1)
    a = run_trajectory(_det(), field, direction="forward", horizon_days=1, diffusivity_m2s=300)
    b = run_trajectory(_det(), field, direction="forward", horizon_days=1, diffusivity_m2s=300)
    assert a.points == b.points
    for bad in (-1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            run_trajectory(_det(), field, horizon_days=1, diffusivity_m2s=bad)
