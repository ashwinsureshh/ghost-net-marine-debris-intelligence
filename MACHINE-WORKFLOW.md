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
2026-08-25 (latest) — MacBook Air — BUILT THE REGION-EXTRACT PIPELINE for the two
credential-free datasets (mpa, rivers). 222 tests pass, ruff clean. This is the
half of the "real artefact" blocker that needs neither a GPU nor a login.

  MACHINE RE-VERIFIED: role: laptop, cuda: no, GPU training OK: NO.
  `fetch_data.py --status` — all 7 datasets still MISSING here. Nothing
  downloaded, no tile or CNN work attempted.

  THE READERS WERE NEVER THE GAP. `RiverTable.from_csv` and
  `load_protected_areas` were already written and tested; what was missing was
  the region-clipped extract they read, and any documented way to produce one.
  `scripts/build_region_extracts.py` is that step:

      python scripts/build_region_extracts.py rivers --region gulf_of_honduras \
          --source <global.csv>
      python scripts/build_region_extracts.py mpa --region gulf_of_honduras \
          --source <wdpa.gpkg>

  Both write straight into the paths the loaders glob, in the shape they parse.
  Round-trip tests run the output back through the real readers, so if either
  side drifts it fails in the suite rather than at export time on your machine.
  `fetch_data.py --instructions` for both datasets now names the command.

  TWO DESIGN DECISIONS worth knowing before you change them:

  1. THE CLIP IS A BUFFERED BBOX, NOT THE BBOX. Debris drifts, so a river mouth
     or reserve just outside the monitored box is still live — the backward
     trajectory reaches it. Clipping to the bare bbox would silently drop the
     true source. Rivers default to 250 km (the demo's 66 km / 7-day envelope
     with margin for a real backtrack); MPAs to 100 km (~2x the 50 km
     MPA_RISK_SCALE_KM decay, beyond which a reserve cannot move a score).
     Both are flags. There is a test that the buffer is what keeps a
     just-outside river, so the mechanism is pinned, not just the default.

  2. MULTIPART REEFS ARE EXPLODED, AND THE APPROXIMATION IS MEASURED.
     ProtectedArea models a WDPA polygon as centroid + radius. For the
     Mesoamerican Barrier Reef — the reserve regions.yaml reason 4 leans on —
     one circle would be centred in open water far from any reef. Parts are now
     split so each patch gets its own circle, and every record carries a new
     `circle_fit` field (polygon area / bounding-circle area) saying how good
     that circle is. On fabricated reef geometry the compact reserve scores 0.64
     and the reef patches 0.02-0.04, and the run prints a NOTE naming the worst.
     That is the number to quote if an evaluator asks how MPA proximity is
     modelled — it is an approximation and now it is a measured one.

  SCHEMA BUMPED 1.0 -> 1.1: ProtectedArea gained `circle_fit` (optional,
  defaults None). Additive, so every existing call site is untouched and the
  committed 1.0 artefact still loads — verified, load_artefact gates on the
  major version only. It rides into the run artefact, so an operator can see
  which ecological-risk numbers rest on a poor polygon fit.

  ONE BUG MY OWN TESTS CAUGHT, worth repeating because it is this project's
  recurring shape: `_circle_fit` wrapped shapely in a try/except AttributeError.
  shapely 2 moved `minimum_bounding_circle` from a method to a module function,
  so every record silently came back "fit n/a" — the diagnostic retired itself
  and nothing failed. The except is gone; it now raises if it cannot compute.
  Ruff caught a second one: two tests shared a name, so Python replaced the
  first and the rivers round-trip never ran at all.

  A LATENT BUG FOR YOU, not fixed here because it is your call how far it
  reaches. Both loaders do `sorted(dir.glob(...))[0]` — they take the
  alphabetically first file, not the file for the region being run. Once a
  second region's extract exists (Gulf of Gonave is the stretch candidate),
  running Haiti would silently attribute against Honduras's rivers and score
  against Honduras's reserves, with no error anywhere. Extracts are named
  `<region_id>.csv` / `.json` so the fix is small — thread the region id into
  `load_river_table()` / `load_protected_areas()` — but it touches pipeline
  call sites you own.

  WHAT THIS DOES NOT DO: it does not download anything. Protected Planet needs
  its terms accepted on a web form, which is not mine to click, and I did not
  fetch the river table either. So the two remaining steps here are Ashwin's:
  download both sources, run the two commands above. After that only oscar and
  gfw are left, and both need credentials nobody has created yet
  (EARTHDATA_TOKEN, GFW_API_TOKEN).

