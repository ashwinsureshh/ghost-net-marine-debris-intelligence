"""Fit and record per-holdout input normalization before GPU training."""

import json
from pathlib import Path

from train_cnn import filter_by_tile, fit_normalisation, split_ids

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT / "eval/geographic_split_audit.json"
    audit = json.loads(path.read_text("utf-8"))
    for tile, row in audit["tiles"].items():
        retained = filter_by_tile(split_ids("train"), exclude=frozenset({tile}))
        statistics = fit_normalisation(retained)
        if statistics["training_ids_sha256"] != row["training_prior"]["training_ids_sha256"]:
            raise ValueError("Training population changed since mask audit")
        row["normalisation"] = statistics
        target = ROOT / "tmp/geographic_jobs" / f"normalisation_{tile}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(statistics, indent=2), encoding="utf-8")
        print(f"Fitted retained-training normalization for {tile}", flush=True)
    path.write_text(json.dumps(audit, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
