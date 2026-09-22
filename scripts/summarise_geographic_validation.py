"""Consolidate six completed strict holdouts; never summarize partial jobs as final."""

import argparse
import json
import statistics
from pathlib import Path

from ghostnet.evidence_hash import TEXT_HASH_METHOD, text_evidence_sha256
from run_geographic_validation import ROOT, SEEDS, TILES, WORK, validate_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", required=True, type=Path)
    args = parser.parse_args()
    audit_path = ROOT / "eval/geographic_split_audit.json"
    audit = json.loads(audit_path.read_text("utf-8"))
    groups = {}
    for tile in TILES:
        support = audit["tiles"][tile]
        runs = []
        for seed in SEEDS:
            name = f"geo_strict_v2_{tile}_{seed}"
            checkpoint = ROOT / "models" / f"{name}.pt"
            result = validate_report(WORK / f"{name}.json", checkpoint, tile, seed,
                                     support["training_prior"]["training_ids_sha256"],
                                     support["normalisation"])
            if (result["holdout"]["patches"] != support["heldout_patches"]
                    or result["holdout"]["per_class"]["Marine Debris"]["support"]
                    != support["debris_pixels"]):
                raise ValueError(f"Evaluation population differs from frozen audit: {name}")
            result["checkpoint"] = f"models/{name}.pt"
            sidecar = json.loads(checkpoint.with_suffix(".json").read_text("utf-8"))
            result["best_validation_debris_f1"] = sidecar["best_val_debris_f1"]
            result["training_minutes"] = sidecar["minutes"]
            runs.append(result)
        summary = {}
        for metric in ("debris_precision", "debris_recall", "debris_f1"):
            values = [r["holdout"][metric] for r in runs]
            summary[metric] = {
                "mean": round(statistics.fmean(values), 4),
                "sample_std": round(statistics.stdev(values), 4),
                "min": min(values), "max": max(values),
            }
        groups[tile] = {"summary": summary, "runs": runs}
    output = {
        "protocol": "strict-training-only-v2", "seeds": list(SEEDS),
        "audit_sha256": text_evidence_sha256(audit_path),
        "audit_hash_method": TEXT_HASH_METHOD,
        "tiles": groups,
        "caveats": [
            "Pixel metrics on sparse labelled MARIDA masks; unlabelled pixels excluded.",
            "Tile held out of training, validation, class priors and normalization.",
            "Three seeds measure training variability, not independent label uncertainty.",
            "16PDC: 143 debris pixels in 37 positive patches; 48PZC: 24 in 8. Low support.",
            "MGRS-tile independence is not proof of independence from neighbouring geography.",
            "Remaining-test metrics mix trained and unseen tiles; do not subtract as a causal gap.",
            "Training sizes, priors and normalization differ; no isolated causal effect claimed.",
            "Served checkpoints unchanged; not confirmed nets or local export accuracy.",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(output, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