2026-08-15 (earlier) — MacBook Air — CONTAINERISED THE CONSOLE FOR A FREE TIER,
and put the measured numbers on its face. 208 tests pass on the merged tree
(nothing skips here — fastapi is present on the Air), ruff clean, tsc clean.
The image builds clean from --no-cache and was verified running.

  MACHINE RE-VERIFIED before starting: role: laptop, cuda available: no,
  GPU training OK: NO. `fetch_data.py --status` — all 7 datasets still MISSING
  here. No CNN work, no tile work, nothing downloaded.

  ### THE METRICS STRIP — 0.407 is now on screen, not just in the report

  New `src/ghostnet/benchmark.py` reads eval/marida_ablation.json and serves it
  at `GET /api/benchmark`; `frontend/src/components/MetricsStrip.tsx` renders it
  under the header. The strip shows, in one row: this run's detected/verified/
  rejected counts, then precision 0.238 -> 0.623 (+0.385), F1 0.385 -> 0.753
  (+0.368), then region recall 0.407 with "misses 140/236" beside it in warning
  colour. Expanding it gives the full before/after table, the false-positive
  rate, the scored-vs-excluded counts, and all four caveats from
  eval/results.md.

  THE DESIGN POINT, since it constrains anything you change here: the two
  numbers are rendered at the same size, in the same row, and the endpoint is
  tested to refuse to serve one without the other
  (test_benchmark_never_serves_the_gain_without_the_region_recall). Your own
  note is why — the precision table is conditioned on candidates the detector
  emitted, so baseline recall is 1.0 by construction, and the gain alone reads
  as "this thing works" to anyone who has not read eval/results.md.

  THREE THINGS I DELIBERATELY DID NOT DO:
  1. The module computes nothing. It reads, reshapes and attaches caveats.
     A second implementation of the arithmetic could disagree with
     eval/results.md, and eval/results.md is the authority.
  2. False-positive rate is DERIVED as 1 - precision rather than read from
     `false_positive_rate_drop`, whose signed-delta convention reads backwards
     (your note 4 from the ablation entry). The trap does not reach the UI.
  3. Nothing claims the numbers describe the run on screen. The strip carries a
     "MARIDA test — not this run" badge, and it compares the artefact's own
     provenance.fdi_threshold against the benchmark's 0.025 and shows a warning
     if they differ. That will fire the moment you export a run at a different
     threshold — that is intended, not a bug.

  ONE THING FOR YOU: eval/marida_ablation.json is STALE ON CHECK NAMES. Its
  per_failure_mode blocks still say sun_glint / foam_whitecap; eval/results.md
  was updated by hand after your rename but the JSON was never regenerated. The
  numbers are fine — that is why nothing caught it. I avoided the problem by
  surfacing only aggregates, so the UI never prints a retired check name, but
  re-running eval_marida.py would fix it at the source. Low priority.

  ### DEPLOYMENT — built and verified, NOT yet live at a URL

  `Dockerfile` (multi-stage: node:24-alpine builds the frontend, python:3.11-slim
  serves it), `.dockerignore`, `render.yaml` blueprint, `requirements-deploy.txt`,
  and `DEPLOY.md`. Verified locally: built from scratch, ran with PORT=10000 to
  prove it honours $PORT the way a PaaS sets it, and driven in a browser —
  /api/health, /api/benchmark, the frontend, the map and the plan all clean, no
  console errors.

  WHAT IS LEFT IS ACCOUNT WORK ONLY, and it is Ashwin's to do: Render dashboard
  -> New -> Blueprint -> connect GitHub -> pick this repo -> optionally set
  ANTHROPIC_API_KEY. I cannot create the account or hold the credential. Steps
  and verification commands are in DEPLOY.md.

  requirements-deploy.txt IS A STRICT SUBSET — do not install it on either dev
  machine, `pytest` would fail on everything touching a tile. The deployed
  server never reads imagery, so it needs no rasterio/GDAL, geopandas, netCDF4,
  xarray or matplotlib. Image is 640 MB and builds in ~1 min; with the
  geospatial stack it would be roughly double both. The Dockerfile smoke-imports
  ghostnet.webapp.app after installing, so if the server's import graph grows a
  dependency the file lacks, the BUILD fails rather than the first request.

  ONE COUPLING BETWEEN YOUR WORK AND THE DEPLOY, worth knowing before you
  refactor ingest.py: requirements-deploy.txt has NO rasterio, pystac-client or
  planetary-computer, and it does not need them because you import all three
  lazily inside functions and detection.load_tiles() imports ingest lazily too.
  Verified after rebasing onto your commit — the image still builds. If any of
  those imports ever moves to module level, the Docker build fails at the smoke
  check with a clear ImportError rather than at runtime. That is the guard
  working; the fix would be to add the package to requirements-deploy.txt, but
  prefer keeping the import lazy — the deployed server genuinely never reads a
  pixel.

  Two deployment choices worth knowing before you change them:
  - ghostnet is run from source with PYTHONPATH=/app/src, NOT pip-installed.
    config.REPO_ROOT is derived from the package's own path and must resolve to
    /app so config/, eval/ and webapp_data/ are found. An installed copy in
    site-packages resolves somewhere else and the app boots empty.
  - GHOSTNET_DURABLE_STORAGE is deliberately UNSET in render.yaml. A free
    instance has an ephemeral disk, so the FR-6.4 approval warning is true;
    setting the flag would silence an accurate warning.

  PUBLISHING A REAL RUN is a commit, not a deploy step: export the artefact on
  your side, commit webapp_data/<run_id>.run.json, push, and Render rebuilds
  (autoDeployTrigger: commit). A few hundred KB is fine to commit.

  ### Also

  - The offline static export now carries the benchmark too, so the viva
    fallback shows the same strip with no server and no network. NOTE: the
    exporter copies frontend/dist, so run `npm run build` FIRST or you ship a
    fallback one version behind — I hit exactly that and it is silent.
  - Fixed a rounding bug the browser caught: `toFixed(3)` rendered the verified
    F1 as 0.752 because 0.7525's nearest double sits just below it, while
    eval/results.md quotes 0.753. The strip rounds half-up instead. All ten
    displayed figures now match the report exactly.
  - The strip wraps rather than scrolling horizontally. A scrolling row put
    region recall and the expand affordance off the right edge below ~1000px,
    which is precisely the number PRD §8 is least willing to see hidden.
  - PRD §9.1 gained two paragraphs: the metrics-strip requirement and the host
    decision. README updated, including its now-stale claim that the demo region
    was undecided.

  ### Still blocking / next

  REBASED ONTO YOUR L2A READER, which landed while this was being written — so
  the "next" list below already accounts for it, and the numbers above were
  re-verified after the rebase, not before.

  - The console still serves ONLY the synthetic run, and per your own entry that
    is now blocked on DATASETS, not on ingestion: export_run.py refuses while
    mpa, oscar, rivers and gfw are missing, and two of those need credentials
    (EARTHDATA_TOKEN, GFW_API_TOKEN) that nobody has created. Protected Planet
    and the river table need neither a GPU nor a credential, so either machine
    can clear them — I can take those on the Air if you would rather stay on
    FR-2.2 and the CNN.
  - When a real artefact does exist: commit `webapp_data/<run_id>.run.json`,
    push, and Render rebuilds. No code changes, and no deploy step.
  - The metrics strip will FLAG your real run if it was detected at a threshold
    other than 0.025 — that is the threshold-parity warning working, not a bug.
  - Detector region recall 0.407 is now visible to every evaluator who opens the
    app. The CNN variant (FR-1.4) is the answer and is not built.

