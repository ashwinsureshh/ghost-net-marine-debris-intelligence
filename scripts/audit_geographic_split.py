"""Audit label support before geographic training; no inference or threshold tuning."""

import argparse
import hashlib
import json
from pathlib import Path

from train_cnn import filter_by_tile, label_counts, split_ids, training_prior


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    splits = {s: split_ids(s) for s in ("train", "val", "test")}
    pooled = [i for ids in splits.values() for i in ids]
    if len(set(pooled)) != len(pooled):
        raise ValueError("Published splits overlap")
    out = {"tiles": {}, "split_sha256": {
        s: hashlib.sha256("\n".join(ids).encode()).hexdigest() for s, ids in splits.items()}}
    for tile in ("16PDC", "48PZC"):
        holdout = frozenset({tile})
        ids = filter_by_tile(pooled, keep_only=holdout)
        retained = {s: filter_by_tile(splits[s], exclude=holdout) for s in ("train", "val")}
        counts = label_counts(ids)
        positive_ids = [pid for pid in ids if label_counts([pid])[1] > 0]
        out["tiles"][tile] = {
            "heldout_patches": len(ids), "heldout_ids": ids,
            "label_counts": counts.tolist(), "labelled_pixels": int(counts[1:].sum()),
            "debris_pixels": int(counts[1]), "unlabelled_pixels": int(counts[0]),
            "debris_positive_patch_ids": positive_ids,
            "debris_positive_patches": len(positive_ids),
            "retained_train_patches": len(retained["train"]),
            "retained_val_patches": len(retained["val"]),
            "training_prior": training_prior(retained["train"], "train-split"),
            "retained_val_debris_pixels": int(label_counts(retained["val"])[1]),
        }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
