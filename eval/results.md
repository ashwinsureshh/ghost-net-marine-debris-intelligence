# Evaluation results

This file is the committed record of every measured result. Model weights stay
local (see `models/README.md`); the *numbers* belong here so both machines and
the final report share one source of truth.

Record, for each run: date, machine, git commit, dataset/split, and the metric.

Reproduce everything below with:

```bash
python scripts/eval_marida.py --fit --split test --json eval/marida_ablation.json
```

---

## Verification Agent contribution (FR-2.4) — headline ablation

**MARIDA test split, held out. Thresholds fitted on train only.**
Run 2026-08-14, workstation, commit `8559696` + working tree, MARIDA v1.0.0.
359 patches → 6074 detections, 5738 excluded as unlabelled, **336 scored**.

| Configuration | Precision | Recall | F1 |
|---|---|---|---|
| Baseline detector (FDI only) | 0.2381 | 1.0000 | 0.3846 |
| \+ Verification, **unfitted** thresholds | 0.2583 | 0.7750 | 0.3875 |
| \+ Verification, **fitted** thresholds | **0.6230** | 0.9500 | **0.7525** |

**Headline: precision 0.238 → 0.623 (+0.385), F1 0.385 → 0.753 (+0.368), for 5
points of recall.** The false-positive rate falls from 0.762 to 0.377.

Confirmed on a second held-out split (val, 328 patches, 381 scored):

| Configuration | Precision | Recall | F1 |
|---|---|---|---|
| Baseline detector | 0.5354 | 1.0000 | 0.6974 |
| \+ Verification, unfitted | 0.5452 | 0.7990 | 0.6481 |
| \+ Verification, fitted | **0.7672** | 0.8725 | **0.8165** |

Two things this shows beyond the headline:

1. **The unfitted agent was worth roughly nothing** (+0.003 F1 on test) **and was
   actively harmful on val** (0.697 → 0.648). Reporting the agent without
   calibrating it would have understated it to the point of appearing useless.
2. **The splits differ in difficulty** — baseline precision is 0.238 on test and
   0.535 on val. Quote the test number as the headline; it is the harder set.

### Per failure mode — what the agent actually rejects

MARIDA test split, fitted thresholds. This is the part that makes the agent
defensible: it is not a uniform confidence haircut, it rejects specific,
named things.

| MARIDA truth class | Candidates | Rejected | Rate | Checks that fired |
|---|---|---|---|---|
| Clouds | 73 | 67 | 91.8% | sun_glint 66, foam 1, kelp 1 |
| Turbid Water | 39 | 39 | 100.0% | foam_whitecap 39 |
| Waves | 47 | 40 | 85.1% | foam 20, sun_glint 27 |
| Ship | 38 | 28 | 73.7% | sun_glint 20, foam 8 |
| Sparse Sargassum | 24 | 16 | 66.7% | kelp_sargassum 16 |
| Dense Sargassum | 9 | 9 | 100.0% | kelp_sargassum 9 |
| Foam | 4 | 4 | 100.0% | foam_whitecap 4 |
| Wakes | 9 | 4 | 44.4% | foam_whitecap 4 |
| **Marine Debris (false rejection)** | **80** | **4** | **5.0%** | sun_glint 4 |

With the unfitted thresholds the same table rejected **22.5% of true Marine
Debris** via `cloud_shadow`, and caught no Sargassum, foam, waves or turbid
water at all.

### Detector region recall — the number that is *not* good

`region_recall` = fraction of annotated Marine Debris regions that any detection
lands on. Unaffected by verification; it is purely the detector.

| Split | Regions | Hit | Region recall |
|---|---|---|---|
| test | 236 | 96 | **0.4068** |
| val | — | — | 0.5635 |

**The FDI baseline misses ~59% of annotated debris regions on test.** The
precision/recall table above is conditioned on candidates the detector emitted,
so it cannot show this. Both numbers must be quoted together or the system looks
better than it is. Improving this is the CNN variant's (FR-1.4) job.

---

## Threshold calibration

Every threshold was a literature-informed starting point. Fitted on **train
only**, detector first (maximising the *baseline's own* F1, so the ablation is
not measured against a strawman), then the verification thresholds by
coordinate descent with the detector held fixed.

