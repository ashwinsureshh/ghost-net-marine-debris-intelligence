# Multi-Agent Ghost Net & Marine Debris Intelligence Pipeline

A six-agent decision-support research prototype that turns a raw satellite
detection of floating ocean debris into a **verified, source-attributed,
risk-prioritised cleanup dispatch recommendation** — using only data sources
that are real, free, and already flowing today.

> This is a research prototype validated on historical and published data. It is
> not operational-grade, and every output stops at a recommendation for human
> review.

- **[PRD.md](PRD.md)** — requirements, success metrics, scope, milestones.
- **[MACHINE-WORKFLOW.md](MACHINE-WORKFLOW.md)** — how work splits across the
  workstation and the MacBook Air. **Read this first in any new session.**

## The six agents

| # | Agent | Does | Primary machine |
|---|---|---|---|
| 1 | Satellite Detection | FDI spectral index over Sentinel-2 tiles; optional CNN variant | Either / **Workstation** for CNN |
| 2 | False-Positive Verification | Actively disqualifies sun glint, foam, kelp, cloud shadow; multi-temporal consistency | Either |
| 3 | Drift | Backward/forward trajectories from NOAA OSCAR currents, with uncertainty | Either |
| 4 | Source Attribution | Ranked probability over candidate source rivers | Either |
| 5 | Dark Vessel Correlation | GFW SAR detections vs. AIS to find AIS-silent vessels | Either |
| 6 | Response Prioritisation | Capacity-constrained ranked dispatch plan with rationale | Either |

The design test throughout: removing any single agent should **break** the
system, not merely degrade it slightly.

## Getting started

**1. Find out what this machine can do.** Do not assume GPU availability —
the pipeline behaves differently on the workstation and the Air.

```bash
python scripts/check_machine.py
```

**2. Install dependencies.**

```bash
python -m pip install -r requirements-base.txt
```

On the workstation only, add the GPU stack. RTX 50-series (Blackwell) is
`sm_120` and requires a CUDA 12.8+ build — read the notes in the file before
installing:

```bash
python -m pip install -r requirements-gpu.txt --index-url https://download.pytorch.org/whl/cu128
```

**3. Add credentials.** Copy `.env.example` to `.env` and fill in the free-tier
tokens (Copernicus, Earthdata, Global Fishing Watch, Anthropic).

**4. Get the data.** Nothing large is committed. See what's present and how to
obtain what isn't:

```bash
python scripts/fetch_data.py --status
python scripts/fetch_data.py --instructions
```

**5. See the pipeline run.** No datasets or credentials needed — the inputs are
generated, so this demonstrates the wiring, not a result:

```bash
python scripts/run_pipeline_demo.py
```

```bash
python scripts/run_pipeline_demo.py --ablation
```

## Operator console (PRD §9.1)

A deployed web application is the operator-facing deliverable. Because the
datasets cannot be deployed, the workstation exports **run artefacts** and the
server recomputes only prioritisation (FR-6.1/6.2) live, generates FR-6.3
rationales server-side, and records the FR-6.4 approval.

```bash
python -m pip install -r requirements-web.txt
python scripts/export_run.py --synthetic       # or --region <id> on the workstation
cd frontend && npm install && npm run build && cd ..
uvicorn ghostnet.webapp.app:app --port 8000
```

Then open <http://localhost:8000>. During frontend work, `npm run dev` in
`frontend/` proxies `/api` to port 8000 with hot reload.

**Offline fallback for the viva** — free-tier hosts sleep and venue wifi fails,
so keep a self-contained copy on disk. It opens with no server and no network:

```bash
python scripts/build_static_export.py && open static_export/index.html
```

The export is read-only: recording an approval and re-running the ablation both
need the live server, and the UI says so rather than pretending.

**Deploying it** — one Docker image builds the frontend and serves it from the
same process, so a free tier needs one service rather than two:

```bash
docker build -t ghostnet-console . && docker run --rm -p 8000:8000 ghostnet-console
```

`render.yaml` defines the free-tier service. Setup, the free-tier caveats, and
how to publish a new run artefact are in **[DEPLOY.md](DEPLOY.md)**.

## Repository layout

```
config/regions.yaml         monitored regions, demo window, dispatch constraints
scripts/check_machine.py    CUDA / machine-role detection
scripts/fetch_data.py       where each dataset lives + how to obtain it
scripts/run_pipeline_demo.py  end-to-end run on synthetic inputs
scripts/eval_marida.py      MARIDA ablation + threshold fitting (workstation)
scripts/export_run.py       write a deployable run artefact (PRD §9.1)
scripts/build_static_export.py  offline viva fallback
src/ghostnet/schemas.py     data contracts passed between agents
src/ghostnet/pipeline.py    LangGraph orchestration + ablation study
src/ghostnet/export.py      run-artefact schema — workstation ↔ deployed app
src/ghostnet/benchmark.py   eval/results.md, reshaped for the console's metrics strip
src/ghostnet/llm.py         Claude integration for dispatch rationales
src/ghostnet/config.py      paths, region config, credentials, dataset checks
src/ghostnet/geo.py         shared geodesy helpers
src/ghostnet/agents/        the six agents (see the package docstring)
src/ghostnet/webapp/        FastAPI backend for the operator console
frontend/                   React + Tailwind operator console
webapp_data/                run artefacts served by the app
Dockerfile                  npm build + FastAPI runtime, one image (see DEPLOY.md)
render.yaml                 free-tier service definition
requirements-deploy.txt     server-only subset — no geospatial stack
tests/                      pytest suite — synthetic fixtures only
eval/results.md             committed record of every measured result
models/                     checkpoints — LOCAL ONLY, never committed
data/                       datasets — LOCAL ONLY, never committed
```

Run the tests with `pytest` — no editable install needed, and no downloaded
data or credentials are required.

## What is never committed

Raw Sentinel-2 tiles, the MARIDA benchmark, NetCDF current fields, MPA
shapefiles, model checkpoints, and `.env`. Git carries code, configs, small
fixtures, and the documented fetch script. If a file was created in a previous
session on the *other* machine, check that it exists locally rather than
assuming — see MACHINE-WORKFLOW.md.

## Status

All six agents are implemented, the LangGraph orchestration runs end to end
including the PRD §12 ablation study, and the operator console (PRD §9.1) is
built, containerised, and runs against exported run artefacts.

**The measured result so far** — the Verification Agent, benchmarked on the
MARIDA held-out test split: precision 0.238 → 0.623, F1 0.385 → 0.753. Quote it
alongside the detector's region recall of 0.407, which is the number that is not
good yet and is the CNN variant's job to improve. Both are shown together on the
console's metrics strip, for the same reason. Full method and caveats in
[eval/results.md](eval/results.md).

The demo region is settled (Gulf of Honduras, Río Motagua outflow) and the
**Sentinel-2 L2A reader** in [src/ghostnet/ingest.py](src/ghostnet/ingest.py)
streams real imagery for it — no credential and no local archive, so
`load_tiles("gulf_of_honduras")` returns real tiles on any machine with
bandwidth. Detection and verification have been run against them.

**Not done:** the CNN detector variant (FR-1.4, workstation), the OSCAR NetCDF
reader, the live Global Fishing Watch query, and Protected Planet / river-table
ingestion. Those four are what still stand between us and a *real* run
artefact — `scripts/export_run.py` refuses to write one until they resolve, so
every artefact in the repo today is synthetic and labelled as such in the UI.
The console is containerised and deployable but is not yet live at a URL; see
[DEPLOY.md](DEPLOY.md) and the Status Log at the bottom of MACHINE-WORKFLOW.md.
