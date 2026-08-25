"""Turn the raw public downloads into the small extracts the agents actually read.

Two datasets in this project are public, credential-free, and *globally huge*:
UNEP-WCMC's Protected Planet (WDPA) and The Ocean Cleanup / Meijer et al. river
emissions. Neither is committable (`.gitignore` excludes `data/**`) and neither
is usable whole — so each machine downloads the source once and runs this to
produce a region-clipped extract that `ghostnet` can load:

    python scripts/build_region_extracts.py rivers \\
        --region gulf_of_honduras --source ~/Downloads/meijer2021_rivers.csv

    python scripts/build_region_extracts.py mpa \\
        --region gulf_of_honduras --source ~/Downloads/WDPA_marine.gpkg

Outputs land where the loaders look, in the shape they expect:

    data/rivers/<region>.csv            -> attribution.RiverTable.from_csv
    data/protected_planet/<region>.json -> prioritisation.load_protected_areas

**The clip is a buffered bbox, not the bbox.** Debris drifts, so a river mouth
or a reserve just outside the monitored box is still a live candidate — the
backward trajectory reaches it even though the detection never sat over it.
Clipping to the bare bbox would silently drop the true source. Both buffers are
flags with defaults justified below; neither is a round number picked for looks.

**The MPA extract is an approximation, and this script measures how bad it is.**
`ProtectedArea` reduces a WDPA polygon to a centroid and one radius. For a
compact reserve that is nearly lossless; for the Mesoamerican Barrier Reef —
~1000 km long and a few km wide — a circle of the same area is a poor stand-in,
placing "boundary" water where there is none and missing reef that is really
there. Two things keep that honest rather than hidden: multipart geometries are
exploded so each reef patch gets its own circle instead of one continent-sized
one, and every record carries a `circle_fit` score that the run reports on. See
:func:`_circle_fit`.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghostnet.config import DATA_ROOT, get_region  # noqa: E402

# --------------------------------------------------------------------------
# Buffers
# --------------------------------------------------------------------------

#: A river outside the monitored box can still be the source — the Drift Agent
#: backtracks days upstream of the detection. The synthetic demo run projects a
#: 66 km envelope over 7 days; a real backtrack over the region's 8-month window
#: reaches considerably further, so 250 km buys margin without dragging the
#: whole Caribbean rim into a ranked distribution that is supposed to discriminate.
DEFAULT_RIVER_BUFFER_KM = 250.0

#: Ecological risk decays over `prioritisation.MPA_RISK_SCALE_KM` (50 km), so a
#: reserve within ~2 scale lengths of the box still moves a priority score.
#: Beyond that its contribution rounds away and it is only extract weight.
DEFAULT_MPA_BUFFER_KM = 100.0

#: Below this, a polygon is poorly represented by a centroid-and-radius circle
#: and the run says so. Not a rejection threshold — the record is still written,
#: because dropping the Mesoamerican reef would be worse than approximating it.
CIRCLE_FIT_WARN = 0.35

#: Equal-area projection for honest polygon areas. Areas computed in EPSG:4326
#: degrees are meaningless; EPSG:6933 (World Cylindrical Equal Area) is the
#: standard global marine choice and is accurate enough at this latitude for a
#: radius that already carries the circle approximation above.
EQUAL_AREA_CRS = "EPSG:6933"

# Source columns vary between distributions of the Meijer data, so accept the
# spellings seen in the wild and fail loudly (naming the real header) otherwise.
RIVER_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "river", "river_name", "NAME", "River"),
    "lon": ("lon", "longitude", "x", "X", "lon_mouth", "mouth_lon"),
    "lat": ("lat", "latitude", "y", "Y", "lat_mouth", "mouth_lat"),
    "emission_tonnes_yr": (
        "emission_tonnes_yr",
        "dwm_tonnes_yr",
        "plastic_emissions_tonnes_yr",
        "emissions",
        "tonnes_yr",
        "mismanaged_plastic_tonnes_yr",
    ),
    "country": ("country", "COUNTRY", "iso", "iso3", "country_name"),
}

MPA_NAME_COLUMNS = ("NAME", "name", "ORIG_NAME", "wdpa_name")
MPA_DESIGNATION_COLUMNS = ("DESIG_ENG", "DESIG", "designation", "IUCN_CAT")


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------


def _buffered_bbox(
    bbox: tuple[float, float, float, float], buffer_km: float
) -> tuple[float, float, float, float]:
    """Grow a lon/lat bbox by an approximate great-circle distance.

    Latitude degrees are ~111 km everywhere; longitude degrees shrink with
    cos(lat), so the widest latitude edge is used for the longitude padding —
    that over-pads slightly rather than under-padding, and over-padding only
    costs a few extra candidate records.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    lat_pad = buffer_km / 111.0
    widest_lat = max(abs(min_lat), abs(max_lat))
    lon_pad = buffer_km / (111.0 * max(math.cos(math.radians(widest_lat)), 0.01))
    return (min_lon - lon_pad, min_lat - lat_pad, max_lon + lon_pad, max_lat + lat_pad)


