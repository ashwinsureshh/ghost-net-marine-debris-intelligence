"""FR-1.4 — CNN detector variant.

An alternative to the FDI spectral index in :mod:`ghostnet.agents.detection`,
satisfying the same contract: :func:`detect` takes a ``Tile`` and returns
``Detection`` objects, differing only in ``detector="cnn"``. The orchestration,
the verification agent and the operator console therefore need no changes.

**WORKSTATION ONLY for training** (MACHINE-WORKFLOW.md). Inference is CPU-capable
but slow; training needs the GPU. The checkpoint lives in ``models/`` and is
never committed, so a session that does not find it must say so rather than
pretend — :func:`load_detector` raises with the command that produces it.

Why a hand-written U-Net rather than segmentation-models-pytorch
----------------------------------------------------------------
``requirements-gpu.txt`` originally listed smp/timm/torchvision. Installing them
here would have resolved against this machine's PyTorch **nightly** (2.12.dev,
cu128) and risked downgrading it — that build is the one verified to carry
sm_120 kernels for the RTX 5070, and losing it would break GPU training
entirely for a dependency that buys little: MARIDA is 11 spectral bands, not
RGB, so ImageNet-pretrained encoders transfer weakly and their first
convolution has to be rebuilt regardless. This U-Net is ~2 MB of plain PyTorch
with no dependency beyond torch itself.

Three things about MARIDA that shape the design
-----------------------------------------------
1. **Class 0 is *unlabelled*, not background, and is 99.06% of all pixels.**
   It is excluded from the loss via ``ignore_index=0``. Training it as a real
   class teaches the model to predict "nothing" almost everywhere, and the
   result looks like a successful run.
2. **Marine Debris is 1943 pixels in the entire train split** — 0.452% of
   *labelled* pixels and 0.0043% of all of them. Unweighted cross-entropy
   collapses to the majority class, so classes are weighted by inverse square
   root frequency.
3. **This is multi-class, not debris-vs-rest.** MARIDA separately labels the
   exact things the Verification Agent has to rule out — Sargassum, foam,
   ships, clouds, turbid water. Learning them as distinct classes is what lets
   the detector avoid the FDI's documented failure modes rather than inherit
   them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ghostnet.agents.detection import Tile
from ghostnet.config import REPO_ROOT, GhostNetError
from ghostnet.schemas import Detection, Evidence

# MARIDA band order — verified physically, not assumed. See
# scripts/eval_marida.py for the evidence (Dense Sargassum's red edge and the
# b10/b11 collapse over water).
MARIDA_BANDS = ("B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12")

# Per-band mean/std over the MARIDA train split (694 patches, finite pixels).
BAND_MEAN = (
    0.051976, 0.047840, 0.040568, 0.031636, 0.029726, 0.034574,
    0.038751, 0.034364, 0.039211, 0.023581, 0.015888,
)
BAND_STD = (
    0.047259, 0.047438, 0.046991, 0.049674, 0.049468, 0.064584,
    0.075949, 0.071203, 0.082511, 0.051115, 0.035244,
)

CLASS_NAMES = (
    "unlabelled", "Marine Debris", "Dense Sargassum", "Sparse Sargassum",
    "Natural Organic Material", "Ship", "Clouds", "Marine Water",
    "Sediment-Laden Water", "Foam", "Turbid Water", "Shallow Water",
    "Waves", "Cloud Shadows", "Wakes", "Mixed Water",
)
NUM_CLASSES = len(CLASS_NAMES)  # 16, index 0 reserved for "unlabelled"
DEBRIS_CLASS = 1

# Inverse-square-root frequency over the train split, mean-normalised, for
# classes 1..15. Index 0 is never trained.
CLASS_WEIGHTS = (
    1.0568, 1.5793, 1.4103, 1.7324, 0.8122, 0.1823, 0.1580,
    0.1186, 2.1510, 0.1581, 0.3958, 0.8540, 0.6184, 0.6605, 3.1124,
)

DEFAULT_CHECKPOINT = REPO_ROOT / "models" / "detector_v1.pt"
PATCH_PX = 256
# Probability above which a pixel counts as debris. CALIBRATED on the MARIDA
# val split, never on test — see eval/results.md for the sweep.
#
# Chosen to maximise *region recall*, which is what FR-1.4 exists to fix, not
# precision. Those pull in opposite directions here: over val, baseline
# precision climbs monotonically with the threshold (0.78 at 0.20 -> 0.90 at
# 0.70) while region recall peaks at 0.40 and then collapses (0.755 -> 0.499).
# A threshold picked on precision alone would have looked better on paper and
# found less debris.
DEFAULT_PROB_THRESHOLD = 0.40
DEFAULT_MIN_PIXELS = 3


class CheckpointMissingError(GhostNetError):
    """The trained weights are not on this machine."""


# --------------------------------------------------------------------- model


def _conv_block(in_ch: int, out_ch: int):
    import torch.nn as nn

    return nn.Sequential(
        nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(inplace=True),
        nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(inplace=True),
    )


def build_unet(in_channels: int = 11, num_classes: int = NUM_CLASSES, width: int = 32):
    """A plain 4-level U-Net. Small on purpose: 694 training patches."""
    import torch
    import torch.nn as nn

    class UNet(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            w = width
            self.enc1 = _conv_block(in_channels, w)
            self.enc2 = _conv_block(w, w * 2)
            self.enc3 = _conv_block(w * 2, w * 4)
            self.enc4 = _conv_block(w * 4, w * 8)
            self.pool = nn.MaxPool2d(2)
            self.bottleneck = _conv_block(w * 8, w * 16)
            self.up4 = nn.ConvTranspose2d(w * 16, w * 8, 2, stride=2)
            self.dec4 = _conv_block(w * 16, w * 8)
            self.up3 = nn.ConvTranspose2d(w * 8, w * 4, 2, stride=2)
            self.dec3 = _conv_block(w * 8, w * 4)
            self.up2 = nn.ConvTranspose2d(w * 4, w * 2, 2, stride=2)
            self.dec2 = _conv_block(w * 4, w * 2)
            self.up1 = nn.ConvTranspose2d(w * 2, w, 2, stride=2)
            self.dec1 = _conv_block(w * 2, w)
            self.head = nn.Conv2d(w, num_classes, 1)

        def forward(self, x):
            e1 = self.enc1(x)
            e2 = self.enc2(self.pool(e1))
            e3 = self.enc3(self.pool(e2))
            e4 = self.enc4(self.pool(e3))
            b = self.bottleneck(self.pool(e4))
            d4 = self.dec4(torch.cat([self.up4(b), e4], 1))
            d3 = self.dec3(torch.cat([self.up3(d4), e3], 1))
            d2 = self.dec2(torch.cat([self.up2(d3), e2], 1))
            d1 = self.dec1(torch.cat([self.up1(d2), e1], 1))
            return self.head(d1)

    return UNet()


def normalise(stack: np.ndarray) -> np.ndarray:
    """Standardise an (11, H, W) reflectance stack with the train statistics."""
    mean = np.asarray(BAND_MEAN, dtype="float32").reshape(-1, 1, 1)
    std = np.asarray(BAND_STD, dtype="float32").reshape(-1, 1, 1)
    return ((stack.astype("float32") - mean) / std).astype("float32")


# ---------------------------------------------------------------- checkpoint


@dataclass
class LoadedDetector:
    model: Any
    meta: dict
    device: str


def load_detector(
    checkpoint: Path | str = DEFAULT_CHECKPOINT, *, device: str | None = None
) -> LoadedDetector:
    """Load trained weights, or say plainly that they are not on this machine."""
    import torch

    path = Path(checkpoint)
    if not path.exists():
        raise CheckpointMissingError(
            f"No CNN checkpoint at {path}. Model weights are never committed "
            "(MACHINE-WORKFLOW.md sync rule 2), so this machine may simply not "
            "have it. Train it on the workstation with:\n"
            "    python scripts/train_cnn.py\n"
            "Until then use the FDI baseline: ghostnet.agents.detection.detect()."
        )

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    blob = torch.load(path, map_location=device, weights_only=False)
    model = build_unet(
        in_channels=blob.get("in_channels", 11),
        num_classes=blob.get("num_classes", NUM_CLASSES),
        width=blob.get("width", 32),
    )
    model.load_state_dict(blob["state_dict"])
    model.to(device).eval()
    return LoadedDetector(model=model, meta=blob.get("meta", {}), device=device)


# ----------------------------------------------------------------- inference


def predict_debris_probability(
    stack: np.ndarray, detector: LoadedDetector, *, overlap: int = 32, batch: int = 4
) -> np.ndarray:
    """Debris-class probability for an (11, H, W) stack, tiled with overlap.

    Tiles are blended with a cosine window so seams do not appear as spurious
    edges — a hard tiling produces gridline artefacts that connected-component
    analysis then reports as detections.
    """
    import torch

    if stack.shape[0] != len(MARIDA_BANDS):
        raise ValueError(
            f"CNN expects {len(MARIDA_BANDS)} bands {list(MARIDA_BANDS)}, "
            f"got {stack.shape[0]}."
        )

    _, height, width = stack.shape
    step = PATCH_PX - overlap
    normalised = normalise(stack)

    accum = np.zeros((height, width), dtype="float32")
    weight = np.zeros((height, width), dtype="float32")

    # Cosine taper, so overlapping tiles average smoothly.
    ramp = np.hanning(PATCH_PX).astype("float32")
    ramp = np.maximum(ramp, 1e-3)
    window = np.outer(ramp, ramp)

    rows = list(range(0, max(height - PATCH_PX, 0) + 1, step))
    cols = list(range(0, max(width - PATCH_PX, 0) + 1, step))
    if rows[-1] + PATCH_PX < height:
        rows.append(height - PATCH_PX)
    if cols[-1] + PATCH_PX < width:
        cols.append(width - PATCH_PX)

    coords = [(r, c) for r in rows for c in cols]
    with torch.inference_mode():
        for start in range(0, len(coords), batch):
            chunk = coords[start : start + batch]
            crops = np.stack(
                [normalised[:, r : r + PATCH_PX, c : c + PATCH_PX] for r, c in chunk]
            )
            tensor = torch.from_numpy(crops).to(detector.device)
            logits = detector.model(tensor)
            probs = torch.softmax(logits, dim=1)[:, DEBRIS_CLASS].float().cpu().numpy()
            for (r, c), prob in zip(chunk, probs, strict=True):
                accum[r : r + PATCH_PX, c : c + PATCH_PX] += prob * window
                weight[r : r + PATCH_PX, c : c + PATCH_PX] += window

    return np.divide(accum, weight, out=np.zeros_like(accum), where=weight > 0)


def _confidence(prob_mean: float, area_px: int) -> float:
    """Mirror the FDI detector's shape so the two are comparable downstream."""
    size = 1.0 - math.exp(-area_px / 8.0)
    return round(min(1.0, 0.65 * float(prob_mean) + 0.35 * size), 4)


