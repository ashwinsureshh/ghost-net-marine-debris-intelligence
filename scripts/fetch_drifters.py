"""Fetch NOAA Global Drifter Program tracks for a region (PRD §3, §12).

    python scripts/fetch_drifters.py                    # default region
    python scripts/fetch_drifters.py --survey           # coverage only, no write
    python scripts/fetch_drifters.py --buffer-km 500

Ground truth for validating the Drift Agent: real GPS-tagged buoy paths, which
PRD §3 requires the predicted trajectories to be compared against.

Needs **no credential**, unlike OSCAR and Global Fishing Watch. Either machine
can run it — the subset is a few hundred kilobytes, not the multi-GB global
archive, because AOML's ERDDAP does the spatial and temporal clipping
server-side.

Read this before assuming a download unblocks the validation
------------------------------------------------------------
Drifters are only *half* of what PRD §12's "drift validated against real buoy
paths" bullet needs. ``drift.mean_track_error_km`` compares a **predicted**
``Trajectory`` against these observations, and producing that prediction needs
a ``CurrentField`` from ``drift.load_oscar_field`` — which needs OSCAR, which
needs ``EARTHDATA_TOKEN``. Fetching drifters removes one of two gates.

Two things the data itself says about the demo region
-----------------------------------------------------
1. **The Gulf of Honduras bbox contains no drifter observations at all during
   the 2018-02-01..2018-10-01 demo window.** Measured, not assumed: the query
   returns zero rows. Validation therefore cannot be contemporaneous with the
   demo run, and must be reported as a model check over whatever years the
   region does have — exactly as the MARIDA benchmark is independent of the
   demo window.
2. Coverage in the bare bbox is thin — 553 observations from 13 drifters,
   confined to 1999, 2000, 2007, 2013 and 2014. Hence the buffer: a wider net
   over the same current system gives a validation sample worth reporting.
   The buffer is recorded in the output so nobody later mistakes a
   western-Caribbean sample for a Gulf-of-Honduras-only one.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_region_extracts import _buffered_bbox, _region_bbox  # noqa: E402
from ghostnet.config import get_region  # noqa: E402

ERDDAP = "https://erddap.aoml.noaa.gov/gdp/erddap/tabledap/drifter_6hour_qc.csv"

# ERDDAP emits this for absent numeric values rather than an empty cell.
# Written through unchanged it would read as a velocity of -999999 cm/s.
FILL_VALUE = -999999.0

# ve/vn are the drifter's own measured velocity; they are ground truth about the
# water, not a prediction, so they are worth keeping alongside the positions.
COLUMNS = ("ID", "WMO", "time", "latitude", "longitude", "ve", "vn", "drogue_lost_date")

# The bare region bbox holds 13 drifters across 5 scattered years. 300 km widens
# to the same current system without drifting into a different regime.
DEFAULT_BUFFER_KM = 300.0
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "drifters"


class FetchError(RuntimeError):
    pass


def build_query(
    bbox: tuple[float, float, float, float],
    *,
    start: str | None = None,
    end: str | None = None,
) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    constraints = [
        f"latitude>={min_lat:.4f}",
        f"latitude<={max_lat:.4f}",
        f"longitude>={min_lon:.4f}",
        f"longitude<={max_lon:.4f}",
    ]
    if start:
        constraints.append(f"time>={start}T00:00:00Z")
    if end:
        constraints.append(f"time<={end}T00:00:00Z")
    projection = urllib.parse.quote(",".join(COLUMNS), safe="")
    # `<` and `>` MUST be percent-encoded. ERDDAP itself accepts them, but the
    # Tomcat in front of it rejects the raw characters with a bare HTTP 400 and
    # an HTML error page, which looks like a dataset problem rather than an
    # encoding one. Only `=` is left literal.
    return f"{ERDDAP}?{projection}&" + "&".join(
        urllib.parse.quote(c, safe="=") for c in constraints
    )


def fetch(url: str, *, timeout: int = 300) -> list[dict]:
    """Return ERDDAP rows, treating 'no matching results' as empty not fatal."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []  # ERDDAP reports an empty result set as 404
        raise FetchError(f"ERDDAP returned HTTP {exc.code} for {url}") from exc
    except OSError as exc:
        raise FetchError(f"Could not reach AOML ERDDAP: {exc}") from exc

    reader = csv.DictReader(io.StringIO(payload))
    rows = list(reader)
    # ERDDAP emits a units row directly under the header; drop it.
    return blank_fill_values(
        [r for r in rows if r.get("time") and r["time"][:1].isdigit()]
    )


