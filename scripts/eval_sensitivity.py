"""Weight sensitivity over immutable real run artifacts; no downloads or LLM calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ghostnet.agents.prioritisation import DEFAULT_WEIGHTS  # noqa: E402
from ghostnet.export import load_artefact  # noqa: E402
from ghostnet.sensitivity import compare_rankings, weight_variants  # noqa: E402
from ghostnet.webapp.planning import PlanningRequest, plan_from_artefact  # noqa: E402


def evaluate(path: Path) -> dict:
    artefact = load_artefact(path)
    if artefact.provenance.inputs_are_synthetic:
        raise ValueError("Research sensitivity requires a real-input artifact")
    capacity, horizon = 3, 7

    def rank(weights):
        result = plan_from_artefact(artefact, PlanningRequest(
            weights=weights, vessel_capacity=capacity, planning_horizon_days=horizon,
            include_rationales=False,
        ))
        return [s.detection_id for s in result.scores]

    baseline = rank(DEFAULT_WEIGHTS)
    rows = {}
    for name, weights in weight_variants(DEFAULT_WEIGHTS).items():
        changed = rank(weights)
        rows[name] = {"weights": weights, "top_dispatch_ids": changed[:capacity],
                      **compare_rankings(baseline, changed, capacity)}
    return {
        "region": artefact.region.id,
        "input_file": path.name,
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "inputs_degraded": list(artefact.degradations),
        "vessel_capacity": capacity, "planning_horizon_days": horizon,
        "candidate_count": len(baseline), "baseline_weights": DEFAULT_WEIGHTS,
        "baseline_ranked_ids": baseline, "variants": rows,
        "summary": {
            "variants": len(rows),
            "top1_changed": sum(r["top1_unchanged"] is False for r in rows.values()),
            "dispatch_set_changed": sum(not r["dispatch_set_unchanged"] for r in rows.values()),
        },
        "caveats": [
            "One-at-a-time relative perturbations, not a joint uncertainty analysis.",
            "Unavailable signals remain dropped and weights renormalised per candidate.",
            "Rank ties are broken by detection ID. Stability does not establish accuracy.",
            "Fixed upstream evidence; this does not test detector or drift uncertainty.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--json", required=True, type=Path)
    args = parser.parse_args()
    output = {"runs": [evaluate(path) for path in args.inputs]}
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {args.json}: {len(output['runs'])} real runs")


if __name__ == "__main__":
    main()
