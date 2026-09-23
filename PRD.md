# Product Requirements Document

**Multi-Agent Ghost Net & Marine Debris Intelligence Pipeline** — Final-Year Major Project — Prepared for Ashwin — August 2026

> Converted to Markdown from `Ghost-Net-Marine-Debris-PRD.docx` so it is versioned
> alongside the code and readable on both machines. Content is unchanged from v1.0.

This PRD translates the approved project proposal into a build specification: what the system must do, who it is for, how success is measured, and what is explicitly out of scope for an undergraduate two-to-three-person team on a one-semester timeline. It is written to be handed to a guide for sign-off and used internally as the source of truth while building.

---

## 1. Overview

### 1.1 Document Control

| Field | Value |
|---|---|
| Product name | Ghost Net & Marine Debris Intelligence Pipeline |
| Document owner | Ashwin (Team lead) |
| Status | Draft — pending guide review |
| Version | v1.0 — August 2026 |
| Related documents | Ghost-Net-Marine-Debris-Proposal.pdf (project proposal) |

### 1.2 Purpose

Build a multi-agent system that turns a raw satellite detection of floating ocean debris into a verified, source-attributed, risk-prioritised cleanup dispatch recommendation — using only data sources that are real, free, and already flowing today (Sentinel-1/2 imagery, NOAA ocean current and drifter data, Global Fishing Watch vessel data, and Protected Planet MPA boundaries). The system is a decision-support research prototype, not an operational deployment.

### 1.3 Background

Detection of floating plastic from Sentinel-2 imagery is a mature research area with over 100 published studies since 2020. The unbuilt layer is everything after detection: telling a genuine debris patch apart from sea foam or sun glint, tracing it to a probable source, correlating it with illegal fishing activity that produces ghost gear, and turning all of that into one ranked, resource-constrained response plan. That is the product this PRD specifies.

---

## 2. Problem Statement & Goals

**Problem:** There is no open system that converts a satellite debris detection into a verified, source-attributed, risk-prioritised, resource-constrained cleanup response — every existing pipeline stops at detection.

### 2.1 Goals

- Detect candidate floating debris patches from free Sentinel-2 imagery over a monitored coastal region.
- Actively verify each detection against documented false-positive modes (sea foam, sun glint, kelp/Sargassum, cloud) rather than reporting raw detector output.
- Model backward and forward drift trajectories for confirmed detections using real ocean current data.
- Attribute a probable source river using published river-emission rankings.
- Correlate detections against dark-vessel (AIS-silent) fishing activity as a documented proxy for illegal fishing and gear abandonment.
- Produce one ranked, capacity-constrained cleanup-vessel dispatch plan that a human operator reviews before any action is taken.
- Demonstrate — via backtesting against real historical/published ground truth — that each agent's contribution is measurable and that removing any one agent degrades the system.

### 2.2 Non-Goals

- This is **not** an operational deployment tool for a coast guard or NGO — it is a research prototype validated on historical and published data.
- This is **not** a deep-sea or underwater debris system — scope is surface and near-surface plastic visible from orbit, consistent with how the field actually tracks debris.
- This is **not** a real-time, always-on monitoring service — the demo scope is a defined historical window over a small number of monitored regions.

---

## 3. Success Metrics

Metrics are chosen so the project has a defensible, numeric result for the report and viva, not just a working demo.

| Metric | Target / How Measured |
|---|---|
| Detection precision/recall | Benchmarked against a published labelled Sentinel-2 debris dataset (e.g. MARIDA), with and without the Verification Agent active |
| Verification Agent contribution | Measurable drop in false-positive rate versus the raw detector baseline — this delta is the headline ablation result |
| Drift model accuracy | Predicted trajectories compared against real GPS-tagged NOAA Global Drifter Program buoy paths (mean position error over N days) |
| Source attribution accuracy | Fraction of flagged probable sources that match The Ocean Cleanup's own published top-emitting river rankings |
| Dark-vessel correlation precision | Cross-checked against Global Fishing Watch's own published dark-fleet case studies |
| System-level ablation | Full pipeline output quality with each agent individually removed, to demonstrate the architecture is load-bearing, not decorative |
| End-to-end demo latency | Time to produce one ranked dispatch plan for a monitored region, from raw tile ingestion to output, on available hardware |

