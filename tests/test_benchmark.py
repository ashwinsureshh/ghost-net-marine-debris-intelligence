"""The measured numbers the console shows, and the framing around them.

These tests care about two things beyond "does it parse": that the weak number
travels alongside the strong one, and that a missing or broken results file
degrades into an honest "unavailable" rather than into zeroes an evaluator
could read as a measurement.
"""

from __future__ import annotations

import json

import pytest

from ghostnet.benchmark import BENCHMARK_FILE, load_benchmark

FITTED = {
    "split": "test",
    "patches": 359,
    "fdi_threshold": 0.025,
    "min_pixels": 3,
    "detections_total": 6074,
    "detections_unlabelled_excluded": 5738,
    "debris_regions": 236,
    "debris_regions_hit": 96,
    "region_recall": 0.4068,
    "metrics": {
        "n_labelled": 336.0,
        "baseline_precision": 0.2381,
        "baseline_recall": 1.0,
        "baseline_f1": 0.3846,
        "verified_precision": 0.623,
        "verified_recall": 0.95,
        "verified_f1": 0.7525,
    },
}


@pytest.fixture
def results_file(tmp_path):
    path = tmp_path / "marida_ablation.json"
    path.write_text(json.dumps({"fitted_fdi_threshold": 0.025, "held_out_fitted": FITTED}))
    return path


# ------------------------------------------------------------- parsing -----


def test_it_reads_the_headline_verification_gain(results_file):
    report = load_benchmark(results_file)
    assert report.available
    assert report.verification is not None
    assert report.verification.baseline_precision == pytest.approx(0.2381)
    assert report.verification.verified_precision == pytest.approx(0.623)
    assert report.verification.precision_gain == pytest.approx(0.3849)
    assert report.verification.f1_gain == pytest.approx(0.3679)
    assert report.verification.recall_cost == pytest.approx(0.05)


def test_false_positive_rate_is_derived_not_read():
    """`precision_recall_delta` reports it as a signed delta whose name reads
    backwards — an improvement shows as a negative. Deriving 1 - precision
    avoids inheriting that trap into the UI."""
    report = load_benchmark(BENCHMARK_FILE)
    assert report.available, report.unavailable_reason
    verification = report.verification
    assert verification is not None
    assert verification.baseline_false_positive_rate == pytest.approx(0.7619)
    assert verification.verified_false_positive_rate == pytest.approx(0.377)


def test_the_detector_region_recall_travels_with_it(results_file):
    """eval/results.md: both numbers must be quoted together, or the system
    looks better than it is."""
    report = load_benchmark(results_file)
    assert report.detector is not None
    assert report.detector.region_recall == pytest.approx(0.4068)
    assert report.detector.regions_hit == 96
    assert report.detector.regions == 236
    assert report.detector.regions_missed == 140


def test_the_committed_results_file_still_parses():
    """The real file, not a fixture — if the workstation re-exports it in a
    different shape the console must fail here, not silently in the browser."""
    report = load_benchmark(BENCHMARK_FILE)
    assert report.available, report.unavailable_reason
    assert report.detector is not None
    assert report.detector.region_recall == pytest.approx(0.407, abs=5e-4)
    assert report.verification is not None
    assert report.verification.precision_gain == pytest.approx(0.385, abs=5e-4)
    assert report.fdi_threshold == pytest.approx(0.025)


def test_the_dump_carries_the_derived_gains(results_file):
    """The UI must not recompute these — that would be a second place for the
    arithmetic to be wrong."""
    data = load_benchmark(results_file).model_dump()
    assert data["verification"]["precision_gain"] == pytest.approx(0.3849)
    assert data["verification"]["baseline_false_positive_rate"] == pytest.approx(0.7619)
    assert data["detector"]["regions_missed"] == 140


# --------------------------------------------------------- degradation -----


def test_a_missing_results_file_says_how_to_produce_one(tmp_path):
    report = load_benchmark(tmp_path / "nothing.json")
    assert not report.available
    assert report.detector is None
    assert report.verification is None
    assert "eval_marida.py" in (report.unavailable_reason or "")


def test_malformed_json_is_unavailable_not_zero(tmp_path):
    """Zeroes would render as a measurement of 0.000 precision. Unavailable is
    the truth; a zero is a lie the strip would state confidently."""
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    report = load_benchmark(path)
    assert not report.available
    assert report.verification is None


def test_results_without_the_fitted_block_are_refused(tmp_path):
    path = tmp_path / "unfitted_only.json"
    path.write_text(json.dumps({"held_out_unfitted": FITTED}))
    report = load_benchmark(path)
    assert not report.available
    assert "held_out_fitted" in (report.unavailable_reason or "")


def test_caveats_name_what_is_unmeasured(results_file):
    caveats = " ".join(load_benchmark(results_file).caveats).lower()
    assert "fr-2.2" in caveats  # multi-temporal is unmeasured on MARIDA
    assert "not on this run" in caveats
    assert "1.0 by construction" in caveats
