"""Place a region's ``aoi_bbox`` by MEASURING water, not by reading a map.

    python scripts/measure_aoi.py --region gulf_of_gonave --json eval/aoi_gonave.json

A region's ``bbox`` is its definition — the coastline the project claims to
monitor. Its ``aoi_bbox`` is what one pipeline run actually ingests, and it
exists because the full bbox is past ``ghostnet.ingest``'s pixel budget and
past a demo-appropriate run time (PRD §8).

Why this is measured rather than chosen
---------------------------------------
The Gulf of Honduras AOI carries a comment recording that boxes centred on the
river mouth scored **38% water** against the chosen box's **67.7%**, because
they sat half outside tile 16PCC's footprint. That is the trap this script
automates:

* **Each STAC item is ONE MGRS tile.** An AOI overrunning a tile footprint is
  mostly nodata per scene, so it looks like ocean on a map and returns empty
  arrays in practice.
* **Cloud is not evenly spread.** A box can be mostly water and still be
  useless if the water is always under cloud, so water is reported twice: over
  all pixels, and over cloud-free pixels only.

Method
------
One STAC search over the whole region, then every candidate box is scored on
the intersecting scenes from that common pool. SCL is read at a coarse resolution — this
estimates *fractions*, and 20 m detail buys nothing while costing minutes.

The output is a ranking, not a decision. Choose a box within the intended coastal
study area before inspecting detector outputs, then record it in
``config/regions.yaml`` with its measured numbers in the comment, the way
``gulf_of_honduras`` records its own, so the choice stays auditable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghostnet.config import get_region  # noqa: E402
from ghostnet.ingest import (  # noqa: E402
    SCL_CLOUD_CLASSES,
    SCL_NODATA,
    SCL_WATER,
    IngestError,
    _configure_gdal,
    _read_asset,
    build_grid,
    search_l2a,
)

Box = tuple[float, float, float, float]


def candidates(bbox: Box, *, width: float, height: float, step: float) -> list[Box]:
    """Tile the region with overlapping candidate AOIs of a fixed size."""
    min_lon, min_lat, max_lon, max_lat = bbox
    out: list[Box] = []
    lat = min_lat
    while lat + height <= max_lat + 1e-9:
        lon = min_lon
        while lon + width <= max_lon + 1e-9:
            out.append(
                (round(lon, 4), round(lat, 4), round(lon + width, 4), round(lat + height, 4))
            )
            lon += step
        lat += step
    return out


def _intersects(box: Box, item: Any) -> bool:
    b = item.bbox
    return not (b[2] < box[0] or b[0] > box[2] or b[3] < box[1] or b[1] > box[3])


def score(box: Box, items: list[Any], *, resolution_m: float) -> dict[str, Any]:
    """Water fraction over all pixels, and over cloud-free pixels only.

    Only scenes whose footprint INTERSECTS the box are read. Scoring a box
    against every scene in the region instead makes nodata meaningless: each
    STAC item is one MGRS tile, so a box sitting squarely inside one tile still
    reads as empty on every scene from the other tiles, and a perfectly good
    AOI comes back 90% nodata. That is an artefact of which scenes were
    averaged, not a property of the box.
    """
    grid = build_grid(box, resolution_m=resolution_m, max_pixels=50_000_000)
    water = cloud_free_water = cloud_free = total = 0
    scenes = 0
    for item in [i for i in items if _intersects(box, i)]:
        try:
            scl = _read_asset(item, "SCL", grid, nearest=True).astype("uint8")
        except (IngestError, OSError, ValueError):
            # One unreadable scene must not decide a box; it is recorded by
            # its absence from scenes_used.
            continue
        scenes += 1
        valid = scl != SCL_NODATA
        is_water = scl == SCL_WATER
        clear = valid & ~np.isin(scl, SCL_CLOUD_CLASSES)
        total += int(valid.sum())
        water += int((is_water & valid).sum())
        cloud_free += int(clear.sum())
        cloud_free_water += int((is_water & clear).sum())

    def pct(num: int, den: int) -> float | None:
        return round(100.0 * num / den, 1) if den else None

    return {
        "bbox": list(box),
        "scenes_used": scenes,
        # The one number that cannot be gamed: cloud-free water as a share of
        # the WHOLE box, nodata included. water_pct is computed over covered
        # pixels only, so a box that is 90% outside its tile can still report
        # 95% water. This is what a run actually gets to look at.
        "usable_water_pct": (
            round(100.0 * cloud_free_water / (grid.pixels * scenes), 1) if scenes else None
        ),
        "pixels_at_20m": build_grid(box, resolution_m=20.0, max_pixels=10**9).pixels,
        "water_pct": pct(water, total),
        "water_pct_cloud_free": pct(cloud_free_water, cloud_free),
        "cloud_free_pct": pct(cloud_free, total),
        # Nodata is the tile-footprint trap made visible: a box straddling two
        # MGRS tiles reads as empty on every scene from either one.
        "nodata_pct": pct(grid.pixels * scenes - total, grid.pixels * scenes) if scenes else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--region", required=True)
    ap.add_argument("--width", type=float, default=0.50, help="candidate width in degrees")
    ap.add_argument("--height", type=float, default=0.40, help="candidate height in degrees")
    ap.add_argument("--step", type=float, default=0.25, help="candidate spacing in degrees")
    ap.add_argument("--scenes", type=int, default=4, help="scenes to average over")
    ap.add_argument("--resolution-m", type=float, default=200.0)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    if min(args.width, args.height, args.step, args.resolution_m, args.scenes) <= 0:
        ap.error("dimensions, spacing, resolution and scene count must be positive")
    _configure_gdal()

    entry = get_region(args.region)
    bbox = tuple(entry["bbox"])
    window = entry["time_window"]
    boxes = candidates(bbox, width=args.width, height=args.height, step=args.step)
    if not boxes:
        ap.error("candidate dimensions exceed the region extent")
    print(f"region     : {args.region}")
    print(f"bbox       : {list(bbox)}")
    print(f"candidates : {len(boxes)} of {args.width} x {args.height} deg\n")

    items = search_l2a(
        bbox,
        str(window["start"]),
        str(window["end"]),
        max_cloud_cover_pct=float(entry.get("max_cloud_cover_pct", 20.0)),
        mgrs_tiles=entry.get("mgrs_tiles"),
        limit=args.scenes,
    )
    if not items:
        print("No L2A scenes matched. Widen the window or the cloud threshold.", file=sys.stderr)
        return 2
    for item in items:
        print(f"  scene {item.id}  tile={item.properties.get('s2:mgrs_tile')} "
              f"cloud={item.properties.get('eo:cloud_cover'):.0f}%")
    print()

    rows = []
    for i, box in enumerate(boxes, 1):
        print(f"  [{i}/{len(boxes)}] {box} ...", flush=True)
        rows.append(score(box, items, resolution_m=args.resolution_m))
        # Preserve completed measurements if a native reader or the process dies.
        # This is explicitly partial, not a completed evaluation artefact.
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.with_suffix(".partial.json").write_text(
                json.dumps({"complete": False, "scenes": [s.id for s in items],
                            "candidates": rows}, indent=2), encoding="utf-8"
            )

    ranked = sorted(
        rows, key=lambda r: (r["usable_water_pct"] or 0, r["water_pct"] or 0), reverse=True
    )
    # nodata is printed, not just stored: a box can look like ocean on water%
    # alone while most of it sits outside the tile footprint and reads empty.
    print(f"\n{'bbox':<44} {'USABLE%':>8} {'water%':>7} {'NODATA%':>8} "
          f"{'scenes':>7} {'Mpx@20m':>8}")
    for r in ranked:
        px = r["pixels_at_20m"] / 1e6
        print(f"{str(r['bbox']):<44} {r['usable_water_pct'] or 0:8.1f} {r['water_pct'] or 0:7.1f} "
              f"{r['nodata_pct'] or 0:8.1f} "
              f"{r['scenes_used']:7d} {px:8.1f}")

    best = ranked[0]
    print(f"\nBEST: aoi_bbox: {best['bbox']}")
    print(f"  {best['usable_water_pct']}% usable water (cloud-free water over the whole box), "
          f"{best['water_pct']}% water where covered, {best['nodata_pct']}% nodata, "
          f"{best['pixels_at_20m'] / 1e6:.1f} M pixels per band at 20 m")
    print("\nThis is a ranking, not a decision. Put the chosen box in "
          "config/regions.yaml WITH these numbers in the comment.")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "region": args.region,
                    "region_bbox": list(bbox),
                    "window": {"start": str(window["start"]), "end": str(window["end"])},
                    "scenes": [i.id for i in items],
                    "resolution_m": args.resolution_m,
                    "candidates": ranked,
                    "caveats": [
                        "Fractions are measured on SCL at a coarse resolution; they "
                        "estimate composition, not any per-pixel result.",
                        "Averaged over the scenes listed. A different window or cloud "
                        "threshold can rank boxes differently.",
                        "Each STAC item is one MGRS tile, so a box overrunning a tile "
                        "footprint scores low because it reads nodata, not because it "
                        "is land.",
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
