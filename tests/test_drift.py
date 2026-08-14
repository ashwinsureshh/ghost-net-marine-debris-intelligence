"""FR-3 — trajectory integration, uncertainty envelope, and reproducibility."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest

from ghostnet.agents.detection import detect
from ghostnet.agents.drift import (
    GriddedCurrentField,
    UniformCurrentField,
    implied_speed_ms,
    mean_track_error_km,
    run_trajectory,
)
from ghostnet.geo import haversine_km

EASTWARD = UniformCurrentField(u_ms=0.2, v_ms=0.0, name="test-eastward")


@pytest.fixture
def detection(debris_tile):
    return detect(debris_tile)[0]


def test_forward_trajectory_follows_the_current(detection):
    track = run_trajectory(
        detection,
        EASTWARD,
        direction="forward",
        horizon_days=5.0,
        ensemble_size=1,
        velocity_sigma=0.0,
        windage_sigma_ms=0.0,
    )
    assert track.endpoint.lon > detection.lon
    assert track.endpoint.lat == pytest.approx(detection.lat, abs=1e-6)


def test_windage_moves_the_patch_off_the_pure_current_line(detection):
    """Windage is unmodelled physics, so it must widen the track, not vanish."""
    pure = run_trajectory(
        detection,
        EASTWARD,
        direction="forward",
        horizon_days=5.0,
        ensemble_size=1,
        velocity_sigma=0.0,
        windage_sigma_ms=0.0,
    )
    with_wind = run_trajectory(
        detection, EASTWARD, direction="forward", horizon_days=5.0, ensemble_size=1
    )
    assert with_wind.endpoint.lat != pytest.approx(pure.endpoint.lat, abs=1e-4)


def test_backward_trajectory_runs_against_the_current(detection):
    track = run_trajectory(
        detection, EASTWARD, direction="backward", horizon_days=5.0, ensemble_size=1
    )
    assert track.endpoint.lon < detection.lon
    assert track.points[-1].t < detection.acquired_at


def test_displacement_matches_speed_times_time(detection):
    """0.2 m/s for 5 days is 86.4 km; RK4 on a uniform field should nail it."""
    track = run_trajectory(
        detection,
        EASTWARD,
        direction="forward",
        horizon_days=5.0,
        ensemble_size=1,
        velocity_sigma=0.0,
        windage_sigma_ms=0.0,
    )
    distance = haversine_km(
        detection.lon, detection.lat, track.endpoint.lon, track.endpoint.lat
    )
    assert distance == pytest.approx(86.4, rel=0.02)


def test_the_run_is_reproducible_for_a_fixed_seed(detection):
    """PRD §8 — same inputs and seed must give the same envelope."""
    a = run_trajectory(detection, EASTWARD, seed=1234, ensemble_size=16)
    b = run_trajectory(detection, EASTWARD, seed=1234, ensemble_size=16)
    assert [p.model_dump() for p in a.points] == [p.model_dump() for p in b.points]

    c = run_trajectory(detection, EASTWARD, seed=999, ensemble_size=16)
    assert c.endpoint.model_dump() != a.endpoint.model_dump()


def test_uncertainty_envelope_starts_at_zero_and_grows(detection):
    """FR-3.3 — a trajectory with an envelope, not a deterministic path."""
    track = run_trajectory(
        detection, EASTWARD, direction="forward", horizon_days=5.0, ensemble_size=48
    )
    radii = [p.uncertainty_km for p in track.points]
    assert radii[0] == 0.0
    assert radii[-1] > 0.0
    # Monotone non-decreasing: spread cannot shrink under a uniform field.
    assert all(b >= a - 1e-6 for a, b in zip(radii, radii[1:], strict=False))


def test_a_single_member_ensemble_reports_no_spread(detection):
    track = run_trajectory(detection, EASTWARD, ensemble_size=1)
    assert all(p.uncertainty_km == 0.0 for p in track.points)


def test_trajectory_records_its_provenance(detection):
    track = run_trajectory(detection, EASTWARD, seed=7, ensemble_size=8)
    assert track.current_field == "test-eastward"
    assert track.seed == 7
    assert track.evidence[0].kind == "current_field"
    assert "seed 7" in track.evidence[0].detail


def test_bad_direction_is_rejected(detection):
    with pytest.raises(ValueError, match="backward.*forward"):
        run_trajectory(detection, EASTWARD, direction="sideways")


def test_gridded_field_interpolates_and_clamps_outside_the_domain():
    field = GriddedCurrentField(
        lons=np.array([0.0, 1.0]),
        lats=np.array([0.0, 1.0]),
        u=np.array([[0.0, 1.0], [0.0, 1.0]]),
        v=np.zeros((2, 2)),
    )
    assert field.velocity(0.5, 0.5, None)[0] == pytest.approx(0.5)
    # Outside the grid clamps to the edge rather than raising.
    assert field.velocity(9.0, 9.0, None)[0] == pytest.approx(1.0)


def test_gridded_field_validates_its_shapes():
    with pytest.raises(ValueError, match="shaped"):
        GriddedCurrentField(
            lons=np.array([0.0, 1.0, 2.0]),
            lats=np.array([0.0, 1.0]),
            u=np.zeros((2, 2)),
            v=np.zeros((2, 2)),
        )


def test_implied_speed_is_the_velocity_magnitude():
    field = UniformCurrentField(u_ms=0.3, v_ms=0.4)
    assert implied_speed_ms(field, 0.0, 0.0, None) == pytest.approx(0.5)


def test_drifter_backtest_scores_a_perfect_prediction_as_zero_error(detection):
    """PRD §12 — trajectories compared against real GDP buoy paths."""
    track = run_trajectory(
        detection, EASTWARD, direction="forward", horizon_days=2.0, ensemble_size=8
    )
    observed = [(p.t, p.lon, p.lat) for p in track.points]
    metrics = mean_track_error_km(track, observed)
    assert metrics["mean_error_km"] == pytest.approx(0.0, abs=1e-6)
    assert metrics["fraction_within_envelope"] == 1.0


def test_drifter_backtest_flags_a_track_that_leaves_the_envelope(detection):
    track = run_trajectory(
        detection, EASTWARD, direction="forward", horizon_days=2.0, ensemble_size=8
    )
    observed = [
        (p.t, p.lon + 5.0, p.lat) for p in track.points[1:]  # ~540 km off
    ]
    metrics = mean_track_error_km(track, observed)
    assert metrics["mean_error_km"] > 100
    assert metrics["fraction_within_envelope"] == 0.0


def test_drifter_backtest_needs_observations(detection):
    track = run_trajectory(detection, EASTWARD, ensemble_size=4)
    with pytest.raises(ValueError, match="No drifter observations"):
        mean_track_error_km(track, [])


def test_step_count_follows_the_horizon(detection):
    track = run_trajectory(
        detection, EASTWARD, horizon_days=2.0, step_hours=6.0, ensemble_size=1
    )
    assert len(track.points) == 9  # start + 8 six-hour steps
    span = track.points[0].t - track.points[-1].t
    assert span == timedelta(days=2)