def detect(
    tile: Tile,
    *,
    detector: LoadedDetector | None = None,
    checkpoint: Path | str = DEFAULT_CHECKPOINT,
    prob_threshold: float = DEFAULT_PROB_THRESHOLD,
    min_pixels: int = DEFAULT_MIN_PIXELS,
    max_detections: int = 200,
) -> list[Detection]:
    """FR-1.4 — the CNN alternative to the FDI baseline.

    Same signature and same ``Detection`` output as
    :func:`ghostnet.agents.detection.detect`, so it drops in behind the same
    orchestration. Requires the tile to carry all 11 MARIDA bands; the FDI path
    only loads four, so fetch tiles with
    ``ghostnet.ingest.load_tiles(..., bands=MARIDA_BANDS)``.
    """
    from scipy import ndimage

    missing = [b for b in MARIDA_BANDS if b not in tile.bands]
    if missing:
        raise ValueError(
            f"Tile {tile.tile_id} is missing band(s) {missing}. The CNN detector "
            f"needs all {len(MARIDA_BANDS)} MARIDA bands, not just the four the "
            "FDI uses — load tiles with bands=detection_cnn.MARIDA_BANDS."
        )

    if detector is None:
        detector = load_detector(checkpoint)

    stack = np.stack([np.asarray(tile.bands[b], dtype="float32") for b in MARIDA_BANDS])
    probability = predict_debris_probability(stack, detector)

    mask = probability > prob_threshold
    if tile.cloud_mask is not None:
        mask &= ~np.asarray(tile.cloud_mask, dtype=bool)

    labelled, count = ndimage.label(mask)
    pixel_area = tile.transform.pixel_area_km2
    tile_evidence = tile.evidence()
    model_ref = str(detector.meta.get("run_id", "detector"))

    detections: list[Detection] = []
    for label_id in range(1, count + 1):
        component = labelled == label_id
        area_px = int(component.sum())
        if area_px < min_pixels:
            continue
        rows, cols = np.nonzero(component)
        lon, lat = tile.transform.to_lonlat(float(cols.mean()), float(rows.mean()))
        prob_mean = float(probability[component].mean())
        detections.append(
            Detection(
                id=f"{tile.tile_id}-c{label_id:04d}",
                tile_id=tile.tile_id,
                acquired_at=tile.acquired_at,
                lon=round(lon, 6),
                lat=round(lat, 6),
                area_px=area_px,
                area_km2=round(area_px * pixel_area, 6),
                # The FDI is not what fired here. Reporting a real FDI would
                # imply the index made this call; 0.0 with detector="cnn" is
                # unambiguous, and the verification agent recomputes its own.
                fdi_mean=0.0,
                ndvi_mean=0.0,
                confidence=_confidence(prob_mean, area_px),
                detector="cnn",
                evidence=[
                    tile_evidence,
                    Evidence(
                        # "derived" rather than a new "model" kind: Evidence.kind
                        # is a closed literal shared with the export schema, and
                        # widening it would force an artefact schema bump on the
                        # console for no gain. The ref names the checkpoint.
                        kind="derived",
                        ref=model_ref,
                        detail=(
                            f"U-Net debris probability {prob_mean:.3f} over "
                            f"{area_px} px (threshold {prob_threshold})"
                        ),
                    ),
                ],
            )
        )

    detections.sort(key=lambda d: d.confidence, reverse=True)
    return detections[:max_detections]
