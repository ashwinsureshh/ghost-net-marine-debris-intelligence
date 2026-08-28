"""The deployed operator console: API surface and live prioritisation.

Every test runs against a temporary artefact directory, so the suite never
depends on whatever happens to be in ``webapp_data/`` on this machine.

Skipped wholesale where FastAPI is absent. The web dependencies live in
requirements-web.txt and are deliberately not part of requirements-base.txt, so
the workstation — which only needs ``ghostnet.export`` — legitimately does not
have them. Without this guard the suite cannot be green on that machine, which
is the same trap as asserting a dataset is absent on the machine that owns it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="web deps are in requirements-web.txt (Air only)")

from ghostnet.export import write_artefact  # noqa: E402
from ghostnet.llm import RationaleWriter  # noqa: E402
from ghostnet.webapp.planning import (  # noqa: E402
    ABLATABLE,
    PlanningRequest,
    plan_from_artefact,
)
from ghostnet.webapp.store import ArtefactStore  # noqa: E402
from tests.test_export import artefact  # noqa: F401,E402 — reused fixture

OFFLINE = RationaleWriter(enabled=False)


@pytest.fixture
def client(artefact, tmp_path, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    from ghostnet.webapp import app as app_module

    write_artefact(artefact, tmp_path)
    monkeypatch.setattr(app_module, "store", ArtefactStore(tmp_path))
    return TestClient(app_module.app)


# --------------------------------------------------------------- meta ------


def test_health_reports_the_artefact_schema(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["runs"] == 1


def test_meta_states_the_prototype_framing(client):
    """PRD §8 — the UI must be able to say what this is on its face."""
    body = client.get("/api/meta").json()
    assert "research prototype" in body["prototype_notice"].lower()
    assert "not operational-grade" in body["prototype_notice"].lower()
    assert [a["id"] for a in body["agents"]][0] == "detection"
    assert body["rationale_source"] in {"llm", "template"}


def test_meta_names_which_agents_can_be_ablated(client):
    body = client.get("/api/meta").json()
    assert "detection" not in body["ablatable_agents"]
    assert "verification" in body["ablatable_agents"]


# ---------------------------------------------------------- benchmark ------


def test_benchmark_serves_the_measured_verification_gain(client):
    body = client.get("/api/benchmark").json()
    assert body["available"], body["unavailable_reason"]
    assert body["verification"]["precision_gain"] == pytest.approx(0.385, abs=5e-4)


def test_benchmark_never_serves_the_gain_without_the_region_recall(client):
    """The headline is conditioned on candidates the detector emitted, so on its
    own it implies the system finds nearly all the debris. It does not — 0.407.
    eval/results.md requires both; so does the endpoint."""
    body = client.get("/api/benchmark").json()
    assert body["verification"] is not None
    assert body["detector"] is not None
    assert body["detector"]["region_recall"] == pytest.approx(0.407, abs=5e-4)
    assert body["detector"]["regions_missed"] == 140


def test_benchmark_serves_one_entry_per_detector(client):
    """The console picks the entry matching the run on screen. Serving a single
    detector's numbers would describe a CNN run with FDI results."""
    body = client.get("/api/benchmark").json()
    by_key = {d["detector"]: d for d in body["detectors"]}
    assert set(by_key) == {"fdi", "cnn"}
    assert by_key["cnn"]["region_recall"] > by_key["fdi"]["region_recall"]
    assert (
        by_key["cnn"]["verification"]["precision_gain"]
        < by_key["fdi"]["verification"]["precision_gain"]
    )


def test_benchmark_warns_that_the_cnn_subsumes_verification(client):
    """PRD 12: quoting +0.385 beside a CNN run overstates the agent."""
    body = client.get("/api/benchmark").json()
    assert body["verification_overlap"] is not None
    assert "+0.080" in body["verification_overlap"]


def test_benchmark_serves_the_negative_fr_2_2_result(client):
    """PRD 12 asks for a per-agent ablation. Multi-temporal's honest current
    answer is 'no measured contribution, blocked on FR-3.1' — an evaluator
    seeing only the FR-2.4 gain would assume every check carries weight."""
    body = client.get("/api/benchmark").json()
    result = body["multi_temporal"]
    assert result is not None
    assert result["contributes"] is False
    assert result["f1_delta"] < 0
    assert any("FR-3.1" in c for c in body["multi_temporal_caveats"])


