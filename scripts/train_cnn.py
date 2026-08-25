"""FR-1.4 — train the CNN detector variant on MARIDA.

    python scripts/train_cnn.py                    # full run
    python scripts/train_cnn.py --epochs 2 --limit 24   # smoke test
    python scripts/train_cnn.py --eval-only        # score an existing checkpoint

WORKSTATION ONLY. This needs the CUDA GPU and the ~5.5 GB MARIDA benchmark;
MACHINE-WORKFLOW.md assigns both to the workstation. It refuses to run a full
training job on CPU rather than appearing to work and taking a day.

Writes ``models/detector_v1.pt`` (weights, never committed) plus a metadata
sidecar. The measured numbers belong in ``eval/results.md``.

The two traps this script exists to avoid
-----------------------------------------
1. **Class 0 is unlabelled, not background** — 99.06% of MARIDA's pixels. The
   loss uses ``ignore_index=0``. Training it as a real class produces a model
   that predicts "nothing" everywhere and a loss curve that looks healthy.
2. **Marine Debris is 1943 pixels in the whole train split**, 0.45% of labelled
   ones. Unweighted cross-entropy collapses to the majority class, so classes
   are weighted by inverse square-root frequency.

Model selection is on **val debris F1**, not on loss and never on accuracy —
accuracy is meaningless at this class balance.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import rasterio

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from eval_marida import MaridaMissingError, _paths_for, split_ids  # noqa: E402
from ghostnet.agents.detection_cnn import (  # noqa: E402
    CLASS_NAMES,
    CLASS_WEIGHTS,
    DEBRIS_CLASS,
    MARIDA_BANDS,
    NUM_CLASSES,
    build_unet,
    normalise,
)

MODELS_DIR = REPO_ROOT / "models"
DEFAULT_OUT = MODELS_DIR / "detector_v1.pt"


def git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return None


class MaridaPatches:
    """MARIDA split as (11, 256, 256) float32 stacks plus int64 class masks."""

    def __init__(
        self,
        split: str,
        *,
        limit: int | None = None,
        augment: bool = False,
        cache: bool = True,
    ):
        self.ids = split_ids(split)[:limit]
        self.augment = augment
        self.split = split
        # ~2.9 MB per patch, so the whole benchmark is ~3 GB of RAM. Disk
        # reads otherwise dominate every epoch and the GPU sits idle.
        self._cache: dict[int, tuple] = {}
        self.cache = cache

    def __len__(self) -> int:
        return len(self.ids)

    def _read(self, index: int):
        if index in self._cache:
            return self._cache[index]
        pid = self.ids[index]
        img_path, mask_path = _paths_for(pid)
        with rasterio.open(img_path) as src:
            stack = src.read().astype("float32")
        with rasterio.open(mask_path) as src:
            # float32 on disk — cast, or class ids misbehave as indices.
            mask = src.read(1).astype("int64")
        stack = np.nan_to_num(stack, nan=0.0, posinf=0.0, neginf=0.0)
        stack = normalise(stack)
        if self.cache:
            self._cache[index] = (stack, mask)
        return stack, mask

    def __getitem__(self, index: int):
        stack, mask = self._read(index)

        if self.augment:
            # D4 symmetries only. No photometric jitter: these are physical
            # reflectances and shifting them would break the spectral
            # relationships the whole method depends on.
            k = np.random.randint(4)
            if k:
                stack = np.rot90(stack, k, axes=(1, 2))
                mask = np.rot90(mask, k)
            if np.random.rand() < 0.5:
                stack = stack[:, :, ::-1]
                mask = mask[:, ::-1]
            stack = np.ascontiguousarray(stack)
            mask = np.ascontiguousarray(mask)

        return stack, mask


def batches(dataset: MaridaPatches, batch_size: int, *, shuffle: bool):
    order = np.random.permutation(len(dataset)) if shuffle else np.arange(len(dataset))
    for start in range(0, len(order), batch_size):
        idx = order[start : start + batch_size]
        pairs = [dataset[int(i)] for i in idx]
        yield (
            np.stack([p[0] for p in pairs]),
            np.stack([p[1] for p in pairs]),
        )


def evaluate(model, dataset: MaridaPatches, device: str, batch_size: int) -> dict:
    """Per-class counts over *labelled* pixels only."""
    import torch

    model.eval()
    tp = np.zeros(NUM_CLASSES, dtype=np.int64)
    fp = np.zeros(NUM_CLASSES, dtype=np.int64)
    fn = np.zeros(NUM_CLASSES, dtype=np.int64)

    with torch.inference_mode():
        for stacks, masks in batches(dataset, batch_size, shuffle=False):
            x = torch.from_numpy(stacks).to(device)
            y = torch.from_numpy(masks).to(device)
            pred = model(x).argmax(1)
            valid = y > 0  # class 0 is unlabelled and is not ground truth
            for cls in range(1, NUM_CLASSES):
                p = (pred == cls) & valid
                t = y == cls
                tp[cls] += int((p & t).sum())
                fp[cls] += int((p & ~t).sum())
                fn[cls] += int((~p & t).sum())

    def prf(cls: int) -> tuple[float, float, float]:
        precision = tp[cls] / (tp[cls] + fp[cls]) if tp[cls] + fp[cls] else 0.0
        recall = tp[cls] / (tp[cls] + fn[cls]) if tp[cls] + fn[cls] else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return float(precision), float(recall), float(f1)

    per_class = {
        CLASS_NAMES[c]: dict(
            zip(("precision", "recall", "f1"), [round(v, 4) for v in prf(c)], strict=True)
        )
        | {"support": int(tp[c] + fn[c])}
        for c in range(1, NUM_CLASSES)
    }
    d_p, d_r, d_f1 = prf(DEBRIS_CLASS)
    macro = float(np.mean([prf(c)[2] for c in range(1, NUM_CLASSES) if tp[c] + fn[c] > 0]))
    return {
        "debris_precision": round(d_p, 4),
        "debris_recall": round(d_r, 4),
        "debris_f1": round(d_f1, 4),
        "macro_f1": round(macro, 4),
        "per_class": per_class,
    }


def train(args) -> int:
    import torch
    import torch.nn as nn

    if not torch.cuda.is_available() and not args.allow_cpu:
        print(
            "ERROR: no CUDA device. MACHINE-WORKFLOW.md assigns CNN training to the\n"
            "workstation; on the Air this would take a day and probably fail. Run\n"
            "`python scripts/check_machine.py` to confirm which machine this is, or\n"
            "pass --allow-cpu if you really mean it (e.g. a 2-epoch smoke test).",
            file=sys.stderr,
        )
        return 2

    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    train_set = MaridaPatches("train", limit=args.limit, augment=True)
    val_set = MaridaPatches("val", limit=args.limit)
    print(f"device {device} | train {len(train_set)} patches | val {len(val_set)}")

    model = build_unet(in_channels=len(MARIDA_BANDS), num_classes=NUM_CLASSES,
                       width=args.width).to(device)
    params = sum(p.numel() for p in model.parameters())
    print(f"U-Net width {args.width}: {params/1e6:.2f} M parameters")

    weights = torch.tensor([0.0, *CLASS_WEIGHTS], dtype=torch.float32, device=device)
    criterion = nn.CrossEntropyLoss(weight=weights, ignore_index=0)
    optimiser = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, T_max=args.epochs)
    autocast_dtype = torch.bfloat16 if device == "cuda" else torch.float32

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    best_f1 = -1.0
    history = []
    started = time.time()

    for epoch in range(1, args.epochs + 1):
        model.train()
        total, seen = 0.0, 0
        for stacks, masks in batches(train_set, args.batch_size, shuffle=True):
            x = torch.from_numpy(stacks).to(device, non_blocking=True)
            y = torch.from_numpy(masks).to(device, non_blocking=True)
            optimiser.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device, dtype=autocast_dtype, enabled=device == "cuda"):
                loss = criterion(model(x), y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            total += float(loss.detach()) * len(stacks)
            seen += len(stacks)
        scheduler.step()

        metrics = evaluate(model, val_set, device, args.batch_size)
        history.append({"epoch": epoch, "loss": round(total / max(seen, 1), 4), **{
            k: v for k, v in metrics.items() if k != "per_class"}})
        marker = ""
        if metrics["debris_f1"] > best_f1:
            best_f1 = metrics["debris_f1"]
            marker = "  <- best"
            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "in_channels": len(MARIDA_BANDS),
                    "num_classes": NUM_CLASSES,
                    "width": args.width,
                    "meta": {
                        "run_id": args.run_id,
                        "epoch": epoch,
                        "val": metrics,
                        "git_commit": git_commit(),
                        "seed": args.seed,
                        "bands": list(MARIDA_BANDS),
                        "torch": torch.__version__,
                        "device": torch.cuda.get_device_name(0) if device == "cuda" else "cpu",
                    },
                },
                args.out,
            )
        print(
            f"epoch {epoch:3d}/{args.epochs}  loss {total/max(seen,1):.4f}  "
            f"val debris P={metrics['debris_precision']:.3f} R={metrics['debris_recall']:.3f} "
            f"F1={metrics['debris_f1']:.3f}  macroF1={metrics['macro_f1']:.3f}{marker}",
            flush=True,
        )

    elapsed = time.time() - started
    print(
        f"\ntrained {args.epochs} epochs in {elapsed/60:.1f} min; "
        f"best val debris F1 {best_f1:.4f}"
    )
    print(f"checkpoint: {args.out}")

    sidecar = Path(args.out).with_suffix(".json")
    sidecar.write_text(json.dumps({
        "run_id": args.run_id,
        "best_val_debris_f1": best_f1,
        "epochs": args.epochs,
        "history": history,
        "git_commit": git_commit(),
        "train_patches": len(train_set),
        "val_patches": len(val_set),
        "minutes": round(elapsed / 60, 2),
    }, indent=2))
    print(f"sidecar:    {sidecar}")
    return 0


def eval_only(args) -> int:
    from ghostnet.agents.detection_cnn import load_detector

    detector = load_detector(args.out)
    for split in ("val", "test"):
        dataset = MaridaPatches(split, limit=args.limit)
        metrics = evaluate(detector.model, dataset, detector.device, args.batch_size)
        print(f"\n{split}: debris P={metrics['debris_precision']:.4f} "
              f"R={metrics['debris_recall']:.4f} F1={metrics['debris_f1']:.4f} "
              f"macroF1={metrics['macro_f1']:.4f}")
        for name, row in metrics["per_class"].items():
            if row["support"]:
                print(f"    {name:26s} P={row['precision']:.3f} R={row['recall']:.3f} "
                      f"F1={row['f1']:.3f}  n={row['support']}")
    if args.json:
        Path(args.json).write_text(json.dumps(metrics, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--seed", type=int, default=20260825)
    ap.add_argument("--limit", type=int, default=None, help="patches per split (smoke test)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--run-id", default="detector_v1")
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--allow-cpu", action="store_true")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    try:
        return eval_only(args) if args.eval_only else train(args)
    except MaridaMissingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