2026-08-15 (earlier) — Workstation — BUILT THE SENTINEL-2 L2A READER (FR-1.1). The
pipeline now runs on real imagery. `load_tiles("gulf_of_honduras")` returns real
Tiles; detection and verification have been run against them. 167 tests pass,
1 skipped, ruff clean.

  NO CREDENTIAL AND NO LOCAL ARCHIVE. src/ghostnet/ingest.py streams
  cloud-optimised GeoTIFFs from Microsoft Planetary Computer's STAC API, which
  serves the SAME Copernicus L2A products named in FR-1.1, anonymously. This
  removes a viva failure mode (a Copernicus login) and means data/raw/sentinel2
  stays empty — it is now an optional cache, not a requirement. earth-search
  (AWS) is a drop-in alternative but uses common-band asset names.
  detection.load_tiles() delegates here, so nothing downstream changed.

  MEASURED ON REAL DATA (AOI, 2018-02, 20 m): 18 products for 16PCC, ~16 s to
  read a tile (8 M px x 4 bands + SCL), 56-81% water, and 200 detections per
  tile of which 36 verified — 145 rejected as floating vegetation. Caribbean
  Sargassum is real and abundant, so that is plausibly correct behaviour and
  worth a sentence in the report, but it is the first thing to sanity-check
  against imagery. NOTE detect() caps at max_detections=200, so that count is a
  ceiling, not a total.

  FOUR TRAPS HANDLED, all documented in the module docstring:
  1. PROCESSING-BASELINE OFFSET. From baseline 04.00 (2022-01-25) L2A carries
     BOA_ADD_OFFSET=-1000 before the 1/10000 scaling. Getting it wrong shifts
     every band by 0.1 reflectance and quietly wrecks the FDI. Our 2018 window
     predates it, so this is LATENT — it bites whoever first picks a recent
     window. Handled per item, inferred from the date when absent, and tested.
  2. LAND. FDI keys off a NIR shoulder and land vegetation has an enormous one;
     unmasked, land swamps everything. Non-water pixels (SCL class 6) are zeroed
     so their FDI is exactly 0.0. Checked first that SCL still calls the turbid
     Motagua plume "water" — it does, 76% of cloud-free pixels — so the mask is
     not discarding the plume we care about.
  3. SCENE CLOUD COVER IS NOT AOI CLOUD COVER. The 2018-02-09 product advertises
     eo:cloud_cover 17% and is 84% clouded over our AOI. Screening now happens
     in two stages, and the AOI stage does the real work: SCL is read first and
     the scene dropped before paying for four band reads.
  4. BAND RESOLUTION. B04/B08 are 10 m but B06/B11 are 20 m, so 20 m is the
     honest working resolution; upsampling SWIR invents detail.

  AOI ADDED to config/regions.yaml. A region's bbox is its definition; a RUN
  needs to stay demo-sized. The full bbox at 20 m is ~67 M px/band. aoi_bbox
  [-88.86, 15.88, -88.36, 16.28] is ~8 M px/band and was placed FROM THE
  IMAGERY, not from a map guess: 67.7% water vs 38% for boxes on the river mouth
  itself, which sit half outside tile 16PCC's footprint and come back nodata
  (each STAC item is ONE MGRS tile). It also contains MARIDA's 16PCC patches, so
  the fitted thresholds were fitted on this exact water.

  FR-2.2 IS NOW UNBLOCKED — the reason this region was chosen. ingest.repeat_pairs()
  pairs passes over the same MGRS tile; the first six tiles alone yield five
  pairs 1-8 days apart. Feeding these to check_persistence is the remaining
  unmeasured verification check. Next thing worth doing here.

  FIXED, same class of bug as the earlier test_config one: tests/test_webapp.py
  hard-errored on this machine because fastapi is deliberately Air-only
  (requirements-web.txt). It now importorskips, so the suite can be green on
  BOTH machines. A test that can only pass on one machine is a broken test.

  A REAL ARTEFACT IS STILL BLOCKED, and not on anything above. export_run.py
  correctly refuses, naming the missing dataset: mpa (Protected Planet), and
  behind it oscar, rivers and gfw. Two of those need credentials nobody has
  created yet — EARTHDATA_TOKEN and GFW_API_TOKEN — and .env does not exist on
  this machine. Until then every artefact stays synthetic and the UI says so.

