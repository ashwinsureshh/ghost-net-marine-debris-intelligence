"""FR-4 — ranked probability over candidate source rivers."""

from __future__ import annotations

from datetime import timedelta

import pytest

from ghostnet.agents.attribution import (
    RiverTable,
    attribute,
    matches_published_ranking,
)
from ghostnet.schemas import Evidence, Trajectory, TrajectoryPoint
from tests.conftest import BASE_TIME


def _backtrack(
    *,
    detection_id: str = "d-1",
    end_lon: float = 79.900,
    end_lat: float = 11.900,
    envelope_km: float = 20.0,
) -> Trajectory:
    """A five-step backward track ending near the fixture's high-emitter river."""
    points = []
    for i in range(6):
        f = i / 5
        points.append(
            TrajectoryPoint(
                t=BASE_TIME - timedelta(days=i),
                lon=80.010 + (end_lon - 80.010) * f,
                lat=12.000 + (end_lat - 12.000) * f,
                uncertainty_km=envelope_km * f,
            )
        )
    return Trajectory(
        detection_id=detection_id,
        direction="backward",
        horizon_days=5.0,
        points=points,
        ensemble_size=32,
        seed=1,
        current_field="test",
        evidence=[Evidence(kind="current_field", ref="test", detail="fixture backtrack")],
    )


@pytest.fixture
def table(river_csv) -> RiverTable:
    return RiverTable.from_csv(river_csv)


def test_table_loads_and_validates_columns(river_csv, tmp_path):
    assert len(RiverTable.from_csv(river_csv)) == 3

    bad = tmp_path / "bad.csv"
    bad.write_text("name,lon\nX,1\n")
    with pytest.raises(ValueError, match="missing required column"):
        RiverTable.from_csv(bad)


def test_empty_table_is_rejected(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("name,lon,lat,emission_tonnes_yr\n")
    with pytest.raises(ValueError, match="no river rows"):
        RiverTable.from_csv(empty)


def test_nearby_high_emitter_wins(table):
    result = attribute(_backtrack(), table)
    assert result.top is not None
    assert result.top.name == "Test Kali"
    assert result.top.probability > 0.5


def test_emission_weight_breaks_a_proximity_tie(table):
    """Two rivers at almost the same distance rank by how much they emit."""
    result = attribute(_backtrack(), table)
    names = [c.name for c in result.candidates]
    assert names.index("Test Kali") < names.index("Small Creek")


def test_a_distant_mega_emitter_does_not_win_on_emissions_alone(table):
    """120,000 t/yr 1,000 km away must lose to 4,200 t/yr on the backtrack."""
    result = attribute(_backtrack(), table)
    assert result.top.name != "Distant Delta"
    assert "Distant Delta" not in [c.name for c in result.candidates]


def test_probabilities_are_a_normalised_distribution(table):
    result = attribute(_backtrack(), table)
    total = sum(c.probability for c in result.candidates)
    assert total == pytest.approx(1.0, abs=1e-3)
    assert all(0.0 <= c.probability <= 1.0 for c in result.candidates)


def test_output_states_that_attribution_is_probabilistic(table):
    """PRD §13 — never a single confident claim."""
    result = attribute(_backtrack(), table)
    assert "Probabilistic" in result.note


def test_a_wider_envelope_admits_more_candidates(table):
    tight = attribute(_backtrack(envelope_km=1.0), table)
    wide = attribute(_backtrack(envelope_km=300.0), table)
    assert len(wide.candidates) >= len(tight.candidates)


def test_no_candidate_within_the_envelope_says_so_rather_than_guessing(table):
    far = _backtrack(end_lon=-40.0, end_lat=-30.0, envelope_km=1.0)
    far = far.model_copy(
        update={
            "points": [
                p.model_copy(update={"lon": -40.0, "lat": -30.0, "uncertainty_km": 1.0})
                for p in far.points
            ]
        }
    )
    result = attribute(far, table)
    assert result.candidates == []
    assert "do not read this as 'no river source'" in result.note


def test_attribution_refuses_a_forward_trajectory(table):
    forward = _backtrack().model_copy(update={"direction": "forward"})
    with pytest.raises(ValueError, match="backward trajectory"):
        attribute(forward, table)


def test_attribution_carries_both_trajectory_and_table_evidence(table):
    result = attribute(_backtrack(), table)
    kinds = {e.kind for e in result.evidence}
    assert {"current_field", "river_table"} <= kinds


def test_published_ranking_match_metric(table):
    results = [attribute(_backtrack(detection_id=f"d-{i}"), table) for i in range(4)]
    metrics = matches_published_ranking(results, {"Test Kali"})
    assert metrics == {"n_attributed": 4.0, "match_fraction": 1.0}

    miss = matches_published_ranking(results, {"Some Other River"})
    assert miss["match_fraction"] == 0.0

    assert matches_published_ranking([], set())["n_attributed"] == 0.0
