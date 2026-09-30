"""Fit eddy diffusivity K on calibration buoys; evaluate on held-out buoys.

    python scripts/calibrate_drift_diffusivity.py --json eval/drift_diffusivity.json

Method frozen in docs/drift-diffusivity-protocol.md before any outcome was
computed. Same buoys, segments, horizon, seed, ensemble and time-mean field as
the mean arm of eval/drift_temporal.json; same ID-hash split as
eval/drift_calibration.json, whose radius multiplier is the comparison.
Served runs and the production default (K = 0) are not changed.
"""

from __future__ import annotations

import argparse
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
from ghostnet.evidence_hash import TEXT_HASH_METHOD, text_evidence_sha256  # noqa: E402
from ghostnet.geo import haversine_km  # noqa: E402
from ghostnet.schemas import Detection  # noqa: E402
from ghostnet.uncertainty import split_buoys  # noqa: E402

GRID = (0.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 10000.0)
TARGET = 0.90
HORIZONS = (24, 48, 72, 96, 120, 168)
CALIBRATION = ROOT / "eval" / "drift_calibration.json"
TEMPORAL = ROOT / "eval" / "drift_temporal.json"


def observations(segments, field, k):
    """Per buoy: list of {hours, error_km, radius_km} for one diffusivity."""
    out = {}
    for buoy, points in segments:
        first = points[0]
        det = Detection(id=f"drifter-{buoy}", tile_id=f"GDP-{buoy}", acquired_at=first["t"],
                        lon=first["lon"], lat=first["lat"], area_px=1, area_km2=0,
                        fdi_mean=0, ndvi_mean=0, confidence=1)
        traj = run_trajectory(det, field, direction="forward", horizon_days=7,
                              diffusivity_m2s=k)
        rows = []
        for obs in points[1:]:
            nearest = min(traj.points, key=lambda p: abs((p.t - obs["t"]).total_seconds()))
            rows.append({
                "hours": (obs["t"] - first["t"]).total_seconds() / 3600,
                "error_km": haversine_km(nearest.lon, nearest.lat, obs["lon"], obs["lat"]),
                "radius_km": nearest.uncertainty_km,
            })
        out[buoy] = rows
    return out


def pooled_coverage(by_buoy, buoys, scale=1.0):
    rows = [o for b in buoys for o in by_buoy[b]]
    return statistics.fmean(o["error_km"] <= scale * o["radius_km"] for o in rows)


def track_summary(by_buoy, buoys, scale=1.0, horizon=None):
    """Track-mean coverage/radius/error, optionally up to a horizon with a fix there."""
    rows = []
    for b in buoys:
        obs = by_buoy[b]
        if horizon is not None:
            if not any(abs(o["hours"] - horizon) < 1e-6 for o in obs):
                continue
            obs = [o for o in obs if o["hours"] <= horizon]
        if obs:
            rows.append(obs)
    if not rows:
        return {"n_tracks": 0}
    return {
        "n_tracks": len(rows),
        "coverage": round(statistics.fmean(
            statistics.fmean(o["error_km"] <= scale * o["radius_km"] for o in r) for r in rows), 4),
        "mean_radius_km": round(statistics.fmean(
            statistics.fmean(scale * o["radius_km"] for o in r) for r in rows), 2),
        "mean_error_km": round(statistics.fmean(
            statistics.fmean(o["error_km"] for o in r) for r in rows), 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", type=Path, required=True)
    args = ap.parse_args()

    start = datetime(2014, 4, 1, tzinfo=UTC)
    end = datetime(2014, 9, 30, 23, 59, 59, tzinfo=UTC)
    region = "gulf_of_honduras"
    field = load_oscar_field(start, end, bbox=tuple(get_region(region)["bbox"]))
    segments = usable_segments(load_tracks(region), start, end, 7)

    reference = json.loads(CALIBRATION.read_text("utf-8"))
    calibration, held_out = split_buoys([buoy for buoy, _ in segments])
    if (calibration, held_out) != (reference["calibration_buoys"], reference["evaluation_buoys"]):
        raise RuntimeError("Buoy split differs from eval/drift_calibration.json; aborting.")
    multiplier = reference["arms"]["mean"]["radius_multiplier"]

    # Reproduce the published baseline before trusting anything else.
    runs = {}
    for k in GRID:
        runs[k] = observations(segments, field, k)
        print(f"K={k:>7.0f}  calibration coverage "
              f"{pooled_coverage(runs[k], calibration):.3f}", flush=True)
    published = json.loads(TEMPORAL.read_text("utf-8"))
    base_err = statistics.fmean(
        statistics.fmean(o["error_km"] for o in runs[0.0][b]) for b in runs[0.0])
    pub_err = statistics.fmean(
        statistics.fmean(o["mean"]["error_km"] for o in r["observations"])
        for r in published["tracks"])
    if abs(base_err - pub_err) > 1e-6:
        raise RuntimeError(f"K=0 mean track error {base_err} != published {pub_err}; aborting.")

    grid = {str(int(k)): {"calibration_pooled_coverage":
                          round(pooled_coverage(runs[k], calibration), 4)} for k in GRID}
    selected = next((k for k in GRID if pooled_coverage(runs[k], calibration) >= TARGET), None)

    def arm(by_buoy, scale=1.0):
        return {"overall": track_summary(by_buoy, held_out, scale),
                "by_horizon_hours": {str(h): track_summary(by_buoy, held_out, scale, h)
                                     for h in HORIZONS}}

    evaluation = {"baseline_K0": arm(runs[0.0]),
                  "radius_multiplier": {"multiplier": multiplier, **arm(runs[0.0], multiplier)}}
    if selected is not None:
        evaluation["diffusivity"] = {"K_m2s": selected, **arm(runs[selected])}

    out = {
        "protocol": "docs/drift-diffusivity-protocol.md",
        "region": region, "window_is_demo_window": False,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "current_field": field.name,
        "reference": "eval/drift_calibration.json",
        "reference_sha256": text_evidence_sha256(CALIBRATION),
        "reference_hash_method": TEXT_HASH_METHOD,
        "baseline_reproduced": True,
        "baseline_mean_track_error_km": round(base_err, 3),
        "calibration_buoys": calibration, "evaluation_buoys": held_out,
        "target_coverage": TARGET, "grid_m2s": list(GRID),
        "calibration_grid": grid,
        "selected_K_m2s": selected,
        "evaluation": evaluation,
        "caveats": [
            "Internal buoy-ID holdout on previously inspected 2014 data; not external "
            "validation and not the demo window.",
            "K selected as the smallest grid value reaching 0.90 pooled calibration coverage; "
            "evaluation coverage is not guaranteed.",
            "Report width with coverage. Mean-path error changes only by ensemble sampling noise.",
            "Served runs and the production default (K = 0) are unchanged.",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nselected K = {selected}\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