---

## 4. Users & Stakeholders

### 4.1 Primary Persona — Cleanup Coordinator (simulated)

A researcher or NGO operator (e.g. at an organisation like The Ocean Cleanup or a coastal-state pollution board) who receives a ranked list of candidate cleanup sites and must decide where to send a limited number of vessels. They need confidence that a flagged detection is real, a sense of urgency (is it drifting toward a Marine Protected Area?), and a defensible reason for the plan — not a black-box score.

### 4.2 Secondary Persona — Marine Researcher / Data Analyst

Wants to audit why the system flagged or rejected a detection, inspect drift model assumptions, and export attributed-source statistics for further study. Needs traceability from every output back to the source imagery and current data.

### 4.3 Academic Stakeholder — Guide / Evaluator

Assesses the project for technical depth, genuine multi-agent design, rigorous evaluation methodology, and societal relevance. Needs the system to demonstrate — quantitatively — that it is more than a single detection model with extra steps.

---

## 5. Scope

### 5.1 In Scope (v1 / Demo Build)

- **Primary monitored region: the Gulf of Honduras (Río Motagua outflow), bbox `[-88.8556, 15.6832, -86.1292, 16.5204]`, demo window 2018-02-01 to 2018-10-01.** Decided 2026-08-14 (resolves Open Question 1); full rationale in `config/regions.yaml`. A second region (Gulf of Gonâve, Haiti) is a documented stretch goal for generalisation, not committed scope.
- **Exploratory Indian Ocean pilot (user-requested 2026-09-16): Puducherry coast, bbox `[79.78, 11.80, 79.98, 12.02]`, window 2021-01-21 to 2021-02-01.** This bounded historical export expands console coverage; it does not change the primary benchmark or establish Indian Ocean-wide coverage or local detection accuracy. GFW was unavailable for this pilot and is explicitly degraded. The coverage atlas distinguishes requested imagery AOIs from larger study-region bounds and excludes synthetic demos from real coverage. Details: `docs/puducherry-pilot.md`.
- A defined historical time window (not live/continuous monitoring) for both the demo and the backtest evaluation.
- All six agents specified in Section 7, running as an orchestrated pipeline with a human-reviewed final output.
- **A deployed operator-facing web application** showing the ranked dispatch plan with rationale and traceable evidence per detection. Decided 2026-08-14 (resolves Open Question 2); a deployed web app is a course deliverable requirement. Architecture in §9.1.

### 5.2 Out of Scope (v1)

- Global, continuous, real-time monitoring across all oceans.
- Integration with a real cleanup vessel's live dispatch or fleet-management system.
- Deep-sea or underwater (ROV/submersible) debris detection.
- Automated action-taking without a human checkpoint — the system always stops at a recommendation.
- Legal or enforcement action against vessels flagged by the Dark Vessel Correlation Agent — output is a research signal, not an accusation.

---

## 6. User Stories

- As a cleanup coordinator, I want a ranked list of candidate debris sites so that I can decide where to send a limited number of vessels.
- As a cleanup coordinator, I want to see why a detection was trusted (or rejected) so that I don't waste a vessel trip on sea foam or sun glint.
- As a marine researcher, I want to see the predicted drift path and probable source river for a confirmed detection so that I can study emission patterns.
- As a marine researcher, I want every output traceable to its source imagery and current data so that I can audit the system's reasoning.
- As a cleanup coordinator, I want detections near a Marine Protected Area or shipping lane flagged as higher priority so that ecologically urgent cases are not missed.
- As a guide/evaluator, I want to see the system's output quality with each agent removed, one at a time, so that I can confirm the architecture is genuinely multi-agent and not a single model in disguise.
- As a cleanup coordinator, I want the final plan bounded by a stated vessel-capacity constraint so that the recommendation is realistic, not a wish list.

---

## 7. Functional Requirements

Grouped by agent. Each agent is independently testable and independently ablatable — the design test used throughout is that removing any single agent should break the system, not merely degrade it slightly.

