import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from eval_river_rankings import compare  # noqa: E402
from ghostnet.evidence_hash import text_evidence_sha256  # noqa: E402


def river(lon, emission):
    return {"name": "same local annotation", "lon": lon, "lat": 10,
            "emission_tonnes_yr": emission}


def run(*candidates):
    return {"detections": [], "attributions": {
        str(i): {"candidates": rows} for i, rows in enumerate(candidates)}}


def test_coordinate_matching_ties_and_global_duplicates_are_explicit():
    high, tied, low = river(1, 20), river(2, 20), river(3, 2)
    result = compare(run([tied], [low]), [high, tied, low], [high, tied, low, low])
    assert result["regional_top_k_counts"]["1"] == 1
    assert result["attributed"] == 2
    assert result["global_records"] == 4
    assert result["global_duplicate_coordinate_records"] == 1
    assert result["regional_top_k_fractions"]["1"] == 0.5
    assert result["emission_only_regional_top_k_fraction"] == 1.0


def test_no_attribution_is_not_zero_accuracy():
    result = compare(run([]), [river(1, 20)], [river(1, 20)])
    assert result["empty_attributions"] == 1
    assert result["global_top_1000_fraction"] is None
    assert result["regional_top_k_fractions"]["5"] is None


def test_changed_or_unmatched_export_rejected():
    with pytest.raises(ValueError, match="Export candidate"):
        compare(run([river(1, 21)]), [river(1, 20)], [river(1, 20)])
    with pytest.raises(ValueError, match="Regional extract"):
        compare(run([]), [river(1, 20)], [river(1, 21)])


@pytest.mark.parametrize("region", ["gulf_of_honduras", "gulf_of_gonave", "puducherry_coast"])
def test_committed_comparison_reconciles(region):
    evidence = json.loads((ROOT / "eval/river_rankings.json").read_text("utf-8"))
    assert evidence["independent_accuracy_measured"] is False
    result = evidence["regions"][region]
    assert result["run_sha256"] == text_evidence_sha256(
        ROOT / "webapp_data" / f"{region}.run.json")
    rows = result["top_mouths"]
    n = result["attributed"]
    assert sum(r["top_attributions"] for r in rows) == n
    assert n + result["empty_attributions"] == result["attribution_records"]
    for k in (1, 5, 10):
        hits = sum(r["top_attributions"] for r in rows if r["regional_emission_rank"] <= k)
        assert result["regional_top_k_counts"][str(k)] == hits
        assert result["regional_top_k_fractions"][str(k)] == round(hits / n, 4)
