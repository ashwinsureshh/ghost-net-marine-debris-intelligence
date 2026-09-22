"""Run the frozen two-tile, three-seed study sequentially on the workstation.

Checkpoints and intermediate outputs stay local. Existing completed jobs are
validated before reuse; partial checkpoints are never silently overwritten.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "tmp" / "geographic_jobs"
TILES = ("16PDC", "48PZC")
SEEDS = (20260825, 20260826, 20260827)


def validate_report(report: Path, checkpoint: Path, tile: str, seed: int, prior_hash: str):
    result = json.loads(report.read_text("utf-8"))
    protocol = result["training_protocol"]
    if (protocol["seed"] != seed or protocol["epochs"] != 60
            or protocol["holdout_tiles"] != [tile]
            or protocol["training_prior"]["mode"] != "train-split"
            or protocol["training_prior"]["training_ids_sha256"] != prior_hash
            or protocol["hyperparameters"] != {"batch_size": 8, "lr": 3e-4, "width": 32}
            or result["checkpoint_sha256"] != hashlib.sha256(checkpoint.read_bytes()).hexdigest()):
        raise ValueError(f"Completed job provenance mismatch: {report}")
    return result


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    audit = json.loads((ROOT / "eval/geographic_split_audit.json").read_text("utf-8"))
    status = {"started_at": datetime.now(UTC).isoformat(), "jobs": []}

    def save():
        target = WORK / "status.json"
        pending = target.with_suffix('.pending')
        pending.write_text(json.dumps(status, indent=2), encoding="utf-8")
        pending.replace(target)

    for tile in TILES:
        support = audit["tiles"][tile]
        if not support["debris_pixels"] or not support["retained_val_debris_pixels"]:
            raise ValueError(f"Missing evaluation/model-selection debris support: {tile}")
        prior_hash = support["training_prior"]["training_ids_sha256"]
        for seed in SEEDS:
            name = f"geo_strict_{tile}_{seed}"
            checkpoint = ROOT / "models" / f"{name}.pt"
            report = WORK / f"{name}.json"
            row = {"tile": tile, "seed": seed, "state": "starting"}
            status["jobs"].append(row)
            save()
            if report.exists():
                validate_report(report, checkpoint, tile, seed, prior_hash)
                row["state"] = "reused"
                save()
                continue
            if checkpoint.exists():
                sidecar = checkpoint.with_suffix(".json")
                meta = json.loads(sidecar.read_text("utf-8")) if sidecar.exists() else {}
                if (meta.get("epochs") != 60 or meta.get("seed") != seed
                        or meta.get("holdout_tiles") != [tile]
                        or meta.get("training_prior", {}).get("mode") != "train-split"
                        or meta.get("training_prior", {}).get("training_ids_sha256") != prior_hash
                        or meta.get("hyperparameters")
                        != {"batch_size": 8, "lr": 3e-4, "width": 32}
                        or meta.get("checkpoint_sha256")
                        != hashlib.sha256(checkpoint.read_bytes()).hexdigest()):
                    raise RuntimeError(f"Partial checkpoint; inspect before reuse: {checkpoint}")
            common = [sys.executable, "-u", "scripts/train_cnn.py", "--holdout-tile", tile,
                      "--seed", str(seed), "--epochs", "60", "--class-weighting", "train-split",
                      "--out", str(checkpoint), "--run-id", name]
            stages = (("training", []), ("evaluation", ["--eval-only", "--json", str(report)]))
            for stage, extra in stages:
                if stage == "training" and checkpoint.exists():
                    continue  # completed training verified above; retry evaluation only
                row["state"] = stage
                save()
                print(f"{name}: {stage}", flush=True)
                with (WORK / f"{name}-{stage}.log").open("w", encoding="utf-8") as log:
                    result = subprocess.run(common + extra, cwd=ROOT, stdout=log,
                                            stderr=subprocess.STDOUT)
                if result.returncode:
                    row.update(state="failed", exit_code=result.returncode)
                    save()
                    return result.returncode
            validate_report(report, checkpoint, tile, seed, prior_hash)
            row["state"] = "complete"
            save()
    status["completed_at"] = datetime.now(UTC).isoformat()
    save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