### FR-1 — Satellite Detection Agent

- **FR-1.1** — Ingest Sentinel-2 optical tiles for a configured monitored region and time window via the Copernicus Open Access Hub / Sentinel Hub API.
- **FR-1.2** — Compute a floating-debris spectral index (FDI/NDVI-style, per published methods) over each tile.
- **FR-1.3** — Output a list of candidate detections with tile coordinates, timestamp, and a raw confidence score.
- **FR-1.4** — Support an optional CNN-based detector trained on a labelled benchmark (e.g. MARIDA) as an alternative to the spectral-index baseline, for comparison.

### FR-2 — False-Positive Verification Agent

- **FR-2.1** — For each candidate detection, actively attempt to disqualify it using documented failure modes: sun glint geometry, foam texture, kelp/Sargassum spectral signature, cloud shadow.
- **FR-2.2** — Check multi-temporal consistency: does the detection persist and move coherently with local currents across repeat satellite passes, rather than appearing once and vanishing?
- **FR-2.3** — Output a verified/rejected label per detection with the specific reason for rejection, not just a binary flag.
- **FR-2.4** — Log a before/after precision-recall comparison so the agent's measured contribution can be reported.

### FR-3 — Drift Agent

- **FR-3.1** — For each verified detection, run backward trajectory modelling using NOAA OSCAR surface current fields to estimate probable origin.
- **FR-3.2** — Run forward trajectory modelling to project the debris's probable path over a configurable horizon (e.g. the next N days).
- **FR-3.3** — Output a trajectory with an uncertainty envelope, not a single deterministic path.

### FR-4 — Source Attribution Agent

- **FR-4.1** — Cross-reference the Drift Agent's backward trajectory against The Ocean Cleanup's published river-emission rankings.
- **FR-4.2** — Output a ranked probability distribution over candidate source rivers, not a single confident claim.

### FR-5 — Dark Vessel Correlation Agent

- **FR-5.1** — Query Global Fishing Watch's public API for radar (SAR)-detected vessels in the detection's time/space window.
- **FR-5.2** — Cross-reference radar-detected vessels against AIS broadcast records to identify AIS-silent ("dark") vessels.
- **FR-5.3** — Output a correlation signal linking dark-vessel presence to the detection, as a documented proxy for illegal or unreported fishing and gear abandonment — reported as a signal for investigation, not an accusation.

### FR-6 — Response Prioritisation Agent

- **FR-6.1** — Combine detection confidence, drift urgency, ecological risk (proximity to Marine Protected Areas via Protected Planet, reefs, shipping lanes), and dark-vessel correlation into a single ranked priority score per detection.
- **FR-6.2** — Apply a configurable cleanup-vessel capacity constraint and produce a bounded, realistic dispatch plan (not an unranked wish list).
- **FR-6.3** — Present the plan with a human-readable rationale per recommended site, traceable back to the evidence each upstream agent produced.
- **FR-6.4** — Require explicit human review/approval before the plan is treated as final output.

---

## 8. Non-Functional Requirements

| Category | Requirement |
|---|---|
| Explainability | Every recommendation must be traceable to the specific evidence (imagery tile, current data, vessel record) that produced it — no unexplained scores |
| Data cost | Must run entirely on free/public-tier data access (Copernicus, Global Fishing Watch public API, NOAA); demo scoped to respect free-tier rate limits |
| Reproducibility | Given the same input tiles and time window, the pipeline must produce the same verified detections and ranked plan |
| Auditability | Rejected detections and their rejection reason must be logged, not discarded silently |
| Human-in-the-loop | No output is treated as final or actionable without an explicit human review step |
| Performance | One monitored region's full pipeline run should complete in a demo-appropriate time (target: well under an hour) on available GPU/cloud resources |
| Honesty about readiness | All outputs and documentation must frame the system as a decision-support research prototype, never as operational-grade or deployment-ready |

---

## 9. System Architecture Summary

Full architectural detail and data-flow diagrams are in the companion proposal document. Summary of the six-agent pipeline:

