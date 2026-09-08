"""The measured numbers the console shows, and the framing around them.

These tests care about two things beyond "does it parse": that the weak number
travels alongside the strong one, and that a missing or broken results file
degrades into an honest "unavailable" rather than into zeroes an evaluator
could read as a measurement.
"""

from __future__ import annotations

import json

import pytest

from ghostnet.benchmark import (
    BENCHMARK_FILE,
    load_benchmark,
    load_detector_benchmarks,
    load_multitemporal,
)

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


def test_caveats_stay_current_with_what_has_been_measured(results_file):
    """Caveats are claims the console states confidently, so they rot like any
    other claim. FR-1.4 is built and FR-2.2 is measured; neither may still be
    described as outstanding."""
    caveats = " ".join(load_benchmark(results_file).caveats).lower()
    assert "not on this run" in caveats
    assert "1.0 by construction" in caveats
    assert "fr-2.2" in caveats
    assert "which is not built" not in caveats, "FR-1.4 is built and measured"
    assert "fr-2.2) is unmeasured" not in caveats, "FR-2.2 has been measured"


# ------------------------------------------------------ FR-2.2 -----------


def test_the_multitemporal_result_is_read_not_recomputed():
    """The committed measurement, from the arm the console reports: with OSCAR."""
    report = load_benchmark(BENCHMARK_FILE)
    result = report.multi_temporal
    assert result is not None, "FR-2.2 has been measured; the console must carry it"
    assert result.tile == "16PCC"
    assert result.baseline_f1 == pytest.approx(0.5)
    assert result.with_check_f1 == pytest.approx(0.5)


def test_the_multitemporal_contribution_is_reported_as_zero_not_negative():
    """The finding CHANGED on 2026-09-04 and this test changed with it.

    With no current field the check actively cost F1. With a real OSCAR field
    the harm is gone and the contribution is exactly zero. Reporting it as still
    negative would be as wrong as reporting it as a gain.
    """
    result = load_benchmark(BENCHMARK_FILE).multi_temporal
    assert result is not None
    assert result.f1_delta == pytest.approx(0.0), "harm is gone"
    assert result.recall_delta == pytest.approx(0.0)
    assert result.contributes is False, "and it still earns nothing"
    assert result.true_debris_lost == 0
    assert result.rejections == 0
    assert result.transients_found == 0, "the check's strongest signal still never fires"


def test_the_dependency_is_closed_and_the_data_shows_it():
    """current_speed_ms was None, and that WAS the whole explanation. It is not
    any more: a real field is loaded, and the check is inert rather than
    blocked. The console must not still say 'blocked on FR-3'."""
    result = load_benchmark(BENCHMARK_FILE).multi_temporal
    assert result is not None
    assert result.current_speed_ms == pytest.approx(0.0139, abs=5e-5)
    assert result.current_speed_source == "oscar"


def test_the_before_and_after_of_the_dependency_both_travel():
    """The claim is that the dependency was tested and closed, so the console
    carries both arms. Without the prior arm, 'inert' is an assertion."""
    result = load_benchmark(BENCHMARK_FILE).multi_temporal
    assert result is not None
    assert result.rejections_without_field == 6
    assert result.true_debris_lost_without_field == 1
    assert result.f1_delta_without_field == pytest.approx(-0.1667, abs=5e-4)
    assert result.harm_removed is True


def test_multitemporal_caveats_report_a_closed_dependency_and_a_live_reason():
    """The caveats must say the dependency closed AND why it still earns zero.
    Dropping either half misreports it: the first alone reads as a fix, the
    second alone loses the evidence that the dependency was ever tested."""
    caveats = " ".join(load_benchmark(BENCHMARK_FILE).multi_temporal_caveats).lower()
    assert "dependency is closed" in caveats
    assert "inert" in caveats
    assert "matching strategy" in caveats
    assert "prd 12" in caveats
    assert "significance test" in caveats
    # The dependency may be described in the PAST tense — that history is the
    # evidence it was tested. What must not survive is a present-tense claim.
    assert "is blocked" not in caveats
    assert "superseded" in caveats


