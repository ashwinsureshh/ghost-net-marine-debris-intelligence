"""Build the offline static export — the viva fallback (PRD §9.1 demo risk).

Free-tier hosts cold-start and sleep, and venue wifi fails. This produces a
self-contained copy of the console that opens straight from disk with no
server, no network and no Python running:

    python scripts/build_static_export.py
    open static_export/index.html

How it works: the same Python that the server uses computes each run's plan and
rejected list ahead of time, and the results are injected into the built
frontend as ``window.__GHOSTNET_STATIC__``. ``lib/api.ts`` sees that global and
reads from it instead of calling ``/api``.

What the fallback deliberately cannot do, and says so in the UI rather than
faking:

* **Record an approval (FR-6.4)** — that is a write, and there is no server.
* **Re-run the ablation** — switching an agent off needs re-scoring. Capacity
  still works, because trimming a ranked list is something the browser can do
  honestly.

So the fallback demonstrates the pipeline's output and its reasoning, not the
live recomputation. If the deploy is up, use the deploy.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghostnet.llm import RationaleWriter  # noqa: E402
from ghostnet.webapp.app import PROTOTYPE_NOTICE  # noqa: E402
from ghostnet.webapp.app import benchmark as benchmark_endpoint  # noqa: E402
from ghostnet.webapp.app import meta as meta_endpoint  # noqa: E402
from ghostnet.webapp.planning import PlanningRequest, plan_from_artefact  # noqa: E402
from ghostnet.webapp.store import ArtefactStore  # noqa: E402

DIST = REPO_ROOT / "frontend" / "dist"
DEFAULT_OUT = REPO_ROOT / "static_export"
MARKER = '<script type="module"'


def build_bundle(store: ArtefactStore, capacity: int, horizon: int) -> dict:
    """Precompute everything the offline app reads."""
    writer = RationaleWriter()
    runs = store.summaries()
    artefacts: dict[str, dict] = {}
    plans: dict[str, dict] = {}
    rejected: dict[str, dict] = {}

    for summary in runs:
        run_id = summary["run_id"]
        if summary.get("unreadable"):
            continue
        artefact = store.get(run_id)
        if artefact is None:
            continue

        artefacts[run_id] = json.loads(artefact.model_dump_json())

        result = plan_from_artefact(
            artefact,
            PlanningRequest(vessel_capacity=capacity, planning_horizon_days=horizon),
            rationale_writer=writer,
        )
        plans[run_id] = {
            "run_id": run_id,
            "plan": json.loads(result.plan.model_dump_json()) if result.plan else None,
            "scores": [json.loads(s.model_dump_json()) for s in result.scores],
            "degradations": result.degradations,
            "considered": result.considered,
            "ablated": result.ablated,
        }

        detections = artefact.detections_by_id()
        rejected[run_id] = {
            "run_id": run_id,
            "count": len(artefact.rejected),
            "detections_total": len(artefact.detections),
            "rejected": [
                {
                    "detection": json.loads(detections[v.detection_id].model_dump_json())
                    if v.detection_id in detections
                    else None,
                    "verification": json.loads(v.model_dump_json()),
                    "reasons": v.rejection_reasons,
                    "failed_checks": [c.name for c in v.checks if c.disqualified],
                }
                for v in artefact.rejected
            ],
        }

    app_meta = meta_endpoint()
    app_meta["prototype_notice"] = (
        PROTOTYPE_NOTICE + " This is the offline export: read-only, with a plan "
        f"precomputed at {capacity}-vessel capacity."
    )

    return {
        "meta": app_meta,
        # The measured numbers travel with the fallback. They are read from a
        # committed 11 KB results file, not from MARIDA, so the offline export
        # can be as honest about detector recall as the deployed app.
        "benchmark": benchmark_endpoint(),
        "runs": runs,
        "artefacts": artefacts,
        "plans": plans,
        "rejected": rejected,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--capacity", type=int, default=3)
    parser.add_argument("--horizon", type=int, default=7)
    args = parser.parse_args()

    if not DIST.is_dir():
        print(
            "frontend/dist does not exist. Build the frontend first:\n"
            "    cd frontend && npm install && npm run build",
            file=sys.stderr,
        )
        return 2

    index = DIST / "index.html"
    html = index.read_text()
    if MARKER not in html:
        print(f"Cannot find the module script tag in {index}.", file=sys.stderr)
        return 2

    store = ArtefactStore()
    if not store.run_ids():
        print(
            "No run artefacts to export. Generate one first:\n"
            "    python scripts/export_run.py --synthetic",
            file=sys.stderr,
        )
        return 2

    bundle = build_bundle(store, args.capacity, args.horizon)

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(DIST, out)

    # `</script>` inside JSON would close the tag early; escaping the slash is
    # the standard fix and stays valid JSON.
    payload = json.dumps(bundle, separators=(",", ":")).replace("</", "<\\/")
    injected = (
        f'<script id="ghostnet-static-data">window.__GHOSTNET_STATIC__={payload};</script>\n    '
    )
    (out / "index.html").write_text(html.replace(MARKER, injected + MARKER, 1))

    size_mb = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1_048_576
    print(f"Wrote {out.relative_to(REPO_ROOT)}/  ({size_mb:.1f} MB, {len(bundle['runs'])} run(s))")
    print(f"  open {out.relative_to(REPO_ROOT)}/index.html")
    print("  Works with no server and no network. Read-only: approval (FR-6.4)")
    print("  and live ablation need the deployed app.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
