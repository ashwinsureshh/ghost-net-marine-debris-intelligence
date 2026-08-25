"""FR-2.4 — measure the Verification Agent's contribution against MARIDA.

This is the PRD's headline ablation: detection precision/recall with and without
the False-Positive Verification Agent, benchmarked on a published labelled
dataset, plus the threshold calibration that has to happen before any of those
numbers can be reported.

    python scripts/eval_marida.py --fit                   # fit on train, report on test
    python scripts/eval_marida.py --split test            # evaluate with current defaults
    python scripts/eval_marida.py --split test --json out.json

WORKSTATION ONLY — needs data/marida (~5.5 GB). Run
`python scripts/fetch_data.py --instructions --dataset marida` if absent.

Method, and its limits — read before quoting any number from this
-----------------------------------------------------------------
* **Band order was verified physically, not assumed.** MARIDA patches carry no
  band descriptions. Dense Sargassum shows a textbook vegetation red edge
  (b4 0.042 -> b7 0.132) while water and Sargassum both collapse at b10/b11 and
  clouds stay bright there, which fixes the stack as
  B01 B02 B03 B04 B05 B06 B07 B08 B8A B11 B12.
* **Ground truth per detection** is the majority *labelled* class in the same
  5x5 window the verification agent samples. MARIDA is sparsely annotated:
  class 0 means "unlabelled", not "background", and is 99.1% of all pixels. A
  candidate whose window holds no labelled pixel has no ground truth and is
  excluded, never assumed negative. The excluded count is always reported.
* **Two different recalls are reported, and they mean different things.**
  ``recall`` in the precision/recall table is over *scored candidates* — of the
  labelled candidates the detector emitted, how many true-debris ones survive
  verification. It is 1.0 for the baseline by construction. ``region_recall``
  is the one that answers "did we find the debris at all": the fraction of
  annotated Marine Debris regions in the split that any detection lands on.
* **Only 3 of the 5 checks can fire here.** MARIDA patches carry no acquisition
  geometry and no repeat passes, so ``bright_swir_target`` can still disqualify
  on spectral grounds but cannot name sun glint as the specific cause, and
  ``multi_temporal`` is inconclusive throughout. This measures the spectral
  checks; the multi-temporal contribution (FR-2.2) needs real L2A scenes and is
  **not** evaluated here.
* **No cloud mask is supplied to the detector.** MARIDA's cloud labels are
  ground truth; feeding them in would leak the answer. The detector runs blind
  and the verifier's cloud check has to earn its keep.
* **Fit on train, report on test.** The detector threshold is fitted to maximise
  the *baseline's own* F1, so the ablation compares against a fairly-tuned
  baseline rather than a strawman. Verification thresholds are then fitted by
  coordinate descent with the detector held fixed.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from scipy import ndimage

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghostnet.agents import verification as V  # noqa: E402
from ghostnet.agents.detection import (  # noqa: E402
    DEFAULT_FDI_THRESHOLD,
    DEFAULT_MIN_PIXELS,
    GeoTransform,
    Tile,
    detect,
    sample_window,
)

MARIDA_ROOT = REPO_ROOT / "data" / "marida"
PATCHES = MARIDA_ROOT / "patches"
SPLITS = MARIDA_ROOT / "splits"

# Verified physically — see the module docstring.
BAND_INDEX = {"B04": 4, "B06": 6, "B08": 8, "B11": 10}

CLASS_NAMES = {
    1: "Marine Debris", 2: "Dense Sargassum", 3: "Sparse Sargassum",
    4: "Natural Organic Material", 5: "Ship", 6: "Clouds", 7: "Marine Water",
    8: "Sediment-Laden Water", 9: "Foam", 10: "Turbid Water",
    11: "Shallow Water", 12: "Waves", 13: "Cloud Shadows", 14: "Wakes",
    15: "Mixed Water",
}
DEBRIS_CLASS = 1

# Which check we expect to catch each MARIDA false-positive class. Reporting
# only — this never influences a decision.
EXPECTED_CHECK = {
    2: "kelp_sargassum", 3: "kelp_sargassum", 4: "kelp_sargassum",
    6: "bright_swir_target", 13: "cloud_shadow",
    9: "bright_water_surface", 12: "bright_water_surface",
    14: "bright_water_surface",
}


class MaridaMissingError(RuntimeError):
    pass


@dataclasses.dataclass
class Candidates:
    """Detector output for a split, cached so thresholds can be swept cheaply."""

    split: str
    fdi_threshold: float
    min_pixels: int
    detections: list
    windows: list
    truth: dict[str, int]           # detection id -> MARIDA class (labelled only)
    unlabelled: int
    patches: int
    debris_regions: int
    debris_regions_hit: int
    failed: list[str]

    @property
    def region_recall(self) -> float:
        if not self.debris_regions:
            return 0.0
        return self.debris_regions_hit / self.debris_regions


def _require_marida() -> None:
    if not PATCHES.is_dir() or not SPLITS.is_dir():
        raise MaridaMissingError(
            f"MARIDA not found at {MARIDA_ROOT}. This is workstation-only data; "
            "run: python scripts/fetch_data.py --instructions --dataset marida"
        )


def split_ids(split: str) -> list[str]:
    _require_marida()
    path = SPLITS / f"{split}_X.txt"
    if not path.exists():
        raise MaridaMissingError(f"No split file {path}")
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]


def _paths_for(pid: str) -> tuple[Path, Path]:
    """Split ids omit the S2_ prefix: '1-12-19_48MYU_0' -> the scene folder."""
    scene = "S2_" + pid.rsplit("_", 1)[0]
    stem = "S2_" + pid
    return PATCHES / scene / f"{stem}.tif", PATCHES / scene / f"{stem}_cl.tif"


def _acquired_at(pid: str) -> datetime:
    m = re.match(r"(\d{1,2})-(\d{1,2})-(\d{2})", pid)
    if not m:
        return datetime(2019, 1, 1)
    day, month, yy = (int(g) for g in m.groups())
    return datetime(2000 + yy, month, day)


def load_patch(pid: str) -> tuple[Tile, np.ndarray]:
    """Return the Tile the detector sees plus MARIDA's class mask."""
    img_path, mask_path = _paths_for(pid)
    if not img_path.exists():
        raise FileNotFoundError(img_path)

    with rasterio.open(img_path) as src:
        bands = {name: src.read(idx).astype("float64") for name, idx in BAND_INDEX.items()}
        crs, transform, height = src.crs, src.transform, src.height

    with rasterio.open(mask_path) as src:
        # Masks are float32 — cast, or class ids silently misbehave as indices.
        mask = src.read(1).astype("int16")

    # MARIDA is per-scene UTM; the Tile contract is a north-up lon/lat grid.
    to_wgs84 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    lon0, lat0 = to_wgs84.transform(transform.c, transform.f)
    _, lat_south = to_wgs84.transform(transform.c, transform.f + transform.e * height)
    lat_step = (lat_south - lat0) / height
    lon_step = abs(lat_step) / max(np.cos(np.radians(lat0)), 1e-6)

    tile = Tile(
        tile_id=pid,
        acquired_at=_acquired_at(pid),
        bands=bands,
        transform=GeoTransform(lon0, lat0, lon_step, lat_step),
        # No geometry and no cloud mask on purpose — see module docstring.
        source="marida",
    )
    return tile, mask


