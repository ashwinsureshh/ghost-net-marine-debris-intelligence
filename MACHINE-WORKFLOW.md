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
2026-08-14 (latest) — Workstation — FIXED THE EXPLAINABILITY BUG, and found a
worse one underneath it. Metrics are UNCHANGED and verified byte-identical
before/after (precision 0.6230, F1 0.7525, every per-class count the same) —
only the operator-facing explanations changed.

  TWO CHECKS RENAMED. Pull before touching verification.py:
      sun_glint      -> bright_swir_target
      foam_whitecap  -> bright_water_surface
  Named for the SIGNATURE they measure rather than one of its causes, because
  fitting made them fire well outside the single mode each was named for
  (bright_water_surface rejects 100% of Turbid Water; bright_swir_target rejects
  clouds and ships). Decisions were right, labels were wrong. Reasons now name a
  specific cause only where evidence supports it: sun glint when the specular
  angle says so, cloud when cloud fraction does, turbidity when NDVI < -0.30
  (new threshold turbid_ndvi_max, affects wording only, never the decision).
  kelp_sargassum and cloud_shadow keep their names — they are genuinely specific.

  THE WORSE BUG, found while renaming: bright_swir_target used to require
  "specular geometry OR no geometry at all" in order to disqualify. MARIDA
  carries no geometry, so it rejected 91.8% of clouds here and looked perfect —
  but on REAL L2A tiles, where geometry IS present and usually non-specular,
  that condition would have gone false and the check would have quietly stopped
  rejecting clouds, taking the headline FR-2.4 result down with it. This would
  have surfaced as "our numbers collapsed when we moved to real data" with no
  obvious cause. Disqualification is now decided on the spectral signature
  alone; geometry only names the cause. Regression test added:
  test_bright_swir_target_is_rejected_even_when_geometry_is_not_specular.

  139 tests pass, ruff clean.

