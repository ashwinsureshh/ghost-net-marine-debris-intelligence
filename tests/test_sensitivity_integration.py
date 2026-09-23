import hashlib
import json

from ghostnet.agents.prioritisation import DEFAULT_WEIGHTS
from ghostnet.config import REPO_ROOT
from ghostnet.sensitivity import weight_variants
from ghostnet.webapp.planning import PlanningRequest, plan_from_artefact
from tests.test_export import artefact  # noqa: F401


def test_unavailable_vessels_do_not_become_zero_evidence(artefact):  # noqa: F811
    artefact.correlations = {}
    original = artefact.model_dump_json()

    def score(weights):
        return plan_from_artefact(artefact, PlanningRequest(
            weights=weights, include_rationales=False,
        ))

    baseline = score(DEFAULT_WEIGHTS)
    changed = score(weight_variants(DEFAULT_WEIGHTS)["dark_vessel_signal:+50%"])
    assert baseline.scores
    assert [s.detection_id for s in baseline.scores] == [s.detection_id for s in changed.scores]
    for left, right in zip(baseline.scores, changed.scores, strict=True):
        assert "dark_vessel_signal" not in right.components
        assert abs(left.score - right.score) < 1e-12
    assert artefact.model_dump_json() == original
    assert not changed.plan.approved


def test_published_sensitivity_matches_current_input_files():
    measured = json.loads((REPO_ROOT / "eval/priority_sensitivity.json").read_text("utf-8"))
    for run in measured["runs"]:
        source = REPO_ROOT / "webapp_data" / run["input_file"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == run["input_sha256"]
        assert run["summary"]["variants"] == len(run["variants"]) == 24
        if run["region"] == "puducherry_coast":
            assert run["inputs_degraded"]
            for name, row in run["variants"].items():
                if name.startswith("dark_vessel_signal:"):
                    assert row["max_rank_shift"] == 0