def test_benchmark_points_back_at_the_authoritative_results(client):
    body = client.get("/api/benchmark").json()
    assert body["results_doc"] == "eval/results.md"
    assert body["dataset"] == "MARIDA"
    # The threshold these numbers were measured at, so the UI can compare it
    # against the artefact's own and flag a mismatch instead of implying none.
    assert body["fdi_threshold"] == pytest.approx(0.025)
    assert body["caveats"]


# --------------------------------------------------------------- runs ------


def test_runs_lists_the_available_artefacts(client):
    runs = client.get("/api/runs").json()["runs"]
    assert [r["run_id"] for r in runs] == ["test-run"]
    assert runs[0]["inputs_are_synthetic"] is True


def test_a_run_serves_its_whole_reasoning_trail(client):
    body = client.get("/api/runs/test-run").json()
    assert body["detections"] and body["verifications"]
    assert body["forward"] and body["attributions"]


def test_an_unknown_run_says_what_is_available(client):
    response = client.get("/api/runs/nope")
    assert response.status_code == 404
    assert "test-run" in response.json()["detail"]


def test_an_unreadable_artefact_does_not_break_the_listing(client, tmp_path):
    (tmp_path / "broken.run.json").write_text('{"schema_version": "99.0"}')
    runs = client.get("/api/runs").json()["runs"]
    assert any(r.get("unreadable") for r in runs)
    assert any(r["run_id"] == "test-run" for r in runs)


def test_a_stale_schema_artefact_returns_conflict_not_garbage(client, tmp_path):
    (tmp_path / "old.run.json").write_text('{"schema_version": "0.1"}')
    response = client.get("/api/runs/old")
    assert response.status_code == 409
    assert "Re-export it from the workstation" in response.json()["detail"]


# ------------------------------------------------------------ rejected -----


def test_rejected_is_a_first_class_endpoint(client):
    """PRD §8/§9.1 — the agent's contribution is what it throws away."""
    body = client.get("/api/runs/test-run/rejected").json()
    assert body["count"] > 0
    assert body["count"] < body["detections_total"]
    for entry in body["rejected"]:
        assert entry["reasons"]
        assert entry["failed_checks"]


# ---------------------------------------------------------------- plan -----


def test_plan_is_ranked_and_bounded_by_capacity(client):
    body = client.post("/api/runs/test-run/plan", json={"vessel_capacity": 1}).json()
    plan = body["plan"]
    assert len(plan["assignments"]) == 1
    assert plan["vessel_capacity"] == 1
    scores = [s["score"] for s in body["scores"]]
    assert scores == sorted(scores, reverse=True)


def test_plan_starts_unapproved(client):
    plan = client.post("/api/runs/test-run/plan", json={}).json()["plan"]
    assert plan["approved"] is False


def test_a_synthetic_run_says_so_on_the_plan(client):
    plan = client.post("/api/runs/test-run/plan", json={}).json()["plan"]
    assert any("GENERATED inputs" in c for c in plan["caveats"])


def test_capacity_zero_produces_an_empty_but_valid_plan(client):
    body = client.post("/api/runs/test-run/plan", json={"vessel_capacity": 0}).json()
    assert body["plan"]["assignments"] == []
    assert body["plan"]["deferred"]


def test_an_unknown_agent_is_rejected(client):
    response = client.post("/api/runs/test-run/plan", json={"ablate": ["telepathy"]})
    assert response.status_code == 422


def test_detection_cannot_be_ablated_through_the_api(client):
    response = client.post("/api/runs/test-run/plan", json={"ablate": ["detection"]})
    assert response.status_code == 422
    assert "no run to serve" in response.json()["detail"]


# ----------------------------------------------------------- ablation ------


def test_ablating_verification_readmits_the_rejected_candidates(artefact):  # noqa: F811
    full = plan_from_artefact(artefact, PlanningRequest(), rationale_writer=OFFLINE)
    without = plan_from_artefact(
        artefact,
        PlanningRequest(ablate=frozenset({"verification"})),
        rationale_writer=OFFLINE,
    )
    assert without.considered > full.considered
    assert without.considered == len(artefact.detections)


