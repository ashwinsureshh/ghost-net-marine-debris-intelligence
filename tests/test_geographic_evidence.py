"""Committed holdout results reconcile without GPU checkpoints or raw imagery."""

import json
import statistics
from pathlib import Path

import pytest

from ghostnet.evidence_hash import validate_text_evidence

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("tile", ["16PDC", "48PZC"])
def test_strict_geographic_results_reconcile(tile):
    audit_path = ROOT / "eval/geographic_split_audit.json"
    audit = json.loads(audit_path.read_text("utf-8"))["tiles"][tile]
    result = json.loads((ROOT / "eval/geographic_validation.json").read_text("utf-8"))
    validate_text_evidence(audit_path, result["audit_sha256"], result["audit_hash_method"])
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


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_geographic_audit_hash_is_portable_and_detects_changes(tmp_path, newline):
    raw = (ROOT / "eval/geographic_split_audit.json").read_bytes().replace(b"\r\n", b"\n")
    result = json.loads((ROOT / "eval/geographic_validation.json").read_text("utf-8"))
    source = tmp_path / "audit.json"
    source.write_bytes(raw.replace(b"\n", newline))
    validate_text_evidence(source, result["audit_sha256"], result["audit_hash_method"])
    source.write_bytes(source.read_bytes().replace(b'"debris_pixels": 143',
                                                  b'"debris_pixels": 144'))
    with pytest.raises(ValueError, match="mismatch"):
        validate_text_evidence(source, result["audit_sha256"], result["audit_hash_method"])
