"""FR-6 — scoring, the capacity constraint, and the human-approval checkpoint."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from ghostnet.agents.detection import detect
from ghostnet.agents.drift import UniformCurrentField, run_trajectory
from ghostnet.agents.prioritisation import (
    ProtectedArea,
    build_plan,
    load_protected_areas,
    nearest_protected_area,
    score_detection,
)
from ghostnet.llm import RationaleWriter
from ghostnet.schemas import VerificationResult, VesselCorrelation, VesselDetection
from tests.conftest import BASE_TIME

EASTWARD = UniformCurrentField(u_ms=0.3, v_ms=0.0, name="test-eastward")
OFFLINE = RationaleWriter(enabled=False)


@pytest.fixture
def detection(debris_tile):
    return detect(debris_tile)[0]


@pytest.fixture
def forward(detection):
    return run_trajectory(
        detection, EASTWARD, direction="forward", horizon_days=7.0, ensemble_size=16
    )


def _score(detection, **kwargs):
    defaults = dict(
        verification=None,
        forward=None,
        attribution=None,
        correlation=None,
        protected_areas=None,
    )
    return score_detection(detection, **{**defaults, **kwargs})


def test_missing_mpa_data_drops_the_component_instead_of_scoring_it_zero(detection, forward):
    """Scoring an unmeasured component 0 would mark every site 'ecologically safe'."""
    score = _score(detection, forward=forward, protected_areas=None)
    assert "ecological_risk" not in score.components
    assert "ecological_risk" not in score.weights
    assert sum(score.weights.values()) == pytest.approx(1.0, abs=1e-3)
    assert score.nearest_mpa_km is None


def test_mpa_data_reinstates_ecological_risk(detection, forward):
    areas = [ProtectedArea(name="Reserve", lon=detection.lon, lat=detection.lat)]
    score = _score(detection, forward=forward, protected_areas=areas)
    assert score.components["ecological_risk"] == pytest.approx(1.0, abs=1e-3)
    assert score.nearest_mpa_km == pytest.approx(0.0, abs=0.1)
    assert sum(score.weights.values()) == pytest.approx(1.0, abs=1e-3)


def test_ecological_risk_falls_off_with_distance(detection, forward):
    near = _score(
        detection,
        forward=forward,
        protected_areas=[ProtectedArea("Near", detection.lon + 0.1, detection.lat)],
    )
    far = _score(
        detection,
        forward=forward,
        protected_areas=[ProtectedArea("Far", detection.lon + 3.0, detection.lat)],
    )
    assert near.components["ecological_risk"] > far.components["ecological_risk"]


def test_urgency_is_higher_for_a_patch_heading_into_a_reserve(detection, forward):
    on_track = forward.points[len(forward.points) // 3]
    intercept = _score(
        detection,
        forward=forward,
        protected_areas=[ProtectedArea("Reserve", on_track.lon, on_track.lat, radius_km=5)],
    )
    away = _score(
        detection,
        forward=forward,
        protected_areas=[ProtectedArea("Elsewhere", detection.lon, detection.lat - 8.0)],
    )
    assert intercept.components["drift_urgency"] > away.components["drift_urgency"]


def test_fast_drift_past_no_reserve_cannot_outrank_a_reserve_interception(detection, forward):
    """Regression: the displacement fallback used to saturate at 1.0, so a patch
    drifting fast past nothing scored *more* urgent than one entering an MPA."""
    on_track = forward.points[len(forward.points) // 2]
    intercept = _score(
        detection,
        forward=forward,
        protected_areas=[ProtectedArea("Reserve", on_track.lon, on_track.lat, radius_km=5)],
    )
    fast_past_nothing = _score(
        detection,
        forward=forward,
        protected_areas=[ProtectedArea("Elsewhere", detection.lon, detection.lat - 8.0)],
    )
    assert fast_past_nothing.components["drift_urgency"] <= 0.5
    assert intercept.components["drift_urgency"] > fast_past_nothing.components["drift_urgency"]
    assert any("no protected area on the projected track" in e.detail
               for e in fast_past_nothing.evidence)


def test_no_forward_track_means_no_urgency_signal(detection):
    score = _score(detection, forward=None)
    assert score.components["drift_urgency"] == 0.0
    assert any("no forward trajectory" in e.detail for e in score.evidence)


def test_verified_confidence_replaces_the_raw_detector_score(detection):
    verification = VerificationResult(
        detection_id=detection.id, verified=True, checks=[], confidence=0.42
    )
    score = _score(detection, verification=verification)
    assert score.components["detection_confidence"] == pytest.approx(0.42)


def test_a_stronger_dark_vessel_signal_raises_the_score(detection, forward):
    """Compare like with like: the score is a weighted mean over the components
    that were measurable, so adding a *new* component moves the mean in
    whichever direction that component sits. The meaningful comparison is
    between two sites that both have the signal."""

    def with_strength(strength: float):
        return _score(
            detection,
            forward=forward,
            correlation=VesselCorrelation(
                detection_id=detection.id,
                dark_vessels=[
                    VesselDetection(
                        id="s1", lon=detection.lon, lat=detection.lat, detected_at=BASE_TIME
                    )
                ],
                correlation_strength=strength,
            ),
        )

    strong, weak = with_strength(0.9), with_strength(0.1)
    assert strong.components["dark_vessel_signal"] == 0.9
    assert strong.score > weak.score


def test_nearest_protected_area_measures_to_the_boundary():
    areas = [ProtectedArea("Reserve", 80.0, 12.0, radius_km=10.0)]
    area, distance = nearest_protected_area(80.0, 12.0, areas)
    assert area.name == "Reserve"
    assert distance == 0.0  # inside the reserve, clamped at the boundary


def test_protected_areas_load_from_json(mpa_json):
    areas = load_protected_areas(mpa_json)
    assert len(areas) == 1 and areas[0].name == "Test Marine Reserve"


# --- plan construction -----------------------------------------------------


def _scores_for(n: int, detection):
    detections = {}
    scores = []
    for i in range(n):
        clone = detection.model_copy(
            update={"id": f"d-{i}", "lon": detection.lon + i * 0.01}
        )
        detections[clone.id] = clone
        scores.append(
            _score(clone).model_copy(update={"score": round(1.0 - i * 0.1, 4)})
        )
    return detections, scores


def test_plan_is_bounded_by_vessel_capacity(detection):
    detections, scores = _scores_for(6, detection)
    plan = build_plan(
        "test-region", detections, scores, vessel_capacity=3, rationale_writer=OFFLINE
    )
    assert len(plan.assignments) == 3
    assert len(plan.deferred) == 3
    assert [a.rank for a in plan.assignments] == [1, 2, 3]
    assert [a.detection_id for a in plan.assignments] == ["d-0", "d-1", "d-2"]
    assert plan.deferred == ["d-3", "d-4", "d-5"]


def test_plan_ranks_by_score_not_input_order(detection):
    detections, scores = _scores_for(3, detection)
    shuffled = [scores[2], scores[0], scores[1]]
    plan = build_plan(
        "test-region", detections, shuffled, vessel_capacity=3, rationale_writer=OFFLINE
    )
    assert [a.detection_id for a in plan.assignments] == ["d-0", "d-1", "d-2"]


def test_each_vessel_is_assigned_once(detection):
    detections, scores = _scores_for(4, detection)
    plan = build_plan(
        "test-region", detections, scores, vessel_capacity=2, rationale_writer=OFFLINE
    )
    assert len({a.vessel_id for a in plan.assignments}) == 2


def test_plan_starts_unapproved_and_needs_a_named_reviewer(detection):
    """FR-6.4 — no output is final without an explicit human checkpoint."""
    detections, scores = _scores_for(2, detection)
    plan = build_plan("test-region", detections, scores, rationale_writer=OFFLINE)
    assert plan.approved is False and plan.approved_by is None

    with pytest.raises(ValueError, match="human reviewer"):
        plan.approve("   ")

    approved = plan.approve("A. Coordinator")
    assert approved.approved is True and approved.approved_by == "A. Coordinator"
    assert plan.approved is False  # the original is untouched


def test_plan_states_that_it_is_a_research_prototype(detection):
    detections, scores = _scores_for(1, detection)
    plan = build_plan("test-region", detections, scores, rationale_writer=OFFLINE)
    assert any("research prototype" in c for c in plan.caveats)


def test_offline_rationales_are_marked_as_such(detection):
    detections, scores = _scores_for(1, detection)
    plan = build_plan("test-region", detections, scores, rationale_writer=OFFLINE)
    assert plan.assignments[0].rationale_source == "template"
    assert plan.assignments[0].rationale
    assert any("deterministic template" in c for c in plan.caveats)


def test_every_assignment_keeps_its_evidence_trail(detection, forward):
    detections, scores = _scores_for(1, detection)
    scores = [scores[0].model_copy(update={"evidence": forward.evidence})]
    plan = build_plan("test-region", detections, scores, rationale_writer=OFFLINE)
    assert plan.assignments[0].evidence


def test_capacity_defaults_come_from_regions_yaml(detection):
    """FR-6.2 — the constraint is configuration, not a hard-coded number."""
    detections, scores = _scores_for(9, detection)
    plan = build_plan("test-region", detections, scores, rationale_writer=OFFLINE)
    assert plan.vessel_capacity == 3
    assert plan.planning_horizon_days == 7
    assert len(plan.assignments) == 3


def test_upstream_degradations_are_carried_into_the_plan_caveats(detection):
    detections, scores = _scores_for(1, detection)
    plan = build_plan(
        "test-region",
        detections,
        scores,
        rationale_writer=OFFLINE,
        caveats=["drift: no current field available"],
    )
    assert "drift: no current field available" in plan.caveats


def test_json_round_trip_keeps_the_plan_reviewable(detection, tmp_path):
    detections, scores = _scores_for(2, detection)
    plan = build_plan("test-region", detections, scores, rationale_writer=OFFLINE)
    path = tmp_path / "plan.json"
    path.write_text(plan.model_dump_json(indent=2))
    reloaded = json.loads(path.read_text())
    assert reloaded["approved"] is False
    assert len(reloaded["assignments"]) == 2
    assert reloaded["assignments"][0]["rationale"]


def test_horizon_is_respected_when_passed_explicitly(detection):
    detections, scores = _scores_for(1, detection)
    plan = build_plan(
        "test-region",
        detections,
        scores,
        planning_horizon_days=14,
        rationale_writer=OFFLINE,
        now=BASE_TIME + timedelta(days=1),
    )
    assert plan.planning_horizon_days == 14