| Parameter | Was | Fitted | Why it moved |
|---|---|---|---|
| `DEFAULT_FDI_THRESHOLD` | 0.006 | **0.025** | Marine water itself scores FDI ≈ 0.013, so 0.006 fires on open water |
| `shadow_brightness_max` | 0.015 | **0.008** | Sat in the middle of the true-debris brightness distribution (median 0.010) and rejected 78.6% of real debris |
| `glint_swir_min` | 0.05 | **0.02** | Clouds/ships sit at B11 ≈ 0.05; debris at 0.012 |
| `glint_flatness_max` | 0.18 | **0.20** | — |
| `foam_red_min` | 0.12 | **0.045** | Foam's red is only ≈ 0.048, so 0.12 never fired |
| `foam_ndvi_max` | 0.05 | **−0.10** | — |
| `kelp_ndvi_min` | 0.20 | **0.10** | Catches Sparse Sargassum (NDVI ≈ 0.25) as well as Dense |
| `kelp_ndvi_fdi_ratio` | 12.0 | **1.0** | — |

`glint_specular_angle_deg`, `shadow_cloud_fraction_min`, `persistence_tolerance_km`
and `inconclusive_penalty` were unchanged — the first three are not exercisable
on MARIDA (see caveats).

### Caveats — read before quoting any of this

1. **The checks now fire outside their named failure modes.** `foam_whitecap`
   rejects 100% of Turbid Water, and `sun_glint` rejects clouds and ships. They
   are doing correct *work* — those are all genuine false positives — but the
   rejection *reason string* the user sees will say "sea foam / whitecap" for
   turbid water. FR-2.3 requires the specific reason, and PRD §8 requires
   explainability, so **the reasons are now partly inaccurate even though the
   decisions are right.** Fix by splitting out dedicated turbid-water and
   cloud/bright-target checks rather than by reverting the thresholds.
2. **Three of seven fitted values landed on a grid edge** (`glint_swir_min`
   0.02, `foam_ndvi_max` −0.10, `kelp_ndvi_fdi_ratio` 1.0). The true optimum may
   lie outside the search range; widen the grid in `VERIFY_GRID` before treating
   these as final.
3. **Only 3 of the 5 checks are evaluable on MARIDA.** Patches carry no
   acquisition geometry and no repeat passes, so `sun_glint` is judged on
   spectral shape alone and `multi_temporal` is inconclusive throughout. The
   multi-temporal contribution (FR-2.2) is **unmeasured** and needs real L2A
   scenes over a chosen region.
4. **Fitted on MARIDA's 12 global regions**, not on the demo region — which is
   still undecided (PRD Open Question 1). Re-check once that is settled.
5. Ground truth per candidate is the majority *labelled* class in the same 5×5
   window verification samples. MARIDA is sparsely annotated (class 0 =
   unlabelled = 99.1% of pixels); unlabelled candidates are excluded, never
   assumed negative. On test that excluded 5738 of 6074 detections.

---

## Detection (FR-1) — precision / recall vs. MARIDA

Baseline FDI detector, from the ablation run above.

| Date | Machine | Commit | Detector | Split | Precision | Recall | Region recall |
|---|---|---|---|---|---|---|---|
| 2026-08-14 | Workstation | `8559696`+ | FDI (spectral) | test | 0.2381 | 1.0000¹ | 0.4068 |
| 2026-08-14 | Workstation | `8559696`+ | FDI (spectral) | val | 0.5354 | 1.0000¹ | 0.5635 |

¹ Recall over *scored candidates* is 1.0 for the baseline by construction — the
baseline selects every candidate it emitted. Region recall is the meaningful
detector-recall number.

CNN variant (FR-1.4): not built. Two traps documented in `data/README.md` —
class 0 is unlabelled not background (99.1% of pixels), and masks load as
float32.

## Drift Agent accuracy (FR-3) — vs. NOAA Global Drifter Program

_No runs yet — `drift.load_oscar_field()` unwritten and OSCAR not downloaded._

## Source attribution (FR-4) — vs. The Ocean Cleanup rankings

_No runs yet._

## Dark vessel correlation (FR-5) — vs. GFW published case studies

_No runs yet — needs a GFW API token._

## System-level ablation

Pipeline-level ablation (each agent removed in turn) is implemented in
`ghostnet.pipeline.run_ablation_study()` but has only ever run on synthetic
inputs. The FR-2.4 verification ablation above is the first agent-level
ablation measured on real data.

## End-to-end demo latency

_Not measured — blocked on the demo region and the L2A tile reader._

---

## Hardware baseline

| Machine | Device | VRAM | Compute | torch | fp32 4096³ matmul | Date |
|---|---|---|---|---|---|---|
| Workstation | RTX 5070 | 12.8 GB | sm_120 (Blackwell) | 2.12.0.dev20260408+cu128 | 18.8 ms (~7.3 TFLOPS) | 2026-08-14 |
| MacBook Air M3 | — | — | no CUDA | not installed | — | 2026-08-14 |
