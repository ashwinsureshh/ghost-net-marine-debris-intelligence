"""LangGraph orchestration end to end, plus the PRD §12 ablation study."""

from __future__ import annotations

import pytest

from ghostnet.agents.attribution import RiverTable
from ghostnet.agents.drift import UniformCurrentField
from ghostnet.agents.prioritisation import ProtectedArea
from ghostnet.llm import RationaleWriter
from ghostnet.pipeline import (
    AGENT_NAMES,
    PipelineConfig,
    build_graph,
    run_ablation_study,
    run_pipeline,
)
from ghostnet.schemas import VesselDetection
from tests.conftest import BASE_TIME

WESTWARD = UniformCurrentField(u_ms=-0.25, v_ms=0.0, name="test-westward")


@pytest.fixture
def config(mixed_tile, river_csv):
    """A run with every input available, so nothing degrades by accident."""
    return PipelineConfig(
        region_id="test-region",
        tiles=[mixed_tile],
        current_field=WESTWARD,
        river_table=RiverTable.from_csv(river_csv),
        vessel_detections=[
            VesselDetection(id="s-dark", lon=80.010, lat=11.990, detected_at=BASE_TIME)
        ],
        protected_areas=[ProtectedArea("Test Reserve", 79.90, 11.99, radius_km=5.0)],
        rationale_writer=RationaleWriter(enabled=False),
        ensemble_size=8,
    )


def test_the_graph_compiles_with_all_six_agents():
    graph = build_graph()
    assert set(AGENT_NAMES) <= set(graph.get_graph().nodes)


def test_full_run_verifies_only_the_real_patch(config):
    run = run_pipeline(config)
    # Four candidates, not five: the cloud-shadow patch is below the
    # MARIDA-fitted FDI threshold and is never raised (see conftest).
    assert len(run.detections) == 4  # the raw detector is fooled three times
    assert len(run.verified) == 1  # FR-2 removes all three
    assert len(run.rejected) == 3


def test_rejections_are_retained_with_their_reasons(config):
    """PRD §8 auditability — rejected detections are logged, not discarded."""
    run = run_pipeline(config)
    for rejection in run.rejected:
        assert rejection.rejection_reasons
        assert rejection.confidence == 0.0
    reasons = " ".join(r for v in run.rejected for r in v.rejection_reasons)
    # Checks are named for the signature they measure, not for one cause, so the
    # reasons read "bright flat SWIR target" / "bright water surface" rather than
    # asserting sun glint or foam specifically. Cloud shadow is absent by design:
    # at the fitted detection threshold that patch is never raised at all.
    for mode in ("SWIR", "bright water surface", "vegetation"):
        assert mode.lower() in reasons.lower()


def test_full_run_produces_a_bounded_unapproved_plan(config):
    run = run_pipeline(config)
    assert run.plan is not None
    assert 0 < len(run.plan.assignments) <= run.plan.vessel_capacity
    assert run.plan.approved is False
    assert run.plan.region_id == "test-region"


def test_every_stage_produced_output_when_all_inputs_are_present(config):
    run = run_pipeline(config)
    verified_id = run.verified[0].detection_id
    assert verified_id in run.backward
    assert verified_id in run.forward
    assert verified_id in run.attributions
    assert verified_id in run.correlations
    assert [s.detection_id for s in run.scores] == [verified_id]
    assert not run.degradations


def test_summary_is_human_readable(config):
    summary = run_pipeline(config).summary()
    assert "Region test-region" in summary
    assert "ablated      : none" in summary


# --- ablation (PRD §12) ----------------------------------------------------


def test_ablating_detection_starves_the_whole_pipeline(config):
    run = run_pipeline(_ablate(config, "detection"))
    assert run.detections == []
    assert run.plan is not None and run.plan.assignments == []
    assert any("only data source" in d for d in run.degradations)