def truth_for(window_slice: np.ndarray) -> int | None:
    """Majority *labelled* class in a window; None when nothing is labelled."""
    labelled = window_slice[window_slice > 0]
    if labelled.size == 0:
        return None
    values, counts = np.unique(labelled, return_counts=True)
    return int(values[counts.argmax()])


def collect(
    split: str,
    *,
    fdi_threshold: float = DEFAULT_FDI_THRESHOLD,
    min_pixels: int = DEFAULT_MIN_PIXELS,
    limit: int | None = None,
    half_width: int = 2,
) -> Candidates:
    """Run the detector over a split once and cache what verification needs."""
    ids = split_ids(split)[:limit]
    detections, windows, failed = [], [], []
    truth: dict[str, int] = {}
    unlabelled = 0
    regions = regions_hit = 0

    for pid in ids:
        try:
            tile, mask = load_patch(pid)
        except (FileNotFoundError, ValueError) as exc:
            failed.append(f"{pid}: {exc}")
            continue

        dets = detect(tile, fdi_threshold=fdi_threshold, min_pixels=min_pixels)
        n_rows, n_cols = tile.shape

        # Region-level recall: connected components of annotated debris that
        # any detection centroid lands inside.
        debris_lbl, n_regions = ndimage.label(mask == DEBRIS_CLASS)
        regions += n_regions
        hit_regions: set[int] = set()

        for det in dets:
            col, row = tile.transform.to_pixel(det.lon, det.lat)
            r0, r1 = max(0, row - half_width), min(n_rows, row + half_width + 1)
            c0, c1 = max(0, col - half_width), min(n_cols, col + half_width + 1)
            if r0 >= r1 or c0 >= c1:
                continue

            if n_regions:
                touched = debris_lbl[r0:r1, c0:c1]
                hit_regions.update(int(v) for v in np.unique(touched) if v)

            detections.append(det)
            windows.append(sample_window(tile, det, half_width=half_width))

            cls = truth_for(mask[r0:r1, c0:c1])
            if cls is None:
                unlabelled += 1
            else:
                truth[det.id] = cls

        regions_hit += len(hit_regions)

    return Candidates(
        split=split,
        fdi_threshold=fdi_threshold,
        min_pixels=min_pixels,
        detections=detections,
        windows=windows,
        truth=truth,
        unlabelled=unlabelled,
        patches=len(ids),
        debris_regions=regions,
        debris_regions_hit=regions_hit,
        failed=failed,
    )


