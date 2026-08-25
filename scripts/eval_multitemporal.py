"""FR-2.2 — measure the multi-temporal consistency check against MARIDA.

The verification agent's other four checks were calibrated and measured in
``scripts/eval_marida.py``. Multi-temporal consistency could not be: MARIDA
patches carry no repeat pass, so the check reported itself inconclusive
throughout and its contribution stayed unmeasured. This script closes that gap.

    python scripts/eval_multitemporal.py                 # default labelled pair
    python scripts/eval_multitemporal.py --list-pairs    # what else is available
    python scripts/eval_multitemporal.py --json out.json

WORKSTATION ONLY — needs data/marida for labels and bandwidth for two L2A reads.

Why this needs the L2A reader rather than MARIDA alone
------------------------------------------------------
MARIDA crops a *different* set of 256x256 patches for every scene, so two dates
over the same MGRS tile share no patch footprint — there is nothing to compare
pixel to pixel. Verified rather than assumed: across all 19 dates on 16PCC, no
two dates share a single identical patch footprint.

So the imagery comes from :mod:`ghostnet.ingest`, which warps every acquisition
onto one fixed lon/lat grid, making pixel (r, c) the same ground position on
both dates by construction. MARIDA's class masks are then rasterised onto that
same grid to supply ground truth. The evaluation AOI is the box where *both*
dates carry annotations.

How a repeat observation is constructed, and why it is not circular
-------------------------------------------------------------------
For each candidate on date A, the nearest candidate on date B within
``--search-km`` is reported as a ``RepeatObservation`` at its true position. The
check then decides for itself whether that displacement is coherent. It is
deliberately *not* pre-filtered to the check's own tolerance — doing so would
only ever hand it observations it must accept, and it would pass everything by
construction.

With no current field loaded (OSCAR is not downloaded) ``current_speed_ms`` is
None, so the check allows only its 5 km base tolerance. That makes this a
conservative test: a real current field would widen the envelope and reject
less.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghostnet.agents import verification as V  # noqa: E402
from ghostnet.agents.detection import detect, sample_window  # noqa: E402
from ghostnet.geo import haversine_km  # noqa: E402
from ghostnet.ingest import build_grid, item_to_tile, search_l2a  # noqa: E402

MARIDA_PATCHES = REPO_ROOT / "data" / "marida" / "patches"
DEBRIS_CLASS = 1

# Chosen from the MARIDA annotations: the labelled same-tile repeat pair with
# the most debris on both dates and a large annotation overlap. See --list-pairs.
DEFAULT_PAIR = {
    "tile": "16PCC",
    "date_a": "2020-09-18",
    "date_b": "2020-09-23",
    "bbox": [-88.631, 15.723, -88.050, 15.897],
}


class EvalError(RuntimeError):
    pass


def _marida_scene_dir(tile: str, date: dt.date) -> Path:
    """MARIDA folders are S2_<D-M-YY>_<tile>, with no zero padding."""
    return MARIDA_PATCHES / f"S2_{date.day}-{date.month}-{date.year % 100}_{tile}"


def marida_label_raster(tile: str, date: dt.date, grid) -> np.ndarray:
    """Rasterise a date's MARIDA class masks onto the run grid.

    Zero means "no annotation here", which in MARIDA also means unlabelled. The
    two are indistinguishable and are treated alike: not ground truth.
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT

    scene = _marida_scene_dir(tile, date)
    if not scene.is_dir():
        raise EvalError(
            f"No MARIDA scene at {scene}. This is workstation-only data; run "
            "python scripts/fetch_data.py --instructions --dataset marida"
        )

    out = np.zeros((grid.height, grid.width), dtype="int16")
    painted = 0
    for mask_path in sorted(scene.glob("*_cl.tif")):
        with rasterio.open(mask_path) as src, WarpedVRT(
            src,
            crs="EPSG:4326",
            transform=grid.transform,
            width=grid.width,
            height=grid.height,
            resampling=Resampling.nearest,
        ) as vrt:
            block = vrt.read(1).astype("int16")
        hit = block > 0
        if hit.any():
            out[hit] = block[hit]
            painted += 1
    if painted == 0:
        raise EvalError(f"No MARIDA annotation from {scene.name} lands in the AOI.")
    return out


def truth_for(window: np.ndarray) -> int | None:
    labelled = window[window > 0]
    if labelled.size == 0:
        return None
    values, counts = np.unique(labelled, return_counts=True)
    return int(values[counts.argmax()])


