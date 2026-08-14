"""FR-2 — the agent must actively disqualify each documented failure mode."""

from __future__ import annotations

from datetime import timedelta

import pytest

from ghostnet.agents.detection import BandWindow, detect, sample_window
from ghostnet.agents.verification import (
    DEFAULT_THRESHOLDS,
    RepeatObservation,
    check_bright_water_surface,
    check_cloud_shadow,
    precision_recall_delta,
    verify,
)
from tests.conftest import BASE_TIME, SIGNATURES, TRANSFORM, make_tile


def _verify_patch(kind: str, **kwargs):
    tile = make_tile({(10, 10): kind}, **kwargs.pop("tile_kwargs", {}))
    detections = detect(tile)
    assert len(detections) == 1, f"fixture {kind!r} should produce one candidate"
    detection = detections[0]
    return detection, verify(detection, sample_window(tile, detection), **kwargs)


def _failed(result) -> set[str]:
    return {c.name for c in result.checks if c.disqualified}


def test_genuine_debris_survives_every_check():
    _, result = _verify_patch("debris")
    assert result.verified is True
    assert _failed(result) == set()
    assert result.confidence > 0


def test_bright_swir_target_is_disqualified():
    _, result = _verify_patch("glint")
    assert result.verified is False
    assert "bright_swir_target" in _failed(result)
    assert "SWIR" in result.rejection_reasons[0]


def test_foam_is_disqualified():
    _, result = _verify_patch("foam")
    assert result.verified is False
    assert "bright_water_surface" in _failed(result)


def test_floating_vegetation_is_disqualified():
    _, result = _verify_patch("kelp")
    assert result.verified is False
    assert "kelp_sargassum" in _failed(result)


def test_cloud_shadow_is_disqualified():
    """Unit-tested on the check directly, not through detect().

    At the MARIDA-fitted thresholds a cloud shadow dark enough to trip
    ``shadow_brightness_max`` (0.008) cannot also clear the detector's FDI
    threshold (0.025) — see the note on the "shadow" signature in conftest.
    The check still has to work for the L2A path, where the scene classification
    layer can hand us a dark candidate the FDI alone would not raise.
    """
    window = BandWindow(
        detection_id="d-shadow",
        tile_id="T44PLT-20260314",
        acquired_at=BASE_TIME,
        band_means=SIGNATURES["shadow"],
        fdi=0.010,
        ndvi=0.33,
        window_px=25,
    )
    check = check_cloud_shadow(window, DEFAULT_THRESHOLDS)
    assert check.disqualified is True
    assert "shadow" in check.reason.lower()


def test_cloud_shadow_fixture_is_below_the_detection_threshold():
    """Guards the claim above: if this ever detects, the test above is stale."""
    tile = make_tile({(10, 10): "shadow"})
    assert detect(tile) == []


def test_rejection_gives_a_specific_reason_not_a_bare_flag():
    """FR-2.3 — the reason must name the mode, not just say 'rejected'."""
    _, result = _verify_patch("foam")
    assert result.rejection_reasons
    assert len(result.rejection_reasons[0]) > 40
    assert result.confidence == 0.0


def test_bright_swir_target_is_rejected_even_when_geometry_is_not_specular():
    """Regression guard: clouds and ships must still be caught on real L2A.

    The check used to require ``specular geometry OR no geometry at all`` to
    disqualify. MARIDA carries no geometry, so it rejected 91.8% of clouds there
    — but on real L2A tiles, where geometry is present and usually non-specular,
    it would have quietly stopped rejecting them and taken the headline FR-2.4
    result with it. Disqualification is now decided on the spectral signature;
    geometry only names the cause.
    """
    _, result = _verify_patch(
        "glint",
        tile_kwargs={
            "geometry": {
                "sun_zenith_deg": 60.0,
                "sun_azimuth_deg": 0.0,
                "view_zenith_deg": 30.0,
                "view_azimuth_deg": 180.0,  # ~30° off specular
            }
        },
    )
    assert result.verified is False
    assert "bright_swir_target" in _failed(result)
    # ...and it must not claim sun glint when the geometry says otherwise.
    assert "sun glint" not in result.rejection_reasons[0].lower()


def test_turbid_water_is_not_reported_as_foam():
    """FR-2.3 — the reason must match the evidence, not a neighbouring mode."""
    window = BandWindow(
        detection_id="d-turbid",
        tile_id="T44PLT-20260314",
        acquired_at=BASE_TIME,
        band_means={"B04": 0.052, "B06": 0.020, "B08": 0.021, "B11": 0.007},
        fdi=0.030,
        ndvi=-0.43,  # MARIDA's Turbid Water median
        window_px=25,
    )
    check = check_bright_water_surface(window, DEFAULT_THRESHOLDS)
    assert check.disqualified is True
    assert "turbid" in check.reason.lower()
    assert "foam" not in check.reason.lower()


