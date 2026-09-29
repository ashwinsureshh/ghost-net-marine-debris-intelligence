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
import base64
import json
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghostnet.llm import RationaleWriter  # noqa: E402
from ghostnet.robustness import robustness_for  # noqa: E402
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
    robustness: dict[str, dict] = {}

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

        robustness[run_id] = robustness_for(run_id, store.paths().get(run_id))

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
        "robustness": robustness,
    }


_SCRIPT_TAG = re.compile(r'<script type="module"[^>]*\ssrc="\./(assets/[^"]+\.js)"[^>]*></script>')
_STYLE_TAG = re.compile(r'<link rel="stylesheet"[^>]*\shref="\./(assets/[^"]+\.css)"[^>]*>')
_CSS_URL = re.compile(r"url\(\./([^)]+?\.woff2)\)")


def inline_assets(html: str, dist: Path) -> str:
    """Make index.html self-contained so it runs from file:// in Chromium.

    Vite emits ``<script type="module" crossorigin src=...>`` and a crossorigin
    stylesheet. A page opened from file:// has a null origin, so Chrome and Edge
    block both under CORS and the export renders blank — the exact failure the
    offline fallback exists to survive. Inline code and data-URI fonts fetch
    nothing, so no CORS check applies. Everything else in dist stays on disk.
    """
    def script(match: re.Match) -> str:
        code = (dist / match.group(1)).read_text(encoding="utf-8")
        # "</script" inside the bundle would end the tag early.
        return '<script type="module">' + code.replace("</script", "<\\/script") + "</script>"

    def style(match: re.Match) -> str:
        css_path = dist / match.group(1)
        css = css_path.read_text(encoding="utf-8")

        def font(m: re.Match) -> str:
            data = base64.b64encode((css_path.parent / m.group(1)).read_bytes()).decode("ascii")
            return f"url(data:font/woff2;base64,{data})"

        return "<style>" + _CSS_URL.sub(font, css).replace("</style", "<\\/style") + "</style>"

    html, scripts = _SCRIPT_TAG.subn(script, html)
    html, styles = _STYLE_TAG.subn(style, html)
    if scripts != 1 or styles != 1:
        raise ValueError(
            f"Expected one module script and one stylesheet in dist/index.html, found "
            f"{scripts} and {styles}; the build layout changed, so inlining is unsafe."
        )
    return html


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
    html = inline_assets(index.read_text(encoding="utf-8"), DIST)
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

    out = Path(args.out).resolve()  # relative --out used to crash the final print
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(DIST, out)

    # `</script>` inside JSON would close the tag early; escaping the slash is
    # the standard fix and stays valid JSON.
    payload = json.dumps(bundle, separators=(",", ":")).replace("</", "<\\/")
    injected = (
        f'<script id="ghostnet-static-data">window.__GHOSTNET_STATIC__={payload};</script>\n    '
    )
    # Explicit UTF-8 both ways: the platform default on Windows is cp1252, which
    # only round-trips the built HTML by luck and fails on some characters.
    (out / "index.html").write_text(html.replace(MARKER, injected + MARKER, 1), encoding="utf-8")

    size_mb = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1_048_576
    try:
        shown = out.relative_to(REPO_ROOT)
    except ValueError:
        shown = out
    print(f"Wrote {shown}/  ({size_mb:.1f} MB, {len(bundle['runs'])} run(s))")
    print(f"  open {shown}/index.html")
    print("  Works with no server and no network. Read-only: approval (FR-6.4)")
    print("  and live ablation need the deployed app.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