def score(cands: Candidates, thresholds: V.VerificationThresholds) -> dict:
    """Run verification over cached candidates and compute the FR-2.4 metrics."""
    results = [
        V.verify(det, window, thresholds=thresholds)
        for det, window in zip(cands.detections, cands.windows, strict=True)
    ]
    labels = {det_id: cls == DEBRIS_CLASS for det_id, cls in cands.truth.items()}
    metrics = V.precision_recall_delta(cands.detections, results, labels)

    by_result = {r.detection_id: r for r in results}
    per_class: dict[int, dict] = defaultdict(
        lambda: {"n": 0, "rejected": 0, "by_check": Counter()}
    )
    for det_id, cls in cands.truth.items():
        entry = per_class[cls]
        entry["n"] += 1
        result = by_result[det_id]
        if not result.verified:
            entry["rejected"] += 1
            for check in result.checks:
                if check.disqualified:
                    entry["by_check"][check.name] += 1

    per_mode = {}
    for cls, entry in sorted(per_class.items()):
        per_mode[CLASS_NAMES.get(cls, str(cls))] = {
            "class_id": cls,
            "candidates": entry["n"],
            "rejected": entry["rejected"],
            "rejection_rate": round(entry["rejected"] / entry["n"], 4) if entry["n"] else 0.0,
            "by_check": dict(entry["by_check"]),
            "expected_check": EXPECTED_CHECK.get(cls),
        }

    return {
        "split": cands.split,
        "patches": cands.patches,
        "fdi_threshold": cands.fdi_threshold,
        "min_pixels": cands.min_pixels,
        "detections_total": len(cands.detections),
        "detections_unlabelled_excluded": cands.unlabelled,
        "debris_regions": cands.debris_regions,
        "debris_regions_hit": cands.debris_regions_hit,
        "region_recall": round(cands.region_recall, 4),
        "metrics": metrics,
        "per_failure_mode": per_mode,
        "patches_failed": cands.failed,
    }