def test_specular_geometry_alone_does_not_reject_a_debris_patch():
    """Glint geometry plus a debris-shaped spectrum is still debris."""
    _, result = _verify_patch(
        "debris",
        tile_kwargs={
            "geometry": {
                "sun_zenith_deg": 30.0,
                "sun_azimuth_deg": 140.0,
                "view_zenith_deg": 30.0,
                "view_azimuth_deg": 140.0,
            }
        },
    )
    assert result.verified is True


def test_missing_repeats_are_inconclusive_and_cost_confidence():
    detection, result = _verify_patch("debris")
    multi = next(c for c in result.checks if c.name == "multi_temporal")
    assert multi.disqualified is False
    assert "inconclusive" in multi.reason
    # Two checks are inconclusive here (glint geometry + persistence), so the
    # penalty is applied twice — a candidate we could not test is not a
    # candidate we verified.
    assert result.confidence < detection.confidence


def test_a_patch_that_appears_once_and_vanishes_is_transient():
    _, result = _verify_patch(
        "debris",
        repeats=[
            RepeatObservation(
                tile_id="repeat-1",
                acquired_at=BASE_TIME + timedelta(days=5),
                lon=None,
                lat=None,
                detected=False,
            )
        ],
    )
    assert result.verified is False
    assert "multi_temporal" in _failed(result)
    assert "Transient" in result.rejection_reasons[0]


def test_motion_beyond_what_the_current_allows_is_rejected():
    detection, _ = _verify_patch("debris")
    _, result = _verify_patch(
        "debris",
        current_speed_ms=0.1,  # ~43 km over 5 days
        repeats=[
            RepeatObservation(
                tile_id="repeat-1",
                acquired_at=BASE_TIME + timedelta(days=5),
                lon=detection.lon + 3.0,  # ~325 km east
                lat=detection.lat,
                detected=True,
            )
        ],
    )
    assert result.verified is False
    assert "Incoherent motion" in result.rejection_reasons[0]


def test_motion_consistent_with_the_current_is_accepted():
    detection, _ = _verify_patch("debris")
    _, result = _verify_patch(
        "debris",
        current_speed_ms=0.2,  # ~86 km over 5 days
        repeats=[
            RepeatObservation(
                tile_id="repeat-1",
                acquired_at=BASE_TIME + timedelta(days=5),
                lon=detection.lon + 0.5,  # ~54 km east
                lat=detection.lat,
                detected=True,
            )
        ],
    )
    assert result.verified is True
    multi = next(c for c in result.checks if c.name == "multi_temporal")
    assert "consistent with the local current" in multi.reason


def test_verification_keeps_evidence_for_every_repeat_pass():
    _, result = _verify_patch(
        "debris",
        repeats=[
            RepeatObservation("repeat-1", BASE_TIME + timedelta(days=5), None, None, False),
            RepeatObservation("repeat-2", BASE_TIME + timedelta(days=10), None, None, False),
        ],
    )
    refs = [e.ref for e in result.evidence]
    assert "repeat-1" in refs and "repeat-2" in refs


def test_precision_recall_delta_reports_the_headline_ablation_number(mixed_tile):
    """FR-2.4 — the measured contribution of this agent over the raw detector."""
    detections = detect(mixed_tile)
    results = [
        verify(d, sample_window(mixed_tile, d)) for d in detections
    ]
    # Ground truth comes from where the fixture *put* the debris patch, not
    # from what the agent decided — otherwise the metric would be circular.
    # The debris block occupies rows/cols 5..11, so its centroid is pixel (8, 8).
    truth_lon, truth_lat = TRANSFORM.to_lonlat(8, 8)
    debris_id = min(
        detections,
        key=lambda d: abs(d.lon - truth_lon) + abs(d.lat - truth_lat),
    ).id
    labels = {d.id: (d.id == debris_id) for d in detections}

    metrics = precision_recall_delta(detections, results, labels)
    # Four candidates, not five: the shadow patch is below the fitted detection
    # threshold and is never raised. See conftest's "shadow" note.
    assert metrics["n_labelled"] == 4.0
    assert metrics["baseline_precision"] == pytest.approx(0.25)
    assert metrics["verified_precision"] == pytest.approx(1.0)
    assert metrics["precision_delta"] > 0
    assert metrics["verified_recall"] == pytest.approx(1.0)  # no true positive lost


def test_precision_recall_ignores_unlabelled_detections(debris_tile):
    detections = detect(debris_tile)
    results = [verify(d, sample_window(debris_tile, d)) for d in detections]
    metrics = precision_recall_delta(detections, results, labels={})
    assert metrics["n_labelled"] == 0.0