| Agent | Data / Method |
|---|---|
| Satellite Detection Agent | Copernicus Sentinel-2 imagery; spectral-index (FDI-based) detection |
| False-Positive Verification Agent | Multi-temporal Sentinel-2 revisits; documented failure-mode checklist |
| Drift Agent | NOAA OSCAR surface current fields; particle-trajectory modelling |
| Source Attribution Agent | The Ocean Cleanup's published river-emission rankings |
| Dark Vessel Correlation Agent | Global Fishing Watch — Sentinel-1 SAR vessel detections vs. AIS records |
| Response Prioritisation Agent | Protected Planet MPA boundary data; constrained optimisation over vessel capacity |

### 9.1 Operator Web Application

Decided 2026-08-14. A deployed web application is a course deliverable
requirement, which resolves Open Question 2.

**The constraint that shapes the whole design: the data cannot be deployed.**
MARIDA is ~5.5 GB and raw Sentinel-2 tiles are larger; both are workstation-only
and are never committed (MACHINE-WORKFLOW.md sync rule 2). No free-tier host
will carry them, and §8 caps this project at free-tier resources. The deployed
app therefore **serves precomputed pipeline runs** rather than ingesting imagery
on demand. This is a scoping decision, not a limitation to hide: §5.2 already
places real-time monitoring out of scope, and §8 requires reproducibility, which
a pinned precomputed run gives directly.

**Split of responsibilities**

| Runs where | What |
|---|---|
| Workstation, offline | Tile ingestion, detection (FR-1), verification (FR-2), drift (FR-3) over real imagery. Exports one JSON run artefact per region/window. |
| Deployed server | Serves run artefacts; recomputes prioritisation (FR-6.1/6.2) live under changed vessel capacity or agent-ablation settings; generates FR-6.3 rationales via the Claude API; records the FR-6.4 approval. |
| Browser | Map, ranked dispatch list, per-detection evidence trail, ablation and capacity controls, approve action. |

Prioritisation is pure scoring over already-computed agent outputs, so it is
cheap enough to run live on a free tier with no dataset present. That is what
makes the deployment *meaningful* rather than a static page behind a URL — real
computation happens server-side in response to operator input.

**A backend is genuinely required, not decorative:** the FR-6.3 rationales call
the Claude API, and that key cannot live in a browser. Approval state (FR-6.4)
also needs somewhere to live.

**Non-functional requirements it inherits**

- Every view must trace back to the evidence that produced it (§8
  explainability); the evidence trail is a first-class screen, not a tooltip.
- Rejected detections must be visible with their rejection reason (§8
  auditability) — the app must show what was *thrown away* and why, since that
  is the Verification Agent's entire measured contribution.
- No plan is final without the explicit human approval step (FR-6.4).
- The app must state on its face that it is a decision-support research
  prototype (§8 honesty about readiness).

**Interface quality is a stated requirement, not a nice-to-have.** The app is a
graded deliverable and is the only part of the system an evaluator experiences
directly. It must look contemporary and deliberate — a considered layout and
type scale, real empty/loading/error states, responsive down to a laptop
screen, keyboard-navigable, and a dark/light treatment that suits a map-heavy
operations view. Build it with a modern component toolkit rather than
hand-rolled CSS; the `21dev` UI skill (and any equivalent UI/UX skill available
in that session) should be used for the component and layout work.

Two cautions specific to this project. First, none of that may come at the cost
of the evidence trail or the rejected-detections view — the interface exists to
make the agents' reasoning legible, and a polished screen that hides why a
detection was rejected is worse than a plain one that shows it. Second, the
visual design must not imply operational readiness: §8 requires the prototype
framing to survive contact with the UI.

**Measured quality must be visible in the app, not only in the report.** The
console shows the Verification Agent's precision gain (FR-2.4) and the
detector's region recall side by side on a run-level metrics strip. The two are
paired deliberately: the precision/recall figures are conditioned on candidates
the detector emitted, so baseline recall reads 1.0 by construction, and showing
the gain alone would let an evaluator conclude the system finds nearly all the
debris when it lands on 96 of 236 annotated regions. `eval/results.md` requires
the two to be quoted together; §8's honesty-about-readiness requirement means
that holds in the interface too. The strip labels the numbers as measured on a
held-out benchmark rather than on the run displayed, and flags a mismatch if the
artefact was computed at a different detector threshold.