def tile_for_date(bbox, tile_id: str, date: dt.date, grid):
    """Stream the one L2A product for this MGRS tile and date."""
    items = search_l2a(
        tuple(bbox),
        (date - dt.timedelta(days=1)).isoformat(),
        (date + dt.timedelta(days=1)).isoformat(),
        max_cloud_cover_pct=100.0,
        mgrs_tiles=[tile_id],
    )
    exact = [i for i in items if i.datetime.date() == date]
    if not exact:
        raise EvalError(
            f"No Sentinel-2 L2A product for {tile_id} on {date}. MARIDA annotates "
            "it, so the product exists — the STAC query or the date is wrong."
        )
    # No AOI cloud screening here: this pair is chosen by its labels, so a
    # clouded scene must be reported as a weak result rather than silently
    # skipped the way a demo run would skip it.
    return item_to_tile(exact[0], grid, water_only=True)


def build_repeats(det, later_dets, later_tile, *, search_km: float):
    """Nearest candidate on the later pass, or an explicit non-observation."""
    best = None
    best_km = float("inf")
    for other in later_dets:
        km = haversine_km(det.lon, det.lat, other.lon, other.lat)
        if km < best_km:
            best_km, best = km, other

    if best is None or best_km > search_km:
        return [
            V.RepeatObservation(
                tile_id=later_tile.tile_id,
                acquired_at=later_tile.acquired_at,
                lon=None,
                lat=None,
                detected=False,
            )
        ], None

    return [
        V.RepeatObservation(
            tile_id=later_tile.tile_id,
            acquired_at=later_tile.acquired_at,
            lon=best.lon,
            lat=best.lat,
            detected=True,
        )
    ], best_km