def test_a_missing_multitemporal_file_is_none_not_a_crash(tmp_path):
    """A console without this file shows the FR-2.4 gain and says the
    multi-temporal number is unavailable — it does not fail to boot."""
    assert load_multitemporal(tmp_path / "nothing.json") is None


def test_a_malformed_multitemporal_file_is_none_not_zero(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    assert load_multitemporal(path) is None


def test_a_multitemporal_file_without_the_before_after_block_is_skipped(tmp_path):
    path = tmp_path / "partial.json"
    path.write_text(json.dumps({"pair": {"tile": "16PCC"}, "transient": 0}))
    assert load_multitemporal(path) is None


def test_the_dump_carries_the_derived_multitemporal_deltas():
    """Both arms reach the wire: zero now, and what it was before OSCAR."""
    data = load_benchmark(BENCHMARK_FILE).model_dump()["multi_temporal"]
    assert data["f1_delta"] == pytest.approx(0.0)
    assert data["contributes"] is False
    assert data["harm_removed"] is True
    assert data["f1_delta_without_field"] == pytest.approx(-0.1667, abs=5e-4)


# ------------------------------------------- per-detector (FR-1.4) --------


def test_both_detectors_are_measured_and_carry_their_own_verification():
    """Region recall and the verification gain are only meaningful as a pair
    for the same detector. Bundling them is what stops the console showing the
    CNN's recall beside the FDI's gain."""
    entries = {d.detector: d for d in load_benchmark(BENCHMARK_FILE).detectors}
    assert set(entries) == {"fdi", "cnn"}

    fdi, cnn = entries["fdi"], entries["cnn"]
    assert fdi.region_recall == pytest.approx(0.4068)
    assert cnn.region_recall == pytest.approx(0.7034)
    assert cnn.regions_hit == 166
    assert cnn.regions_missed == 70
    assert cnn.candidates_emitted < fdi.candidates_emitted


def test_the_cnn_subsumes_most_of_the_verification_gain():
    """The PRD 12 finding. Verification is worth +0.385 precision over the FDI
    and +0.080 over the CNN, because the network already declines to emit most
    of what the checks existed to reject."""
    entries = {d.detector: d for d in load_benchmark(BENCHMARK_FILE).detectors}
    fdi_gain = entries["fdi"].verification.precision_gain
    cnn_gain = entries["cnn"].verification.precision_gain

    assert fdi_gain == pytest.approx(0.385, abs=5e-4)
    assert cnn_gain == pytest.approx(0.080, abs=5e-4)
    assert cnn_gain < fdi_gain / 4, "the collapse is the finding, not a rounding artefact"


def test_the_overlap_note_is_served_once_two_detectors_exist():
    report = load_benchmark(BENCHMARK_FILE)
    assert report.verification_overlap is not None
    note = report.verification_overlap
    assert "+0.385" in note and "+0.080" in note


def test_no_overlap_note_when_only_one_detector_is_measured(tmp_path, monkeypatch):
    """With a single detector there is no second number to mistake the first
    for, and the note would be noise."""
    import ghostnet.benchmark as bench

    only_fdi = {"fdi": bench.DETECTOR_FILES["fdi"]}
    monkeypatch.setattr(bench, "DETECTOR_FILES", only_fdi)
    report = load_benchmark(BENCHMARK_FILE)
    assert len(report.detectors) == 1
    assert report.verification_overlap is None


def test_an_unmeasured_detector_is_skipped_not_fatal(tmp_path):
    """A checkout where only the FDI has been evaluated still shows the FDI."""
    entries = load_detector_benchmarks({"cnn": tmp_path / "absent.json"})
    assert entries == []


def test_a_malformed_detector_file_is_skipped(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    assert load_detector_benchmarks({"cnn": path}) == []


def test_the_dump_carries_derived_fields_per_detector():
    data = load_benchmark(BENCHMARK_FILE).model_dump()
    cnn = next(d for d in data["detectors"] if d["detector"] == "cnn")
    assert cnn["regions_missed"] == 70
    assert cnn["verification"]["precision_gain"] == pytest.approx(0.0798, abs=5e-4)
