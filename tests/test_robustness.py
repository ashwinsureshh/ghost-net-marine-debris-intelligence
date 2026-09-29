"""The console's plan-robustness panel serves a measurement, or says why not."""

from __future__ import annotations

import json

import pytest

from ghostnet.evidence_hash import text_evidence_sha256
from ghostnet.robustness import robustness_for


def _write(tmp_path, artefact_text="{}\n", recorded_hash=None):
    artefact = tmp_path / "demo.run.json"
    artefact.write_text(artefact_text, encoding="utf-8")
    sensitivity = tmp_path / "priority_sensitivity.json"
    sensitivity.write_text(json.dumps({"runs": [{
        "input_file": "demo.run.json",
        "input_sha256": recorded_hash or text_evidence_sha256(artefact),
        "vessel_capacity": 3, "planning_horizon_days": 7, "candidate_count": 10,
        "inputs_degraded": [], "baseline_weights": {"a": 1.0},
        "variants": {"a:-50%": {"spearman_ordinal": 0.91}, "a:+50%": {"spearman_ordinal": 0.97}},
        "summary": {"variants": 2, "top1_changed": 1, "dispatch_set_changed": 0},
        "caveats": ["Stability does not establish accuracy."],
    }]}), encoding="utf-8")
    return artefact, sensitivity


def test_a_matching_artefact_serves_the_measurement(tmp_path):
    artefact, sensitivity = _write(tmp_path)
    report = robustness_for("demo", artefact, source=sensitivity)
    assert report["status"] == "measured"
    assert (report["top1_changed"], report["dispatch_set_changed"], report["variants"]) == (1, 0, 2)
    assert report["min_spearman"] == 0.91
    assert report["measured_at"] == {"vessel_capacity": 3, "planning_horizon_days": 7}


def test_a_changed_artefact_is_stale_and_serves_no_numbers(tmp_path):
    artefact, sensitivity = _write(tmp_path, recorded_hash="0" * 64)
    report = robustness_for("demo", artefact, source=sensitivity)
    assert report["status"] == "stale"
    assert "top1_changed" not in report


def test_an_unmeasured_run_says_so(tmp_path):
    artefact, sensitivity = _write(tmp_path)
    assert robustness_for("other", artefact, source=sensitivity)["status"] == "not_measured"
    assert robustness_for("demo", artefact, source=tmp_path / "missing.json")["status"] \
        == "not_measured"


def test_line_endings_do_not_make_a_run_stale(tmp_path):
    artefact, sensitivity = _write(tmp_path, artefact_text='{"a": 1}\n')
    artefact.write_bytes(b'{"a": 1}\r\n')  # a Windows checkout of the same file
    assert robustness_for("demo", artefact, source=sensitivity)["status"] == "measured"


def test_the_endpoint_serves_the_panel(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from ghostnet.webapp import app as app_module
    from ghostnet.webapp.store import ArtefactStore
    from tests.test_export import artefact as _  # noqa: F401

    monkeypatch.setattr(app_module, "store", ArtefactStore(tmp_path))
    client = TestClient(app_module.app)
    assert client.get("/api/runs/nope/robustness").status_code == 404
