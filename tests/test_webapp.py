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

import json

import pytest

pytest.importorskip("fastapi", reason="web deps are in requirements-web.txt (Air only)")

from ghostnet.config import REPO_ROOT  # noqa: E402
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


def test_benchmark_never_serves_the_pairing_that_reads_backwards(client):
    """The one number this experiment must not put on screen.

    `--eval-only --holdout-tile` also prints the holdout model's score on the
    REST of the test split (debris F1 0.6637). Showing that beside its 18QYF
    score (0.8581) reads as a before/after and is not one: 18QYF carries 13.24
    debris px/patch against 0.98 for the rest of test, so the pairing measures
    task difficulty, not distribution shift — and it comes out backwards, making
    the *unseen* region look easier. Only the paired table over identical
    patches is meaningful.

    eval/results.md says so under "One number in this experiment must not be
    quoted" and scripts/train_cnn.py warns about it. So does the endpoint.
    """
    body = client.get("/api/benchmark").json()
    generalisation = body["generalisation"]
    assert generalisation is not None

    forbidden = json.loads(
        (REPO_ROOT / "eval" / "holdout_18QYF.json").read_text()
    )["in_distribution_test"]["debris_f1"]

    # Structural, not a string search: no served field may carry that value,
    # however it is spelled or nested.
    for key, value in generalisation.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            assert value != pytest.approx(forbidden, abs=5e-4), (
                f"generalisation.{key} serves {value}, the holdout model's "
                "rest-of-test score. Paired against the 18QYF score it reads "
                "backwards — see eval/results.md."
            )

    # And no field is even named for that arm, which is how it would creep back.
    assert not [k for k in generalisation if "in_distribution" in k or "rest" in k]


def test_the_generalisation_arms_are_the_same_patches(client):
    """What makes the pairing valid, asserted rather than assumed."""
    generalisation = client.get("/api/benchmark").json()["generalisation"]
    assert generalisation["patches"] == 84
    assert generalisation["debris_px_per_patch"] == pytest.approx(13.24, abs=5e-3)
    assert generalisation["f1_cost"] == pytest.approx(-0.0723, abs=5e-5)


def test_the_generalisation_caveats_warn_off_the_bad_pairing(client):
    """An evaluator who computes it unaided should have been told not to."""
    caveats = " ".join(client.get("/api/benchmark").json()["generalisation_caveats"])
    assert "-0.194" in caveats
    assert "task difficulty" in caveats


def test_the_console_never_implies_the_holdout_model_is_the_shipped_detector(client):
    """detector_v1.pt is still the pipeline's detector and is unchanged.

    The generalisation figures come from an experiment checkpoint that is not
    committed and never ran the pipeline. Nothing on screen may suggest the run
    was produced by it.
    """
    body = client.get("/api/benchmark").json()
    caveats = " ".join(body["generalisation_caveats"])
    assert "detector_v1" in caveats, (
        "the strip shows a second model's scores; it has to say which checkpoint "
        "actually ships"
    )
    assert "not committed" in caveats or "experiment" in caveats.lower()

    # The detector entries are the shipped ones and are untouched by the
    # experiment: still fdi and cnn, still their own region recalls.
    assert {d["detector"] for d in body["detectors"]} == {"fdi", "cnn"}


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


def test_the_run_listing_marks_which_runs_are_synthetic(client):
    """The console picks its default run from this flag, so it has to be served.

    Ordering alone is not enough: the store sorts run ids, so the real run
    leads only because "gulf_of_honduras" precedes "synthetic-coastal-demo".
    A region sorting after "s" would open the console on generated data.
    """
    runs = client.get("/api/runs").json()["runs"]
    assert runs, "no runs to choose from"
    for run in runs:
        assert "inputs_are_synthetic" in run, (
            "the frontend cannot prefer a real run without this flag"
        )

    real = [r for r in runs if not r["inputs_are_synthetic"]]
    if real:
        assert any(r["detections"] > 0 for r in real), (
            "a real run that carries no detections would be a worse default "
            "than the synthetic one"
        )