**Hosting.** Render's free web tier, deployed from the repo's `Dockerfile` via
the `render.yaml` blueprint. It was chosen because it builds a Dockerfile
directly from a private GitHub repo with no payment method, which suits this
project's two-toolchain build (npm plus pip). The deployed image deliberately
installs only `requirements-deploy.txt` — no geospatial stack — since the
server never touches imagery. Operational detail is in `DEPLOY.md`.

**Demo risk.** Free-tier hosts cold-start and sleep; a Render free instance
spins down after ~15 minutes idle and takes about a minute to wake. A
pre-generated static export of the same run must be kept on disk as a viva
fallback, so a failed deploy or dead venue wifi cannot cost the demonstration.

---

## 10. Data Requirements

- **Copernicus Sentinel-2** — free optical imagery for debris detection and multi-temporal verification.
- **NOAA OSCAR** — surface ocean current fields for drift modelling.
- **NOAA Global Drifter Program** — GPS-tagged buoy tracks, used to validate the Drift Agent against real trajectories.
- **The Ocean Cleanup — river emission rankings** — published source-river data for the Source Attribution Agent.
- **Global Fishing Watch public API** — SAR vessel detections and AIS records for dark-vessel correlation.
- **UNEP-WCMC Protected Planet** — Marine Protected Area boundaries for ecological-risk scoring.
- **MARIDA** — labelled Sentinel-2 marine debris benchmark, used for detection/verification evaluation.

See `scripts/fetch_data.py` for where each dataset must live locally and how to obtain it.

---

## 11. Milestones & Release Plan

| Phase | Duration | Exit Criteria |
|---|---|---|
| Phase 1 — Detection baseline | ~1 month | Sentinel-2 access working; spectral-index detector running; MARIDA-style labelled benchmark assembled for later evaluation |
| Phase 2 — Verification | ~1 month | False-Positive Verification Agent implemented; measured precision/recall delta over the raw detector documented |
| Phase 3 — Drift & attribution | ~1 month | Drift Agent validated against Global Drifter Program buoy tracks; Source Attribution Agent producing ranked river probabilities |
| Phase 4 — Vessel correlation | ~1 month | Dark Vessel Correlation Agent integrated with Global Fishing Watch API; correlated case studies reproduced |
| Phase 5 — Prioritisation & demo | ~1 month | Response Prioritisation Agent complete; full pipeline ablation study run; demo, report and viva materials ready |

**Delivery target agreed September 22: October 10, 2026.** The remaining
execution schedule is in `docs/completion-plan.md`, with a feature freeze and
acceptance/rehearsal window on October 7–9. Delivery means a tested research
prototype, reproducible measured evidence, report and demo; paper suitability is
the guide's subsequent decision. Independent external validation must remain
explicitly outstanding where evidence cannot be obtained by the deadline.

---

## 12. Evaluation & Acceptance Criteria

The build is considered functionally complete when all of the following hold:

- The full six-agent pipeline runs end to end on at least one monitored region and time window, producing a ranked, capacity-constrained dispatch plan.
- Detection and verification are benchmarked against a published labelled dataset, with a documented precision/recall improvement attributable to the Verification Agent.
- The Drift Agent's predicted trajectories are compared against real NOAA Global Drifter Program buoy paths with a reported error metric.
- Source attribution output is checked against The Ocean Cleanup's own published rankings and dark-vessel correlation against Global Fishing Watch's own case studies.
- An ablation study exists showing pipeline output degrades in a specific, explainable way when each agent is individually removed.
- Every output in the demo can be traced back to its underlying evidence on request (imagery tile, current field, vessel record).

**One measured exception to the ablation criterion, recorded rather than hidden
(2026-08-25, re-measured 2026-09-04).** Multi-temporal consistency (FR-2.2) has
been measured on real repeat Sentinel-2 passes, and removing it does *not*
degrade the pipeline. That contradicts the "removing any agent should break the
system" design test for this one check, and the exception is recorded here
rather than papered over.