# --- fitting ---------------------------------------------------------------

FDI_GRID = [0.006, 0.010, 0.015, 0.020, 0.025, 0.030, 0.035, 0.040, 0.050, 0.060]

# Coordinate-descent grids. Ranges bracket the class-conditional distributions
# measured on train; see eval/results.md for those.
VERIFY_GRID: dict[str, list[float]] = {
    "shadow_brightness_max": [0.0, 0.004, 0.006, 0.008, 0.010, 0.015],
    "glint_swir_min": [0.020, 0.025, 0.030, 0.035, 0.040, 0.045, 0.050],
    "glint_flatness_max": [0.12, 0.15, 0.18, 0.20, 0.22, 0.25],
    "foam_red_min": [0.035, 0.040, 0.045, 0.050, 0.060, 0.120],
    "foam_ndvi_max": [-0.10, -0.05, 0.0, 0.05, 0.10],
    "kelp_ndvi_min": [0.05, 0.10, 0.15, 0.20, 0.25],
    "kelp_ndvi_fdi_ratio": [1.0, 2.0, 4.0, 8.0, 12.0, 20.0],
}


def fit_fdi(split: str, *, min_pixels: int, limit: int | None) -> tuple[float, list[dict]]:
    """Pick the detector threshold that maximises the BASELINE's own F1.

    Tuning the baseline to its best is deliberate: the ablation has to compare
    against a fairly-tuned detector, not a strawman that makes verification look
    good for free.
    """
    rows = []
    for value in FDI_GRID:
        cands = collect(split, fdi_threshold=value, min_pixels=min_pixels, limit=limit)
        out = score(cands, V.LITERATURE_THRESHOLDS)
        m = out["metrics"]
        rows.append(
            {
                "fdi_threshold": value,
                "n_labelled": m["n_labelled"],
                "baseline_precision": m["baseline_precision"],
                "baseline_f1": m["baseline_f1"],
                "region_recall": out["region_recall"],
            }
        )
        print(
            f"  fdi>{value:<7.4f} scored={m['n_labelled']:<6.0f} "
            f"baseline P={m['baseline_precision']:.3f} F1={m['baseline_f1']:.3f} "
            f"region_recall={out['region_recall']:.3f}",
            flush=True,
        )
    best = max(rows, key=lambda r: r["baseline_f1"])
    return best["fdi_threshold"], rows


def fit_verification(
    cands: Candidates, *, passes: int = 2
) -> tuple[V.VerificationThresholds, list[dict]]:
    """Coordinate descent over the check thresholds, maximising verified F1."""
    current = V.LITERATURE_THRESHOLDS
    trace = []
    best_f1 = score(cands, current)["metrics"]["verified_f1"]
    print(f"  start verified_f1={best_f1:.4f}")

    for p in range(passes):
        for name, grid in VERIFY_GRID.items():
            best_value = getattr(current, name)
            for value in grid:
                trial = dataclasses.replace(current, **{name: value})
                f1 = score(cands, trial)["metrics"]["verified_f1"]
                if f1 > best_f1 + 1e-9:
                    best_f1, best_value = f1, value
            if best_value != getattr(current, name):
                print(
                    f"  pass {p + 1}: {name} {getattr(current, name)} -> "
                    f"{best_value}  (verified_f1={best_f1:.4f})",
                    flush=True,
                )
                current = dataclasses.replace(current, **{name: best_value})
            trace.append({"pass": p + 1, "param": name, "value": getattr(current, name),
                          "verified_f1": round(best_f1, 4)})
    return current, trace