2026-08-14 (earlier) — Workstation — DEMO REGION CHOSEN. PRD Open Question 1 is
RESOLVED, so the last blocker on real tile ingestion is gone.

  PRIMARY REGION: Gulf of Honduras — Río Motagua outflow (Guatemala/Honduras).
      bbox   [-88.8556, 15.6832, -86.1292, 16.5204]
      window 2018-02-01 .. 2018-10-01
      MGRS   16PCC, 16PDC, 16PEC, 16QED
  config/regions.yaml now has status: selected, so get_region() no longer
  raises. Full rationale is in that file; PRD.md §5.1 and §14 updated.

  Chosen from MARIDA on this machine, not from a literature guess. Four reasons,
  three of them measured:
  1. FR-4 gets a citable answer — the Motagua is widely reported as the world's
     single largest plastic-emitting river (~2% of global emissions) and hosts
     The Ocean Cleanup's Interceptor 021, so ranked-river output can be checked
     against that organisation's own published data, as PRD §3 requires.
  2. IT IS THE ONLY VIABLE REGION FOR FR-2.2. Tile 16PCC has 19 passes with five
     repeat pairs 5–15 days apart (2018-02-21/26, 2018-08-30 -> 09-14 -> 09-19,
     2020-09-18/23/28). Multi-temporal consistency is the one check with no
     measured contribution at all. EVERY Southeast Asian MARIDA tile (48MXU,
     48MYU, 48PZC, 51PTS) has NO repeat pair within 15 days — picking one would
     have left FR-2.2 permanently unmeasurable. This is why the choice departs
     from the PRD's illustrative "South/Southeast Asian" framing; that was an
     example, not a constraint.
  3. Most labelled ground truth of any region: 1084 patches, 1768 debris pixels
     across the four tiles. The thresholds in eval/results.md were fitted on
     data including it, so they transfer.
  4. The Mesoamerican Barrier Reef and Bay Islands reserves are inside the bbox,
     so FR-6.1 MPA proximity scoring is not a no-op.

  SECONDARY (stretch, status: candidate): Gulf of Gonâve, Haiti (18QYF) — densest
  debris in MARIDA (1112 px in 84 patches) and eight repeat pairs, so it is a
  real generalisation test. Attempt only after the primary runs end to end.
  REJECTED and kept auditable: Jakarta Bay / Citarum — closest to the PRD's
  original framing, but 4 scenes, 45 patches and no usable repeat pair.

  Two config tests were updated: they asserted the placeholder region raises, and
  the placeholder is gone. Now assert the selected region merges defaults
  correctly, and that a bbox-less entry still fails loudly. 140 tests, ruff clean.

  UNBLOCKED FOR THE WORKSTATION: the L2A -> Tile reader can now be built and
  pointed at a real region. That is the next big piece here.

