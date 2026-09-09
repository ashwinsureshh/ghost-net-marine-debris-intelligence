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

The design test is to measure what changes when each agent is removed. The
real-input ablation exposes important limits: attribution does not alter dispatch,
and the vessel arm cannot be assessed until GFW inputs are available. See
[eval/results.md](eval/results.md#system-level-ablation--every-agent-removed-in-turn-on-real-inputs).

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
scripts/build_region_extracts.py  clip WDPA + river tables to the demo region
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

Updated 2026-09-09 against the committed results. The six-agent orchestration
and operator console are built. **Five of six agents now run on real inputs**;
the GFW SAR query remains unimplemented. The latest workstation status records
four of six PRD §12 criteria complete, with the full-region run and the external
attribution/vessel comparison still partial. The ablation has been run, with
limits described below; this is not a claim that every agent improves dispatch.

The committed Gulf of Honduras run uses real Sentinel-2 imagery, OSCAR currents,
221 river mouths and 82 protected areas: **826 CNN candidates, 443 verified,
383 rejected, and a capacity-limited plan of three sites**. GFW is its only
missing input. The console deliberately defaults to a readable real run and
labels the separate synthetic demo. Exporting with missing inputs requires
`--allow-degraded`; a real-input run is not necessarily a complete run.

**Measured detection results**, on the held-out MARIDA test split:

- **Verification over FDI:** precision 0.238 → 0.623, F1 0.385 → 0.753;
  FDI detector region recall is 0.407.
- **CNN detector:** region recall **0.703 (within-tile)**, precision 0.672,
  and 7.6× fewer candidates than FDI. Verification adds **+0.080** precision
  over the CNN, not the FDI's +0.385.

These are benchmark results, not measured accuracy of the Gulf of Honduras run.
MARIDA splits by patch; 91% of test patches share tiles with training data.
The console pairs verification gain with the displayed run's detector benchmark
and shows the geographic-generalisation caveat.

**Measured limitations:**

- Multi-temporal verification (FR-2.2) is **inert** with real OSCAR currents:
  the earlier harm disappears, but F1 gain and transients found remain zero.
  Nearest-neighbour matching is the identified limitation.
- Drift was checked against 19 buoy tracks from **2014**, outside the demo
  window. Mean track error is 10.46 km at ≤4.5 days and 48.74 km beyond it;
  overall uncertainty-envelope coverage is only 24.5%. This does not validate
  the demo trajectories.
- Real-input ablation shows dependencies, but removing attribution does not
  change dispatch. The vessel ablation is uninformative because GFW was absent
  before removal. Attribution still needs comparison with The Ocean Cleanup's
  published river rankings.

The recorded end-to-end run took **15.6 minutes, 90.6% in network ingestion**;
this was not an asserted cold run. Performance belongs in the report, not beside
finished recommendations as a quality metric.

**Remaining work:** GFW integration and case-study evaluation, the published
river-ranking comparison, a new full export and vessel ablation, the report,
and deployment. The console is containerised; no live deployment is recorded.
See [DEPLOY.md](DEPLOY.md), [docs/project-status.md](docs/project-status.md), and
[MACHINE-WORKFLOW.md](MACHINE-WORKFLOW.md) for the machine split and handoff.
Full methods and caveats are in [eval/results.md](eval/results.md).
