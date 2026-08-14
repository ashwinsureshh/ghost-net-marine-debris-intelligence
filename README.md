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

## Repository layout

```
config/regions.yaml     monitored regions, demo window, dispatch constraints
scripts/check_machine.py    CUDA / machine-role detection
scripts/fetch_data.py       where each dataset lives + how to obtain it
src/ghostnet/agents/    the six agents (see the package docstring)
eval/results.md         committed record of every measured result
models/                 checkpoints — LOCAL ONLY, never committed
data/                   datasets — LOCAL ONLY, never committed
```

## What is never committed

Raw Sentinel-2 tiles, the MARIDA benchmark, NetCDF current fields, MPA
shapefiles, model checkpoints, and `.env`. Git carries code, configs, small
fixtures, and the documented fetch script. If a file was created in a previous
session on the *other* machine, check that it exists locally rather than
assuming — see MACHINE-WORKFLOW.md.

## Status

Phase 0 — repository scaffolding. No agent is implemented yet. The demo region
(PRD Open Question 1) is still undecided. See the Status Log at the bottom of
MACHINE-WORKFLOW.md for the current state.
