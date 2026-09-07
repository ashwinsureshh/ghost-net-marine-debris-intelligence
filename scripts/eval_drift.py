"""FR-3 / PRD §12 — validate predicted drift against real NOAA drifter paths.

    python scripts/eval_drift.py --region gulf_of_honduras --json eval/drift.json
    python scripts/eval_drift.py --region gulf_of_honduras --survey

WORKSTATION ONLY: needs ``data/oscar`` and ``data/drifters``, which are
workstation-local by MACHINE-WORKFLOW.md.

What this measures, and what it does NOT
----------------------------------------
Each usable drifter track is treated as an experiment. The drifter's first
position seeds :func:`drift.run_trajectory` on the real OSCAR field; the
predicted track is then compared against where that buoy actually went, via
:func:`drift.mean_track_error_km`. A satellite detection has no ground truth
about where it drifted, so a buoy is the only object in the water whose real
path we know.

**THIS IS A MODEL CHECK OVER OTHER PERIODS, NOT A VALIDATION OF THE DEMO RUN,
and the distinction is not pedantry — it is forced by the data.** Zero drifter
observations fall inside the Gulf of Honduras bbox during the demo window; the
buoys that exist are in other years, and the fetch uses a 300 km buffer to get
a usable sample at all. So the honest claim is "the drift model reproduces real
buoy paths in this current system to within X km", never "the demo run's
trajectories are validated". Every report line this produces says so.

Three limits that shape the numbers
-----------------------------------
1. **The current field is a time-MEAN.** ``GriddedCurrentField`` has no time
   axis, so a months-long OSCAR window collapses to one field and seasonal
   reversals average out. Error therefore grows with horizon faster than a
   time-varying field would produce. The field's ``name`` records what was
   averaged, and it is copied into the output.
2. **Only periods with BOTH OSCAR and buoys can be scored.** OSCAR is fetched
   per window (``scripts/fetch_oscar.py``); a period with buoys but no
   downloaded currents is skipped and counted, never silently dropped.
3. **A drifter is drogued or undrogued.** A drogued buoy follows the 15 m
   current, which is what OSCAR models; once the drogue is lost it is pushed by
   wind and slip and is a different object. ``drogue_lost_date`` is respected —
   observations after it are excluded, and the count is reported.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
import statistics
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghostnet.agents.drift import (  # noqa: E402
    mean_track_error_km,
    run_trajectory,
)
from ghostnet.config import DataUnavailableError, dataset_path, get_region  # noqa: E402
from ghostnet.schemas import Detection  # noqa: E402

#: A track needs enough points to be worth integrating against. The product is
#: 6-hourly, so 8 observations is two days.
MIN_OBSERVATIONS = 8

#: Horizon to predict. Matches the pipeline's forward default, so the number
#: this reports is the accuracy of the track the console actually draws.
DEFAULT_HORIZON_DAYS = 7.0


def _utc(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_tracks(region_id: str) -> dict[str, list[dict[str, Any]]]:
    """Group the drifter CSV into per-buoy tracks, drogued observations only."""
    path = dataset_path("drifters", required=True, purpose="Drift validation (FR-3, PRD §12).")
    matches = sorted(path.glob(f"{region_id}.csv")) or sorted(path.glob("*.csv"))
    if not matches:
        raise DataUnavailableError(
            "drifters",
            path,
            message=(
                f"No drifter CSV for region {region_id!r} in {path}. Fetch it with "
                f"`python scripts/fetch_drifters.py --region {region_id}`."
            ),
        )
    rows = list(csv.DictReader(matches[0].open(encoding="utf-8")))

    tracks: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    undrogued = 0
    for row in rows:
        try:
            when = _utc(row["time"])
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (KeyError, ValueError):
            continue
        # A buoy that has shed its drogue is wind-driven, not current-driven,
        # and OSCAR models the current. Scoring it would measure the wrong
        # thing and would flatter or damn the model for the wrong reason.
        lost = (row.get("drogue_lost_date") or "").strip()
        if lost:
            try:
                if when >= _utc(lost):
                    undrogued += 1
                    continue
            except ValueError:
                pass
        tracks[row["ID"]].append({"t": when, "lon": lon, "lat": lat})

    for points in tracks.values():
        points.sort(key=lambda p: p["t"])
    tracks["__undrogued_excluded__"] = [{"n": undrogued}]  # carried out-of-band
    return tracks


def usable_segments(
    tracks: dict[str, list[dict[str, Any]]],
    start: dt.datetime,
    end: dt.datetime,
    horizon_days: float,
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Per-buoy observation runs inside the window, long enough to score."""
    out = []
    for buoy, points in tracks.items():
        if buoy.startswith("__"):
            continue
        inside = [p for p in points if start <= p["t"] <= end]
        if len(inside) < MIN_OBSERVATIONS:
            continue
        # Trim to the horizon: comparing a 7-day prediction against 18 days of
        # buoy track would score the model on time it never claimed to cover.
        t0 = inside[0]["t"]
        clipped = [p for p in inside if (p["t"] - t0).total_seconds() <= horizon_days * 86400]
        if len(clipped) >= MIN_OBSERVATIONS:
            out.append((buoy, clipped))
    return out


