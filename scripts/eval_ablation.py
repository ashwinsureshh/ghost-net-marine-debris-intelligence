"""PRD §12 — the system-level ablation, on REAL inputs.

    python scripts/eval_ablation.py --region gulf_of_honduras --detector cnn \
        --allow-degraded --json eval/ablation_system.json

WORKSTATION ONLY: needs the real datasets and, for ``--detector cnn``, the
checkpoint and a GPU.

PRD §12 asks for *"an ablation study showing pipeline output degrades in a
specific, explainable way when each agent is individually removed"*. Two words
in that sentence do the work:

* **specific** — it is not enough that a score drops. Each removal has to name
  the capability that went missing, which is why this reports every run's
  ``degradations`` text alongside its numbers.
* **explainable** — a drop with no stated mechanism is an observation, not a
  finding.

``ghostnet.pipeline.run_ablation_study`` has existed since the pipeline was
built, but had only ever run on the synthetic demo scene, whose numbers are
illustrative and must not be quoted. This runs it on the real Gulf of Honduras
artefact inputs.

**Expect at least one agent whose removal does NOT degrade the pipeline.**
FR-2.2 multi-temporal consistency is measured inert (eval/results.md), and the
PRD records it as a measured exception to the every-agent-is-load-bearing
design test. An ablation that showed every agent mattering would contradict a
result this project already published, so it would be evidence of a bug in this
harness rather than a good outcome.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from ghostnet.config import DataUnavailableError  # noqa: E402
from ghostnet.pipeline import AGENT_NAMES, run_ablation_study  # noqa: E402


def summarise(run: Any) -> dict[str, Any]:
    """The output shape an operator would actually notice changing."""
    plan = getattr(run, "plan", None)
    verifications = getattr(run, "verifications", []) or []
    return {
        "detections": len(getattr(run, "detections", []) or []),
        "verified": sum(1 for v in verifications if v.verified),
        "rejected": sum(1 for v in verifications if not v.verified),
        "trajectories_forward": len(getattr(run, "forward", {}) or {}),
        "attributions": len(getattr(run, "attributions", {}) or {}),
        "dispatched": len(plan.assignments) if plan else 0,
        "deferred": len(plan.deferred) if plan else 0,
        "top_score": round(plan.assignments[0].score, 4)
        if plan and plan.assignments
        else None,
        "degradations": list(getattr(run, "degradations", []) or []),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", default="gulf_of_honduras")
    ap.add_argument("--detector", choices=["fdi", "cnn"], default="cnn")
    ap.add_argument("--step-hours", type=float, default=12.0)
    ap.add_argument("--allow-degraded", action="store_true")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    from export_run import real_config  # type: ignore

    try:
        config, region, _protected, missing = real_config(
            args.region,
            allow_degraded=args.allow_degraded,
            detector=args.detector,
            step_hours=args.step_hours,
        )
    except DataUnavailableError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"region   : {region.name}")
    print(f"detector : {args.detector}")
    if missing:
        print(f"NOTE     : {', '.join(missing)} absent, so the agents needing them are "
              "already degraded BEFORE any ablation. Their rows measure the "
              "removal of an agent that was not fully working.")
    print(f"\nrunning {len(AGENT_NAMES) + 1} pipelines (full + one per agent)...\n", flush=True)

    runs = run_ablation_study(config)
    rows = {name: summarise(run) for name, run in runs.items()}
    full = rows["full"]

    width = max(len(n) for n in rows)
    print(f"{'variant':<{width}}  {'disp':>5} {'verif':>6} {'rej':>6} {'attrib':>7} {'top':>7}")
    for name, row in rows.items():
        top = f"{row['top_score']:.3f}" if row["top_score"] is not None else "  —  "
        print(f"{name:<{width}}  {row['dispatched']:5d} {row['verified']:6d} "
              f"{row['rejected']:6d} {row['attributions']:7d} {top:>7}")

    print("\nwhat each removal actually costs:")
    for agent in AGENT_NAMES:
        row = rows.get(f"without_{agent}")
        if not row:
            continue
        changed = [
            k for k in ("dispatched", "verified", "rejected", "attributions", "top_score")
            if row[k] != full[k]
        ]
        verdict = "CHANGES " + ", ".join(changed) if changed else "NO MEASURABLE CHANGE"
        print(f"\n  {agent}: {verdict}")
        # The specific capability that went missing — the half of PRD §12 that
        # a score table alone cannot show.
        for note in row["degradations"]:
            if note not in full["degradations"]:
                print(f"      - {note[:150]}")

    out = {
        "region": args.region,
        "detector": args.detector,
        "inputs_degraded_before_ablation": missing,
        "runs": rows,
        "caveats": [
            "Run on real Gulf of Honduras inputs, not the synthetic demo scene.",
            "An agent whose inputs were already absent (see "
            "inputs_degraded_before_ablation) cannot show its full contribution "
            "here — its row measures removing an agent that was already starved.",
            "At least one agent is expected to show NO measurable change: FR-2.2 "
            "multi-temporal consistency is separately measured as inert, and PRD "
            "§12 records that as an exception to the every-agent-is-load-bearing "
            "test. Every agent mattering would contradict a published result.",
        ],
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
