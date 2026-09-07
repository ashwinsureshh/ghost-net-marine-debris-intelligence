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

## Ownership — who owns what across three people

The table above splits work by *machine*. This section splits it by *person*,
because the team is now three. Both apply: the machine rules say where a job can
run, the ownership rules say whose job it is.

| | Owns the agents | Owns the datasets | Needs the credential | Owns these `eval/results.md` sections |
|---|---|---|---|---|
| **A** | Drift (FR-3), Source Attribution (FR-4) | `oscar`, `drifters`, `rivers` | `EARTHDATA_TOKEN` | Drift accuracy vs the Global Drifter Program; source attribution vs published rankings |
| **B** | Dark Vessel Correlation (FR-5), the ecological-risk half of Prioritisation (FR-6.1) | `gfw`, `mpa` | `GFW_API_TOKEN` | Dark vessel correlation vs GFW case studies |
| **Ashwin** | Detection (FR-1) incl. the CNN, Verification (FR-2), integration, the console, release | `sentinel2`, `marida` | — | Detection, verification, FR-2.2, the system-level ablation |

Why this seam and not "two agents each": the four outstanding datasets split
2/2 along it, each half needs exactly one free signup, and the halves touch
different files — so three people can work at once without fighting over the
same module. Each column also closes a named PRD §12 acceptance bullet, which
makes the split defensible in the viva and legible to a marker.

**Current state of each column.** A's readers are written — `load_oscar_field()`
exists and is tested — so A's job is now *download, run, and measure*, not
build. B still has real code to write: `vessels.GlobalFishingWatchClient
.sar_detections()` is the last `NotImplementedError` in the codebase. Ashwin's
column is largely done and measured; what remains there is integration and the
deploy.

### Rules that keep three people from colliding

1. **Branch per person; PR into `main`.** Everything landed straight on `main`
   while this was one person on two machines. With three it will not hold —
   pushes have already collided once.
2. **The Status Log and `eval/results.md` are the shared files.** Append your own
   entry; never edit someone else's. Each person owns only the results sections
   named in the table above.
3. **Pull before you start and push before you stop** — sync rule 1 below, which
   matters more, not less, with three people.
4. **Do not commit anything under `data/` or `models/`** — sync rule 2. A
   teammate's first instinct on getting a dataset working is to commit it.

### Four conventions to read before writing any code

These are not style preferences; each one has already caused a real bug here.

- A missing dataset **degrades** the run with the `fetch_data.py` command to fix
  it. It never crashes, and it never silently proceeds.
- A signal that cannot be measured is **dropped and its weight redistributed**,
  never scored zero — scoring zero would quietly mark every site as safe.
- Thresholds are **fitted on a train split**, never guessed. Reporting unfitted
  values once made the Verification Agent look worthless.
- Tests use **synthetic fixtures only**: no network, no credentials, no
  downloaded data, so the suite runs on a fresh clone.

### If a teammate cannot write Python at this level

Do not split the code three ways anyway. Put them on PRD §12 bullets 5 and 6 —
the ablation write-up, the evidence-traceability demo, and the report and viva
materials, all of which are graded and none of which are written — and give
their agent to the other teammate. The rule that matters either way: **no number
reaches `eval/results.md` that the person who produced it cannot derive and
defend.** An evaluator asking "why is drift error 12 km?" is asking the person,
not the tool.

## Sync workflow — git is the source of truth, not chat history

Claude Code sessions are local to each machine and do not sync with each other. Do not rely on a previous conversation's context being available on the other machine. Instead:

1. Commit and push before switching machines. Pull before starting work on the other one.
2. Do **not** commit large raw data: Sentinel-2 tiles, the full MARIDA dataset, or trained model weights/checkpoints. Add these to `.gitignore`. Commit only code, configs, small fixture/sample files, and a documented script that fetches the real data on demand (with instructions for where it expects the data to live locally).
3. At the end of any meaningful work session, update this file's **Status Log** section below and update `PRD.md` if scope or design decisions changed. This — not the chat transcript — is what gives the next session (on either machine) full context.
4. Never assume a file exists locally just because it was created in a previous session — check for it, and if it's missing (e.g. a checkpoint that only lives on the workstation), say so rather than proceeding as if it's there.

## Status log

Update this section (newest entry on top) at the end of each work session so the next session — on either machine — knows exactly where things stand.

