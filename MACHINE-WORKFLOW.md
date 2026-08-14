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
2026-08-14 (later still) — Workstation — Downloaded and validated the MARIDA
benchmark. Zenodo DOI 10.5281/zenodo.5151941, CC-BY-4.0, 1.08 GB zip, md5
verified against the Zenodo manifest, ~5.5 GB extracted to data/marida/.
WORKSTATION ONLY — do not sync to the Air. Confirmed nothing reached git.

  Validated rather than assumed intact: 63 scene folders, splits 694/328/359 =
  1381 patches with no overlap between train/val/test, patches load through
  rasterio as 11-band 256x256 float32 ACOLITE reflectance in per-scene UTM.

  TWO TRAPS FOR WHOEVER TRAINS THE CNN (FR-1.4) — both would silently produce a
  useless model, full detail in data/README.md:
  1. Class 0 is UNLABELLED, not background. MARIDA is sparsely annotated — only
     drawn polygons carry labels, so class 0 is 99.6% of pixels. Mask it out of
     the loss or the model learns to predict "nothing" everywhere.
  2. Masks load as float32, not an int type. Cast before using as class indices.
  Marine Debris is ~0.002% of pixels: use class weighting or focal loss, and
  report precision/recall, never accuracy.

  Useful for scoping: MARIDA's classes include Sargassum, Ship, Clouds, Foam,
  Waves, Cloud Shadows and Wakes — i.e. the exact false-positive modes FR-2.1
  asks the Verification Agent to rule out. So MARIDA can evaluate the
  Verification Agent too, not just the detector. That is the headline ablation
  in PRD §3 and it can be measured without any new data.

  Still no Sentinel-2 tiles (blocked on the undecided demo region) and no .env.

2026-08-14 (later, same session) — Workstation — Installed requirements-base.txt
into Python 3.11 (the interpreter that holds the verified cu128 torch — do not
use 3.13/3.14 here, they have no torch). Full stack now present and smoke-tested:
rasterio 1.4.4 / GDAL 3.10.3, geopandas 1.1.4, shapely 2.1.2, pyproj 3.7.2,
xarray 2026.7.0, netCDF4 1.7.4, langgraph 1.2.11, langchain-core 1.5.4,
anthropic 0.122.0. Verified working, not just importable: GeoTIFF read/write,
FDI-style band math, CRS reprojection, spatial join, netCDF round-trip.

  GPU re-verified AFTER the install — numpy stayed at 2.4.4 and the cu128 torch
  build is intact (CUDA matmul + numpy interop both clean). This was the main
  risk of installing the geospatial stack alongside a torch nightly; it did not
  materialise, but re-check it after any future big install.

  Tightened requirements-base.txt: langgraph and langchain-core resolved to
  1.2.11 / 1.5.4, way above the original `>=0.2` / `>=0.3` floors. Those floors
  would have let the Air install 0.2.x, whose orchestration API is materially
  different — two machines writing incompatible code against the same repo. Now
  bounded to >=1.2,<2 and >=1.5,<2, and anthropic raised to >=0.122. The Air
  will therefore get 1.x too. If it resolves anything materially different,
  record it here.

  This supersedes the "no dependencies installed" note in the entry below.
  Still true: no datasets downloaded, no .env, no agent implemented, demo region
  undecided.

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
  - [SUPERSEDED by the entry above — the base stack was installed later the same
    day.] No dependencies installed beyond torch+numpy+pandas+scikit-learn on
    py3.11; requirements-base.txt written but not yet pip-installed.
  - No agent implemented. src/ghostnet/agents/ is a documented layout only.
  - No credentials yet: .env does not exist (copy .env.example and fill in).
  - PRD Open Question 1 — the demo region — is STILL UNDECIDED. config/regions.yaml
    holds a placeholder entry with bbox/time_window = null. This blocks Phase 1
    tile ingestion and should be settled next.
  PUSHED — the Air can pull this now:
  https://github.com/ashwinsureshh/ghost-net-marine-debris-intelligence
  Private repo, default branch `main`, origin tracking set up. Verified that
  only the 23 code/config/doc files reached GitHub — no tiles, no checkpoints,
  no .env. First step on the Air:
      git clone https://github.com/ashwinsureshh/ghost-net-marine-debris-intelligence.git
      python scripts/check_machine.py     # records the Air's profile
      cp .env.example .env                # then fill in the free-tier tokens

[Format for future entries:]
2026-08-XX — Workstation — Trained baseline CNN detector on MARIDA, checkpoint saved locally at models/detector_v1.pt (not committed). Precision/recall logged in eval/results.md.
2026-08-XX — MacBook Air — Wired up LangGraph orchestration for Detection -> Verification -> Drift. Verification Agent still stubbed, returns raw detections unchanged — needs real logic next.
```
