"""Committed holdout results reconcile without GPU checkpoints or raw imagery."""

import hashlib
import json
import statistics
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("tile", ["16PDC", "48PZC"])
def test_strict_geographic_results_reconcile(tile):
    audit_path = ROOT / "eval/geographic_split_audit.json"
    audit = json.loads(audit_path.read_text("utf-8"))["tiles"][tile]
    result = json.loads((ROOT / "eval/geographic_validation.json").read_text("utf-8"))
    assert result["audit_sha256"] == hashlib.sha256(audit_path.read_bytes()).hexdigest()
    group = result["tiles"][tile]
    assert [r["training_protocol"]["seed"] for r in group["runs"]] == result["seeds"]
    for run in group["runs"]:
        protocol = run["training_protocol"]
        assert protocol["epochs"] == 60
        assert protocol["holdout_tiles"] == [tile]
        assert protocol["normalisation"] == audit["normalisation"]
        assert protocol["training_prior"] == audit["training_prior"]
        held = run["holdout"]
        assert held["patches"] == audit["heldout_patches"]
        counts = held["per_class"]["Marine Debris"]
        tp, fp, fn = (counts[key] for key in ("tp", "fp", "fn"))
        assert tp + fn == audit["debris_pixels"]
        assert tp + fp + fn + counts["tn"] == held["labelled_pixels"]
        assert held["debris_precision"] == round(tp / (tp + fp), 4)
        assert held["debris_recall"] == round(tp / (tp + fn), 4)
        assert held["debris_f1"] == round(2 * tp / (2 * tp + fp + fn), 4)
    for metric, summary in group["summary"].items():
        values = [r["holdout"][metric] for r in group["runs"]]
        assert summary == {"mean": round(statistics.fmean(values), 4),
                           "sample_std": round(statistics.stdev(values), 4),
                           "min": min(values), "max": max(values)}
