# Development Workflow — Workstation ↔ MacBook Air

This file tells Claude Code how work on this project is split across two machines, so that any session — whichever machine it starts on — behaves correctly instead of assuming the wrong hardware or missing files. Keep this file at the repo root and keep it updated; it is read as project context at the start of every session.

## Project

Multi-Agent Ghost Net & Marine Debris Intelligence Pipeline — six agents (Satellite Detection, False-Positive Verification, Drift, Source Attribution, Dark Vessel Correlation, Response Prioritisation). See `PRD.md` / the project proposal for full architecture and requirements.

## The two machines

| | Workstation | MacBook Air M3 |
|---|---|---|
| Hardware | RTX 5070 (CUDA GPU) | Apple Silicon, no dedicated GPU, fanless |
| Location | Home | Carried to college |
| Role | GPU-heavy work | Everything else |
| Local data | Raw Sentinel-2 tiles, MARIDA benchmark, trained model checkpoints | Small cached samples only |

**Detect which machine a session is running on before assuming GPU availability.** Check for CUDA (`nvidia-smi` present and working) rather than assuming based on OS. Do not attempt local CNN training or large batch tile processing on a machine without a working CUDA GPU — it will be slow or fail outright; fall back to cloud API / smaller sample sizes / stubbed output instead, and say so explicitly rather than silently doing something different from what was asked.

## Division of work by agent

| Agent | Primary machine | Why |
|---|---|---|
| Satellite Detection Agent — spectral-index baseline | Either | Lightweight, CPU-fine |
| Satellite Detection Agent — CNN variant (stretch goal) | Workstation | Needs GPU to train/fine-tune in reasonable time |
| False-Positive Verification Agent | Either | Classical checks (multi-temporal consistency, spectral heuristics), no GPU needed |
| Drift Agent | Either | Numerical/geospatial (current-field trajectory modelling), CPU-fine |
| Source Attribution Agent | Either | Lightweight lookup/cross-reference logic |
| Dark Vessel Correlation Agent | Either | API calls + cross-referencing, no GPU needed |
| Response Prioritisation Agent | Either | Scoring/optimisation logic, CPU-fine |
| Batch processing over many Sentinel-2 tiles | Workstation | GPU + faster local storage; avoid large downloads on the Air |
| Agent orchestration (LangGraph/CrewAI wiring), LLM API integration | MacBook Air | Needs no GPU; this is most of the day-to-day coding while at college |
| Tests, docs, small-sample debugging | Either | Use a small cached sample of tiles/data, never the full dataset |

In short: the workstation is for training the detector and running data-heavy batch jobs; the Air is for building and wiring the agents, API integration, and everyday coding. Most of the six agents' core logic is not GPU-bound and can be built and tested on either machine — treat "needs a GPU" as the exception, not the default assumption.

## Sync workflow — git is the source of truth, not chat history

Claude Code sessions are local to each machine and do not sync with each other. Do not rely on a previous conversation's context being available on the other machine. Instead:

1. Commit and push before switching machines. Pull before starting work on the other one.
2. Do **not** commit large raw data: Sentinel-2 tiles, the full MARIDA dataset, or trained model weights/checkpoints. Add these to `.gitignore`. Commit only code, configs, small fixture/sample files, and a documented script that fetches the real data on demand (with instructions for where it expects the data to live locally).
3. At the end of any meaningful work session, update this file's **Status Log** section below and update `PRD.md` if scope or design decisions changed. This — not the chat transcript — is what gives the next session (on either machine) full context.
4. Never assume a file exists locally just because it was created in a previous session — check for it, and if it's missing (e.g. a checkpoint that only lives on the workstation), say so rather than proceeding as if it's there.

## Status log

Update this section (newest entry on top) at the end of each work session so the next session — on either machine — knows exactly where things stand.

```
2026-08-14 — Workstation — Repo initialised (first session, previously empty folder). Created .gitignore (excludes Sentinel-2 tiles, MARIDA, NetCDF/shapefiles, checkpoints, .env), scaffolding (config/, scripts/, src/ghostnet/, eval/, models/, data/) and the initial commit. Converted Ghost-Net-Marine-Debris-PRD.docx to PRD.md at repo root so the PRD is versioned and readable on both machines.

  GPU VERIFIED on this workstation — the key fact this session establishes:
  RTX 5070 is Blackwell / compute capability sm_120, 11.94 GB usable VRAM.
  torch 2.12.0.dev20260408+cu128 (Python 3.11) has sm_120 in get_arch_list();
  fp32 4096^3 matmul 18.8 ms (~7.3 TFLOPS) and the cuDNN conv path both run
  clean. So CNN detector training (FR-1.4) and batch tile processing are good
  to go here. WATCH OUT: a default `pip install torch` can pull a build with no
  sm_120 kernels — it imports fine and reports cuda.is_available() == True, then
  fails at the first real CUDA op. Always install from the cu128 index
  (requirements-gpu.txt) and confirm with `python scripts/check_machine.py`.

  Added scripts/check_machine.py — implements this file's "detect CUDA, don't
  assume" rule as one shared function (get_profile().can_train), so no agent or
  session has to guess. Run it first on the Air to record its profile.
  Added scripts/fetch_data.py — documents where all 7 datasets must live locally
  and how to obtain each; `--status` reports present vs missing. Directory
  layout created; all 7 datasets currently MISSING on this machine (nothing
  downloaded yet).

  NOT done yet / next up:
  - No dependencies installed beyond torch+numpy+pandas+scikit-learn on py3.11.
    requirements-base.txt is written but NOT yet pip-installed anywhere — the
    geospatial stack (rasterio, geopandas, xarray) is still absent.
  - No agent implemented. src/ghostnet/agents/ is a documented layout only.
  - No credentials yet: .env does not exist (copy .env.example and fill in).
  - PRD Open Question 1 — the demo region — is STILL UNDECIDED. config/regions.yaml
    holds a placeholder entry with bbox/time_window = null. This blocks Phase 1
    tile ingestion and should be settled next.
  - Nothing pushed: no git remote is configured yet. Add one before switching
    to the Air, or the Air has no way to pull this.

[Format for future entries:]
2026-08-XX — Workstation — Trained baseline CNN detector on MARIDA, checkpoint saved locally at models/detector_v1.pt (not committed). Precision/recall logged in eval/results.md.
2026-08-XX — MacBook Air — Wired up LangGraph orchestration for Detection -> Verification -> Drift. Verification Agent still stubbed, returns raw detections unchanged — needs real logic next.
```