2026-08-14 (later) — Workstation — MEASURED THE FR-2.4 ABLATION AGAINST MARIDA.
The project's first real number. Full method, tables and caveats in
eval/results.md; machine-readable in eval/marida_ablation.json.

  HEADLINE (MARIDA test split, held out, thresholds fitted on train only):
  precision 0.238 -> 0.623 (+0.385), F1 0.385 -> 0.753, recall cost 5 points,
  false-positive rate 0.762 -> 0.377. Confirmed on val as a second held-out
  split: precision 0.535 -> 0.767. Per-failure-mode: Clouds 91.8% rejected,
  Turbid Water 100%, Dense Sargassum 100%, Foam 100%, Waves 85.1%, Ship 73.7%,
  Sparse Sargassum 66.7%, while only 5.0% of true debris is falsely rejected.

  THE THRESHOLDS WERE NOT MERELY UNFITTED, THEY WERE NET-HARMFUL. Unfitted, the
  agent was worth +0.003 F1 on test and *lowered* F1 on val (0.697 -> 0.648).
  shadow_brightness_max=0.015 sat in the middle of the true-debris brightness
  distribution and rejected 78.6% of real debris; foam_red_min=0.12 never fired
  because foam's red is ~0.048. Reporting the agent uncalibrated would have made
  it look useless. Fitted values are now the defaults in the source, with
  provenance comments. detection.DEFAULT_FDI_THRESHOLD 0.006 -> 0.025 (marine
  water's own FDI is ~0.013, so 0.006 fired on open water).

  BAND ORDER WAS VERIFIED PHYSICALLY, NOT ASSUMED. MARIDA patches carry no band
  descriptions and the docs don't state the order. Confirmed via Dense Sargassum's
  red edge (b4 0.042 -> b7 0.132) plus water/Sargassum collapsing at b10/b11
  while clouds stay bright: B01 B02 B03 B04 B05 B06 B07 B08 B8A B11 B12. FDI
  therefore needs indices 4, 6, 8, 10. Getting this wrong is silent, not loud.

  FOUR THINGS THE AIR SHOULD KNOW:
  1. Fixed tests/test_config.py::test_no_dataset_is_committed_to_git. It asserted
     the data dirs were empty ON DISK, which conflates "not committed" with "not
     present". It passed on the Air only because no data exists there and could
     never pass on the workstation — the machine the data belongs on. Now asks
     `git ls-files data/` instead.
  2. The mixed_tile fixture now yields 4 detections, not 5. At the fitted FDI
     threshold the cloud-shadow patch is not raised at all, and that is not
     tunable: FDI > 0.025 needs B08 > ~0.024, which alone breaks the brightness
     budget shadow_brightness_max=0.008 defines. So "dark enough to be a shadow"
     and "bright enough to detect" are mutually exclusive. check_cloud_shadow is
     now unit-tested directly instead of through detect(). Matches MARIDA, where
     cloud shadow gave 1 candidate and *clouds* were the real false positive.
     The glint fixture was retuned (FDI 0.018 -> 0.033) so it still detects.
  3. EXPLAINABILITY BUG — NOW FIXED on the workstation, see the entry above this
     one. TWO CHECKS WERE RENAMED, so pull before touching verification:
     sun_glint -> bright_swir_target, foam_whitecap -> bright_water_surface.
  4. precision_recall_delta's "false_positive_rate_drop" is a signed delta, so
     an improvement shows as a NEGATIVE number (-0.385 here). Reads oddly given
     the name.

  THE NUMBER THAT IS NOT GOOD: detector region recall is 0.407 on test — the FDI
  baseline misses ~59% of annotated debris regions (96/236 hit). The
  precision/recall table cannot show this because it is conditioned on
  candidates the detector emitted, and baseline recall there is 1.0 by
  construction. Both must be quoted together or the system looks better than it
  is. Improving it is the CNN variant's job (FR-1.4).

  Also note only 3 of 5 checks are evaluable on MARIDA: patches carry no
  acquisition geometry and no repeat passes, so multi_temporal (FR-2.2) is
  inconclusive throughout and its contribution is UNMEASURED.

  137 tests pass, ruff clean. MARIDA still workstation-only, nothing added to git
  except eval/marida_ablation.json (11 KB of results, not data).

  PRD OPEN QUESTION 2 IS RESOLVED: the operator-facing output is a DEPLOYED WEB
  APPLICATION — a course deliverable requirement, so this is settled, not a
  preference. Architecture written up in PRD.md §9.1. The constraint that drives
  it: the data cannot be deployed (MARIDA ~5.5 GB, tiles larger, free tier only),
  so the app serves PRECOMPUTED run artefacts exported from the workstation, and
  recomputes only prioritisation (FR-6.1/6.2) live. That keeps the server doing
  real work — plus FR-6.3 rationales need the Claude API key server-side, which a
  static page could never hold. This is Air work: FastAPI + frontend, no GPU.
  Keep a static export on disk as a viva fallback; free-tier hosts sleep.

  STILL BLOCKING: PRD Open Question 1, the demo region. Unchanged.

2026-08-14 — MacBook Air — First session on the Air. Cloned the repo, built the
  agent orchestration, the LLM integration and all six agents' non-GPU logic.
  136 tests pass; ruff clean.

  MACHINE VERIFIED — `python scripts/check_machine.py` on this machine reports:
  role: laptop, Darwin 25.5.0 (arm64), nvidia-smi: no, cuda available: no,
  GPU training OK: NO. Confirmed before any work started, per this file's
  "detect CUDA, don't assume" rule. No CNN training and no batch tile
  processing was attempted here — those stay on the workstation.

  ENVIRONMENT — created .venv on python3.11.15 (homebrew), matching the
  workstation's 3.11. NOTE: this machine has no bare `python` on PATH, only
  `python3`; the venv provides `python`, so activate it before following the
  README verbatim. requirements-base.txt installed CLEANLY IN FULL:
  rasterio 1.4.4, geopandas 1.1.4, xarray 2026.7.0, rioxarray 0.19.0,
  netCDF4 1.7.4, shapely 2.1.2, pyproj 3.7.2, pystac-client 0.9.0,
  planetary-computer 1.0.0, folium 0.20.0, matplotlib 3.11.1, plus
  langgraph 1.2.11, langchain-core 1.5.4, anthropic 0.122.0, pydantic 2.13.4,
  numpy 2.4.6, pandas 3.0.5, scipy 1.17.1, scikit-learn 1.9.0.
  No torch on the Air (deliberate — it is only needed for the CNN variant).

  ANSWERING THE WORKSTATION'S QUESTION about version drift: the Air resolved
  NOTHING materially different. langgraph 1.2.11, langchain-core 1.5.4 and
  anthropic 0.122.0 are identical to the workstation's, and the orchestration
  is written against LangGraph 1.x, so the >=1.2,<2 bound is right and both
  machines agree. Only trivial drift: numpy 2.4.6 here vs 2.4.4 there. (These
  installs were done from the unbounded requirements-base.txt and only
  afterwards reconciled with the workstation's bounded version — the resolved
  versions satisfy the new bounds either way.)

  DATA — `python scripts/fetch_data.py --status` run BEFORE writing any code:
  all 7 datasets MISSING on this machine. Nothing was synced from the
  workstation and nothing was downloaded. Everything below was therefore built
  and tested against small synthetic fixtures, never real data.
  Also created .env from .env.example with the values left BLANK — no
  credentials on this machine, so the LLM path runs in its offline mode.

  BUILT (all CPU-only, all this machine's assigned work):
  - pyproject.toml — src layout + pytest pythonpath, so `pytest` works on a
    fresh clone with no editable install. Also ruff config.
  - src/ghostnet/schemas.py — the pydantic data contracts every agent exchanges.
    Explainability and auditability are structural: every artefact carries an
    `evidence` list, and a rejected detection is a VerificationResult with
    verified=False rather than an absence.
  - src/ghostnet/pipeline.py — the LangGraph wiring: detection -> verification
    -> drift -> attribution -> vessels -> prioritisation, plus PipelineConfig,
    run_pipeline() and run_ablation_study(). ABLATION IS BUILT IN: an ablated
    agent still runs a stub that records WHY its output is missing, and each
    downstream node records how it degraded — so PRD §12's study reads a named
    failure mode off `run.degradations`, not just a worse number. Missing
    datasets degrade the run with the exact fetch_data.py command; they never
    crash it.
  - src/ghostnet/llm.py — Claude integration for FR-6.3 rationales, on
    claude-opus-5 via messages.parse() with a pydantic schema. The LLM only
    *explains* the plan; every number it sees is computed by the agents, so
    PRD §8 reproducibility holds. With no ANTHROPIC_API_KEY (the current state
    here) or on any API failure it falls back to a deterministic template and
    marks the rationale's source as "template" in the output.
  - src/ghostnet/config.py, _datasets.py, geo.py — paths, region config,
    credential handling, dataset presence checks, geodesy helpers.
  - All six agents (src/ghostnet/agents/): FDI spectral index + connected
    components (FR-1.2/1.3); the four documented false-positive checks plus
    multi-temporal coherence and the FR-2.4 precision/recall delta; RK4
    ensemble drift with a seeded uncertainty envelope and a drifter-backtest
    metric; emission x proximity river attribution using the drift envelope as
    the Gaussian width; greedy SAR/AIS matching and dark-vessel correlation;
    weighted prioritisation with the capacity constraint and the FR-6.4
    approval checkpoint.
  - tests/ — 136 tests on synthetic fixtures only. No downloaded data, no
    network, no credentials.
  - scripts/run_pipeline_demo.py — end-to-end run on generated inputs, with
    --ablation. Its numbers are NOT results and must not go in eval/results.md.

  TWO DESIGN DECISIONS worth knowing before changing the scoring:
  1. A signal that cannot be measured is DROPPED and its weight redistributed,
     never scored zero. With no Protected Planet data, ecological risk is
     omitted and the plan carries a caveat — scoring it 0 would silently mark
     every site as ecologically safe.
  2. Fixed a scoring flaw the tests caught: the drift-urgency fallback used to
     saturate at 1.0, so a patch drifting fast past nothing outranked one
     heading into an MPA. The fallback is now capped at 0.5 when MPA data IS
     loaded (we know nothing is threatened) and uncapped when it is absent (we
     know nothing at all). Regression test in tests/test_prioritisation.py.

  FOR THE WORKSTATION SESSION — what changed that affects you, and what is
  yours to build. Pull before starting.
  - Build the L2A -> Tile reader against the Tile / GeoTransform contract in
    agents/detection.py. `load_tiles()` currently raises NotImplementedError
    pointing at exactly that. The detection maths needs no changes.
  - The CNN variant (FR-1.4) should satisfy the same detect() signature and
    return Detection objects with detector="cnn"; the orchestration then needs
    no edits at all.
  - Every threshold in the agents is a literature-informed starting point, NOT
    a fitted constant — verification.VerificationThresholds and
    detection.DEFAULT_FDI_THRESHOLD especially. Re-fit against MARIDA before
    any precision/recall number goes in the report or eval/results.md.
  - verification.precision_recall_delta() computes the FR-2.4 headline number
    (baseline vs verified precision/recall/F1) — feed it MARIDA labels. Your
    MARIDA entry notes the benchmark carries Sargassum / Foam / Clouds / Cloud
    Shadow / Ship classes, i.e. exactly the modes the four checks in
    agents/verification.py try to disqualify. Those classes map onto the check
    names kelp_sargassum / foam_whitecap / cloud_shadow, so the ablation can be
    measured per-failure-mode, not just in aggregate, with no new data. That
    looks like the highest-value next thing to run on the workstation.
  - drift.load_oscar_field() and vessels.GlobalFishingWatchClient.
    sar_detections() are the other two unwritten readers; both raise with the
    contract to build against. OSCAR is small enough for either machine.
  - Do NOT commit anything the .gitignore excludes; the Air has no datasets and
    should stay that way.

  STILL NOT DONE / next up:
  - PRD Open Question 1 — the demo region — is STILL UNDECIDED and now the
    single biggest blocker. config/regions.yaml still holds the placeholder,
    and get_region() deliberately raises on it rather than querying a null
    bbox. Nothing real can be ingested until this is settled.
  - No measured result of any kind exists; eval/results.md is still empty.
  - PRD Open Question 2 (dashboard vs report vs notebook) untouched.
  PUSHED to main.

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