def _region_bbox(region_id: str) -> tuple[float, float, float, float]:
    region = get_region(region_id)
    bbox = region.get("bbox")
    if not bbox or len(bbox) != 4:
        raise SystemExit(
            f"Region {region_id!r} has no usable bbox in config/regions.yaml "
            f"(found {bbox!r}). A region must be selected before extracts can "
            "be clipped to it."
        )
    return tuple(float(v) for v in bbox)  # type: ignore[return-value]


def _resolve_column(fieldnames: list[str], target: str) -> str | None:
    """Match a required column against its known aliases, case-insensitively."""
    lowered = {f.lower().strip(): f for f in fieldnames}
    for alias in RIVER_COLUMN_ALIASES[target]:
        found = lowered.get(alias.lower())
        if found is not None:
            return found
    return None


# --------------------------------------------------------------------------
# Rivers (FR-4)
# --------------------------------------------------------------------------


def build_rivers(
    source: Path,
    region_id: str,
    *,
    buffer_km: float = DEFAULT_RIVER_BUFFER_KM,
    out_dir: Path | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    """Clip a global river-emission table to one region and write the extract."""
    region = get_region(region_id)
    bbox = _region_bbox(region_id)
    min_lon, min_lat, max_lon, max_lat = _buffered_bbox(bbox, buffer_km)

    with Path(source).open(newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        resolved = {t: _resolve_column(fieldnames, t) for t in RIVER_COLUMN_ALIASES}
        missing = [t for t in ("name", "lon", "lat", "emission_tonnes_yr") if not resolved[t]]
        if missing:
            raise SystemExit(
                f"{source} is missing required column(s) {missing}. Its header is "
                f"{fieldnames}. Known aliases per field: "
                + "; ".join(f"{k}={list(v)}" for k, v in RIVER_COLUMN_ALIASES.items())
            )

        kept: list[dict[str, Any]] = []
        total = 0
        for row in reader:
            total += 1
            try:
                lon = float(row[resolved["lon"]])
                lat = float(row[resolved["lat"]])
                emission = float(row[resolved["emission_tonnes_yr"]])
            except (TypeError, ValueError):
                continue  # unparseable row in a public CSV; skip rather than abort
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                continue
            country_col = resolved["country"]
            kept.append(
                {
                    "name": (row[resolved["name"]] or "").strip(),
                    "lon": lon,
                    "lat": lat,
                    "emission_tonnes_yr": emission,
                    "country": ((row.get(country_col) or "") if country_col else "").strip(),
                }
            )

    # FR-4.2 wants a ranked distribution, and `matches_published_ranking` checks
    # our order against the publisher's — so write it already ranked.
    kept.sort(key=lambda r: r["emission_tonnes_yr"], reverse=True)

    if not kept:
        raise SystemExit(
            f"No rivers fell inside {region_id}'s bbox buffered by {buffer_km:g} km "
            f"(searched {total} rows). Check the source's lon/lat convention — a "
            "table using 0-360 longitudes will produce exactly this."
        )

    out_dir = Path(out_dir or DATA_ROOT / "rivers")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{region_id}.csv"
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["name", "lon", "lat", "emission_tonnes_yr", "country"]
        )
        writer.writeheader()
        writer.writerows(kept)

    _report_rivers(region, kept, total, buffer_km, out_path)
    return out_path, kept


def _report_rivers(
    region: dict[str, Any],
    kept: list[dict[str, Any]],
    total: int,
    buffer_km: float,
    out_path: Path,
) -> None:
    print(f"rivers: kept {len(kept)} of {total} rows (bbox + {buffer_km:g} km)")
    for row in kept[:5]:
        print(f"  {row['emission_tonnes_yr']:12,.1f} t/yr  {row['name']}  ({row['country']})")
    if len(kept) > 5:
        print(f"  ... and {len(kept) - 5} more")

    # The region was chosen partly because FR-4 has a citable answer here. If
    # that river missed the clip, the headline check cannot run — say so now,
    # not when the attribution output looks inexplicably wrong.
    expected = (region.get("source_river") or "").strip()
    if expected:
        names = " | ".join(r["name"].lower() for r in kept)
        stem = expected.lower().replace("río ", "").replace("rio ", "").strip()
        if stem and stem not in names:
            print(
                f"  WARNING: {expected!r} is named as this region's source river in "
                f"config/regions.yaml but is not in the extract. FR-4 cannot be "
                f"checked against the publisher's ranking without it — widen "
                f"--buffer-km, or check how the source spells it.",
                file=sys.stderr,
            )
    print(f"  wrote {out_path}")


# --------------------------------------------------------------------------
# Protected areas (FR-6.1)
# --------------------------------------------------------------------------


def _circle_fit(geometry: Any) -> float:
    """How well a centroid-and-radius circle stands in for this polygon, 0..1.

    Polygon area over the area of its minimum bounding circle. A disc scores
    ~1.0; a long, thin reef scores near 0. This is the honest measure of what
    the `ProtectedArea` approximation costs on any given record, and it is the
    number to quote if an evaluator asks how MPA proximity is modelled.

    Note shapely returns the bounding circle as a many-segment polygon, so its
    area is a touch under the true circle's and a perfect square scores ~0.641
    rather than the analytic 2/pi. That bias is well below the resolution this
    number is used at.

    Deliberately not wrapped in a try/except: a fit that silently came back
    unavailable would leave every record reading "n/a" and quietly retire the
    only measure of how good the approximation is.
    """
    import shapely  # bundled with geopandas; module-level function since 2.0

    circle = shapely.minimum_bounding_circle(geometry)
    if circle.area <= 0:
        return float("nan")
    return float(geometry.area / circle.area)


def build_mpa(
    source: Path,
    region_id: str,
    *,
    buffer_km: float = DEFAULT_MPA_BUFFER_KM,
    out_dir: Path | None = None,
    layer: str | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    """Clip WDPA polygons to one region and reduce each part to centroid+radius."""
    try:
        import geopandas as gpd
    except ImportError as exc:  # pragma: no cover - environment guard
        raise SystemExit(
            "geopandas is required to build the MPA extract. Install the base "
            "stack: python -m pip install -r requirements-base.txt"
        ) from exc

    bbox = _buffered_bbox(_region_bbox(region_id), buffer_km)

    # bbox= filters at read time — WDPA global is far too large to load whole.
    read_kwargs: dict[str, Any] = {"bbox": bbox}
    if layer:
        read_kwargs["layer"] = layer
    frame = gpd.read_file(source, **read_kwargs)
    if frame.empty:
        raise SystemExit(
            f"No protected areas intersect {region_id}'s bbox buffered by "
            f"{buffer_km:g} km. Check that {source} is the marine subset and "
            "covers this part of the world."
        )
    if frame.crs is None:
        raise SystemExit(f"{source} declares no CRS; cannot place its geometries.")
    frame = frame.to_crs("EPSG:4326")

    # One circle per part. A reef system arrives as a MultiPolygon of many
    # separate patches; collapsing it to a single centroid would put its centre
    # in open water hundreds of km from any reef.
    frame = frame.explode(index_parts=False, ignore_index=True)
    frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty]

    equal_area = frame.to_crs(EQUAL_AREA_CRS)
    areas_m2 = equal_area.geometry.area
    fits = [_circle_fit(geom) for geom in equal_area.geometry]
    centroids = frame.geometry.representative_point()

    name_col = next((c for c in MPA_NAME_COLUMNS if c in frame.columns), None)
    desig_col = next((c for c in MPA_DESIGNATION_COLUMNS if c in frame.columns), None)

    records: list[dict[str, Any]] = []
    for i, (_, row) in enumerate(frame.iterrows()):
        area_m2 = float(areas_m2.iloc[i])
        if area_m2 <= 0:
            continue
        radius_km = math.sqrt(area_m2 / math.pi) / 1000.0
        records.append(
            {
                "name": str(row[name_col]).strip() if name_col else f"WDPA part {i}",
                "lon": float(centroids.iloc[i].x),
                "lat": float(centroids.iloc[i].y),
                "radius_km": round(radius_km, 4),
                "designation": str(row[desig_col]).strip() if desig_col else "",
                "circle_fit": round(float(fits[i]), 4) if fits[i] == fits[i] else None,
            }
        )

    if not records:
        raise SystemExit(f"Every geometry in {source} clipped to zero area for {region_id}.")

    records.sort(key=lambda r: r["radius_km"], reverse=True)

    out_dir = Path(out_dir or DATA_ROOT / "protected_planet")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{region_id}.json"
    out_path.write_text(json.dumps(records, indent=2))

    _report_mpa(records, buffer_km, out_path)
    return out_path, records


def _report_mpa(
    records: list[dict[str, Any]], buffer_km: float, out_path: Path
) -> None:
    print(f"mpa: wrote {len(records)} area(s) (bbox + {buffer_km:g} km)")
    for rec in records[:5]:
        fit = rec["circle_fit"]
        fit_text = "fit n/a" if fit is None else f"fit {fit:.2f}"
        print(f"  r={rec['radius_km']:8.1f} km  {fit_text}  {rec['name']}")
    if len(records) > 5:
        print(f"  ... and {len(records) - 5} more")

    poor = [r for r in records if r["circle_fit"] is not None and r["circle_fit"] < CIRCLE_FIT_WARN]
    if poor:
        worst = min(poor, key=lambda r: r["circle_fit"])
        print(
            f"  NOTE: {len(poor)} of {len(records)} areas are poorly described by a "
            f"circle (fit < {CIRCLE_FIT_WARN}); worst is {worst['name']!r} at "
            f"{worst['circle_fit']:.2f}. Their ecological-risk distances are "
            f"approximate — quote this if asked how MPA proximity is modelled.",
            file=sys.stderr,
        )
    print(f"  wrote {out_path}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="what", required=True)

    rivers = sub.add_parser("rivers", help="Clip The Ocean Cleanup river table (FR-4)")
    rivers.add_argument("--source", type=Path, required=True, help="Global river CSV")
    rivers.add_argument("--region", default="gulf_of_honduras")
    rivers.add_argument("--buffer-km", type=float, default=DEFAULT_RIVER_BUFFER_KM)
    rivers.add_argument("--out-dir", type=Path, default=None)

    mpa = sub.add_parser("mpa", help="Clip the WDPA marine subset (FR-6.1)")
    mpa.add_argument("--source", type=Path, required=True, help="WDPA shapefile/geopackage")
    mpa.add_argument("--region", default="gulf_of_honduras")
    mpa.add_argument("--buffer-km", type=float, default=DEFAULT_MPA_BUFFER_KM)
    mpa.add_argument("--layer", default=None, help="Layer name, for multi-layer GeoPackages")
    mpa.add_argument("--out-dir", type=Path, default=None)

    args = parser.parse_args(argv)
    if not args.source.exists():
        raise SystemExit(f"Source not found: {args.source}")

    if args.what == "rivers":
        build_rivers(
            args.source, args.region, buffer_km=args.buffer_km, out_dir=args.out_dir
        )
    else:
        build_mpa(
            args.source,
            args.region,
            buffer_km=args.buffer_km,
            out_dir=args.out_dir,
            layer=args.layer,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