def _is_fill(value: str) -> bool:
    """True for anything that is not a usable measurement.

    NaN needs the explicit check: it parses as a float perfectly well and every
    comparison against it is False, so a sentinel test alone lets it through as
    a real velocity.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return True
    return math.isnan(number) or number <= FILL_VALUE + 1.0


def blank_fill_values(rows: list[dict]) -> list[dict]:
    """Replace ERDDAP's -999999.0 sentinel with an empty cell."""
    for row in rows:
        for key in ("ve", "vn"):
            if key in row and _is_fill(row[key]):
                row[key] = ""
    return rows


def summarise(rows: list[dict]) -> dict:
    if not rows:
        return {"observations": 0, "drifters": 0, "years": {}, "with_velocity": 0}
    years = collections.Counter(r["time"][:4] for r in rows)
    return {
        "observations": len(rows),
        "drifters": len({r["ID"] for r in rows}),
        "years": dict(sorted(years.items())),
        "with_velocity": sum(1 for r in rows if r.get("ve") not in (None, "")),
    }


def _report(label: str, bbox, stats: dict) -> None:
    print(f"{label}")
    print(
        f"  bbox   [{bbox[0]:.4f}, {bbox[1]:.4f}, {bbox[2]:.4f}, {bbox[3]:.4f}]"
    )
    print(f"  {stats['observations']} observations from {stats['drifters']} drifters")
    if stats.get("with_velocity") is not None and stats["observations"]:
        print(
            f"  {stats['with_velocity']} carry a measured velocity "
            f"({stats['with_velocity'] / stats['observations']:.0%})"
        )
    if stats["years"]:
        span = f"{min(stats['years'])}-{max(stats['years'])}"
        print(f"  years  {span}: {stats['years']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default="gulf_of_honduras")
    ap.add_argument("--buffer-km", type=float, default=DEFAULT_BUFFER_KM)
    ap.add_argument("--start", default=None, help="YYYY-MM-DD (default: all years)")
    ap.add_argument("--end", default=None)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument(
        "--survey",
        action="store_true",
        help="report coverage at the bare bbox and the buffered one, write nothing",
    )
    args = ap.parse_args()

    try:
        bare = _region_bbox(args.region)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    buffered = _buffered_bbox(bare, args.buffer_km)

    try:
        if args.survey:
            _report("Bare region bbox, all years:", bare, summarise(fetch(build_query(bare))))
            print()
            _report(
                f"Buffered +{args.buffer_km:.0f} km, all years:",
                buffered,
                summarise(fetch(build_query(buffered))),
            )
            entry = get_region(args.region)
            window = entry["time_window"]
            demo = summarise(
                fetch(build_query(bare, start=str(window["start"]), end=str(window["end"])))
            )
            print(
                f"\nInside the demo window {window['start']}..{window['end']}: "
                f"{demo['observations']} observations"
            )
            if demo["observations"] == 0:
                print(
                    "  -> No drifter passed through this region during the demo window,\n"
                    "     so drift validation cannot be contemporaneous with the demo run.\n"
                    "     Report it as a model check over the years the region does have."
                )
            return 0

        rows = blank_fill_values(fetch(build_query(buffered, start=args.start, end=args.end)))
        if not rows:
            raise FetchError(
                f"No drifter observations for {args.region!r} within "
                f"{args.buffer_km:.0f} km. Widen --buffer-km or drop --start/--end."
            )

        args.out_dir.mkdir(parents=True, exist_ok=True)
        out = args.out_dir / f"{args.region}.csv"
        with out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
            writer.writeheader()
            writer.writerows({k: r.get(k, "") for k in COLUMNS} for r in rows)

        stats = summarise(rows)
        _report(f"Wrote {out.relative_to(REPO_ROOT)}", buffered, stats)
        print(f"  buffer {args.buffer_km:.0f} km around the {args.region} bbox")
        print(f"  {out.stat().st_size / 1024:.1f} KB")
        print(
            "\nNOTE: this is one of two inputs the PRD §12 drift-validation bullet\n"
            "needs. The other is a real current field to predict with — OSCAR, via\n"
            "drift.load_oscar_field(), which needs EARTHDATA_TOKEN."
        )
    except FetchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
