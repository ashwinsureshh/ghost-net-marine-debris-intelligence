# Evaluation results

This file is the committed record of every measured result. Model weights stay
local (see `models/README.md`); the *numbers* belong here so both machines and
the final report share one source of truth.

Record, for each run: date, machine, git commit, dataset/split, and the metric.

## Detection (FR-1) — precision / recall vs. MARIDA

_No runs yet._

| Date | Machine | Commit | Detector | Split | Precision | Recall | Notes |
|---|---|---|---|---|---|---|---|

## Verification Agent contribution (FR-2.4) — headline ablation

The PRD's headline result: false-positive rate with the Verification Agent
active vs. the raw detector baseline.

_No runs yet._

| Date | Commit | Baseline FP rate | Verified FP rate | Delta |
|---|---|---|---|---|

## Drift Agent accuracy (FR-3) — vs. NOAA Global Drifter Program

Mean position error over N days against real GPS-tagged buoy paths.

_No runs yet._

## Source attribution (FR-4) — vs. The Ocean Cleanup rankings

Fraction of flagged probable sources matching published top-emitting rivers.

_No runs yet._

## Dark vessel correlation (FR-5) — vs. GFW published case studies

_No runs yet._

## System-level ablation

Pipeline output quality with each agent individually removed, demonstrating the
architecture is load-bearing.

_No runs yet._

## End-to-end demo latency

Raw tile ingestion to ranked dispatch plan, one monitored region.
Target per PRD §8: well under an hour.

_No runs yet._

---

## Hardware baseline

Recorded so timings are comparable across runs and machines.

| Machine | Device | VRAM | Compute | torch | fp32 4096³ matmul | Date |
|---|---|---|---|---|---|---|
| Workstation | RTX 5070 | 12.8 GB | sm_120 (Blackwell) | 2.12.0.dev20260408+cu128 | 18.8 ms (~7.3 TFLOPS) | 2026-08-14 |
| MacBook Air M3 | — | — | no CUDA | — | — | not yet recorded |
