"""Post-hoc radius calibration on separate buoys; never modifies served trajectories."""

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ghostnet.evidence_hash import TEXT_HASH_METHOD, text_evidence_sha256  # noqa: E402
from ghostnet.uncertainty import fit_radius_multiplier, split_buoys  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.input.read_text("utf-8"))["tracks"]
    calibration, held_out = split_buoys([r["buoy"] for r in records])
    arms = {}
    for arm in ("mean", "temporal"):
        training = [o[arm] for r in records if r["buoy"] in calibration
                    for o in r["observations"]]
        factor = fit_radius_multiplier([o["error_km"] for o in training],
                                       [o["radius_km"] for o in training])
        evaluation = [[o[arm] for o in r["observations"]]
                      for r in records if r["buoy"] in held_out]
        arms[arm] = {
            "radius_multiplier": factor,
            "calibration_observations": len(training),
            "evaluation_observations": sum(map(len, evaluation)),
            "uncalibrated_track_mean_coverage": statistics.fmean(
                statistics.fmean(o["error_km"] <= o["radius_km"] for o in row)
                for row in evaluation),
            "calibrated_track_mean_coverage": statistics.fmean(
                statistics.fmean(o["error_km"] <= factor * o["radius_km"] for o in row)
                for row in evaluation),
            "calibrated_track_mean_radius_km": statistics.fmean(
                statistics.fmean(factor * o["radius_km"] for o in row) for row in evaluation),
        }
    output = {
        "source_sha256": text_evidence_sha256(args.input),
        "source_hash_method": TEXT_HASH_METHOD,
        "calibration_buoys": calibration, "evaluation_buoys": held_out,
        "target_empirical_coverage": .90, "arms": arms,
        "caveats": [
            "Internal buoy-ID holdout on previously inspected historical data, "
            "not external validation.",
            "Post-hoc radius dilation, not a change to physical ensemble "
            "trajectories or mean paths.",
            "Calibration pools observations; evaluation averages per track. No coverage guarantee.",
            "Wider envelopes can be less useful. Report width with coverage, never coverage alone.",
            "Served runs are unchanged; experimental calibration is not deployed.",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(output, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
