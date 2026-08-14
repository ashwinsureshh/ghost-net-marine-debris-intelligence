"""FR-1 — spectral-index detection over synthetic tiles."""

from __future__ import annotations

import numpy as np
import pytest

from ghostnet.agents.detection import (
    detect,
    floating_debris_index,
    ndvi,
    sample_window,
)
from tests.conftest import SIGNATURES, TRANSFORM, make_tile


def _fdi_of(kind: str) -> float:
    s = SIGNATURES[kind]
    return float(
        floating_debris_index(
            np.array(s["B04"]), np.array(s["B06"]), np.array(s["B08"]), np.array(s["B11"])
        )
    )


def test_clean_water_has_near_zero_fdi():
    assert abs(_fdi_of("water")) < 1e-3


def test_debris_signature_lifts_the_index_well_clear_of_water():
    assert _fdi_of("debris") > 0.04
    assert _fdi_of("debris") > _fdi_of("water") + 0.03


def test_featureless_water_yields_no_detections(water_tile):
    assert detect(water_tile) == []


def test_single_debris_patch_is_found_once(debris_tile):
    detections = detect(debris_tile)
    assert len(detections) == 1

    found = detections[0]
    assert found.area_px == 49  # the 7x7 fixture patch
    assert found.detector == "fdi"
    assert 0.0 < found.confidence <= 1.0
    assert found.area_km2 == pytest.approx(49 * TRANSFORM.pixel_area_km2, rel=1e-6)
    # Centroid of rows/cols 10..16 is index 13.
    expected_lon, expected_lat = TRANSFORM.to_lonlat(13, 13)
    assert found.lon == pytest.approx(expected_lon, abs=1e-6)
    assert found.lat == pytest.approx(expected_lat, abs=1e-6)


def test_detection_carries_tile_evidence(debris_tile):
    found = detect(debris_tile)[0]
    assert [e.kind for e in found.evidence] == ["sentinel2_tile"]
    assert found.evidence[0].ref == debris_tile.tile_id


def test_small_patches_are_filtered_by_min_pixels():
    tile = make_tile({(10, 10): "debris"}, patch_px=2)
    assert detect(tile, min_pixels=5) == []
    assert len(detect(tile, min_pixels=3)) == 1


def test_cloud_mask_suppresses_detections(debris_tile):
    debris_tile.cloud_mask = np.ones(debris_tile.shape, dtype=bool)
    assert detect(debris_tile) == []


def test_mixed_tile_finds_the_false_positives_too(mixed_tile):
    """The raw detector is supposed to be fooled — that is why FR-2 exists.

    Four, not five: at the MARIDA-fitted FDI threshold the cloud-shadow patch is
    too dark to be raised at all, so the detector is fooled three times rather
    than four. See the "shadow" note in conftest.
    """
    detections = detect(mixed_tile)
    assert len(detections) == 4


def test_transform_pixel_roundtrip():
    for col, row in [(0, 0), (13, 27), (39, 39)]:
        lon, lat = TRANSFORM.to_lonlat(col, row)
        assert TRANSFORM.to_pixel(lon, lat) == (col, row)


def test_sample_window_recovers_the_patch_signature(debris_tile):
    found = detect(debris_tile)[0]
    window = sample_window(debris_tile, found)
    for band, expected in SIGNATURES["debris"].items():
        assert window.band_means[band] == pytest.approx(expected, rel=1e-9)
    assert window.window_px == 25
    assert window.fdi == pytest.approx(_fdi_of("debris"), rel=1e-9)


def test_sample_window_rejects_a_detection_outside_the_tile(debris_tile):
    found = detect(debris_tile)[0]
    off_tile = found.model_copy(update={"lon": 120.0, "lat": -40.0})
    with pytest.raises(ValueError, match="outside tile"):
        sample_window(debris_tile, off_tile)


def test_ndvi_handles_zero_denominator_without_dividing_by_zero():
    zeros = np.zeros((2, 2))
    assert np.all(ndvi(zeros, zeros) == 0.0)