def test_ablating_verification_lets_false_positives_through(config):
    """The FR-2.4 baseline arm: glint, foam and kelp reach the dispatch plan."""
    full = run_pipeline(config)
    without = run_pipeline(_ablate(config, "verification"))

    assert len(full.scores) == 1
    assert len(without.scores) == 4
    assert len(without.plan.assignments) > len(full.plan.assignments)
    assert any("unfiltered" in d for d in without.degradations)


def test_ablating_drift_removes_attribution_entirely(config):
    """Removing one agent breaks a capability rather than nudging a number."""
    run = run_pipeline(_ablate(config, "drift"))
    assert run.backward == {} and run.forward == {}
    assert run.attributions == {}
    assert any("no trajectories" in d for d in run.degradations)
    assert any("backward trajectories" in d for d in run.degradations)
    # The plan still exists, but its drift-urgency component is gone.
    assert run.scores[0].components["drift_urgency"] == 0.0


def test_ablating_attribution_keeps_the_plan_but_loses_the_source_finding(config):
    run = run_pipeline(_ablate(config, "attribution"))
    assert run.attributions == {}
    assert run.plan is not None and run.plan.assignments
    assert any("where it came from" in d for d in run.degradations)


def test_ablating_vessels_drops_the_ghost_gear_signal(config):
    run = run_pipeline(_ablate(config, "vessels"))
    assert run.correlations == {}
    assert "dark_vessel_signal" not in run.scores[0].components
    assert any("ghost-gear" in d for d in run.degradations)


def test_ablating_prioritisation_leaves_the_operator_with_no_plan(config):
    run = run_pipeline(_ablate(config, "prioritisation"))
    assert run.plan is None
    assert run.scores == []
    assert any("unordered pile" in d for d in run.degradations)


def test_ablation_study_covers_every_agent(config):
    runs = run_ablation_study(config)
    assert set(runs) == {"full", *(f"without_{a}" for a in AGENT_NAMES)}
    for agent in AGENT_NAMES:
        run = runs[f"without_{agent}"]
        assert run.ablated == [agent]
        # Each arm must explain its own failure, not just score lower.
        assert any("ABLATED" in d for d in run.degradations)


def test_unknown_agent_names_are_rejected_up_front():
    with pytest.raises(ValueError, match="Cannot ablate unknown agent"):
        PipelineConfig(region_id="x", ablate=frozenset({"telepathy"}))


# --- degradation instead of crashing --------------------------------------


def test_no_tiles_degrades_with_the_fetch_command(mixed_tile):
    run = run_pipeline(PipelineConfig(region_id="test-region", tiles=[]))
    assert run.detections == []
    assert any("fetch_data.py" in d for d in run.degradations)


def test_a_missing_current_field_degrades_drift_not_the_run(config):
    run = run_pipeline(_replace(config, current_field=None))
    assert run.verified  # detection and verification still work
    assert run.backward == {}
    assert any("oscar" in d for d in run.degradations)
    assert run.plan is not None


def test_a_missing_river_table_degrades_attribution_only(config):
    run = run_pipeline(_replace(config, river_table=None))
    assert run.backward  # drift still ran
    assert run.attributions == {}
    assert any("river-emission table" in d for d in run.degradations)


def test_missing_mpa_data_is_flagged_on_the_plan_itself(config):
    run = run_pipeline(_replace(config, protected_areas=None))
    assert any("NOT scored zero" in d for d in run.degradations)
    assert any("NOT scored zero" in c for c in run.plan.caveats)


def test_no_vessel_records_degrades_the_correlation_signal(config):
    run = run_pipeline(_replace(config, vessel_detections=[]))
    assert run.correlations == {}
    assert any("gfw" in d for d in run.degradations)


# --- helpers ---------------------------------------------------------------


def _replace(config: PipelineConfig, **changes) -> PipelineConfig:
    return PipelineConfig(**{**vars(config), **changes})


def _ablate(config: PipelineConfig, agent: str) -> PipelineConfig:
    return _replace(config, ablate=frozenset({agent}))