2026-08-14 (earlier) — MacBook Air — BUILT THE OPERATOR WEB APPLICATION
(PRD §9.1): run-artefact export schema, FastAPI backend, React frontend, and
the offline viva fallback. 180 tests pass, ruff clean, tsc clean.

  MACHINE RE-VERIFIED before starting: role: laptop, cuda available: no,
  GPU training OK: NO. `fetch_data.py --status` — all 7 datasets still MISSING
  here; nothing was synced and no CNN/tile work was attempted.

  PULLED your five commits first. Noted and honoured: the two renamed checks
  (bright_swir_target, bright_water_surface) are what the UI displays; I did
  not touch verification.py or redo the explainability fix.

  ### THE EXPORT SCHEMA — this is the thing you were blocked on

  `src/ghostnet/export.py`, schema_version 1.0. Write artefacts with:

      python scripts/export_run.py --region <id> --out webapp_data/

  It assembles the run from the real local datasets (raising with the
  fetch_data command if one is missing), runs the pipeline, and writes
  `<run_id>.run.json`. `--synthetic` regenerates the demo scene with no data.

  An artefact carries: detections, EVERY verification check with its reason
  (rejections included), backward + forward trajectories with envelopes,
  attributions, vessel correlations, the clipped MPA extract, all evidence
  refs, plus provenance (thresholds actually used, tile IDs, ensemble/seed,
  git commit, and an `inputs_are_synthetic` flag the UI renders on its face).
  It deliberately carries NO dispatch plan — that is a function of vessel
  capacity and which agents are on, both operator-controlled, so the server
  recomputes it live. And NO imagery: only derived detections, which is what
  keeps the synthetic artefact at 50 KB. Budget a few hundred KB for a real
  region; if one ever exceeds ~2 MB, cut trajectory step resolution before
  cutting evidence or rejections.

  ONE THING I'D LIKE FROM YOU, when convenient. The app lets an evaluator
  switch Verification off and re-plan. Because your pipeline runs drift,
  attribution and vessel correlation DOWNSTREAM of verification, an artefact
  has those outputs only for detections that passed — so re-admitting the
  rejected ones gives them no trajectory and no source, and they score lower
  than a true verification-off run would give them. That flatters the ablation
  arm. The app now states this caveat explicitly and points at eval/results.md
  for the real number, so nothing is misreported. If you ever want that arm to
  be faithful in the UI, the fix is on your side: export upstream outputs for
  ALL detections rather than only verified ones. Not urgent, and NOT worth
  changing the measured pipeline for — eval/results.md is the authority.

  ### The app

  - `src/ghostnet/webapp/` — FastAPI. Serves artefacts; recomputes
    prioritisation per request; generates FR-6.3 rationales server-side (the
    reason a backend is genuinely required — that key cannot sit in a browser);
    records the FR-6.4 approval. Ablation semantics deliberately mirror
    ghostnet.pipeline so the demo cannot contradict eval/results.md.
  - `frontend/` — React 19 + Vite + Tailwind v4 + shadcn-style primitives,
    Leaflet map, lucide icons. Three panes: ranked dispatch, rejected
    detections, evidence trail. Dark/light, keyboard navigable, responsive to
    375px, real empty/loading/error states.
  - Rejected detections are a first-class tab with per-check filter chips and
    the full reason text — your MARIDA work is the best result in the project
    and the UI leads with it rather than hiding it behind a filter.
  - `scripts/build_static_export.py` — the viva fallback. Opens from `file://`
    with no server and no network. Read-only by design: approval and live
    ablation need the server, and it says so instead of faking them.
  - Basemap tiles degrade gracefully: three failed tiles and the map falls back
    to a graticule, keeping every marker, track and MPA. Dead venue wifi cannot
    blank the map.

  ### Notes on the UI skills you flagged

  `21dev` turned out to be a shadcn-compatible component *registry* (copy-in
  components + a shadcn CLI install command), not a package — so the practical
  target was shadcn/ui conventions, which is what the primitives follow:
  CSS-variable theming, `:root` + `.dark`, cva variants, no hardcoded palette
  values. Also ran `ui-ux-pro-max`, which recommended the Data-Dense Dashboard
  pattern and a Fira Sans/Fira Code pairing; I used Inter + JetBrains Mono
  instead as the closer contemporary equivalent, self-hosted via fontsource so
  the offline export renders correctly with no CDN.

  ### Three real bugs the browser found, all fixed

  1. The approval modal rendered BEHIND the map. Leaflet assigns its panes
     z-index 400-800 and its controls up to 1000; Tailwind's `z-50` is 50. Any
     future overlay needs to clear Leaflet explicitly.
  2. Selecting a site re-fitted the map to the 66 km drift envelope, yanking
     the view and losing the sites being compared. The map now frames once per
     run, on detections and MPAs only.
  3. At 375px the dispatch list collapsed to zero height (flex-1 inside an
     auto-sized grid row) and the header overflowed horizontally.

  Also shortened the offline rationale template: it repeated the prototype
  disclaimer per site, which pushed the actual evidence off the card. The
  disclaimer lives on the plan's caveats and twice in the UI chrome instead.

  ### Environment additions (Air only — your install is untouched)

  `requirements-web.txt`: fastapi 0.141.1, uvicorn 0.52.3, httpx 0.28.1. Kept
  OUT of requirements-base.txt on purpose — you only need `ghostnet.export`,
  which is pure pydantic and already covered by the base file. Also
  `pip install -e .` so uvicorn can import ghostnet; Node 24.10.0 for the
  frontend. `frontend/dist/`, `frontend/node_modules/`, `static_export/` and
  `webapp_data/approvals.json` are gitignored; the 50 KB synthetic artefact IS
  committed so a fresh clone can run the app immediately.

  ### Still blocking / next

  - PRD Open Question 1, the demo region, was the last thing between us and a
    real end-to-end demo when this entry was written. The workstation resolved
    it in the entry above — Gulf of Honduras. Everything downstream is built
    and waiting: build the L2A -> Tile reader, run
    `python scripts/export_run.py --region gulf_of_honduras --out webapp_data/`,
    and the console shows real results with NO code changes. Verified after
    rebasing onto that decision that export_run reads the new regions.yaml
    correctly (bbox, time_window, merged defaults).
  - The app is built but NOT yet deployed to a host. That is next on the Air.
  - Detector region recall 0.407 still stands as the weak number, and the UI
    does not currently surface it — worth adding a run-level metrics strip once
    a real artefact exists.

2026-08-14 (earlier) — Workstation — FIXED THE EXPLAINABILITY BUG, and found a
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

  INTERFACE QUALITY IS A GRADED REQUIREMENT, now written into PRD.md §9.1. The
  app is the only part of the system an evaluator touches directly, so it must
  look contemporary and deliberate — considered layout and type scale, real
  empty/loading/error states, responsive, keyboard-navigable, dark/light suited
  to a map-heavy operations view. Build with a modern component toolkit rather
  than hand-rolled CSS: use the `21dev` UI skill, plus any equivalent UI/UX
  skill available in that session (check the session's own skill list — skills
  differ per machine). TWO CONSTRAINTS: polish must not cost the evidence trail
  or the rejected-detections view, which are the whole point of the interface;
  and the design must not imply operational readiness (PRD §8).

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