def evaluate(
    region_id: str,
    horizon_days: float,
    verbose: bool,
    window_start: str | None = None,
    window_end: str | None = None,
) -> dict[str, Any]:
    from ghostnet.agents.drift import load_oscar_field

    entry = get_region(region_id)
    bbox = tuple(entry["bbox"])
    # The validation window is separate from the DEMO window on purpose, and
    # defaults to it only for convenience. Zero drifters crossed this region
    # during the demo window, so a real validation almost always runs somewhere
    # else — that is the "model check over other years" framing, made explicit
    # in the interface rather than left as a footnote.
    demo = entry["time_window"]
    window = {
        "start": window_start or str(demo["start"]),
        "end": window_end or str(demo["end"]),
    }
    is_demo_window = (window["start"], window["end"]) == (
        str(demo["start"]), str(demo["end"]),
    )
    start = _utc(f"{window['start']}T00:00:00Z")
    end = _utc(f"{window['end']}T23:59:59Z")

    tracks = load_tracks(region_id)
    undrogued = tracks["__undrogued_excluded__"][0]["n"]
    segments = usable_segments(tracks, start, end, horizon_days)
    if not segments:
        raise SystemExit(
            f"No drifter track in {region_id} has {MIN_OBSERVATIONS}+ drogued "
            f"observations inside {window['start']}..{window['end']}. Widen the "
            "window, or fetch OSCAR for a period the buoys actually cover."
        )

    field = load_oscar_field(start, end, bbox=bbox)
    if verbose:
        print(f"region        : {entry.get('name', region_id)}")
        print(f"window        : {window['start']} .. {window['end']}")
        print(f"current field : {field.name}")
        print(f"segments      : {len(segments)} buoy track(s), {undrogued} undrogued obs excluded")
        print()

    results = []
    for buoy, points in segments:
        seed = points[0]
        # The trajectory integrator takes a Detection; the buoy's first fix is
        # the "detection" whose future we are predicting.
        # A synthetic seed, not a claim about imagery. run_trajectory takes a
        # Detection because that is what it advects in the pipeline; here the
        # buoy's first fix plays that role. The spectral fields are zero
        # because no imagery is involved, and `detector` stays "fdi" only
        # because the schema allows nothing else — the id says plainly what
        # this is, and nothing here is written to a run artefact.
        detection = Detection(
            id=f"drifter-{buoy}",
            tile_id=f"GDP-{buoy}",
            acquired_at=seed["t"],
            lon=seed["lon"],
            lat=seed["lat"],
            area_px=1,
            area_km2=0.0,
            fdi_mean=0.0,
            ndvi_mean=0.0,
            confidence=1.0,
        )
        predicted = run_trajectory(
            detection,
            field,
            direction="forward",
            horizon_days=horizon_days,
        )
        observed = [(p["t"], p["lon"], p["lat"]) for p in points[1:]]
        stats = mean_track_error_km(predicted, observed)
        span_h = (points[-1]["t"] - seed["t"]).total_seconds() / 3600.0
        stats |= {"drifter_id": buoy, "span_hours": round(span_h, 1),
                  "start": seed["t"].isoformat()}
        results.append(stats)
        if verbose:
            print(f"  {buoy:>16s}  {stats['n_observations']:3.0f} obs over "
                  f"{span_h/24:4.1f} d   mean {stats['mean_error_km']:7.2f} km   "
                  f"median {stats['median_error_km']:7.2f} km   "
                  f"in envelope {stats['fraction_within_envelope']:.0%}")

    means = [r["mean_error_km"] for r in results]
    inside = [r["fraction_within_envelope"] for r in results]
    summary = {
        "region": region_id,
        "region_name": entry.get("name", region_id),
        "window": {"start": window["start"], "end": window["end"]},
        "window_is_demo_window": is_demo_window,
        "horizon_days": horizon_days,
        "current_field": field.name,
        "n_tracks": len(results),
        "n_observations": int(sum(r["n_observations"] for r in results)),
        "undrogued_observations_excluded": undrogued,
        "mean_track_error_km": round(statistics.fmean(means), 3),
        "median_track_error_km": round(statistics.median(means), 3),
        "worst_track_error_km": round(max(means), 3),
        "mean_fraction_within_envelope": round(statistics.fmean(inside), 4),
        "tracks": results,
        "caveats": [
            "NOT a validation of the demo run. Zero drifter observations fall "
            "inside this region's bbox during the demo window, so this is a "
            "model check over the periods the region does have — the same way "
            "the MARIDA benchmark is independent of the demo window.",
            "The drifter sample comes from the region bbox plus a 300 km "
            "buffer (scripts/fetch_drifters.py). It characterises the same "
            "current system, not this bbox alone.",
            "The OSCAR field is a TIME-MEAN over the window, so seasonal "
            "reversals average out and error grows with horizon faster than a "
            "time-varying field would give. The field name records what was "
            "averaged.",
            "Undrogued observations are excluded: a buoy that has shed its "
            "drogue is wind-driven, and OSCAR models the 15 m current.",
            f"{len(results)} track(s) is a small sample. Quote the spread, not "
            "just the mean.",
        ],
    }
    return summary