def _print_report(out: dict, *, title: str) -> None:
    m = out["metrics"]
    print(f"\n{title}")
    print(f"MARIDA {out['split']} split — {out['patches']} patches, "
          f"FDI>{out['fdi_threshold']}, min_pixels {out['min_pixels']}")
    print(
        f"{out['detections_total']} detections, "
        f"{out['detections_unlabelled_excluded']} excluded (no labelled pixel), "
        f"{m['n_labelled']:.0f} scored"
    )
    print("\n                       precision     recall         F1")
    print(f"  baseline detector    {m['baseline_precision']:9.4f} {m['baseline_recall']:10.4f} "
          f"{m['baseline_f1']:10.4f}")
    print(f"  + verification       {m['verified_precision']:9.4f} {m['verified_recall']:10.4f} "
          f"{m['verified_f1']:10.4f}")
    print(f"  delta                {m['precision_delta']:+9.4f} {m['recall_delta']:+10.4f} "
          f"{m['verified_f1'] - m['baseline_f1']:+10.4f}")
    print(f"\n  false-positive rate drop : {m['false_positive_rate_drop']:+.4f}")
    print(f"  debris region recall     : {out['region_recall']:.4f} "
          f"({out['debris_regions_hit']}/{out['debris_regions']} annotated regions)")

    print("\nPer failure mode (MARIDA truth class -> rejection by the agent):")
    print(f"  {'class':26s} {'cand':>5s} {'rej':>5s} {'rate':>7s}  checks that fired")
    for name, row in sorted(
        out["per_failure_mode"].items(), key=lambda kv: -kv[1]["candidates"]
    ):
        checks = ", ".join(f"{k}:{v}" for k, v in sorted(row["by_check"].items())) or "-"
        print(f"  {name:26s} {row['candidates']:5d} {row['rejected']:5d} "
              f"{row['rejection_rate']:7.1%}  {checks}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="test", choices=["train", "val", "test"])
    parser.add_argument("--fdi-threshold", type=float, default=DEFAULT_FDI_THRESHOLD)
    parser.add_argument("--min-pixels", type=int, default=DEFAULT_MIN_PIXELS)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--fit", action="store_true",
                        help="fit on train, then report on --split (default test)")
    parser.add_argument("--json", type=Path, help="write full results as JSON")
    args = parser.parse_args()

    try:
        if args.fit:
            print("STEP 1 — fit the detector threshold on TRAIN (maximise baseline F1):")
            fdi, fdi_rows = fit_fdi("train", min_pixels=args.min_pixels, limit=args.limit)
            print(f"  chosen FDI threshold: {fdi}")

            print("\nSTEP 2 — fit verification thresholds on TRAIN (coordinate descent):")
            train = collect("train", fdi_threshold=fdi, min_pixels=args.min_pixels,
                            limit=args.limit)
            fitted, trace = fit_verification(train)

            print("\nSTEP 3 — report on the held-out split:")
            held = collect(args.split, fdi_threshold=fdi, min_pixels=args.min_pixels,
                           limit=args.limit)
            before = score(held, V.LITERATURE_THRESHOLDS)
            after = score(held, fitted)
            _print_report(before, title="=== UNFITTED thresholds (literature defaults) ===")
            _print_report(after, title="=== FITTED thresholds (calibrated on train) ===")

            print("\nFitted thresholds:")
            for f in dataclasses.fields(fitted):
                d, a = getattr(V.LITERATURE_THRESHOLDS, f.name), getattr(fitted, f.name)
                flag = "  <-- changed" if d != a else ""
                print(f"  {f.name:28s} {d!s:>8} -> {a!s:>8}{flag}")

            out = {
                "fitted_fdi_threshold": fdi,
                "fdi_sweep": fdi_rows,
                "fitted_thresholds": dataclasses.asdict(fitted),
                "fit_trace": trace,
                "held_out_unfitted": before,
                "held_out_fitted": after,
            }
        else:
            cands = collect(args.split, fdi_threshold=args.fdi_threshold,
                            min_pixels=args.min_pixels, limit=args.limit)
            out = score(cands, V.DEFAULT_THRESHOLDS)
            _print_report(out, title="=== current defaults ===")
    except MaridaMissingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        args.json.write_text(json.dumps(out, indent=2, default=str))
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