```
2026-09-07 (latest, workstation) — Workstation — THE CREDENTIALS LANDED AND THE
PROJECT MOVED. Both tokens created and verified, OSCAR downloaded, FR-2.2
re-measured, THE FIRST REAL RUN ARTEFACT EXISTS, and FR-3 drift validation is
measured. PRD §12 goes from 2 of 6 acceptance criteria to 3½ of 6.
368 pass, 1 skipped, ruff clean, provenance PASS. Commits 08ce088..7f9e4c7.

  DATASETS NOW: marida, oscar (87 files, 2.89 GB), drifters, rivers, mpa all
  PRESENT. Only gfw missing. sentinel2 stays "missing" and does not matter —
  imagery streams from Planetary Computer.

  ### 1. CREDENTIALS — verified properly, and my first check was wrong

  EARTHDATA_TOKEN and GFW_API_TOKEN are in .env and both authenticate. NOTE
  EARTHDATA_TOKEN EXPIRES 2026-11-03; when it lapses PO.DAAC answers with a 302
  to a login page rather than an error, so it will look like a broken download.

  I first "verified" Earthdata by getting HTTP 200 from CMR granule search and
  calling it AUTH OK. That endpoint is PUBLIC — 200 with no token at all. The
  control run (no token / bad token / real token) exposed it. Real proof was
  pulling 2048 bytes of HDF from archive.podaac.earthdata.nasa.gov. GFW proved
  by discrimination: no token 401, bad token 401, real token 422.

  ### 2. FR-2.2 RE-MEASURED — the harm is gone, the contribution is still zero

      16PCC 2020-09-18->09-23, measured current 0.0139 m/s
        incoherent rejections  6 -> 0
        true debris lost       1 -> 0
        dF1               -0.167 -> 0.000
        TRANSIENTS FOUND WITH THE REAL FIELD: still 0

  It moved from ACTIVELY HARMFUL to INERT, not to load-bearing. "Blocked on
  FR-3.1" is no longer the honest framing: that data exists now, the check got
  exactly what it asked for, and it still earns nothing. The cause is NAMED —
  nearest-neighbour matching means the transient never fires — and the fix is a
  design change to check_persistence, not more data. eval/results.md and PRD §12
  are rewritten. This is a BETTER result for the report: the original could be
  dismissed as "you were missing a dataset".

  Caveat that must travel: OSCAR is 0.25 deg and three of the four AOIs are
  SMALLER THAN ONE GRID CELL. 18QYF reads 0.0001 m/s in March and 0.0907 in
  November over the IDENTICAL AOI. Fine as an envelope, not a statement about
  local circulation.

  ### 3. FR-3 DRIFT VALIDATION — PRD §12 bullet 3 now has a number

  New scripts/eval_drift.py. 19 drogued Global Drifter Program tracks, 406
  observations, scored against run_trajectory on the real OSCAR field:

      mean track error   34.64 km
      median / worst     35.51 / 73.88 km
      within envelope    24.5%

  TWO FINDINGS THE MEAN HIDES, both in eval/results.md:
  1. Error is BIMODAL in horizon, not noise: 10.46 km and 52% inside the
     envelope at <=4.5 days, against 48.74 km and 9% beyond. 4.7x growth with a
     known cause — GriddedCurrentField has no time axis, so a six-month window
     collapses to one mean field. The reader's docstring predicted exactly this.
     THE PIPELINE DRAWS A 7-DAY TRACK, so the honest headline for what the
     console shows is the WORSE number.
  2. THE ENVELOPE IS MISCALIBRATED. It contains the truth one time in four, 9%
     beyond 4.5 days. Calibration finding, not integrator failure — the mean
     path is good at short range.

  RUN IT ON 2014, NOT THE DEMO WINDOW. Zero drifters crossed this region during
  the demo window, so validation can only ever be a model check over another
  period. eval/drift.json records window_is_demo_window structurally, provenance
  pins it False, and the artefact is deliberately NOT SURFACED on the console:
  showing it beside the displayed trajectories would imply it validates them.

  The first attempt FAILED and that was correct. 3855 undrogued observations are
  excluded (a buoy that has shed its drogue is wind-driven; OSCAR models the
  15 m current), which left no usable 2018 track. The script refused rather than
  relaxing MIN_OBSERVATIONS. 2014 was then chosen because that is where the
  drogued buoys are — 19 tracks against 0 — and OSCAR fetched for it.

  ### 4. THE FIRST REAL RUN ARTEFACT — and why there was never one before

  webapp_data/gulf_of_honduras.run.json, COMMITTED: 826 CNN detections on real
  streamed Sentinel-2, 443 verified, 383 rejected with reasons, 443 trajectories
  on a 32-step OSCAR field, 2.85 MB, synthetic=False.

  ROOT CAUSE OF THE SYNTHETIC-ONLY HISTORY: export_run.real_config() was
  STRICTER THAN THE PIPELINE IT FEEDS. PipelineConfig takes current_field,
  river_table, vessel_detections and protected_areas as None and degrades
  explicitly around each — that IS the documented convention — but real_config
  called all five loaders unconditionally, so one absent dataset blocked a run
  the pipeline was built to survive. New --allow-degraded resolves what is
  present and names what is not in the artefact's provenance. Imagery stays
  mandatory: no tiles, no run.

  THE CNN IS NOW WIRED INTO pipeline.py (PipelineConfig.detector, and
  --detector on export_run). The import is LAZY because torch is
  workstation-only and requirements-deploy.txt omits it while pipeline sits in
  the deployed server's import graph via webapp.planning. Verified by importing
  the server with torch and the geo stack blocked.
  On real data the CNN gave 3600 candidates -> 826 while verified held at
  448 -> 443. Same debris, a quarter of the proposals.

  SIZE went 13 MB -> 2.85 MB in the order the evidence pointed: the CNN, then
  step_hours=12 once trajectories were 63% of the file, then compact JSON —
  indentation alone was 1.74 MB of 4.59 MB.

  ### 5. AN ENCODING BUG I MIS-DIAGNOSED TWICE

  The demo region's em dash was arriving as three characters. ROOT CAUSE was
  config.py reading regions.yaml with open() and no encoding: cp1252 on this
  workstation, UTF-8 on the Air and in the Linux container. E2 80 94 became
  U+00E2 U+20AC U+201D.

  I called it fixed twice while it was still broken. First as an
  artefact-writer bug — which it also was, separately — then as resolved
  because get_region() PRINTED correctly. IT DOES NOT: a terminal renders the
  mojibake close enough to an em dash to fool a reader. Only visible in
  codepoints. The lesson, and it cost an hour: "the file decodes cleanly" and
  "the file says the right thing" are different assertions, and print() is not
  a test for either.

  EVERY text read in the package is now explicit — regions.yaml, the river
  table, the MPA extract, vessel records, provenance, four in benchmark.py.
  Most carry no non-ASCII today, so the bug was latent in all of them. The
  regression tests assert on CODEPOINTS and cover Gonave's circumflex too.

  ### 6. DATASETS — what the downloads actually needed

  MPA: Protected Planet marine geodatabase, layer WDPA_WDOECM_poly_Sep2026_marine.
  82 areas for the region (Islas de la Bahia, Punta de Manabique, Cayos
  Cochinos, Turneffe Atolls). 25 of 82 are poorly described by a circle, worst
  0.02 — that is the number to quote if asked how MPA proximity is modelled.

  RIVERS: needed a new scripts/convert_meijer_rivers.py, because the Meijer
  2021 dataset (figshare 14515590) ships as a shapefile with ONE attribute and
  NO RIVER NAMES. Two things recorded rather than assumed:
    - dots_exten IS the emission figure: it sums to 1,005,984 t/yr, Meijer's
      published global estimate. The truncated name is a shapefile artefact.
      An arbitrary display field has no reason to total the paper's headline.
    - The missing names are not an omission — Meijer models mouths from
      hydrology, not a gazetteer. Names are OURS, by coordinate proximity, and
      every row carries name_source so a report can separate "ranked 4th by
      modelled emission" from "the Motagua". THIS DISTINCTION MUST SURVIVE
      INTO THE REPORT.

  ### 7. THE CONSOLE WAS REDESIGNED THREE TIMES, ALL ON MAIN

  Ashwin asked for successive directions; the third landed and merged. Now: a
  sidebar rail (nav + active panel) | dominant map | investigation panel. The
  old tab strip is gone — Detections/Rejected/Controls are sidebar items and
  Diagnostics opens the metrics drawer. Every rail item is an existing panel;
  nothing invented. Geist replaces IBM Plex, Geist Mono for technical values
  only. ~1000 lines of frontend changed across 7 commits.

  BASEMAP: two providers failed the same way and the shape is worth knowing.
  Neither returns 404 when it cannot serve a tile — CARTO returns one stamped
  "API KEY REQUIRED", Esri's Ocean basemap one reading "Map data not yet
  available" past zoom 10, both HTTP 200. So tileerror never fires and the
  graticule fallback never triggers. Now Esri Canvas at maxNativeZoom 16,
  MEASURED tile-by-tile at both regions, not taken from the service metadata
  which claims 23. IF YOU CHANGE BASEMAP, FETCH A TILE AT THE ZOOM YOU CARE
  ABOUT AND LOOK AT IT.

  THE INVARIANT THAT MUST SURVIVE ANY FURTHER UI WORK: the verification
  precision gain and the detector's region recall render together, same size,
  whenever the diagnostics strip is open. .metric-value is one class with no
  hero variant. eval/results.md requires the pair and
  test_benchmark_never_serves_the_gain_without_the_region_recall enforces it.
  docs/console-redesign-brief.md lists all eleven honesty invariants.

  ### 8. WHERE THE PROJECT STANDS

  PRD §12: 2 done (verification benchmark, evidence traceability), 3½ counting
  drift; criterion 1 is PARTIAL — the real run had 3 of 6 agents on real data
  when it was exported, and rivers/mpa have since landed, so A RE-EXPORT NOW
  WOULD GIVE 5 OF 6. That is the single highest-value next action here and
  takes about 20 minutes.

  Also open: FR-5 needs CODE not the token (vessels.py sar_detections is still
  NotImplementedError); the system-level ablation on real inputs; THE REPORT,
  which is the largest remaining item and has only an outline; the console
  defaults to the synthetic run though a real one now exists; deploy to a URL.

  docs/project-status.md is a one-page summary for the team and supervisor,
  every claim verified against the repo.

2026-09-04 (earlier, workstation) — Workstation — EARTHDATA_TOKEN EXISTS. OSCAR
DOWNLOADED. FR-2.2 RE-MEASURED AGAINST A REAL CURRENT FIELD. The harm is gone and
the contribution is still exactly zero. 325 pass, 1 skipped, ruff clean,
provenance PASS. data/oscar is now `present` for the first time in this project.

  CREDENTIALS VERIFIED PROPERLY, and my first attempt was wrong. I probed
  EARTHDATA_TOKEN against CMR granule search, got HTTP 200 and reported AUTH OK.
  That endpoint is PUBLIC — it returns 200 with no token at all, so the check
  proved nothing. Control runs (no token / bad token / real token) exposed it.
  Real proof: 2048 bytes of HDF pulled from archive.podaac.earthdata.nasa.gov
  where no token gets a 302 to a login page. GFW proved by discrimination: no
  token 401, bad token 401, real token 422 (auth passed, query malformed).
  NOTE EARTHDATA_TOKEN EXPIRES 2026-11-03 — about 60 days. When it lapses PO.DAAC
  answers with a redirect to a login page, not an error, so it will look like a
  broken download rather than an expired credential.

  NEW scripts/fetch_oscar.py. 32 granules, 1.06 GB, 0 failed.
      python scripts/fetch_oscar.py --pairs
  Fetches only the days the FR-2.2 pairs span. The full Feb-Oct demo window is
  243 files and 7.7 GB, which is a lot of disk to compute one time-mean field
  over a small bbox. THE COLLECTION IS FINAL, NOT NRT: OSCAR_L4_OC_NRT_V2.0
  begins in 2021 and returns ZERO granules for the 2018 dates, which reads as
  "no data exists" rather than "wrong collection". The script checks magic bytes
  on everything it writes and deletes anything that is not NetCDF, so an expired
  token fails loudly instead of leaving an HTML login page on disk as a .nc.

  TRAP 6 IN THE OSCAR READER, found by the first real file. OSCAR FINAL declares
  calendar: julian, so xarray decodes time to cftime.DatetimeJulian and window
  selection raises TypeError: cannot compare ... (different calendars). Synthetic
  fixtures decode as datetime64, so NO TEST COULD HAVE CAUGHT THIS before the
  data existed — the Air built the reader correctly against what it could see.
  Fixed in _standard_calendar. The conversion is by date COMPONENTS, not absolute
  instant: Julian and Gregorian differ by ~13 days for modern dates, and
  reinterpreting the instant would have silently shifted every field a fortnight
  and selected the wrong days. Verified against granule filenames (2018-09-13 to
  2018-09-13, matching the _20180913 file) BEFORE relying on it.

  THE RESULT. --oscar on eval_multitemporal.py sizes the envelope from the real
  field. All four pairs re-run:
      pair                     speed m/s   rejects   debris lost      dF1
      16PCC 2020-09-18->09-23     0.0139    6 -> 0      1 -> 0   -0.167 -> 0.000
      18QYF 2020-03-14->03-19     0.0001    0 -> 0      0 -> 0    0.000 -> 0.000
      18QYF 2020-11-29->12-04     0.0907    0 -> 0      0 -> 0       n/a
      16PCC 2018-09-14->09-19     0.0157    0 -> 0      0 -> 0       n/a
      TRANSIENTS FOUND, WITH THE REAL FIELD: 0
  Envelope grows 5 km -> ~11 km on the headline pair. Every false rejection and
  the one true-debris loss disappear. FR-2.2 moved from ACTIVELY HARMFUL to
  INERT, not to load-bearing. The 0.10 m/s sensitivity arm predicted this
  correctly for a slightly wrong reason — the real current is 0.0139 m/s, an
  order of magnitude slower, and the rejections vanish anyway because doubling
  the envelope sufficed.

  WHY THIS IS A BETTER RESULT FOR THE REPORT, not a worse one: the original
  negative could be dismissed as "you were missing a dataset". This version says
  the dataset arrived, the check got exactly what it asked for, and the answer
  did not change. The cause is now NAMED — nearest-neighbour matching means the
  transient never fires — and the fix is a design change to check_persistence
  (drift-predicted position plus a spectral-similarity gate), not more data.

  THE MEASURED SPEEDS ARE SUB-GRID AND THREE OF FOUR MUST NOT BE QUOTED ALONE.
  OSCAR is 0.25 deg (~28 km); these AOIs are 5-60 km. 16PCC headline spans
  2.32 x 0.70 cells — the only one resolving more than one. 18QYF spans
  0.48 x 0.19, SMALLER THAN ONE CELL, so every sample interpolates between the
  same few nodes. The giveaway is 18QYF reading 0.0001 m/s in March and 0.0907 in
  November over the IDENTICAL AOI — a 900x swing showing the field is poorly
  constrained there, not seasonal variability anyone resolved. Fine for an
  envelope (debris advects with the large-scale current); not a statement about
  local circulation. Do not quote 0.0001 m/s as Gulf of Gonave's current.

  A MACHINE-DEPENDENT TEST BROKE AND I FIXED THE TEST, not the data.
  test_a_missing_dataset_points_at_the_fetch_command asserted `oscar` was ABSENT
  and started failing the moment OSCAR was downloaded. A test that passes only on
  the machine missing the data is the same broken shape as one that passes only
  on the machine holding it. Now hermetic via a tmp DATA_ROOT, plus two new tests
  for the other half of the contract: a populated dataset resolves, and a
  directory holding only .gitkeep still counts as missing.

  FOR THE AIR — THE CONSOLE IS NOW STALE, and this is the next UI job.
  benchmark.py still reads eval/multitemporal.json (no field) and still states
  FR-2.2 is "blocked on FR-3". FR-3.1's data now exists, so that caveat is false.
  It needs the CAVEAT REWRITTEN, not the number swapped: the finding is no longer
  "blocked on a missing dependency" but "given the dependency, still inert,
  because of the matching strategy". Registered in provenance as surfaced=False
  with that gap spelled out, so the checker records it rather than letting it
  pass silently.

  STILL BLOCKED: GFW_API_TOKEN exists and is verified, but vessels.py
  sar_detections() is still NotImplementedError, so FR-5 needs code, not the
  token. Protected Planet and the river table are still undownloaded, so FR-4 and
  FR-6.1 are unchanged. FR-3 drift validation is now UNBLOCKED for the first time
  — OSCAR and the drifters are both here — but remember zero drifters crossed the
  demo region during the demo window, so it must be reported as a model check
  over other years, never as validating the demo run.

2026-09-04 (earlier, workstation) — Workstation — CLOSED THE VIVA PACK'S §6 ITEM 1:
the CNN probability-threshold sweep is no longer prose-only. All eighteen
published cells reproduced EXACTLY. 323 pass here, 1 skipped, ruff clean,
provenance PASS.

  VERIFIED THE AIR'S WORK FIRST, since five commits landed at once. 323 pass on
  this machine against their 347 — the difference is tests/test_webapp.py, which
  importorskips because fastapi is deliberately Air-only. Not a failure. Their
  `python -m ghostnet.provenance` PASSES here too: 0 artefacts unaccounted for,
  0 served numbers undeclared, 0 numbers disagreeing with their evidence. The
  §12 evidence-traceability bullet is genuinely closed, and closed as a CHECK
  rather than as a document, which is the part that will survive.

  THEIR FINDING WAS CORRECT AND I CONFIRMED IT BEFORE FIXING IT. eval/results.md
  carried the 0.20–0.70 table justifying DEFAULT_PROB_THRESHOLD = 0.40 and no
  eval/*.json held those rows — grepped, not assumed. Same shape as the FR-2.2
  supporting-arms gap: a number the report leans on that nothing could re-derive.

  NEW --prob-sweep ON eval_marida.py, so it is one command rather than six runs
  and a hand-assembled table:
      python scripts/eval_marida.py --prob-sweep --detector cnn --split val \
          --json eval/cnn_prob_sweep_val.json
  Re-run on val against models/detector_v1.pt (epoch 51, cuda). Every cell:
      prob  precision      F1   region recall
      0.20     0.7825  0.8780   0.7038 (316/449)
      0.30     0.8219  0.9022   0.7350 (330/449)
      0.40     0.8626  0.9262   0.7550 (339/449)  <- DEFAULT
      0.50     0.8885  0.9410   0.7127 (320/449)
      0.60     0.8915  0.9426   0.6169 (277/449)
      0.70     0.9031  0.9491   0.4989 (224/449)
  Identical to the published table in all 18 cells, and no drift warning fired.

  TWO SAFEGUARDS BUILT IN, both because of how this project keeps getting bitten:
  1. --prob-sweep REFUSES --split test, with the reason in the error. Sweeping an
     objective over the held-out split is how it stops being held out: every
     later test number would then be reported through a cut-off chosen on test.
     The threshold was selected on val and must stay that way.
  2. It WARNS if the sweep's best region recall stops matching the configured
     DEFAULT_PROB_THRESHOLD, so the constant and eval/results.md cannot drift
     apart silently — which is exactly how the FR-2.4 baseline was lost once.

  REGISTERED IN THE AIR'S PROVENANCE SYSTEM, and it caught me first. Adding a new
  eval/*.json made their check FAIL with "artefacts nothing accounts for: 1"
  before I had registered it. That is the check doing its job on its first
  encounter with a file it had never seen, which is the strongest evidence it
  works. Now an Artefact entry, unsurfaced (the console reports the detector's
  performance, not how its cut-off was chosen), with nine invariants pinning the
  two facts the write-ups lean on: 0.40 is still the region-recall optimum, and
  precision peaks somewhere else. If a re-run moved either, the claim that the
  objectives conflict would need REWRITING, not re-quoting.

  ALSO UPDATED docs/viva-pack.md, the Air's file — flagging that again. Its §6
  item 1 said the table was prose-only, and its §4 defence of 0.703 pointed at
  that gap. Both now false. §6 item 1 is struck through and marked CLOSED with
  the artefact and command; §4 answers "why 0.40?" from the artefact instead of
  from reasoning. Their §6 items 2 and 3 are untouched and still stand — the
  fdi_sweep train/test warning is a good catch and needs no code.

  NOTE ON HANDOFF.md: the Air's copy did not reach this machine. That is the
  gitignore working as designed — hand-off prompts are pasted by hand, not
  committed — but worth knowing that anything written only there does not
  travel. The Status Log did its job instead, which is the point of the rule.

  STILL THE BOTTLENECK, unchanged and still nobody's: EARTHDATA_TOKEN,
  GFW_API_TOKEN, Protected Planet, the river table. FR-2.2's re-measurement,
  FR-3, FR-4, FR-5, FR-6.1, the system-level ablation on real inputs and the
  end-to-end latency figure all still wait on that account work.

2026-09-04 (earlier, MacBook Air) — MacBook Air — WROTE THE REPORT AND VIVA
MATERIALS: docs/viva-pack.md (238 lines) and docs/report-outline.md (175), plus
tests/test_report_materials.py guarding both. 347 pass, 1 skipped, ruff clean,
provenance PASS. This was the last unstarted §12 item.

  MACHINE RE-VERIFIED: role laptop, cuda no, GPU training OK NO, python 3.11.15.
  Pulled first: already at 031dbb0. Nothing re-run — assembled by READING
  committed eval/*.json, same method as docs/ablation-study.md.

  ### docs/viva-pack.md — built around "derive and defend"

  Not a summary of the results; a defence of them. Every claim is written as
  CLAIM -> ARTEFACT -> DERIVATION -> THE ANSWER YOU GIVE OUT LOUD, with the
  sample size attached to each, because "is n big enough" is the question that
  follows every figure here. Also carries:
    - the four pairings that must never be broken (gain without region recall;
      +0.385 without +0.080; 0.703 without "within-tile"; the load-bearing claim
      without the FR-2.2 exception);
    - nine anticipated questions with answers, including the hostile ones
      ("isn't your verification agent redundant now?", "how do I know the
      baseline isn't badly tuned?");
    - the DO-NOT-CLAIM list with the reason for each;
    - the demo running order and the offline fallback.

  ### THREE THINGS FOUND BY CHECKING PROSE AGAINST ARTEFACTS

  1. THE CNN PROBABILITY-THRESHOLD SWEEP IS PROSE-ONLY. eval/results.md carries
     the 0.20-0.70 table that justifies DEFAULT_PROB_THRESHOLD = 0.40, and NO
     eval/*.json holds it. "Why 0.40?" is a likely viva question and the answer
     currently rests on prose that cannot be re-derived. Same shape as the FR-2.2
     supporting-arms gap. FOR THE WORKSTATION: re-run the sweep to its own
     --json. Until then the pack says the table is not artefact-backed and
     defends the choice by its reasoning instead.
  2. fdi_sweep IN marida_ablation.json IS THE TRAIN FIT, NOT TEST. At 0.025 it
     reads P=0.4144, region recall 0.5541 over n=835; held-out test is 0.2381
     and 0.4068 over n=336. Both live in the SAME FILE. Quoting the sweep as a
     test result would overstate the detector by 15 points of region recall.
     Recorded in the pack so nobody mixes them.
  3. THE 0.7525 -> 0.753 ROUNDING NOW HAS AN ANSWER. An evaluator with the JSON
     open will ask why the report says 0.753 when the artefact says 0.7525:
     half-up vs half-to-even. The console already hit this (toFixed gave 0.752);
     the pack now carries the explanation so it is a convention, not a
     discrepancy.

  ### docs/report-outline.md — section by section, marked [E]/[W]/[B]

  Evidence-backed / needs a person / blocked on data. Roughly half the report can
  be assembled from artefacts and half cannot. It deliberately DOES NOT draft
  the introduction, related work, discussion or conclusion — the governing rule
  applies to prose too, and a generated related-work section fails on contact
  with the first question. It does say which discussion points are worth
  leading with, and they are all negative results.

  ### tests/test_report_materials.py — 12 tests, and the NEGATIVE ones matter

  Positive: every headline figure still matches its artefact; both verification
  gains present; "within-tile" and 91% present. Negative: the do-not-claim list
  still names each prohibition, and THE PACK NEVER CLAIMS DRIFT WAS VALIDATED.
  PROVED IT BITES — inserted "We validated the drift model against the drifter
  tracks" and it fails with "the pack claims 'validated the drift'". Reverted.
  A document that quietly acquires a forbidden claim later is exactly the
  failure this guards.

  ### STILL THE BOTTLENECK, unchanged
  EARTHDATA_TOKEN and GFW_API_TOKEN still do not exist; Protected Planet and the
  river table still undownloaded. Drift, FR-4, FR-5, FR-6.1, FR-2.2's
  re-measurement, the real-input ablation and end-to-end latency all still
  blocked on that account work. Console still not live at a URL. With this, every
  PRD §12 item has something written or built against it; what is left is not
  writing but data.

2026-09-03 (earlier, MacBook Air) — MacBook Air — CLOSED THREE REAL GAPS IN THE
GENERALISATION SURFACING. Most of this task had already landed in 6e36f56; the
hand-off predated it. What had NOT landed was the part that matters most.
335 pass, 1 skipped, ruff clean, tsc clean, provenance check PASS.

  MACHINE RE-VERIFIED: role laptop, cuda no, GPU training OK NO, python 3.11.15.
  Pulled first: already at 6e36f56, up to date.

  ### WHAT WAS ALREADY DONE (6e36f56, previous session)
  benchmark.py reads both holdout artefacts; the strip has a fourth item beside
  region recall; expanding gives the paired table, the 84-patch sample and the
  caveats; and in_distribution_test is never read, so the forbidden number never
  entered the payload. I re-verified each rather than assuming.

  ### GAP 1 — "WITHIN-TILE" WAS ONLY IN A HOVER HINT
  This is the one worth reading twice. The caveat was in the Metric's `hint`
  attribute, so it existed but was INVISIBLE: not on the collapsed strip, not in
  a screenshot in a report, not on touch. An evaluator scanning the strip saw
  region recall 0.703 with nothing telling them it was within-tile — which is
  exactly the defect the hand-off was written to fix, and my previous session
  had only half-fixed it. It now renders on the face, in warning colour, on the
  number it qualifies:
      DETECTOR REGION RECALL  0.407  misses 140/236  within-tile
  Putting a caveat somewhere it technically exists is not the same as putting it
  where it will be read.

  ### GAP 2 — NOTHING GUARDED THE TRAP
  in_distribution_test was not served, but nothing stopped a future change from
  serving it. Added test_benchmark_never_serves_the_pairing_that_reads_backwards
  (tests/test_webapp.py), in the spirit of the region-recall guard. It is
  STRUCTURAL rather than a string search: it reads the forbidden value out of
  eval/holdout_18QYF.json and asserts no served generalisation field carries it,
  and that no field is even NAMED for that arm, which is how it would creep back.
  PROVED IT BITES: added in_distribution_f1 to the model and re-ran — fails with
  "generalisation.in_distribution_f1 serves 0.6637, the holdout model's
  rest-of-test score ... reads backwards — see eval/results.md." Reverted.
  Three more guards alongside it: the arms are the same 84 patches at 13.24
  px/patch, the caveats warn off the bad pairing, and the shipped detector is
  still fdi/cnn.

  ### GAP 3 — THE UI DID NOT SAY WHICH CHECKPOINT SHIPS
  The strip showed a second model's scores with nothing saying detector_v1.pt is
  still the pipeline's detector. A reader could reasonably have concluded the
  run on screen came from the holdout model. Sixth caveat added, and asserted by
  test_the_console_never_implies_the_holdout_model_is_the_shipped_detector.

  ### VERIFIED IN THE BROWSER, not just in tests
  Read back off the rendered DOM: "within-tile" visible, the checkpoint caveat
  rendered in full, the paired table (0.930 -> 0.858) and the 84-patch sample
  present, the -0.194 wrong-sign warning present, and 0.6637 NOWHERE on screen.
  Static export rebuilt.

  ### STILL THE BOTTLENECK, unchanged
  EARTHDATA_TOKEN and GFW_API_TOKEN still do not exist; Protected Planet and the
  river table still undownloaded. FR-2.2's re-measurement, FR-3, FR-4, FR-5,
  FR-6.1, the real-input system ablation and end-to-end latency all still
  blocked on that account work. Console still not live at a URL. The remaining
  §12 item is the report and viva materials.

2026-09-03 (earlier, MacBook Air) — MacBook Air — BUILT THE PRD §12 EVIDENCE
TRACE: a repeatable reconciliation check (ghostnet.provenance) plus the
walk-through doc. 331 pass, 1 skipped, ruff clean, tsc clean. This was the last
§12 bullet with nothing built against it.

  MACHINE RE-VERIFIED: role laptop, cuda no, GPU training OK NO, python 3.11.15.
  All 7 datasets MISSING. Nothing measured here — the check READS committed
  eval/*.json, which is all the Air can do and all it should.

  ### HALF A — src/ghostnet/provenance.py + tests/test_provenance.py

  88 Claims declare every number /api/benchmark serves against the artefact and
  JSON pointer behind it. It asserts BOTH directions, because either alone
  leaves a hole:
    - every declared field still equals what its artefact records; and
    - NO UNDECLARED NUMBER reached the wire. Adding a figure to the report
      without declaring its evidence now fails the suite.
  Plus: every eval/*.json accounted for (surfaced, or registered
  checked-not-surfaced WITH THE REASON), and unsurfaced artefacts held to
  recorded invariants so a supporting result cannot rot unnoticed.
  Run it: python -m ghostnet.provenance

  A MISMATCH FAILS NAMING THE FIELD, BOTH VALUES AND THE SOURCE FILE, and
  several tests deliberately break something to prove it — a check that cannot
  be made to fail proves nothing.

  ### THE CHECK'S FIRST TWO USEFUL ACTS

  1. FOUND A ROUNDING-ORDER DISAGREEMENT. The console derives the CNN
     verification gain as 0.7514 - 0.6716 = 0.0798; the artefact records
     precision_delta 0.0799, because the eval script rounds a full-precision
     delta while the console subtracts two already-rounded values. Both display
     as +0.080 so NO PUBLISHED CLAIM IS AFFECTED. Handled with a documented
     ROUNDING_TOLERANCE (5e-4) that applies ONLY to derived-vs-recorded
     comparisons; direct reads stay at 5e-7.

  2. FOUND A GAP IN MY OWN FIRST DESIGN, and this one matters. Reconciliation
     ALONE CANNOT CATCH A DOCTORED ARTEFACT: the console reads the same JSON, so
     editing it moves both sides together and they still agree. I proved this by
     doctoring detector_cnn_test.json — the check said PASS. Correct behaviour
     (the artefact IS the source of truth) but it left the published figures
     tamper-blind, which are exactly the ones a report and a viva quote.
     Closed with PUBLISHED: 18 pins holding the headline numbers eval/results.md
     actually publishes. Nothing is computed — they are the machine-readable
     form of "eval/results.md is the authority". Re-ran the same tamper: now
     FAILS, naming both values and pointing at the prose. My draft walk-through
     had claimed the plain check would catch this; that claim was WRONG and is
     corrected in the doc, including which guard actually fires.

  ### THE SURFACING DECISION (part of the task)

  Six artefacts were unread, not four. Decided:
    SURFACED — holdout_18QYF.json + holdout_18QYF_leaky.json. The strip already
      shows REGION RECALL, which is a WITHIN-TILE number, and alone it reads as
      generalisation evidence. That is the SAME DEFECT docs/ablation-study.md §4
      was corrected for last session, and the console still had it. It now shows
      the paired holdout beside it: F1 0.930 -> 0.858, -0.072 on an unseen
      region, with the wrong-sign subtraction (-0.194) warned against in the
      caveats and the 8.5%-less-data upper bound carried across.
      New GeneralisationResult in benchmark.py + loader that REFUSES an unpaired
      experiment (different patch counts would measure task difficulty, not
      geography). Rendered in MetricsStrip, collapsed metric + expanded detail.
    CHECKED, NOT SURFACED — the sensitivity arm and the three supporting FR-2.2
      pairs, each with its reason recorded in ARTEFACTS. The sensitivity arm is
      the strongest candidate to promote next: it would turn the "blocked on
      FR-3.1" caveat from an assertion into a number.

  ### HALF B — docs/evidence-traceability.md

  The walk-through, ~250 lines. Distinguishes the TWO kinds of claim the console
  makes: about THIS RUN (evidence refs + provenance) and about MEASURED QUALITY
  (eval/*.json via the check). Traces one detection through all four evidence
  kinds — sentinel2_tile, current_field, vessel_record, river_table — including
  that the drift ref carries the SEED, so an envelope is reproducible rather
  than merely plausible. Also traces a REJECTED detection, which keeps its tile
  ref and all five check reasons: the absence of downstream output is itself
  traceable. Then a 10-step viva sequence ending in breaking the check on
  purpose.

  tests/test_evidence_trace.py pins the walk-through's structural claims against
  the committed artefact, so the document cannot rot either.

  ### CONSTRAINTS HONOURED
  Synthetic fixtures only — no network, credentials or downloaded data; the
  check reads committed artefacts, which are not downloaded data. The run is
  still SYNTHETIC and still says so on its face (asserted by a test). Nothing
  computes a metric a second way: derived fields are checked as arithmetic
  identities over JSON-backed inputs, and eval/results.md remains the authority.

  ### STILL THE BOTTLENECK, unchanged
  EARTHDATA_TOKEN and GFW_API_TOKEN still do not exist; Protected Planet and the
  river table are still undownloaded. FR-2.2's re-measurement, FR-3, FR-4, FR-5,
  FR-6.1, the real-input system ablation and end-to-end latency remain blocked
  on that account work. Console still not live at a URL. With this bullet
  closed, the remaining §12 item is the report and viva materials.

2026-09-02 (earlier, MacBook Air) — MacBook Air — FOLDED THE GEOGRAPHIC
GENERALISATION RESULT INTO docs/ablation-study.md §4, WHICH WAS SILENTLY
PRESENTING A WITHIN-TILE NUMBER AS IF IT SHOWED GENERALISATION. Doc only, no
code. 300 pass, 1 skipped, ruff clean, tsc clean.

  MACHINE RE-VERIFIED: role laptop, cuda no, GPU training OK NO, python 3.11.15.
  All 7 datasets MISSING here. Nothing re-measured — every figure was read from
  the committed JSON, which is all the Air can do.

  ### THE PROBLEM WITH §4 AS IT STOOD

  It presented region recall 0.407 -> 0.703 with no indication that 327 of the
  359 test patches (91%) sit on MGRS tiles the model trained on, because MARIDA
  splits by patch rather than by tile. The comparison is still FAIR — the FDI is
  scored through the identical path — but it is not evidence of generalisation,
  and §4 read as though it were. There is now a blockquote saying exactly that,
  placed immediately after the headline table so it cannot be missed, pointing
  at the new §4.2.

  ### NEW §4.2 — the paired holdout, and the trap next to it

  A second detector trained with 18QYF (Gulf of Gonave) withheld from train AND
  val — val too, because selection is on val debris F1. Both models scored on
  THE IDENTICAL 84 18QYF patches:

      detector_v1 (trained on it)   P 0.9355  R 0.9254  F1 0.9304
      holdout    (never saw it)     P 0.9085  R 0.8129  F1 0.8581
      cost of the region unseen       -0.0270   -0.1125   -0.0723

  ABOUT 7 F1 POINTS ON UNSEEN WATER, ALMOST ALL OF IT RECALL. Precision barely
  moves: it finds less on new water but what it flags stays trustworthy — the
  better failure direction for a screening stage feeding verification.

  THE NUMBER THAT MUST NOT BE QUOTED is written into the section rather than
  left to be rediscovered: the holdout model's rest-of-test F1 (0.6637) minus
  its 18QYF F1 (0.8581) is -0.194, WRONG SIGN, because 18QYF carries 13.24
  debris px/patch against 0.98 for the rest of test. That subtraction measures
  task difficulty, not distribution shift. Only the paired table is valid.
  All five caveats carried across verbatim, including the two that most change
  how the number reads: the holdout model trained on 8.5% LESS DATA so -0.072 is
  an UPPER BOUND, and Haiti is the same current system as the demo region, so
  this is an unseen TILE in the western Caribbean, not a different ocean.

  ### VERIFIED AGAINST THE ARTEFACTS, NOT THE PROSE

  Wrote a check that pulls all 13 figures out of eval/holdout_18QYF.json and
  eval/holdout_18QYF_leaky.json and asserts each appears in §4.2: 13/13 match,
  0 mismatches. It also asserts the two arms are genuinely PAIRED (both 84
  patches at 13.24 px/patch) — if a future re-run broke the pairing the table
  would be meaningless, and that is now checkable rather than assumed.

  ONE FIGURE IS DELIBERATELY NOT JSON-BACKED and is labelled as such in the
  doc: the 91% within-tile share is a property of the MARIDA split files, not of
  any run, so it cannot be re-derived from eval/*.json. It is asserted in
  scripts/train_cnn.py and eval/results.md and needs the splits (workstation
  only). Flagged in the header so the "everything is JSON-backed" claim stays
  true.

  ### ALSO, since your two fixes landed
  §4.1's discrepancy block and the header now read RESOLVED rather than
  "needs a correction" — your correction is in eval/results.md and I confirmed
  the table there matches detector_cnn_test.json. §5.1/§8/§9 are yours,
  untouched. §1's table now names the unseen-region holdout beside the
  held-out test/val.

  ### STILL THE BOTTLENECK, unchanged
  EARTHDATA_TOKEN and GFW_API_TOKEN still do not exist; Protected Planet and the
  river table are still undownloaded. FR-2.2's re-measurement, FR-3, FR-4, FR-5,
  FR-6.1, the system-level ablation on real inputs and end-to-end latency remain
  blocked on that account work. Console still not live at a URL. Next
  credential-free item is the §12 evidence-traceability demo.

2026-09-02 (earlier, workstation) — Workstation — RE-RAN ALL FIVE FR-2.2 ARMS TO
PER-ARM ARTEFACTS, closing the Air's §9 item 2. EVERY PUBLISHED CELL REPRODUCED
EXACTLY. 280 pass, 1 skipped, ruff clean.

  THE GAP THE AIR FOUND WAS REAL. eval_multitemporal.py writes whichever run it
  was last given, so the three supporting pairs and the 0.10 m/s sensitivity row
  had been run and then overwritten — present in eval/results.md prose, absent
  from any committed artefact. Not fabricated, just not re-derivable, which for
  a graded report is close enough to the same problem.

  ALL FOUR PAIRS AND THE SENSITIVITY ROW NOW VERIFY CELL-FOR-CELL against the
  published table — candidates, labelled count, all three deltas, true debris
  lost:
      16PCC 2020-09-18->09-23  144 cand, 12 lab, dF1 -0.167, 1 lost   MATCH
      18QYF 2020-03-14->03-19   21 cand,  7 lab, dF1  0.000, 0 lost   MATCH
      18QYF 2020-11-29->12-04   22 cand,  0 lab, no deltas,  0 lost   MATCH
      16PCC 2018-09-14->09-19    0 cand,  0 lab, no deltas             MATCH
      sensitivity 0.10 m/s: 6 rejections -> 0, 1 debris lost -> 0      MATCH
  Artefacts: eval/multitemporal.json plus _18QYF_2020-03, _18QYF_2020-11,
  _16PCC_2018-09 and _sensitivity_010. Nothing in the FR-2.2 conclusion moves —
  it is still a measured NEGATIVE, still blocked on FR-3.1, still to be reported
  as a dependency and never as a contribution. What changed is that all of it is
  now backed by an artefact instead of prose.

  A TRAP IN THE AIR'S SUGGESTED COMMANDS, fixed in their doc. §8 proposed
  `--tile 18QYF --date-a ... --json ...` with NO --bbox. The bbox default is the
  HEADLINE PAIR'S — a Gulf of Honduras box. Run that way, an 18QYF pair scores a
  Haiti tile against a Honduras AOI and comes back with nothing, no error, no
  warning: it would read as "this pair has no candidates", which is a plausible
  result and wrong. Each pair's real AOI is the box where BOTH dates carry
  annotations and is printed by --list-pairs. Now documented in both files, and
  the per-arm commands in eval/results.md all carry their own --bbox.

  EDITED docs/ablation-study.md, which is the Air's file — flagging that
  deliberately. §5.1 and §9 both asserted these arms "cannot currently be
  re-derived", which my re-run made false, and leaving a known-false provenance
  claim in graded report material seemed worse than touching their document.
  Both §9 items are marked DONE with their outcomes kept rather than deleted,
  since how each was caught is the useful part. Their prose and conclusions are
  otherwise untouched.

  ALSO from the previous entry, unchanged: geographic generalisation measured at
  -0.072 debris F1 on an unseen region, and the CNN candidate table corrected to
  137 / 25 / 13.

  STILL BLOCKED, unchanged and still nobody's: EARTHDATA_TOKEN, GFW_API_TOKEN,
  Protected Planet, the river table. FR-2.2's RE-MEASUREMENT with a real current
  field — the thing that would make this check finally evaluable — is still
  waiting on the first of those.

2026-09-02 (earlier, workstation) — Workstation — MEASURED GEOGRAPHIC
GENERALISATION, the question the published CNN numbers could not answer, and
CORRECTED the mis-transcribed candidate table the Air's write-up caught.
280 pass (271 + 9 new), 1 skipped, ruff clean.

  WHY THIS EXISTED. MARIDA's published splits are by PATCH, not by tile. I
  checked rather than assumed: 6 of the 8 MGRS tiles in test also appear in
  train, so 327 of 359 test patches — 91% — sit on ground the model trained on.
  Every CNN number in eval/results.md is therefore a WITHIN-TILE number. The
  comparison is still fair (the FDI is scored through the identical path), but
  it says nothing about a new region, which is the first thing an evaluator
  asks and the project had no answer to.

  NEW --holdout-tile ON train_cnn.py withholds an MGRS tile from train AND val.
  Val too, and that is the point: model selection is on val debris F1, so
  leaving the tile in val would pick the checkpoint that best fits the very
  region the experiment calls unseen. Trained a second detector with 18QYF
  (Gulf of Gonave) held out — 635 train / 305 val patches, otherwise identical
  recipe, seed and epoch budget to detector_v1.

  THE RESULT, over the IDENTICAL 84 18QYF patches:
      detector_v1 (trained on 18QYF)   P=0.9355  R=0.9254  F1=0.9304
      holdout     (never saw 18QYF)    P=0.9085  R=0.8129  F1=0.8581
      cost of the region being unseen   -0.0270  -0.1125   -0.0723
  The detector loses ~7 F1 points on unseen water and the loss is ALMOST ALL
  RECALL. Precision barely moves: it finds less, but what it flags is still
  trustworthy — the better failure direction for a screening stage feeding a
  verification agent, and the strongest evidence yet that it learned a spectral
  signature rather than memorising four tiles of Caribbean water.

  A NUMBER THIS EXPERIMENT MAKES EASY TO QUOTE WRONGLY, now guarded in code.
  --eval-only also prints the holdout model's score on the rest of test (0.6637).
  Subtracting that from the 18QYF score is NOT a generalisation gap: 18QYF
  carries 13.24 debris px/patch against 0.98 for the rest of test, so a model
  scores higher there whether or not it trained on it. The naive subtraction
  gives -0.194 — wrong sign, meaningless magnitude. The script now prints both
  densities and refuses to label it a gap, and says which paired comparison to
  run instead. Only identical patches isolate the effect.

  CORRECTED THE CANDIDATE TABLE the Air flagged in eval/results.md §"Where the
  improvement actually comes from". Three CNN cells read 112 / 19 / 12; the
  committed JSON says 137 / 25 / 13. The JSON wins and I verified why rather
  than taking it on trust: its per-class candidates sum to exactly 204, which is
  both its own n_labelled AND detections_total (795) minus
  detections_unlabelled_excluded (591). The prose reconciled with nothing. Every
  other CNN figure was already exact, so it was a mis-transcription of one
  table, not a bad run. The FDI column was correct throughout.

  STILL OUTSTANDING FOR THIS MACHINE, from the Air's write-up: the FR-2.2 per-arm
  JSON re-run, so the four-pair table and the 0.10 m/s sensitivity row are
  re-derivable rather than prose-only. Not done here.

  CAVEATS ON THE NEW NUMBER, in eval/results.md in full: one region, one seed,
  no repeats; the holdout model trained on 8.5% less data so -0.072 is an UPPER
  bound; Haiti is the same current system as the demo region, so this is an
  unseen TILE in the western Caribbean, not a different ocean. It does not on
  its own license the Gulf of Gonave stretch goal — it speaks to detection only,
  not drift, attribution or that region's extracts.

  detector_v1.pt is UNCHANGED and remains the pipeline's detector.
  models/detector_holdout_18QYF.pt is an experiment artefact, 31 MB, NOT
  committed (sync rule 2). eval/holdout_18QYF.json and _leaky.json are.

  STILL BLOCKED, unchanged: EARTHDATA_TOKEN and GFW_API_TOKEN do not exist, and
  Protected Planet + the river table are not downloaded. FR-2.2 re-measurement,
  FR-3, FR-4, FR-5 and FR-6.1 all still wait on those.

2026-09-02 (earlier, MacBook Air) — MacBook Air — WROTE THE PRD §12 ABLATION
WRITE-UP (docs/ablation-study.md, 396 lines), AND CROSS-CHECKING IT AGAINST
eval/*.json TURNED UP TWO PROVENANCE PROBLEMS IN eval/results.md. No code
changed; 291 pass, 1 skipped, ruff clean, tsc clean.

  MACHINE RE-VERIFIED: role laptop, cuda no, GPU training OK NO, python 3.11.15.
  All 7 datasets MISSING here. Nothing re-measured on this machine — the
  document was assembled by READING eval/*.json, which is all the Air can do.

  ### THE WRITE-UP

  docs/ablation-study.md covers the three results the hand-off asked for:
  FR-2.4 (precision 0.238 -> 0.623, F1 0.385 -> 0.753 on held-out MARIDA, with
  the fitted-vs-literature threshold protocol so the baseline is not a
  strawman); FR-1.4 (region recall 0.407 -> 0.703) INCLUDING the subsumption
  finding, with both verification deltas quoted together (+0.385 over FDI,
  +0.080 over CNN) and an explicit instruction never to quote +0.385 alone once
  the CNN is the detector; and FR-2.2 framed as a measured DEPENDENCY on FR-3.1,
  never a contribution, keeping the PRD §12 exception wording.

  §6 is the part that does the §12 work: the design test agent by agent, with an
  EVIDENCE column separating real-data verdicts from synthetic ones. Detection
  and Verification are backed by real numbers; Drift/Attribution/Vessels/
  Prioritisation carry the pipeline's own degradation strings and are marked
  "not yet quantified" rather than being written up as if they were measured.

  ### TWO PROVENANCE PROBLEMS — BOTH ARE YOURS, NEITHER IS FATAL

  I checked every quoted figure against the committed JSON rather than copying
  prose, per the "no number you cannot derive and defend" rule. The FDI tables
  reconcile EXACTLY, including the full per-failure-mode rejection table. Two
  things did not:

  1. eval/results.md's CNN CANDIDATE-CLASS TABLE IS WRONG IN THREE CELLS.
     Prose: Marine Debris 112, Waves 19, Ship 12.
     eval/detector_cnn_test.json: 137, 25, 13.
     The JSON is self-consistent — its per-class candidate counts sum to exactly
     204, which is its own n_labelled; the prose figures do not. Every OTHER CNN
     figure in results.md reconciles exactly (region recall 0.7034, detector
     precision 0.6716, F1 0.8035, delta +0.0799), so this reads as a
     mis-transcription of one table, not a bad run. NO RE-RUN NEEDED — confirm
     against the JSON and correct the prose. The write-up uses the JSON numbers
     and flags the disagreement in place rather than silently picking one.

  2. FR-2.2's SUPPORTING ARMS HAVE NO COMMITTED ARTEFACT.
     eval/multitemporal.json holds ONE pair (16PCC 2020-09-18 -> 09-23, current
     speed null) and it verifies exactly. The other three pairs and the 0.10 m/s
     sensitivity row are in results.md but were never saved —
     eval_multitemporal.py writes whichever run it was last given, so the extra
     arms were overwritten. Not fabricated, but not currently re-derivable.
     NEEDS A WORKSTATION RE-RUN, one --json path per arm, before the report
     quotes the four-pair table or the sensitivity analysis. Suggested commands
     are in §8 of the write-up.

  Neither weakens a headline. The two numbers the project leads with — the
  FR-2.4 verification gain and the FR-1.4 region recall — both reconcile.

  ### FOR THE WORKSTATION SESSION — pull, then:
  - Correct the CNN candidate-class table in eval/results.md from
    eval/detector_cnn_test.json (item 1 above). Prose-only fix.
  - Re-run the three extra FR-2.2 pairs and the 0.10 m/s sensitivity arm to
    their own JSON files (item 2). Needs MARIDA + L2A, so it can only happen
    there.
  - Nothing in docs/ is machine-specific; it reads fine on either.

  ### STILL THE BOTTLENECK, unchanged
  EARTHDATA_TOKEN and GFW_API_TOKEN still do not exist, and Protected Planet +
  the river table are still undownloaded. FR-2.2's re-measurement, FR-3, FR-4,
  FR-5, FR-6.1, the system-level ablation on real inputs and the end-to-end
  latency figure are all still blocked on that account work. The console is
  still not live at a URL. NEXT credential-free item is the §12
  evidence-traceability demo.

2026-08-28 (earlier, MacBook Air) — MacBook Air — RE-THEMED THE OPERATOR CONSOLE:
light-first Swiss-minimal, merged to main via PR #1 (squash `890985e`).
291 pass, 1 skipped, ruff clean, tsc clean. Frontend-only — no Python, no data
contract, no threshold touched.

  MACHINE RE-VERIFIED: role laptop, cuda no, GPU training OK NO. All 7 datasets
  MISSING here (the concurrent workstation drifter fetch is workstation-local).
  No CNN, no tile work.

  WHAT CHANGED — four files: frontend/index.html, frontend/src/index.css,
  package.json, package-lock.json.
  - Light is now the DEFAULT theme. Dark is retained and retuned from the old
    blue-slate to a neutral charcoal with the same accent; index.html switches
    to dark only on a stored choice or an OS dark-mode preference.
  - Single deep-ocean-blue accent (oklch(0.47 0.12 245)), hairline borders
    instead of shadows, tighter radii.
  - Fonts: Inter + JetBrains Mono -> the IBM Plex superfamily (Sans for UI, Mono
    for coordinates/scores/IDs). Still self-hosted via fontsource, so the
    offline viva export renders with no network. Static export rebuilt and
    confirmed carrying the new theme with fonts bundled.
  - Amber PRESERVED for the approval-pending signal — the one load-bearing
    colour, deliberately not restyled away.
  NO component changes: every colour already routed through a shadcn-style
  token and there are zero hardcoded palette classes in src/. Verified in the
  browser across Dispatch / evidence trail / Rejected / Controls, both themes,
  responsive to 375px.

  FOR ANYONE TOUCHING frontend/: pull main first — the token set and font deps
  moved. Nothing outside frontend/ is affected, so the workstation and the
  Drift/Dark-Vessel owners need nothing from this.

  STILL THE BOTTLENECK, unchanged: EARTHDATA_TOKEN and GFW_API_TOKEN (account
  work nobody has done), and the console still not live at a URL (needs a
  Render account).

2026-08-28 (later, workstation) — Workstation — MERGE CHECK ONLY. Pulled the
Air's console retheme and confirmed it does not touch the Python side.

  9e886b1..890985e, fast-forward, no conflicts. Commit 890985e "Re-theme the
  operator console: light-first Swiss-minimal (#1)" changes only frontend/
  (index.html, index.css, package.json, package-lock.json) — CSS/font work, no
  Python, no eval/, no Status Log entry from them yet, so this looks like an
  interim push rather than their session hand-off.

  py -3.11 -m pytest after the merge: 271 passed, 1 skipped, 1 warning (the
  pre-existing numpy binary-compat RuntimeWarning in test_oscar.py, not new).
  Identical to before the pull. Nothing broke across the merge. Did not run
  tsc / frontend lint — the Air's lane, and a CSS retheme cannot move the
  Python suite.

2026-08-28 (earlier, workstation) — Workstation — STATE CHECK ONLY, NO CODE
CHANGED. Confirmed the project is exactly where the two 2026-08-27 entries left
it: there is no unblocked workstation work, and the bottleneck is account work
nobody has done.

  MACHINE VERIFIED: role workstation, CUDA yes, RTX 5070 sm_120, torch
  2.12.0.dev+cu128, GPU training OK. 271 pass, 1 skipped, ruff clean — identical
  to the last workstation run, nothing regressed.

  DATA: marida present, drifters present (data/drifters/gulf_of_honduras.csv,
  950 KB). MISSING: oscar, rivers, gfw, mpa, sentinel2 (the last is an optional
  cache — ingest streams from Planetary Computer anonymously, so it does not
  block). No .env on this machine; EARTHDATA_TOKEN and GFW_API_TOKEN both unset.

  SWEEP FOR UNBLOCKED WORK — nothing found:
  - FR-1 detection + FR-2.4 verification on real imagery: already measured in the
    L2A-reader session. CNN FR-1.4 measured. Do not redo.
  - FR-2.2 re-measurement: needs a real OSCAR field -> EARTHDATA_TOKEN. Blocked.
  - FR-3 drift validation: needs OSCAR too (predicted trajectory). Blocked.
  - FR-4 / FR-5 / FR-6.1: need rivers / gfw / mpa. Blocked.
  - eval/results.md "end-to-end demo latency — not measured": the two blockers
    it names (region, L2A reader) are cleared, BUT the full six-agent path still
    needs oscar+rivers+gfw+mpa, so latency still cannot be measured end to end.
  - Secondary region Gulf of Gonave: gated on the primary running e2e. Blocked.
  - scripts/ has no fetch_oscar.py — OSCAR is the one dataset with no fetch
    script. Deliberately NOT written blind this session: the network/auth path
    to PO.DAAC cannot be tested without EARTHDATA_TOKEN, and Ashwin's 08-27
    hand-off explicitly warned against untested code on a headline number's
    path. Left for a session that has the token and can verify end to end.

  UNBLOCK CHECKLIST (all Ashwin's, none need a GPU, ~2 signups + 2 downloads):
  1. EARTHDATA_TOKEN — free, urs.earthdata.nasa.gov -> Generate Token -> .env.
     Unblocks OSCAR download, FR-2.2 re-measurement, FR-3 drift validation.
  2. GFW_API_TOKEN — free, globalfishingwatch.org/our-apis -> .env. Unblocks FR-5.
  3. Protected Planet WDPA marine subset (accept terms on the web form), then
     python scripts/build_region_extracts.py mpa --region gulf_of_honduras
         --source <wdpa.gpkg>
  4. Meijer 2021 / Ocean Cleanup global river table, then
     python scripts/build_region_extracts.py rivers --region gulf_of_honduras
         --source <global.csv>

2026-08-27 (earlier, workstation) — Workstation — FETCHED THE GLOBAL DRIFTER
PROGRAM DATA (PRD §3, §12 ground truth). New scripts/fetch_drifters.py + 17
tests. 271 pass, 1 skipped, ruff clean. data/drifters is now `present`.

  10401 observations from 226 drifters, 1980-2025, 928 KB, 99% carrying a
  measured velocity. No credential — AOML's ERDDAP clips server-side, so this is
  a sub-megabyte query rather than the multi-GB global archive, and EITHER
  machine can run it. Not committed (data/**), as usual.

  READ THIS BEFORE ASSUMING DRIFT VALIDATION IS UNBLOCKED — it is NOT.
  drift.mean_track_error_km compares a PREDICTED Trajectory against these
  observations, and that prediction comes from run_trajectory(field, ...) which
  needs a real CurrentField from load_oscar_field(). So PRD §12's "drift
  validated against real buoy paths" bullet needs BOTH, and OSCAR still needs
  EARTHDATA_TOKEN. This removes one of two gates. I checked the function
  signature rather than assuming the download was sufficient.

  TWO THINGS THE DATA SAYS ABOUT THE DEMO REGION, both measured:
  1. ZERO drifter observations fall inside the Gulf of Honduras bbox during the
     2018-02-01..2018-10-01 demo window. Not few — zero. Drift validation
     therefore CANNOT be contemporaneous with the demo run and must be reported
     as a model check over the years the region does have, the same way the
     MARIDA benchmark is independent of the demo window. If the report implies
     the buoys validate the demo run itself, that is wrong.
  2. The bare bbox holds only 553 observations from 13 drifters, in 1999, 2000,
     2007, 2013 and 2014. That is too thin to validate against, which is why the
     fetch defaults to a 300 km buffer (10401 obs / 226 drifters over the same
     current system). The buffer is printed and documented so nobody later
     mistakes a western-Caribbean sample for a Gulf-of-Honduras-only one.

  TWO TRAPS HANDLED, both of which fail SILENTLY:
  1. AOML's ERDDAP accepts raw `<` and `>` but the Tomcat in front of it returns
     a bare HTTP 400 with an HTML body — which reads as a broken dataset rather
     than a broken URL. They must be percent-encoded. Regression test.
  2. ve/vn come back as -999999.0 when there is no measurement. Written through
     unchanged that is a velocity of -999999 cm/s, and no schema would reject
     it. Now blanked. NaN needed an explicit check too: it parses as a float and
     every comparison against it is False, so a sentinel test alone let it pass
     as a real velocity — the test caught that, not me.

  scripts/fetch_data.py's drifters entry now names the command and carries the
  "this is only half the bullet" warning, so the next session cannot read
  `present` as `validated`.

  STILL BLOCKING, and none of it is code: EARTHDATA_TOKEN and GFW_API_TOKEN are
  free signups nobody has done, and Protected Planet + the river table need
  downloading. FR-2.2 re-measurement, FR-3 validation and FR-5 all wait on those.

2026-08-27 (earlier) — MacBook Air — MADE THE CONSOLE DETECTOR-AWARE, so the CNN
result is not described with the FDI's numbers. 274 tests pass, 1 skipped, ruff
clean, tsc clean. Also caught two caveats the console was stating confidently
that your last two sessions made untrue.

  MACHINE RE-VERIFIED: role: laptop, cuda: no, GPU training OK: NO. All 7
  datasets MISSING. No CNN training, no tile processing, models/detector_v1.pt
  is correctly absent here.

  ### THE STRIP NOW FOLLOWS THE RUN'S DETECTOR

  You were right that it was out of date, and the fix had to be selection
  rather than a new constant — which number is correct depends on which
  detector produced the run on screen. Detections already carry `detector`, so
  no schema change was needed:

    benchmark.py reads eval/detector_fdi_test.json and detector_cnn_test.json
    into `detectors[]`, each entry bundling that detector's region recall WITH
    the verification delta measured over it. The UI reads the detector off the
    artefact's detections and picks the matching entry.

  Verified in the browser by loading a CNN-flavoured artefact beside the FDI one
  and switching between them:
    FDI run -> "MARIDA test · FDI spectral index", +0.385, recall 0.407, 140/236
    CNN run -> "MARIDA test · CNN (MARIDA-trained)", +0.080, recall 0.703, 70/236
  Region recall and the verification gain are bundled per detector on purpose:
  showing the CNN's recall beside the FDI's gain would flatter both. If a run's
  detector has no measured benchmark the strip says so rather than falling back
  to the first entry — falling back is precisely the bug.

  THE SUBSUMPTION FINDING IS ON THE FACE OF IT. A warning-boxed note states it
  in full: +0.385 over FDI, +0.080 over CNN, 73 cloud candidates becoming 1,
  turbid water and Sargassum disappearing entirely, and that the agent is
  SUBSUMED rather than redundant — it still removes what survives. Both
  detectors' pairs are listed beneath it so the comparison is checkable. The
  endpoint is tested to serve the note and to refuse to describe one detector
  with another's numbers.

  ### TWO STALE CAVEATS, CAUGHT BY LOOKING AT THE RENDERED PANEL

  The console was asserting, in the same panel as the new numbers:
    "Improving it is the CNN variant's job (FR-1.4), which is not built."
    "Multi-temporal consistency (FR-2.2) is unmeasured."
  Both were true when written and both are now false — FR-1.4 is measured at
  0.703, and FR-2.2's result was rendering two lines above the claim that it did
  not exist. Rewritten, and the test that guards them now asserts the stale
  phrasings are ABSENT rather than just checking a keyword, because a caveat is
  a claim the console states confidently and rots like any other.

  ### FR-2.2 RE-RUN — I COULD NOT DO IT HERE, AND WANT TO BE PLAIN ABOUT WHY

  You asked me to re-run eval_multitemporal.py with a real current field. I did
  not, because it cannot run on this machine and producing something that merely
  looked like a result would be worse than not running it:
    - scripts/eval_multitemporal.py line 12 says WORKSTATION ONLY — it needs
      data/marida for labels. MARIDA is MISSING here and is workstation-only by
      the sync rules.
    - data/oscar is MISSING on BOTH machines and EARTHDATA_TOKEN still does not
      exist, so there is no real current field to wire in anywhere yet.
  No code is missing for this. `--current-speed-ms` already exists and is what
  produced your 0.10 m/s sensitivity result; `load_oscar_field()` is written and
  tested. The gap is purely the OSCAR download. Once that token exists, whoever
  has MARIDA runs the command and the console picks up the new multi_temporal
  block with no code change — the endpoint already serves whatever the file says.

  I deliberately did NOT add speculative --oscar wiring I cannot execute or
  verify. It would be untested code on the critical path of a headline number.

  ONE MORE EDGE FIXED WHILE WRITING THE HAND-OFF, so you pull once: the
  threshold-parity badge compared provenance.fdi_threshold unconditionally. On a
  CNN run that is meaningless — provenance still carries an fdi_threshold the
  network never consulted — so your first real CNN export would have shown
  "computed at FDI > X but measured at 0.025" beside CNN numbers. Now suppressed
  unless the active detector is the FDI. Verified both ways in the browser: an
  FDI artefact with a mismatched threshold still warns, a CNN artefact with the
  SAME mismatch does not.

  ### Interface changes of yours I read and honoured
  bands= on load_tiles, --detector on eval_marida, detector="cnn" with evidence
  kind "derived" (no schema bump needed, agreed), BandWindow pinned to
  REQUIRED_BANDS. Nothing I touched conflicts with any of them.

  ### Still open
  - EARTHDATA_TOKEN and GFW_API_TOKEN: still the long pole, still nobody's.
    Neither needs a GPU. These now block FR-2.2's re-measurement, the Drift
    Agent's own validation, and FR-5 — three deliverables on two free signups.
  - mpa/rivers: extract pipeline ready, still needs the two downloads.
  - Console deployable, still not live at a URL (needs a Render account).

2026-08-26 (earlier) — MacBook Air — WROTE THE OSCAR READER (FR-3.1), FIXED THE
REGION-SCOPING BUG, AND PUT THE NEGATIVE FR-2.2 RESULT ON THE CONSOLE.
265 tests pass, ruff clean, tsc clean. All three items from your brief, in the
order you asked.

  MACHINE RE-VERIFIED: role: laptop, cuda: no, GPU training OK: NO. All 7
  datasets still MISSING here — nothing downloaded, no tile or CNN work
  attempted, and the workstation's FR-1.4 run is untouched.

  ### 1. REGION SCOPING — the wrong-answer bug is closed

  New `config.region_dataset_file()` resolves `<region_id><suffix>` by name.
  `load_river_table(region_id)` and `load_protected_areas(region_id=...)` use
  it, and `export_run.real_config()` now threads the id it already had. Three
  behaviours, and the middle one is the point:
    - region named -> that file, or a raise naming the file, what WAS found,
      and the build command;
    - no region + exactly one extract -> loads it, so existing callers are
      unaffected;
    - no region + several extracts -> RAISES rather than picking. Loading one
      arbitrarily is what silently scored a run against another region's data.
  `DataUnavailableError` gained an optional `message=` override so the ambiguous
  case does not claim the data "is not available" — it is right there, and
  sending the reader off to fetch_data would waste their time.
  9 regression tests in tests/test_region_scoping.py, including that Haiti and
  Honduras do not cross-contaminate. Note `gulf_of_gonave` sorts BEFORE
  `gulf_of_honduras`, so under the old code Haiti's extract would have won for
  both regions.

  ### 2. OSCAR READER (FR-3.1) — built against a synthetic NetCDF, as instructed

  `load_oscar_field(start, end, *, bbox=None)` returns a GriddedCurrentField;
  the integrator needed no changes. 15 tests in tests/test_oscar.py write real
  NetCDF into tmp_path — no EARTHDATA_TOKEN, no download, absence still raises
  the documented DataUnavailableError.

  IT RETURNS A TIME-MEAN FIELD AND THAT IS A REAL APPROXIMATION.
  GriddedCurrentField has no time axis — `velocity()` takes `when` and ignores
  it — so the Feb-Oct window collapses to one mean and seasonal reversals
  average out. The field's `name` records the window, step count, file count
  and land fraction so the artefact shows what was averaged. This is the first
  thing to revisit if the drifter backtest disappoints.

  FIVE TRAPS, four of which fail SILENTLY. Each has its own test:
  1. DESCENDING LATITUDE. OSCAR ships lat 90 -> -90. `_interp` uses np.interp,
     which needs an ascending axis and otherwise returns plausible garbage —
     verified here: a 1.5 lookup on a descending axis returns 3.0, not 1.5.
     Rows are flipped. This one would have quietly sampled the wrong latitude
     for every trajectory in the project.
  2. LONGITUDE CONVENTION. Some distributions run 0-360. The Gulf of Honduras
     at -88 does not exist in such a grid, so every lookup would clamp to a
     Pacific edge value. Wrapped to -180..180 and re-sorted.
  3. LAND IS NaN. One NaN corner poisons the bilinear interpolation and the
     trajectory integrates to NaN from that step on. Filled with zero velocity;
     the fraction filled is reported.
  4. GEOSTROPHIC-ONLY FILES. ug/vg omit the Ekman component, which is much of
     what actually moves floating debris. Accepted only when the total current
     is absent, and the field renames itself "oscar-geostrophic" so it cannot
     be mistaken for the real thing.
  5. TIMEZONE. NetCDF times decode tz-naive; this codebase passes tz-aware.
     pandas refuses to compare them. Converted in `_as_naive_utc`.

  TWO DEPENDENCY DECISIONS: xarray is imported LAZILY inside the function,
  because drift.py sits in the deployed server's import graph and
  requirements-deploy.txt deliberately has no xarray — same coupling I flagged
  for ingest.py, and I verified `ghostnet.webapp.app` still imports with the
  whole geo stack blocked. And files are opened and concatenated by hand rather
  than with `open_mfdataset`, which requires dask.

  `bbox=` is optional and pads by 5 degrees, because `_interp` CLAMPS outside
  the grid rather than raising — too tight a subset would silently become a
  constant boundary current. export_run now passes the region bbox.

  ### 3. FR-2.2 ON THE CONSOLE — reported as a dependency, never a contribution

  benchmark.py reads eval/multitemporal.json (reads, does not recompute) and
  the strip now carries a third warning-toned metric beside region recall:
  "MULTI-TEMPORAL (FR-2.2)  0.500 -> 0.333  blocked on FR-3". Expanding gives
  the before/after F1 and recall, 6 rejections of which 1 was real debris,
  0 transients found, the pair and its labelled count, and all four of your
  reasons. `contributes` is a field on the payload and it is False.

  PRD §12 UPDATED. It asserted every agent's removal degrades the pipeline;
  that is now measurably untrue for one check, so §12 records the exception,
  the 5 km-floor explanation and the "dependency not contribution" framing
  rather than leaving the criterion reading as satisfied.

  ### What is left, and who owns it

  - oscar: reader done, DATA still absent. EARTHDATA_TOKEN does not exist on
    either machine — that signup is the long pole now and needs no GPU.
  - mpa/rivers: extract pipeline done, both still need Ashwin to download the
    sources and run the two commands.
  - gfw: needs GFW_API_TOKEN, also not created.
  - Once OSCAR data lands, RE-RUN scripts/eval_multitemporal.py — FR-2.2 should
    become measurable for the first time, and the console will pick the new
    number up with no code change.
2026-08-25 (workstation) — Workstation — BUILT AND MEASURED THE CNN
DETECTOR (FR-1.4). Region recall 0.407 -> 0.703 on the held-out MARIDA test
split. That was the weakest measured number in the project and the reason FR-1.4
existed. 215 tests pass, 1 skipped, ruff clean.

  HELD-OUT TEST (359 patches), FDI vs CNN, scored by the SAME script through the
  same loading, labelling and region-recall code — that is what makes it a claim:
      candidates emitted   6074  ->   795   (7.6x fewer)
      detector precision  0.2381 -> 0.6716
      detector F1         0.3846 -> 0.8035
      + verification P    0.6230 -> 0.7514
      REGION RECALL       0.4068 -> 0.7034  (96/236 -> 166/236 regions)
  The false positives largely stop being generated rather than being filtered
  later: Clouds 73 -> 1 candidates, Turbid Water 39 -> 0, Sargassum 33 -> 0,
  Foam 4 -> 0, while Marine Debris candidates rise 80 -> 112.

  THE FINDING THAT MATTERS FOR PRD §12, and it needs to be in the report: THE CNN
  SUBSTANTIALLY SUBSUMES THE VERIFICATION AGENT. Verification's contribution
  falls from +0.3849 precision over the FDI to +0.0799 over the CNN. Training
  multi-class is why — MARIDA labels Sargassum, cloud and turbid water as their
  own classes, so the network learns them instead of inheriting the index's
  confusion. Verification is load-bearing FOR THE SPECTRAL BASELINE and becomes
  a smaller safety net behind a learned detector. Quote both numbers; do not
  quote the +0.385 alone once the CNN is the detector.

  MODEL: plain 4-level U-Net, 7.77 M params, 11 bands -> 16 classes, PLAIN TORCH
  with no other dependency. I deliberately did NOT install
  segmentation-models-pytorch / torchvision / timm: they pin against a released
  torch ABI and this machine runs the 2.12.dev+cu128 NIGHTLY, which is the build
  verified to carry sm_120 kernels for the RTX 5070. Resolving torch backwards
  would have destroyed GPU training on the only machine that can do it, to gain
  an ImageNet encoder that transfers weakly to 11 spectral bands anyway.
  requirements-gpu.txt is corrected to match, with the reasoning recorded.
  60 epochs in 6.4 min; best val debris F1 0.844 at epoch 51.
  models/detector_v1.pt is 31 MB and NOT COMMITTED — if you do not have it,
  load_detector() raises and names the command. The FDI path still works.

  THRESHOLD CALIBRATED ON VAL, never test: DEFAULT_PROB_THRESHOLD = 0.40, chosen
  to maximise REGION RECALL. Those objectives genuinely conflict — over val,
  precision rises monotonically with the threshold (0.78 -> 0.90) while region
  recall peaks at 0.40 and then collapses (0.755 -> 0.499). Tuning on precision
  would have produced a better-looking table and found half the debris.

  A REAL BUG THIS EXPOSED, now fixed. BandWindow.brightness and .flatness
  averaged over WHATEVER BANDS THE DICT HELD. The verification thresholds were
  fitted against four bands; feeding the CNN's 11-band tiles through them dropped
  held-out precision 0.623 -> 0.447 and cloud rejection 91.8% -> 69.9%, with no
  error anywhere. Both statistics are now pinned to REQUIRED_BANDS and the
  published FDI numbers reproduce exactly. A threshold is only meaningful
  against a fixed basis — worth remembering if you ever add a band.

  FOR THE AIR: ghostnet.ingest.load_tiles() now takes bands=; pass
  detection_cnn.MARIDA_BANDS for the CNN path, and the FDI default is unchanged.
  scripts/eval_marida.py takes --detector {fdi,cnn}. Detection objects from the
  CNN carry detector="cnn" and evidence kind "derived" — I did NOT widen
  Evidence.kind, so no artefact schema bump. The console needs no changes, but
  the metrics strip currently shows the FDI's 0.407; once a real artefact exists
  it may be worth showing which detector produced it.

2026-08-25 (earlier) — MacBook Air — BUILT THE REGION-EXTRACT PIPELINE for the two
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

2026-08-25 (workstation) — Workstation — MEASURED FR-2.2, THE LAST
UNMEASURED CHECK. The answer is NEGATIVE and should be reported as such:
multi-temporal consistency contributes nothing today, and on the one pair where
it acted it removed a true detection and no false positive. Full method, all
four pairs and the sensitivity analysis in eval/results.md; machine-readable in
eval/multitemporal.json. New scripts/eval_multitemporal.py + 10 tests.

  WHY IT NEEDED THE L2A READER. MARIDA crops a DIFFERENT set of patches for
  every scene, so two dates over one MGRS tile share no patch footprint —
  checked, and across all 19 dates on 16PCC not one pair matches. The harness
  therefore streams two real acquisitions onto ONE FIXED GRID (pixel (r,c) is
  the same ground position on both dates by construction) and rasterises MARIDA
  masks onto that grid for labels. The AOI is the box where BOTH dates have
  annotations.

  THREE REASONS IT CONTRIBUTES NOTHING, only one of them the check's own fault:
  1. STRUCTURALLY BLOCKED ON FR-3. check_persistence allows
     current_speed x dt + 5 km. With no OSCAR field current_speed_ms is None, so
     the envelope collapses to 5 km — while real debris at 0.1 m/s covers ~43 km
     in the 5 days between passes. It calls genuine drift "incoherent motion".
     Measured: no current field -> 6 rejections, 1 true debris lost; at an
     ASSUMED 0.10 m/s -> 0 and 0. Every false rejection is an artefact of the
     missing current field. FR-2.2 cannot be fairly evaluated until FR-3.1
     exists. If you build the OSCAR reader on the Air, this becomes measurable.
  2. ZERO TRANSIENTS IN EVERY PAIR — the check's strongest signal never fires.
     Repeats are paired by nearest neighbour, and with 9-130 candidates in an
     AOI something is always in range: 144/144, 21/21, 22/22 re-observed.
     Proximity cannot separate "this patch persisted" from "some other detection
     exists nearby". A real implementation needs identity-preserving matching —
     drift-predicted position plus a spectral-similarity gate.
  3. TINY SAMPLES — 12 and 7 labelled candidates on the two usable pairs.
     None of these deltas would survive a significance test.

  FOR PRD §12: on current evidence, removing multi-temporal verification would
  NOT degrade the pipeline — it would slightly improve recall. That contradicts
  the "every agent is load-bearing" design test and should be stated plainly
  rather than hidden. The check is sound in principle and standard in the
  literature; it is inert here because its current field does not exist. DO NOT
  quote FR-2.2 as a contribution — quote it as a measured dependency on FR-3.1.

  FIXED A REPRODUCIBILITY BUG THAT WOULD HAVE DESTROYED THE HEADLINE NUMBER.
  The "before" arm of the FR-2.4 result was no longer reproducible from code:
  eval_marida.py built it from DEFAULT_THRESHOLDS, and I had overwritten those
  with the FITTED values. Re-running --fit would have compared the calibrated
  agent against ITSELF and reported a delta of zero — while looking like a
  clean successful run. Added LITERATURE_THRESHOLDS (verification.py) and
  LITERATURE_FDI_THRESHOLD (detection.py) holding the published values;
  eval_marida.py now starts both the fit and the "before" arm from those.
  PRD §8 reproducibility now actually holds. Regenerating
  eval/marida_ablation.json from this also clears the stale sun_glint /
  foam_whitecap names you flagged.

  Also corrected two caveats in eval/results.md that this work contradicted:
  FR-2.2 is no longer "unmeasured", and the demo region is no longer
  "undecided".

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