def _pr(rows, key):
    tp = sum(1 for r in rows if r[key] and r["truth"] == DEBRIS_CLASS)
    fp = sum(1 for r in rows if r[key] and r["truth"] != DEBRIS_CLASS)
    fn = sum(1 for r in rows if not r[key] and r["truth"] == DEBRIS_CLASS)
    p = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * rec / (p + rec) if p + rec else 0.0
    return {
        "precision": round(p, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def summarise(rows, pair, grid, tile_a, tile_b, dets_a, dets_b, search_km) -> dict:
    labelled = [r for r in rows if r["truth"] is not None]
    baseline_precision = (
        round(sum(1 for r in labelled if r["truth"] == DEBRIS_CLASS) / len(labelled), 4)
        if labelled
        else 0.0
    )
    transient = [r for r in rows if not r["reobserved"]]
    incoherent = [r for r in rows if r["reobserved"] and r["mt_disqualified"]]
    # What the check adds beyond the four spectral ones: candidates the spectral
    # checks passed that multi-temporal then rejects.
    marginal = [r for r in rows if r["verified_without"] and not r["verified_with"]]
    marginal_labelled = [r for r in marginal if r["truth"] is not None]

    return {
        "pair": pair,
        "search_km": search_km,
        "grid": {
            "width": grid.width,
            "height": grid.height,
            "resolution_m": grid.resolution_m,
        },
        "tiles": {
            "a": {
                "id": tile_a.tile_id,
                "candidates": len(dets_a),
                "cloud_frac": round(float(tile_a.cloud_mask.mean()), 4),
                "water_frac": round(float((tile_a.bands["B08"] > 0).mean()), 4),
            },
            "b": {
                "id": tile_b.tile_id,
                "candidates": len(dets_b),
                "cloud_frac": round(float(tile_b.cloud_mask.mean()), 4),
                "water_frac": round(float((tile_b.bands["B08"] > 0).mean()), 4),
            },
        },
        "candidates_total": len(rows),
        "candidates_labelled": len(labelled),
        "baseline_precision": baseline_precision,
        "reobserved": sum(1 for r in rows if r["reobserved"]),
        "transient": len(transient),
        "incoherent_motion": len(incoherent),
        "spectral_only": _pr(labelled, "verified_without"),
        "with_multi_temporal": _pr(labelled, "verified_with"),
        "marginal_rejections": len(marginal),
        "marginal_rejections_labelled": len(marginal_labelled),
        "marginal_truth_breakdown": dict(Counter(str(r["truth"]) for r in marginal_labelled)),
        "marginal_true_debris_lost": sum(
            1 for r in marginal_labelled if r["truth"] == DEBRIS_CLASS
        ),
    }


def evaluate(
    pair: dict,
    *,
    resolution_m: float,
    search_km: float,
    verbose: bool,
    current_speed_ms: float | None = None,
) -> dict:
    bbox = pair["bbox"]
    tile_id = pair["tile"]
    date_a = dt.date.fromisoformat(pair["date_a"])
    date_b = dt.date.fromisoformat(pair["date_b"])
    grid = build_grid(tuple(bbox), resolution_m=resolution_m)

    if verbose:
        print(f"AOI {bbox}  grid {grid.width}x{grid.height} ({grid.pixels:,} px)")
        print(f"reading {tile_id} {date_a} and {date_b} ...", flush=True)

    tile_a = tile_for_date(bbox, tile_id, date_a, grid)
    tile_b = tile_for_date(bbox, tile_id, date_b, grid)
    labels_a = marida_label_raster(tile_id, date_a, grid)

    dets_a = detect(tile_a)
    dets_b = detect(tile_b)
    if verbose:
        print(
            f"  {tile_a.tile_id}: {len(dets_a)} candidates, "
            f"cloud {tile_a.cloud_mask.mean():.1%}, "
            f"water {(tile_a.bands['B08'] > 0).mean():.1%}"
        )
        print(
            f"  {tile_b.tile_id}: {len(dets_b)} candidates, "
            f"cloud {tile_b.cloud_mask.mean():.1%}, "
            f"water {(tile_b.bands['B08'] > 0).mean():.1%}"
        )

    rows = []
    n_rows, n_cols = tile_a.shape
    for det in dets_a:
        col, row = tile_a.transform.to_pixel(det.lon, det.lat)
        r0, r1 = max(0, row - 2), min(n_rows, row + 3)
        c0, c1 = max(0, col - 2), min(n_cols, col + 3)
        if r0 >= r1 or c0 >= c1:
            continue
        cls = truth_for(labels_a[r0:r1, c0:c1])
        window = sample_window(tile_a, det)
        repeats, moved_km = build_repeats(det, dets_b, tile_b, search_km=search_km)

        without = V.verify(det, window)  # multi-temporal inconclusive
        with_mt = V.verify(
            det, window, repeats=repeats, current_speed_ms=current_speed_ms
        )  # multi-temporal active
        mt_check = next(c for c in with_mt.checks if c.name == "multi_temporal")
        rows.append(
            {
                "id": det.id,
                "truth": cls,
                "moved_km": moved_km,
                "reobserved": repeats[0].detected,
                "verified_without": without.verified,
                "verified_with": with_mt.verified,
                "mt_disqualified": mt_check.disqualified,
                "mt_reason": mt_check.reason,
            }
        )

    out = summarise(rows, pair, grid, tile_a, tile_b, dets_a, dets_b, search_km)
    out["current_speed_ms"] = current_speed_ms
    return out


def list_pairs() -> None:
    """Every same-tile MARIDA date pair with labelled debris on both sides."""
    import itertools

    import rasterio
    from pyproj import Transformer

    info = {}
    for scene in sorted(MARIDA_PATCHES.iterdir()):
        m = re.match(r"S2_(\d+)-(\d+)-(\d+)_(\w+)$", scene.name)
        if not m:
            continue
        d, mo, y, tile = int(m[1]), int(m[2]), int(m[3]), m[4]
        date = dt.date(2000 + y, mo, d)
        debris, lons, lats = 0, [], []
        for mask in scene.glob("*_cl.tif"):
            with rasterio.open(mask) as src:
                arr = src.read(1)
                n = int((arr == DEBRIS_CLASS).sum())
                if n:
                    debris += n
                    t = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True)
                    b = src.bounds
                    lo1, la1 = t.transform(b.left, b.bottom)
                    lo2, la2 = t.transform(b.right, b.top)
                    lons += [lo1, lo2]
                    lats += [la1, la2]
        if debris:
            info[(tile, date)] = (debris, min(lons), min(lats), max(lons), max(lats))

    header = (
        f"{'tile':7s} {'date A':11s} {'date B':11s} "
        f"{'gap':>4s} {'debris A/B':>12s}  overlap bbox"
    )
    print(header)
    for tile in sorted({t for t, _ in info}):
        dates = sorted(d for t, d in info if t == tile)
        for d1, d2 in itertools.combinations(dates, 2):
            gap = (d2 - d1).days
            if gap > 20:
                continue
            a, b = info[(tile, d1)], info[(tile, d2)]
            lo, la = max(a[1], b[1]), max(a[2], b[2])
            hi, ha = min(a[3], b[3]), min(a[4], b[4])
            if hi <= lo or ha <= la:
                continue
            print(
                f"{tile:7s} {d1!s:11s} {d2!s:11s} {gap:4d} {a[0]:5d}/{b[0]:<6d}  "
                f"[{lo:.3f}, {la:.3f}, {hi:.3f}, {ha:.3f}]"
            )


def _report(out: dict) -> None:
    p = out["pair"]
    print(
        f"\nFR-2.2 multi-temporal consistency — MARIDA {p['tile']} "
        f"{p['date_a']} -> {p['date_b']}"
    )
    a, b = out["tiles"]["a"], out["tiles"]["b"]
    print(
        f"  {a['id']}: {a['candidates']:4d} candidates  "
        f"cloud {a['cloud_frac']:.1%}  water {a['water_frac']:.1%}"
    )
    print(
        f"  {b['id']}: {b['candidates']:4d} candidates  "
        f"cloud {b['cloud_frac']:.1%}  water {b['water_frac']:.1%}"
    )
    print(
        f"  {out['candidates_total']} candidates on date A, "
        f"{out['candidates_labelled']} carry a MARIDA label"
    )

    speed = out.get("current_speed_ms")
    if speed:
        print(
            f"\n  current field: {speed} m/s — ASSUMED, sensitivity analysis only. "
            "The real value must come from the Drift Agent (FR-3.1)."
        )
    else:
        print(
            "\n  current field: none loaded, so the coherent-motion envelope is "
            "only the 5 km base tolerance."
        )
    print(f"  re-observed within {out['search_km']} km : {out['reobserved']}")
    print(f"  transient (never re-observed) : {out['transient']}")
    print(f"  re-observed but incoherent    : {out['incoherent_motion']}")

    so, wm = out["spectral_only"], out["with_multi_temporal"]
    print("\n                          precision   recall       F1")
    print(f"  baseline detector       {out['baseline_precision']:9.4f} {1.0:8.4f}        -")
    print(f"  4 spectral checks       {so['precision']:9.4f} {so['recall']:8.4f} {so['f1']:8.4f}")
    print(f"  + multi-temporal        {wm['precision']:9.4f} {wm['recall']:8.4f} {wm['f1']:8.4f}")
    print(
        f"  delta from FR-2.2       {wm['precision'] - so['precision']:+9.4f} "
        f"{wm['recall'] - so['recall']:+8.4f} {wm['f1'] - so['f1']:+8.4f}"
    )

    print(
        f"\n  marginal rejections (passed spectral, killed by multi-temporal): "
        f"{out['marginal_rejections']}"
    )
    print(
        f"    of which labelled: {out['marginal_rejections_labelled']}  "
        f"truth breakdown {out['marginal_truth_breakdown']}"
    )
    print(f"    TRUE DEBRIS LOST to this check: {out['marginal_true_debris_lost']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list-pairs", action="store_true")
    ap.add_argument("--tile", default=DEFAULT_PAIR["tile"])
    ap.add_argument("--date-a", default=DEFAULT_PAIR["date_a"])
    ap.add_argument("--date-b", default=DEFAULT_PAIR["date_b"])
    ap.add_argument("--bbox", type=float, nargs=4, default=DEFAULT_PAIR["bbox"])
    ap.add_argument("--resolution-m", type=float, default=20.0)
    ap.add_argument("--search-km", type=float, default=50.0)
    ap.add_argument(
        "--current-speed-ms",
        type=float,
        default=None,
        help=(
            "Assumed surface current speed, widening the coherent-motion "
            "envelope. SENSITIVITY ANALYSIS ONLY - the real value must come "
            "from the Drift Agent's OSCAR field (FR-3.1), which is unwritten."
        ),
    )
    ap.add_argument("--json", type=Path)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not MARIDA_PATCHES.is_dir():
        print(
            f"ERROR: MARIDA not found at {MARIDA_PATCHES}. Workstation-only data; run "
            "python scripts/fetch_data.py --instructions --dataset marida",
            file=sys.stderr,
        )
        return 2

    if args.list_pairs:
        list_pairs()
        return 0

    pair = {
        "tile": args.tile,
        "date_a": args.date_a,
        "date_b": args.date_b,
        "bbox": list(args.bbox),
    }
    try:
        out = evaluate(
            pair,
            resolution_m=args.resolution_m,
            search_km=args.search_km,
            verbose=not args.quiet,
            current_speed_ms=args.current_speed_ms,
        )
    except EvalError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    _report(out)
    if args.json:
        args.json.write_text(json.dumps(out, indent=2, default=str))
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("GDAL_HTTP_TIMEOUT", "60")
    sys.exit(main())
