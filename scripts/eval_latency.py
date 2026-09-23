"""PRD §8 / §12 — end-to-end demo latency for one monitored region.

    python scripts/eval_latency.py --region gulf_of_honduras --detector cnn \
        --allow-degraded --json eval/latency.json

WORKSTATION ONLY: needs the real datasets and, for the CNN, a GPU.

PRD §8 sets the target: *"one monitored region's full pipeline run should
complete in a demo-appropriate time (target: well under an hour) on available
GPU/cloud resources"*, measured **from raw tile ingestion to output** — so the
number that matters includes the network, not just the compute.

Method
------
Three phases are timed separately because they fail and scale for different
reasons:

* **ingest** — streaming Sentinel-2 from a public STAC catalogue. Network
  bound, and on this project's measurements the dominant term. It is the only
  phase whose cost depends on someone else's server.
* **pipeline** — the six agents, broken down per node. The agent functions are
  wrapped here rather than instrumented in ``pipeline.py``: timing is a
  measurement concern, and adding stopwatches to the graph would put
  measurement code on the path of every real run.
* **export** — assembling and writing the artefact.

The breakdown matters more than the total. A number that is 90% network says
something different about the system than one that is 90% inference, and only
the second is improved by a faster GPU.

Caveat this reports and the report must carry: **tile streaming is cached by
the OS and by any prior run in the same session.** A warm run understates
ingest badly. Use ``--cold`` notes in the output to say which was measured;
this script cannot clear someone else's CDN.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from ghostnet import pipeline as pipeline_mod  # noqa: E402
from ghostnet.config import DataUnavailableError  # noqa: E402
from ghostnet.export import export_run, write_artefact  # noqa: E402


def instrument() -> dict[str, float]:
    """Wrap each agent node with a stopwatch. Returns the dict it fills.

    Patches ``pipeline.NODES``, NOT the module-level function attributes.
    ``NODES`` is a dict built at import time holding direct references, and
    ``build_graph()`` reads from it — so rebinding ``pipeline.node_detection``
    leaves the graph pointing at the original and the breakdown comes back
    silently empty. It did, on the first run of this script.
    """
    timings: dict[str, float] = {}

    def wrap(name: str, original):
        def timed(state):
            t0 = time.perf_counter()
            try:
                return original(state)
            finally:
                timings[name] = timings.get(name, 0.0) + time.perf_counter() - t0

        return timed

    for name, fn in list(pipeline_mod.NODES.items()):
        pipeline_mod.NODES[name] = wrap(name, fn)
    return timings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", default="gulf_of_honduras")
    ap.add_argument("--detector", choices=["fdi", "cnn"], default="cnn")
    ap.add_argument("--step-hours", type=float, default=12.0)
    ap.add_argument("--allow-degraded", action="store_true")
    ap.add_argument("--cold", action="store_true",
                    help="assert this was a cold run (nothing cached); recorded, not enforced")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    from export_run import real_config  # type: ignore

    timings = instrument()

    print("timing one full region run, from tile ingestion to artefact...\n", flush=True)
    t_total = time.perf_counter()

    t0 = time.perf_counter()
    try:
        config, region, protected, missing = real_config(
            args.region,
            allow_degraded=args.allow_degraded,
            detector=args.detector,
            step_hours=args.step_hours,
        )
    except DataUnavailableError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    ingest_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    run = pipeline_mod.run_pipeline(config)
    pipeline_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    artefact = export_run(
        run, run_id=region.id, region=region, generated_on="workstation",
        inputs_are_synthetic=False, protected_areas=protected,
        notes=["Latency measurement output; not a replacement for the served run."],
    )
    with tempfile.TemporaryDirectory(prefix="ghostnet-latency-") as directory:
        written = write_artefact(artefact, Path(directory))
        export_bytes = written.stat().st_size
    export_s = time.perf_counter() - t0
    total_s = time.perf_counter() - t_total

    if not timings:
        # A silently empty breakdown is worse than a failure: the total still
        # prints and looks like a complete result.
        print(
            "ERROR: no per-node timings were collected, so the instrumentation "
            "did not reach the graph. The total above is valid but the "
            "breakdown -- which is the point -- is missing. Refusing to write "
            "a partial artefact.",
            file=sys.stderr,
        )
        return 2

    rows = sorted(timings.items(), key=lambda kv: -kv[1])
    print(f"{'phase':<18} {'seconds':>9}  {'% of total':>10}")
    print(f"{'ingest (network)':<18} {ingest_s:9.1f}  {ingest_s/total_s:9.1%}")
    for name, seconds in rows:
        print(f"  {name:<16} {seconds:9.1f}  {seconds/total_s:9.1%}")
    print(f"{'export':<18} {export_s:9.1f}  {export_s/total_s:9.1%}")
    print(f"{'-'*40}")
    print(f"{'TOTAL':<18} {total_s:9.1f}  ({total_s/60:.1f} min)")

    target_s = 3600.0
    verdict = "WELL UNDER" if total_s < target_s / 2 else (
        "under" if total_s < target_s else "OVER")
    print(f"\nPRD §8 target: well under an hour. Measured {total_s/60:.1f} min "
          f"-> {verdict} target.")
    if not args.cold:
        print("\nNOTE: run WITHOUT --cold. Cache state was not controlled; "
              "this is not a cold-start performance measurement.")

    out: dict[str, Any] = {
        "region": args.region,
        "detector": args.detector,
        "cold_run_asserted": args.cold,
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "detections": len(run.detections),
        "verified": sum(1 for v in run.verifications if v.verified),
        "inputs_degraded": missing,
        "export_bytes": export_bytes,
        "seconds": {
            "ingest": round(ingest_s, 2),
            **{k: round(v, 2) for k, v in timings.items()},
            "pipeline_total": round(pipeline_s, 2),
            "export": round(export_s, 2),
            "total": round(total_s, 2),
        },
        "prd_target_seconds": target_s,
        "meets_target": total_s < target_s,
        "caveats": [
            "Measured from raw tile ingestion through artifact assembly and "
            "local serialization; does not include deployment or browser rendering. "
            "The historical baseline excluded serialization, so scopes differ.",
            "Cache state is not independently controlled by this script. The "
            "cold flag is a caller assertion, not proof of uncached ingestion.",
            "One region, one run, one machine. The machine block records which.",
            "The split matters more than the total: a network-dominated number "
            "is not improved by a faster GPU.",
        ],
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