def test_the_verification_arm_admits_what_it_cannot_show(artefact):  # noqa: F811
    """The artefact has no drift for rejected detections, so this arm
    understates them. The app must say that rather than imply it reproduces
    the measured MARIDA result."""
    result = plan_from_artefact(
        artefact,
        PlanningRequest(ablate=frozenset({"verification"})),
        rationale_writer=OFFLINE,
    )
    joined = " ".join(result.degradations)
    assert "CAVEAT on this arm" in joined
    assert "eval/results.md" in joined


def test_ablating_drift_removes_attribution_too(artefact):  # noqa: F811
    result = plan_from_artefact(
        artefact, PlanningRequest(ablate=frozenset({"drift"})), rationale_writer=OFFLINE
    )
    assert all(s.components["drift_urgency"] == 0.0 for s in result.scores)
    assert any("cannot run" in d for d in result.degradations)


def test_ablating_vessels_drops_that_component(artefact):  # noqa: F811
    result = plan_from_artefact(
        artefact, PlanningRequest(ablate=frozenset({"vessels"})), rationale_writer=OFFLINE
    )
    assert all("dark_vessel_signal" not in s.components for s in result.scores)


def test_ablating_prioritisation_leaves_no_plan(artefact):  # noqa: F811
    result = plan_from_artefact(
        artefact,
        PlanningRequest(ablate=frozenset({"prioritisation"})),
        rationale_writer=OFFLINE,
    )
    assert result.plan is None
    assert any("unordered pile" in d for d in result.degradations)


def test_every_ablatable_agent_explains_itself(artefact):  # noqa: F811
    for agent in ABLATABLE:
        result = plan_from_artefact(
            artefact, PlanningRequest(ablate=frozenset({agent})), rationale_writer=OFFLINE
        )
        assert any("ABLATED" in d for d in result.degradations), agent


def test_planning_request_validates_its_inputs():
    with pytest.raises(ValueError, match="Cannot ablate"):
        PlanningRequest(ablate=frozenset({"nonsense"}))
    with pytest.raises(ValueError, match="cannot be negative"):
        PlanningRequest(vessel_capacity=-1)
    with pytest.raises(ValueError, match="at least 1"):
        PlanningRequest(planning_horizon_days=0)


# ----------------------------------------------------------- approval ------


def test_approval_records_what_was_reviewed(client):
    plan = client.post("/api/runs/test-run/plan", json={"vessel_capacity": 2}).json()["plan"]
    ids = [a["detection_id"] for a in plan["assignments"]]

    response = client.post(
        "/api/runs/test-run/approve",
        json={"reviewer": "A. Coordinator", "vessel_capacity": 2, "detection_ids": ids},
    )
    assert response.status_code == 201
    record = response.json()["approval"]
    assert record["reviewer"] == "A. Coordinator"
    assert record["detection_ids"] == ids
    assert record["vessel_capacity"] == 2


def test_an_unnamed_reviewer_cannot_approve(client):
    """FR-6.4 requires a *named* human."""
    response = client.post(
        "/api/runs/test-run/approve", json={"reviewer": "   ", "vessel_capacity": 3}
    )
    assert response.status_code == 422


def test_a_missing_reviewer_field_is_rejected(client):
    assert client.post("/api/runs/test-run/approve", json={}).status_code == 422


def test_ephemeral_storage_is_disclosed_rather_than_implied(client):
    response = client.post(
        "/api/runs/test-run/approve", json={"reviewer": "A. Coordinator"}
    ).json()
    assert response["approval"]["durable"] is False
    assert "ephemeral" in response["warning"]


def test_durable_storage_drops_the_warning(client, monkeypatch, tmp_path):
    from ghostnet.webapp import app as app_module

    monkeypatch.setenv("GHOSTNET_DURABLE_STORAGE", "1")
    monkeypatch.setattr(app_module, "store", ArtefactStore(tmp_path))
    response = client.post(
        "/api/runs/test-run/approve", json={"reviewer": "A. Coordinator"}
    ).json()
    assert response["approval"]["durable"] is True
    assert response["warning"] is None


def test_approvals_are_listed_newest_first(client):
    for name in ("First Reviewer", "Second Reviewer"):
        client.post("/api/runs/test-run/approve", json={"reviewer": name})
    approvals = client.get("/api/runs/test-run/approvals").json()["approvals"]
    assert len(approvals) == 2
    assert approvals[0]["reviewer"] == "Second Reviewer"


def test_approving_an_unknown_run_is_a_404(client):
    response = client.post("/api/runs/nope/approve", json={"reviewer": "X"})
    assert response.status_code == 404
