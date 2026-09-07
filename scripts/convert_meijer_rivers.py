"""Convert the Meijer et al. 2021 river shapefile to the CSV FR-4 expects.

    python scripts/convert_meijer_rivers.py --source Meijer2021_midpoint_emissions.shp \
        --out data/rivers/meijer2021_global.csv

Then clip it to a region the usual way::

    python scripts/build_region_extracts.py rivers --region <id> --source <that csv>

Why this step exists
--------------------
The published dataset (figshare 14515590, supplementary to *Science Advances*
7(18) eaaz5803) ships as a point shapefile carrying **one attribute**:
``dots_exten``. Two things about that are worth recording, because both would
otherwise be guesses:

1. **``dots_exten`` is the emission figure**, despite reading like a rendering
   attribute for the paper's map. Verified rather than assumed: it sums to
   1,005,984 t/yr over 31,819 points, which is Meijer's published global
   estimate of ~1 Mt/yr. An arbitrary display field has no reason to total the
   paper's headline number. The name is a shapefile artefact — the format
   truncates field names to 10 characters, so ``dots_extent`` lost its final t.

2. **The dataset has no river names, and that is not an omission.** Meijer
   models emissions at ~31,000 river *mouths* derived from hydrology, not from
   a gazetteer; the named "top 1000" on The Ocean Cleanup's map come from a
   separate lookup for presentation. So names here are OURS, added by
   coordinate proximity, and are marked as such: every annotated row carries
   ``name_source=annotated`` and every other row keeps a positional id with
   ``name_source=coordinate``.

That distinction has to survive into the report. "Most likely source: Motagua"
is a claim about a name we attached; "ranked 4th by modelled emission in the
region" is a claim from the data.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

#: River mouths we name, and the evidence for each.
#:
#: Kept deliberately small. These are the rivers this project actually claims —
#: the Motagua is the reason the Gulf of Honduras was chosen (PRD §5.1, the
#: "world's largest single plastic-emitting river" framing that FR-4 checks
#: against) — plus its two significant neighbours, which matter because
#: attribution has to be able to get the answer *wrong* for the result to mean
#: anything. Tolerance is deliberately tight: a mouth more than ~12 km from the
#: published position is a different river.
NAMED_MOUTHS: tuple[tuple[str, float, float, str], ...] = (
    ("Motagua", 15.810, -88.758, "Guatemala/Honduras border; Interceptor 021 site"),
    ("Ulua", 15.895, -87.791, "Honduras, discharges into the Gulf of Honduras"),
    ("Chamelecon", 15.845, -87.845, "Honduras, adjacent to the Ulua delta"),
)
NAME_TOLERANCE_KM = 12.0


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance, good enough at these separations."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def annotate(lat: float, lon: float) -> tuple[str, str]:
    """Return (name, name_source) for one river mouth."""
    best, best_km = None, NAME_TOLERANCE_KM
    for name, nlat, nlon, _why in NAMED_MOUTHS:
        d = _km(lat, lon, nlat, nlon)
        if d < best_km:
            best, best_km = name, d
    if best:
        return best, "annotated"
    # Positional id. Readable, stable, and obviously not a real river name, so
    # nobody quotes it in a report by accident.
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"river_{abs(lat):.3f}{ns}_{abs(lon):.3f}{ew}", "coordinate"


def convert(source: Path, out: Path) -> int:
    import geopandas as gpd

    frame = gpd.read_file(source)
    if "dots_exten" not in frame.columns:
        raise SystemExit(
            f"{source} has columns {list(frame.columns)}; expected 'dots_exten'. "
            "This converter is for the Meijer 2021 midpoint-emissions shapefile "
            "(figshare 14515590)."
        )
    if frame.crs and frame.crs.to_epsg() != 4326:
        frame = frame.to_crs(4326)

    total = float(frame["dots_exten"].sum())
    # The check that says dots_exten is emissions and not a display field. If a
    # future release renames or rescales it, this fails rather than silently
    # ranking rivers by the wrong quantity.
    if not 5e5 < total < 3e6:
        raise SystemExit(
            f"'dots_exten' sums to {total:,.0f}, outside the 0.5-3 Mt/yr range "
            "Meijer 2021 reports globally. That column may not be the emission "
            "figure in this release — check before using it."
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    named = 0
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "lat", "lon", "emission_tonnes_yr", "name_source"])
        for geom, emission in zip(frame.geometry, frame["dots_exten"], strict=True):
            if geom is None or geom.is_empty:
                continue
            lat, lon = float(geom.y), float(geom.x)
            name, source_kind = annotate(lat, lon)
            named += source_kind == "annotated"
            writer.writerow(
                [name, f"{lat:.5f}", f"{lon:.5f}", f"{float(emission):.4f}", source_kind]
            )

    print(f"wrote {out}")
    print(f"  {len(frame):,} river mouths, {total:,.0f} t/yr total")
    print(f"  {named} named by annotation, {len(frame) - named:,} positional ids")
    print("  NOTE names are OURS, not Meijer's — the dataset carries none. Any")
    print("       report sentence naming a source river is quoting an annotation.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, required=True, help="Meijer2021_midpoint_emissions.shp")
    ap.add_argument("--out", type=Path,
                    default=REPO_ROOT / "data" / "rivers" / "meijer2021_global.csv")
    args = ap.parse_args()
    return convert(args.source, args.out)


if __name__ == "__main__":
    sys.exit(main())
