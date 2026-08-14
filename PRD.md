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

- One or two monitored coastal regions with known, documented debris activity (e.g. a Southeast Asian or South Asian coastline near a high-emission river mouth).
- A defined historical time window (not live/continuous monitoring) for both the demo and the backtest evaluation.
- All six agents specified in Section 7, running as an orchestrated pipeline with a human-reviewed final output.
- A simple operator-facing view (dashboard or notebook-driven report) showing the ranked dispatch plan with rationale and traceable evidence per detection.

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

---

## 12. Evaluation & Acceptance Criteria

The build is considered functionally complete when all of the following hold:

- The full six-agent pipeline runs end to end on at least one monitored region and time window, producing a ranked, capacity-constrained dispatch plan.
- Detection and verification are benchmarked against a published labelled dataset, with a documented precision/recall improvement attributable to the Verification Agent.
- The Drift Agent's predicted trajectories are compared against real NOAA Global Drifter Program buoy paths with a reported error metric.
- Source attribution output is checked against The Ocean Cleanup's own published rankings and dark-vessel correlation against Global Fishing Watch's own case studies.
- An ablation study exists showing pipeline output degrades in a specific, explainable way when each agent is individually removed.
- Every output in the demo can be traced back to its underlying evidence on request (imagery tile, current field, vessel record).

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

1. Which specific coastal region(s) will be used for the demo and backtest — selection should balance known debris activity, data availability, and relevance to a citable published case study.
2. Should the operator-facing output be a lightweight dashboard, a generated report, or a notebook — this affects Phase 5 scope and should be settled before Phase 4 ends.
3. How much of the CNN-based detector (as an alternative to the spectral-index baseline) is worth building given the team's timeline — recommend treating it as a stretch goal, not a Phase 1 requirement.
