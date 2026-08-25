"""FR-1.4 — the CNN detector variant.

Skipped wholesale where PyTorch is absent. torch is in requirements-gpu.txt and
is deliberately workstation-only — the Air has no reason to carry a 3 GB CUDA
build for a model it must not train. Without this guard the suite could not be
green on the Air, which is the same trap as a test that only passes on the
machine holding the data.

Nothing here needs a trained checkpoint or MARIDA: the model is exercised
untrained through the public contract, because what these tests protect is the
*interface* the orchestration depends on, not the accuracy. The accuracy lives
in eval/results.md.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="torch is workstation-only (requirements-gpu.txt)")

from ghostnet.agents.detection import GeoTransform, Tile  # noqa: E402
from ghostnet.agents.detection_cnn import (  # noqa: E402
    BAND_MEAN,
    BAND_STD,
    CLASS_NAMES,
    CLASS_WEIGHTS,
    DEBRIS_CLASS,
    MARIDA_BANDS,
    NUM_CLASSES,
    CheckpointMissingError,
    LoadedDetector,
    build_unet,
    detect,
    load_detector,
    normalise,
)

TRANSFORM = GeoTransform(lon_origin=-88.86, lat_origin=16.28, lon_step=0.0002, lat_step=-0.0002)


def _tile(bands=MARIDA_BANDS, size: int = 256) -> Tile:
    rng = np.random.default_rng(0)
    return Tile(
        tile_id="S2-16PCC-20200918",
        acquired_at=datetime(2020, 9, 18),
        bands={b: rng.uniform(0.01, 0.06, (size, size)).astype("float32") for b in bands},
        transform=TRANSFORM,
        source="synthetic",
    )


def _untrained() -> LoadedDetector:
    """A real model with random weights — enough to exercise the contract."""
    model = build_unet(in_channels=len(MARIDA_BANDS), num_classes=NUM_CLASSES, width=4)
    model.eval()
    return LoadedDetector(model=model, meta={"run_id": "untrained-test"}, device="cpu")


# --- constants ------------------------------------------------------------


def test_normalisation_statistics_cover_every_band():
    assert len(BAND_MEAN) == len(BAND_STD) == len(MARIDA_BANDS) == 11


def test_class_weights_cover_every_real_class():
    """Index 0 is unlabelled and is never trained, so weights run 1..15."""
    assert len(CLASS_WEIGHTS) == NUM_CLASSES - 1 == 15
    assert len(CLASS_NAMES) == NUM_CLASSES


def test_the_unlabelled_class_is_index_zero():
    assert CLASS_NAMES[0] == "unlabelled"
    assert CLASS_NAMES[DEBRIS_CLASS] == "Marine Debris"


def test_rare_classes_are_weighted_above_common_ones():
    """Debris is 0.45% of labelled pixels, water 20%. Unweighted CE collapses."""
    debris = CLASS_WEIGHTS[DEBRIS_CLASS - 1]
    water = CLASS_WEIGHTS[6]  # Marine Water
    assert debris > water * 5


def test_normalise_centres_each_band_independently():
    stack = np.stack([np.full((8, 8), m, dtype="float32") for m in BAND_MEAN])
    out = normalise(stack)
    assert np.allclose(out, 0.0, atol=1e-5)


def test_normalise_scales_by_the_band_std():
    stack = np.stack(
        [np.full((4, 4), m + s, dtype="float32") for m, s in zip(BAND_MEAN, BAND_STD, strict=True)]
    )
    assert np.allclose(normalise(stack), 1.0, atol=1e-4)


# --- model ----------------------------------------------------------------


def test_the_unet_maps_eleven_bands_to_per_pixel_classes():
    model = build_unet(in_channels=11, num_classes=NUM_CLASSES, width=4)
    out = model(torch.zeros(2, 11, 64, 64))
    assert out.shape == (2, NUM_CLASSES, 64, 64)


def test_the_unet_preserves_spatial_resolution():
    """Segmentation, not classification — one prediction per pixel."""
    model = build_unet(in_channels=11, num_classes=NUM_CLASSES, width=4)
    assert model(torch.zeros(1, 11, 128, 128)).shape[-2:] == (128, 128)


# --- contract with the orchestration --------------------------------------


def test_detect_returns_detections_marked_as_the_cnn():
    """FR-1.4 — same output type as the FDI baseline, distinguishable by field."""
    found = detect(_tile(), detector=_untrained(), prob_threshold=0.0, min_pixels=1)
    assert found, "threshold 0 should surface at least one component"
    for d in found:
        assert d.detector == "cnn"
        assert d.id.startswith("S2-16PCC-20200918-c")
        assert -180 <= d.lon <= 180 and -90 <= d.lat <= 90
        assert 0.0 <= d.confidence <= 1.0


def test_detections_carry_the_model_as_evidence():
    """PRD §8 — every output names the thing that produced it."""
    found = detect(_tile(), detector=_untrained(), prob_threshold=0.0, min_pixels=1)
    kinds = {e.kind for e in found[0].evidence}
    assert "derived" in kinds and "sentinel2_tile" in kinds
    model_evidence = next(e for e in found[0].evidence if e.kind == "derived")
    assert "U-Net debris probability" in model_evidence.detail


def test_an_impossible_threshold_yields_no_detections():
    assert detect(_tile(), detector=_untrained(), prob_threshold=1.01) == []


def test_a_four_band_fdi_tile_is_rejected_with_the_fix():
    """The FDI path loads four bands; the CNN needs eleven. Fail loudly."""
    with pytest.raises(ValueError, match="MARIDA bands"):
        detect(_tile(bands=("B04", "B06", "B08", "B11")), detector=_untrained())


def test_the_cloud_mask_still_suppresses_detections():
    tile = _tile()
    tile.cloud_mask = np.ones(tile.shape, dtype=bool)
    assert detect(tile, detector=_untrained(), prob_threshold=0.0, min_pixels=1) == []


def test_max_detections_is_respected():
    found = detect(_tile(), detector=_untrained(), prob_threshold=0.0,
                   min_pixels=1, max_detections=3)
    assert len(found) <= 3


# --- checkpoint handling --------------------------------------------------


def test_a_missing_checkpoint_names_the_command_that_makes_it(tmp_path):
    """Weights are never committed, so absence is expected, not exceptional."""
    with pytest.raises(CheckpointMissingError) as excinfo:
        load_detector(tmp_path / "nope.pt")
    message = str(excinfo.value)
    assert "scripts/train_cnn.py" in message
    assert "detection.detect" in message  # points at the working fallback