def survey(region_id: str) -> int:
    """What could be scored, before committing to a run."""
    tracks = load_tracks(region_id)
    undrogued = tracks["__undrogued_excluded__"][0]["n"]
    by_year: dict[str, int] = collections.Counter()
    for buoy, points in tracks.items():
        if buoy.startswith("__"):
            continue
        for p in points:
            by_year[str(p["t"].year)] += 1
    oscar = sorted({f.name[-11:-3] for f in (REPO_ROOT / "data" / "oscar").glob("*.nc")})
    have = {d[:4] for d in oscar}
    print(f"drogued observations by year ({undrogued} undrogued excluded):")
    for year in sorted(by_year):
        mark = "  <- OSCAR on disk" if year in have else ""
        print(f"   {year}: {by_year[year]:5d}{mark}")
    print(f"\nOSCAR days on disk: {len(oscar)}"
          + (f" ({oscar[0]} .. {oscar[-1]})" if oscar else ""))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", default="gulf_of_honduras")
    ap.add_argument("--horizon-days", type=float, default=DEFAULT_HORIZON_DAYS)
    ap.add_argument("--start", help="validation window start, YYYY-MM-DD "
                                    "(default: the region's demo window)")
    ap.add_argument("--end", help="validation window end, YYYY-MM-DD")
    ap.add_argument("--survey", action="store_true",
                    help="report what could be scored, and run nothing")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    try:
        if args.survey:
            return survey(args.region)
        out = evaluate(
            args.region,
            args.horizon_days,
            verbose=not args.quiet,
            window_start=args.start,
            window_end=args.end,
        )
    except DataUnavailableError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        print()
        print(f"  MEAN TRACK ERROR      {out['mean_track_error_km']:8.2f} km"
              f"   over {out['n_tracks']} track(s), {out['n_observations']} observations")
        print(f"  median / worst        {out['median_track_error_km']:8.2f} / "
              f"{out['worst_track_error_km']:.2f} km")
        print(f"  within envelope       {out['mean_fraction_within_envelope']:8.1%}")
        print()
        print("  READ BEFORE QUOTING:")
        for caveat in out["caveats"]:
            print(f"    - {caveat}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