**The 2026-09-04 re-measurement changed how it fails, and did not rescue it.**
When first measured, no OSCAR current field existed, so `check_persistence`
collapsed its `current_speed x dt + 5 km` envelope to the 5 km floor and
rejected genuine drift as incoherent motion — removing the check would then have
*improved* recall (F1 0.500 -> 0.333 on the headline pair; one true detection
lost, no false positive removed). `EARTHDATA_TOKEN` was created on 2026-09-04,
OSCAR was downloaded, and every pair was re-run against the real field. The
measured current is 0.0139 m/s, the envelope grows to about 11 km, and **all six
false rejections and the one true-debris loss disappear**. Removing FR-2.2 would
now change nothing measurable: dF1 0.000, and zero transients found across all
four pairs.

So the honest reading is no longer "blocked on FR-3.1". FR-3.1's data exists,
the check was given exactly what it asked for, and it still contributes nothing.
The cause is now identified as the check's own design rather than a missing
dependency: repeats are paired by nearest neighbour, and with 9-130 candidates
in an AOI something is always within range (144/144, 21/21, 22/22 re-observed),
so the transient — the check's strongest signal — never fires. A defensible
implementation needs identity-preserving matching: drift-predicted position plus
a spectral-similarity gate. That is a design change to `check_persistence`, not
more data.

**FR-2.2 must not be quoted as a contribution.** Quote it as a measured negative
with a named cause. Method, all four pairs before and after the current field,
and the sub-grid caveat on the measured speeds are in `eval/results.md`;
per-arm artefacts are `eval/multitemporal*.json`. The operator console surfaces
the negative result alongside the FR-2.4 gain so an evaluator is not left
assuming every check carries weight. The console now reads the real-current
arm and retains the no-field result for comparison: the harm is gone, but the
check remains inert with zero transients found.

---

## 13. Risks & Assumptions

| Risk / Assumption | Mitigation |
|---|---|
| Spectral detection has a real, literature-acknowledged false-positive problem | This is precisely why the Verification Agent exists; report its measured contribution rather than hiding the baseline's weakness |
| Free-tier API access (Global Fishing Watch, Copernicus) may be rate-limited at scale | Scope the demo to a small number of monitored regions and a defined historical window rather than global real-time coverage |
| Source attribution is inherently probabilistic over long drift distances/times | Report attribution as a ranked probability distribution, never a single confident claim |
| Risk of the system being read as deployment-ready | Frame consistently, in documentation and demo, as a decision-support research prototype validated against historical and published data |

---

## 14. Open Questions

1. ~~Which specific coastal region(s) will be used for the demo and backtest?~~ **RESOLVED 2026-08-14 — the Gulf of Honduras (Río Motagua outflow).** Chosen on evidence measured directly from MARIDA on the workstation, not from a literature guess. The Motagua is widely reported as the world's largest plastic-emitting river (~2% of global emissions) and hosts The Ocean Cleanup's Interceptor 021, giving FR-4 a citable answer to check against; MARIDA tile 16PCC carries 19 passes with five repeat pairs 5–15 days apart, making it the only candidate that can measure FR-2.2 at all; it holds the most labelled ground truth (1084 patches, 1768 debris pixels); and the Mesoamerican Barrier Reef sits inside the bbox so FR-6.1 ecological scoring is genuinely exercised. This departs from §5.1's original illustrative "Southeast Asian or South Asian" framing — that was an example rather than a constraint, and no Southeast Asian MARIDA tile has any repeat pass within 15 days, which would have left FR-2.2 permanently unmeasurable. Rejected alternatives are kept in `config/regions.yaml` so the decision stays auditable.
2. ~~Should the operator-facing output be a lightweight dashboard, a generated report, or a notebook?~~ **RESOLVED 2026-08-14 — a deployed web application, required as a course deliverable. See §9.1 for the architecture and the constraint that drives it.**
3. How much of the CNN-based detector (as an alternative to the spectral-index baseline) is worth building given the team's timeline — recommend treating it as a stretch goal, not a Phase 1 requirement.
