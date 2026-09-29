"""Candidate-level scoring for the strict holdouts, on synthetic arrays.

Pins the rule that matters under MARIDA's sparse labels: a candidate touching
only unlabelled pixels is ``unverifiable``, never a false positive.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("sklearn")
pytest.importorskip("rasterio")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from eval_holdout_candidates import score_patch  # noqa: E402


def _scene():
    mask = np.zeros((20, 20), dtype=np.int64)  # 0 = unlabelled
    mask[2:4, 2:4] = 1                          # labelled debris object A
    mask[15, 15] = 1                            # labelled debris object B (1 px)
    mask[10:13, 2:5] = 7                        # labelled non-debris
    prob = np.zeros((20, 20), dtype=np.float32)
    prob[2:4, 2:5] = 0.9                        # hits A
    prob[10:12, 2:4] = 0.9                      # on non-debris only -> contradicted
    prob[6:8, 14:16] = 0.9                      # unlabelled only -> unverifiable
    prob[18, 0] = 0.9                           # 1 px -> below min size, dropped
    argmax = np.where(prob > 0.5, 1, 0)
    return prob, argmax, mask


def test_candidates_are_classified_by_what_labels_they_touch():
    out = score_patch(*_scene(), threshold=0.4, min_pixels=3)
    assert (out["hit"], out["contradicted"], out["unverifiable"]) == (1, 1, 1)


def test_objects_are_recalled_by_overlap_and_small_labels_are_counted():
    out = score_patch(*_scene(), threshold=0.4, min_pixels=3)
    assert out["objects"] == 2
    assert out["objects_recalled"] == 1
    assert out["objects_under_min_pixels"] == 1


def test_pixel_counts_use_labelled_pixels_only():
    out = score_patch(*_scene(), threshold=0.4, min_pixels=3)
    # argmax debris on A (4 tp), plus 2 px beside A on unlabelled ground (ignored),
    # plus 4 px on non-debris (fp); B is missed (fn=1). Unlabelled hits are not fp.
    assert (out["px_tp"], out["px_fp"], out["px_fn"]) == (4, 4, 1)