def test_benchmark_serves_the_inert_fr_2_2_result(client):
    """PRD 12 asks for a per-agent ablation. Multi-temporal's honest current
    answer changed on 2026-09-04: no longer 'blocked on FR-3.1' but 'given the
    dependency, still inert'. An evaluator seeing only the FR-2.4 gain would
    assume every check carries weight; one told it is still blocked would
    assume the finding is pending rather than reached."""
    body = client.get("/api/benchmark").json()
    result = body["multi_temporal"]
    assert result is not None
    assert result["contributes"] is False
    assert result["f1_delta"] == pytest.approx(0.0), "harm gone with a real field"
    assert result["current_speed_source"] == "oscar"
    assert result["harm_removed"] is True
    assert result["transients_found"] == 0, "and it still finds nothing"


def test_the_console_never_says_fr_2_2_is_blocked_on_a_missing_dependency(client):
    """The stale claim this endpoint carried for four sessions.

    OSCAR exists and the check was re-measured against it. Saying it is blocked
    describes a project state that ended, and points a reader at the wrong fix:
    the problem is now the matching strategy, not a missing input.
    """
    body = client.get("/api/benchmark").json()

    # EVERY served caveat list, not just the multi-temporal one. The first
    # version of this test checked only multi_temporal_caveats and missed an
    # identical stale claim sitting in the general `caveats` list, which the
    # rendered panel showed side by side with the corrected one.
    everywhere = " ".join(body["multi_temporal_caveats"] + body["caveats"])

    assert "is blocked" not in everywhere, "must not be a present-tense claim"
    assert "does not exist yet" not in everywhere
    assert "costs recall" not in everywhere, "true without a field, false with one"

    scoped = " ".join(body["multi_temporal_caveats"])
    assert "no current field existed" in scoped, "past tense is fine and is the evidence"
    # It must still explain WHY it earns nothing — the reason simply moved.
    assert "matching strategy" in scoped
    assert "transient" in scoped.lower()


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


def test_run_list_contains_lightweight_coverage(client, artefact):  # noqa: F811
    response = client.get("/api/runs")
    row = response.json()["runs"][0]
    coverage = row["coverage"]
    assert coverage["runId"] == artefact.run_id
    assert coverage["detections"] == len(artefact.detections)
    assert coverage["start"] == artefact.region.window_start.isoformat()
    assert coverage["synthetic"] is True
    assert row["input_status"] == "synthetic"
    assert "provenance" not in row and "forward" not in row
    assert len(response.content) < 2000


def test_coverage_summary_preserves_aoi_and_unavailable_inputs(artefact):  # noqa: F811
    artefact = artefact.model_copy(deep=True)
    artefact.provenance.inputs_are_synthetic = False
    artefact.provenance.notes.append("Imagery covers AOI [79.78, 11.8, 79.98, 12.02]")
    artefact.degradations.append("gfw unavailable")
    row = artefact.summary()
    assert row["coverage"]["bounds"] == [79.78, 11.8, 79.98, 12.02]
    assert row["coverage"]["scope"] == "requested-aoi"
    assert row["coverage"]["partial"] is True
    assert row["input_status"] == "partial"


@pytest.mark.parametrize("note", ["", "Imagery covers AOI [bad]",
                                 "Imagery covers AOI [0, 0, 181, 10]"])
def test_coverage_summary_falls_back_to_labelled_region(artefact, note):  # noqa: F811
    artefact = artefact.model_copy(deep=True)
    artefact.provenance.notes = [note]
    assert artefact.coverage_summary()["scope"] == "region"
    artefact.region.bbox = None
    assert artefact.coverage_summary()["bounds"] is None
    assert artefact.coverage_summary()["scope"] == "unknown"


def test_static_bundle_includes_coverage_summaries(artefact, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.syspath_prepend(str(REPO_ROOT / "scripts"))
    from build_static_export import build_bundle
    write_artefact(artefact, tmp_path)
    bundle = build_bundle(ArtefactStore(tmp_path), 3, 7)
    assert bundle["runs"][0]["coverage"] == artefact.coverage_summary()


def test_benchmark_discloses_historical_holdout_confounding(client):
    response = client.get("/api/benchmark")
    assert response.status_code == 200
    caveats = " ".join(response.json()["generalisation_caveats"])
    assert "class weights" in caveats and "normalization" in caveats
    assert "withheld patches" in caveats and "635 vs 694" in caveats
    assert "does not establish an isolated causal effect" in caveats
    assert "does not establish a justified upper bound" in caveats
    assert "isolates the effect" not in caveats
    assert "is an UPPER bound" not in caveats
