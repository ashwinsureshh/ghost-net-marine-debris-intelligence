"""Threshold-free and candidate-level metrics for the strict geographic holdouts.

    python scripts/eval_holdout_candidates.py --json eval/geographic_candidates.json

WORKSTATION ONLY (GPU + MARIDA). Re-scores the six existing strict holdout
checkpoints (eval/geographic_validation.json) on their unseen tiles. No
training; checkpoints and their normalisation are verified by hash first.

Why this exists: the published holdout numbers are argmax PIXEL confusion
counts. The pipeline does not emit pixels; it emits CANDIDATES — connected
components of debris probability above 0.40, at least 3 pixels
(ghostnet.agents.detection_cnn.detect). Two things were missing:

* PR-AUC (average precision) of the debris probability over labelled pixels,
  which does not depend on a threshold chosen elsewhere.
* Candidate-level counts under the production rule.

MARIDA masks are SPARSE: most pixels are unlabelled (class 0), which means
"not annotated", not "not debris". So a predicted candidate is classified
three ways, and only two are evidence:

* ``hit``          — overlaps a labelled debris pixel;
* ``contradicted`` — overlaps labelled non-debris and no labelled debris;
* ``unverifiable`` — touches only unlabelled pixels. NOT a false positive.

Candidate precision is therefore reported as a BOUND:
hit/(hit+contradicted+unverifiable) <= precision <= hit/(hit+contradicted).

Labelled debris objects are 4-connected components of class 1. An object is
recalled when any candidate pixel overlaps it.

The argmax pixel metrics are recomputed and must match the published
artefact; a mismatch aborts, because it would mean this is not measuring the
same thing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from eval_marida import split_ids  # noqa: E402
from ghostnet.agents.detection_cnn import (  # noqa: E402
    DEBRIS_CLASS,
    DEFAULT_MIN_PIXELS,
    DEFAULT_PROB_THRESHOLD,
    load_detector,
)
from ghostnet.evidence_hash import TEXT_HASH_METHOD, text_evidence_sha256  # noqa: E402
from train_cnn import MaridaPatches  # noqa: E402

REFERENCE = ROOT / "eval" / "geographic_validation.json"


def score_patch(prob: np.ndarray, argmax: np.ndarray, mask: np.ndarray,
                threshold: float, min_pixels: int) -> dict:
    labelled = mask > 0
    debris = mask == DEBRIS_CLASS
    out = {"hit": 0, "contradicted": 0, "unverifiable": 0,
           "objects": 0, "objects_recalled": 0}

    candidates, n = ndimage.label(prob > threshold)
    kept = np.zeros_like(debris)
    for cid in range(1, n + 1):
        comp = candidates == cid
        if comp.sum() < min_pixels:
            continue
        kept |= comp
        if (comp & debris).any():
            out["hit"] += 1
        elif (comp & labelled).any():
            out["contradicted"] += 1
        else:
            out["unverifiable"] += 1

    objects, m = ndimage.label(debris)
    out["objects"] = m
    sizes = np.bincount(objects.ravel())[1:]
    out["objects_under_min_pixels"] = int((sizes < min_pixels).sum())
    out["object_px"] = [int(s) for s in sizes]
    out["objects_recalled"] = sum(bool((objects == oid)[kept].any()) for oid in range(1, m + 1))

    pred = argmax == DEBRIS_CLASS
    out["px_tp"] = int((pred & debris).sum())
    out["px_fp"] = int((pred & labelled & ~debris).sum())
    out["px_fn"] = int((~pred & debris).sum())
    return out


def evaluate_run(run: dict, threshold: float, min_pixels: int, batch: int) -> dict:
    import torch

    checkpoint = ROOT / run["checkpoint"]
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    if digest != run["checkpoint_sha256"]:
        raise RuntimeError(f"Checkpoint hash changed since publication: {checkpoint}")
    detector = load_detector(checkpoint)
    if detector.meta.get("normalisation") != run["training_protocol"]["normalisation"]:
        raise RuntimeError(f"Normalisation differs from the published protocol: {checkpoint}")

    holdout = frozenset(run["holdout_tiles"])
    pooled = [i for s in ("train", "val", "test") for i in split_ids(s)]
    data = MaridaPatches("pooled", ids=pooled, only_tiles=holdout,
                         normalisation=detector.meta.get("normalisation"))

    totals: dict[str, int] = {}
    scores, truths = [], []
    detector.model.eval()
    with torch.inference_mode():
        for start in range(0, len(data), batch):
            pairs = [data[i] for i in range(start, min(start + batch, len(data)))]
            x = torch.from_numpy(np.stack([p[0] for p in pairs])).to(detector.device)
            logits = detector.model(x)
            probs = torch.softmax(logits, 1)[:, DEBRIS_CLASS].float().cpu().numpy()
            argmax = logits.argmax(1).cpu().numpy()
            for k, (_, mask) in enumerate(pairs):
                for key, v in score_patch(probs[k], argmax[k], mask,
                                          threshold, min_pixels).items():
                    totals[key] = totals.get(key, [] if key == "object_px" else 0) + v
                labelled = mask > 0
                scores.append(probs[k][labelled])
                truths.append(mask[labelled] == DEBRIS_CLASS)

    y_score, y_true = np.concatenate(scores), np.concatenate(truths)
    tp, fp, fn = totals["px_tp"], totals["px_fp"], totals["px_fn"]
    published = run["holdout"]["per_class"]["Marine Debris"]
    reproduced = (tp, fp, fn) == (published["tp"], published["fp"], published["fn"])
    if not reproduced:
        raise RuntimeError(
            f"{checkpoint.name}: argmax pixel counts {(tp, fp, fn)} do not reproduce the "
            f"published {(published['tp'], published['fp'], published['fn'])}; aborting."
        )

    hit, con, unv = totals["hit"], totals["contradicted"], totals["unverifiable"]
    return {
        "checkpoint": run["checkpoint"],
        "checkpoint_sha256": digest,
        "holdout_tiles": run["holdout_tiles"],
        "seed": run["training_protocol"]["seed"],
        "patches": len(data),
        "published_pixel_counts_reproduced": reproduced,
        "pixel": {
            "labelled_pixels": int(y_true.size),
            "debris_pixels": int(y_true.sum()),
            "debris_prevalence": round(float(y_true.mean()), 6),
            "pr_auc": round(float(average_precision_score(y_true, y_score)), 4),
            "argmax_tp": tp, "argmax_fp": fp, "argmax_fn": fn,
        },
        "candidates": {
            "rule": {"prob_threshold": threshold, "min_pixels": min_pixels,
                     "connectivity": 4},
            "total": hit + con + unv,
            "hit": hit, "contradicted": con, "unverifiable": unv,
            "precision_lower_bound": round(hit / (hit + con + unv), 4) if hit + con + unv else None,
            "precision_upper_bound": round(hit / (hit + con), 4) if hit + con else None,
            "labelled_debris_objects": totals["objects"],
            # MARIDA debris labels are sparse pixel annotations, not object
            # outlines: these fragments are not physical objects.
            "label_fragments_under_min_pixels": totals["objects_under_min_pixels"],
            "label_fragment_median_px": float(np.median(totals["object_px"]))
            if totals["object_px"] else None,
            "objects_recalled": totals["objects_recalled"],
            "object_recall": round(totals["objects_recalled"] / totals["objects"], 4)
            if totals["objects"] else None,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", type=Path, required=True)
    ap.add_argument("--batch-size", type=int, default=8)
    args = ap.parse_args()

    reference = json.loads(REFERENCE.read_text("utf-8"))
    threshold, min_pixels = DEFAULT_PROB_THRESHOLD, DEFAULT_MIN_PIXELS
    tiles = {}
    for tile, block in reference["tiles"].items():
        runs = []
        for run in block["runs"]:
            print(f"{tile} seed {run['training_protocol']['seed']} ...", flush=True)
            row = evaluate_run(run, threshold, min_pixels, args.batch_size)
            c = row["candidates"]
            print(f"  PR-AUC {row['pixel']['pr_auc']}  candidates {c['total']} "
                  f"(hit {c['hit']}, contradicted {c['contradicted']}, "
                  f"unverifiable {c['unverifiable']})  objects {c['objects_recalled']}/"
                  f"{c['labelled_debris_objects']}", flush=True)
            runs.append(row)
        auc = [r["pixel"]["pr_auc"] for r in runs]
        rec = [r["candidates"]["object_recall"] for r in runs
               if r["candidates"]["object_recall"] is not None]
        tiles[tile] = {"runs": runs, "summary": {
            "pr_auc_mean": round(float(np.mean(auc)), 4),
            "pr_auc_min": min(auc), "pr_auc_max": max(auc),
            "object_recall_mean": round(float(np.mean(rec)), 4) if rec else None,
            "debris_prevalence": runs[0]["pixel"]["debris_prevalence"],
        }}

    out = {
        "protocol": "strict-holdout-candidates-v1",
        "reference": "eval/geographic_validation.json",
        "reference_sha256": text_evidence_sha256(REFERENCE),
        "reference_hash_method": TEXT_HASH_METHOD,
        "tiles": tiles,
        "caveats": [
            "Same six checkpoints and unseen tiles as geographic_validation.json; no retraining.",
            "PR-AUC is over labelled pixels only; compare it with debris_prevalence (the "
            "no-skill baseline), not with 0.5.",
            "Unverifiable candidates touch only unlabelled pixels; MARIDA sparsity means "
            "they are neither confirmed nor false. Precision is reported as a bound.",
            "Candidate rule is the production one (p>0.40, 4-connected, >=3 px) but on "
            "MARIDA patches, without cloud masks or verification; not export accuracy.",
            "Labelled debris 'objects' are 4-connected fragments of sparse pixel "
            "annotations (see label_fragment_median_px), not physical objects; object "
            "recall counts annotation fragments touched, not debris items found.",
            "Very low support (48PZC: 8 positive patches); three seeds measure training "
            "variability, not label uncertainty. Candidates are not confirmed nets.",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
