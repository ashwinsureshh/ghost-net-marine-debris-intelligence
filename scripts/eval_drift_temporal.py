"""Paired temporal-current model check; method in docs/drift-comparison-protocol.md."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from eval_drift import load_tracks, usable_segments  # noqa: E402
from ghostnet.agents.drift import load_oscar_field, run_trajectory  # noqa: E402
from ghostnet.config import get_region  # noqa: E402
from ghostnet.geo import haversine_km  # noqa: E402
from ghostnet.schemas import Detection  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", required=True, type=Path)
    args = parser.parse_args()
    start, end = datetime(2014, 4, 1, tzinfo=UTC), datetime(2014, 9, 30, 23, 59, 59, tzinfo=UTC)
    region = "gulf_of_honduras"
    bbox = tuple(get_region(region)["bbox"])
    tracks = load_tracks(region)
    segments = usable_segments(tracks, start, end, 7)
    fields = {
        "mean": load_oscar_field(start, end, bbox=bbox),
        "temporal": load_oscar_field(start, end, bbox=bbox, time_varying=True),
    }
    records, excluded = [], []
    for buoy, points in segments:
        first = points[0]
        detection = Detection(id=f"drifter-{buoy}", tile_id=f"GDP-{buoy}",
                              acquired_at=first["t"], lon=first["lon"], lat=first["lat"],
                              area_px=1, area_km2=0, fdi_mean=0, ndvi_mean=0, confidence=1)
        try:
            predictions = {key: run_trajectory(detection, field, direction="forward",
                                              horizon_days=7) for key, field in fields.items()}
        except ValueError as exc:
            excluded.append({"buoy": buoy, "reason": str(exc)})
            continue
        rows = []
        for observed in points[1:]:
            hours = (observed["t"] - first["t"]).total_seconds()/3600
            row = {"hours": hours}
            for key, prediction in predictions.items():
                nearest = min(prediction.points,
                              key=lambda p: abs((p.t-observed["t"]).total_seconds()))
                row[key] = {
                    "error_km": haversine_km(nearest.lon, nearest.lat,
                                              observed["lon"], observed["lat"]),
                    "radius_km": nearest.uncertainty_km,
                }
            rows.append(row)
        records.append({"buoy": buoy, "observations": rows})
        print(f"paired {buoy}: {len(rows)} observations", flush=True)

    if not records:
        raise ValueError("No paired trajectories; refusing empty results")
    summaries = {}
    for horizon in (24, 48, 72, 96, 120, 168):
        eligible = [r for r in records if any(abs(o["hours"]-horizon) < 1e-6
                                            for o in r["observations"])]
        arms = {}
        for key in fields:
            values = [[o[key] for o in r["observations"] if o["hours"] <= horizon]
                      for r in eligible]
            arms[key] = {
                "n_tracks": len(values), "n_observations": sum(map(len, values)),
                "mean_track_error_km": statistics.fmean(
                    statistics.fmean(v["error_km"] for v in row) for row in values
                ) if values else None,
                "mean_endpoint_error_km": statistics.fmean(row[-1]["error_km"] for row in values)
                if values else None,
                "mean_track_envelope_coverage": statistics.fmean(
                    statistics.fmean(v["error_km"] <= v["radius_km"] for v in row)
                    for row in values) if values else None,
                "mean_track_envelope_radius_km": statistics.fmean(
                    statistics.fmean(v["radius_km"] for v in row) for row in values
                ) if values else None,
            }
        summaries[str(horizon)] = arms
    source = ROOT / "data/drifters" / f"{region}.csv"
    output = {
        "region": region, "window_is_demo_window": False,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "drifter_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "current_fields": {k: v.name for k, v in fields.items()},
        "n_paired_tracks": len(records), "paired_exclusions": excluded,
        "horizons_hours": summaries, "tracks": records,
        "caveats": [
            "Other-year drogued-buoy model check, not validation of demo debris trajectories.",
            "Temporal interpolation of existing approximately six-day snapshots, not daily data.",
            "Identical observations per arm at each horizon; track count changes with horizon.",
            "Uncalibrated original ensemble; coverage and width are both reported.",
            "Spatial edge clamping and zero-filled land remain approximations in both arms.",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {args.json}")


if __name__ == "__main__":
    main()
