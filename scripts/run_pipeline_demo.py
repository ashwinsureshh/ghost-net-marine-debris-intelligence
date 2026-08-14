"""Run the six-agent pipeline end to end on synthetic data, then ablate it.

This exists so the orchestration can be demonstrated and inspected on a machine
with no downloaded datasets and no API credentials — which, per
MACHINE-WORKFLOW.md, is the normal state of the MacBook Air.

    python scripts/run_pipeline_demo.py             # one full run
    python scripts/run_pipeline_demo.py --ablation  # PRD §12 ablation study
    python scripts/run_pipeline_demo.py --json      # machine-readable plan

**The input is synthetic.** The tile is a generated array containing one
debris-like patch and one each of the four documented false-positive modes; the
current field is uniform and the river table is three invented rows. Numbers
printed here demonstrate that the wiring works. They are not results, and
nothing from this script belongs in eval/results.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghostnet.agents.attribution import River, RiverTable  # noqa: E402
from ghostnet.agents.detection import GeoTransform, Tile  # noqa: E402
from ghostnet.agents.drift import UniformCurrentField  # noqa: E402
from ghostnet.agents.prioritisation import ProtectedArea  # noqa: E402
from ghostnet.pipeline import (  # noqa: E402
    PipelineConfig,
    run_ablation_study,
    run_pipeline,
)
from ghostnet.schemas import VesselDetection  # noqa: E402

ACQUIRED = datetime(2026, 3, 14, 5, 30, tzinfo=UTC)
TRANSFORM = GeoTransform(lon_origin=80.0, lat_origin=12.0, lon_step=0.001, lat_step=-0.001)

SIGNATURES = {
    "water": {"B04": 0.030, "B06": 0.004, "B08": 0.002, "B11": 0.003},
    "debris": {"B04": 0.045, "B06": 0.020, "B08": 0.050, "B11": 0.010},
    "glint": {"B04": 0.090, "B06": 0.090, "B08": 0.090, "B11": 0.080},
    "foam": {"B04": 0.150, "B06": 0.100, "B08": 0.120, "B11": 0.030},
    "kelp": {"B04": 0.020, "B06": 0.050, "B08": 0.100, "B11": 0.050},
}


def synthetic_tile() -> Tile:
    bands = {k: np.full((40, 40), v) for k, v in SIGNATURES["water"].items()}
    for (row, col), kind in {
        (5, 5): "debris",
        (5, 25): "glint",
        (20, 5): "foam",
        (20, 25): "kelp",
    }.items():
        for band, value in SIGNATURES[kind].items():
            bands[band][row : row + 7, col : col + 7] = value
    return Tile(
        tile_id="SYNTHETIC-20260314",
        acquired_at=ACQUIRED,
        bands=bands,
        transform=TRANSFORM,
        source="synthetic (scripts/run_pipeline_demo.py)",
    )


def demo_config() -> PipelineConfig:
    return PipelineConfig(
        region_id="synthetic-demo",
        tiles=[synthetic_tile()],
        current_field=UniformCurrentField(u_ms=-0.25, v_ms=0.05, name="synthetic-westward"),
        river_table=RiverTable(
            rivers=[
                River("Demo Kali", 79.80, 12.05, 4200, "Synthetic"),
                River("Demo Creek", 79.82, 12.02, 90, "Synthetic"),
            ],
            source="synthetic",
        ),
        vessel_detections=[
            VesselDetection(
                id="SYN-SAR-1",
                lon=79.95,
                lat=12.02,
                detected_at=ACQUIRED - timedelta(days=2),
                length_m=26.0,
            )
        ],
        protected_areas=[
            ProtectedArea("Demo Marine Reserve", 79.70, 12.08, radius_km=8.0, designation="MPA")
        ],
        ensemble_size=32,
    )


def print_run(run) -> None:
    print(run.summary())
    print("\n  pipeline log:")
    for line in run.log:
        print(f"    - {line}")

    if run.rejected:
        print("\n  rejected detections (retained for audit, PRD §8):")
        for rejection in run.rejected:
            print(f"    - {rejection.detection_id}: {rejection.rejection_reasons[0]}")

    if run.plan and run.plan.assignments:
        print(f"\n  DISPATCH PLAN — approved: {run.plan.approved}")
        for assignment in run.plan.assignments:
            print(
                f"    {assignment.rank}. {assignment.detection_id} "
                f"({assignment.lat:.4f}, {assignment.lon:.4f}) "
                f"score {assignment.score:.3f} [{assignment.rationale_source}]"
            )
            print(f"       {assignment.rationale}")
        for caveat in run.plan.caveats:
            print(f"    ! {caveat}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ablation", action="store_true", help="run the PRD §12 study")
    parser.add_argument("--json", action="store_true", help="emit the plan as JSON")
    args = parser.parse_args()

    config = demo_config()

    print("SYNTHETIC DEMO — generated inputs, not real data. Not a result.\n")

    if args.ablation:
        runs = run_ablation_study(config)
        for name, run in runs.items():
            print("=" * 72)
            print(name)
            print("=" * 72)
            print(run.summary())
            print()
        return 0

    run = run_pipeline(config)
    if args.json:
        print(run.plan.model_dump_json(indent=2) if run.plan else json.dumps(None))
        return 0

    print_run(run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
