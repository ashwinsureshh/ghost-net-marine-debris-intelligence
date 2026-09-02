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
| Clouds | 73 | 67 | 91.8% | bright_swir_target 66, bright_water_surface 1, kelp 1 |
| Turbid Water | 39 | 39 | 100.0% | bright_water_surface 39 |
| Waves | 47 | 40 | 85.1% | bright_swir_target 27, bright_water_surface 20 |
| Ship | 38 | 28 | 73.7% | bright_swir_target 20, bright_water_surface 8 |
| Sparse Sargassum | 24 | 16 | 66.7% | kelp_sargassum 16 |
| Dense Sargassum | 9 | 9 | 100.0% | kelp_sargassum 9 |
| Foam | 4 | 4 | 100.0% | bright_water_surface 4 |
| Wakes | 9 | 4 | 44.4% | bright_water_surface 4 |
| Sediment-Laden Water | 1 | 1 | 100.0% | bright_water_surface 1 |
| **Marine Debris (false rejection)** | **80** | **4** | **5.0%** | bright_swir_target 4 |

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
better than it is.

**This was the CNN variant's job, and it is now done:** FR-1.4 raises region
recall to **0.7034** on the same split — see the CNN section below. Everything
in this section describes the FDI baseline, which remains the fallback wherever
`models/detector_v1.pt` is absent.

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

1. ~~The checks fire outside their named failure modes.~~ **FIXED 2026-08-14.**
   Fitting made `foam_whitecap` reject 100% of Turbid Water and `sun_glint`
   reject clouds and ships — correct decisions, inaccurate labels, which FR-2.3
   and PRD §8 both care about. The checks are now named for the *signature* they
   measure (`bright_swir_target`, `bright_water_surface`) and name a specific
   cause only where the evidence supports it: sun glint when the specular angle
   says so, cloud when the cloud fraction does, turbidity when NDVI is below
   −0.30. Verified decision-neutral — every metric and per-class count above is
   byte-identical before and after the rename.
2. **Three of seven fitted values landed on a grid edge** (`glint_swir_min`
   0.02, `foam_ndvi_max` −0.10, `kelp_ndvi_fdi_ratio` 1.0). The true optimum may
   lie outside the search range; widen the grid in `VERIFY_GRID` before treating
   these as final.
3. **Only 3 of the 5 checks are evaluable on MARIDA.** Patches carry no
   acquisition geometry and no repeat passes, so `bright_swir_target` still
   disqualifies on spectral grounds but cannot name sun glint specifically, and
   `multi_temporal` is inconclusive throughout. **FR-2.2 has since been
   measured separately** against real L2A repeat passes — see the
   multi-temporal section below. It contributes nothing at present and is
   blocked on FR-3.1.

   Related bug found and fixed while renaming: `bright_swir_target` used to
   require *specular geometry or no geometry at all* in order to disqualify.
   MARIDA has no geometry, so it rejected 91.8% of clouds here — but on real
   L2A tiles, where geometry is present and usually non-specular, it would have
   silently stopped rejecting clouds and taken the headline result with it.
   Disqualification is now decided on the spectral signature alone; geometry
   only names the cause. Regression test in `tests/test_verification.py`.
4. **Fitted on MARIDA's 12 global regions**, not on the demo region alone. The
   region has since been settled (Gulf of Honduras) and the run AOI overlaps
   MARIDA's 16PCC annotations, so these thresholds were fitted on data that
   includes the demo water — but they are not tuned *to* it. Re-check if the
   AOI moves.
5. Ground truth per candidate is the majority *labelled* class in the same 5×5
   window verification samples. MARIDA is sparsely annotated (class 0 =
   unlabelled = 99.1% of pixels); unlabelled candidates are excluded, never
   assumed negative. On test that excluded 5738 of 6074 detections.

---

## CNN detector variant (FR-1.4) — vs. the FDI baseline

Run 2026-08-25, workstation (RTX 5070), commit `1c9d48a`. Reproduce with:

```bash
python scripts/train_cnn.py
python scripts/eval_marida.py --split test --detector fdi --json eval/detector_fdi_test.json
python scripts/eval_marida.py --split test --detector cnn --json eval/detector_cnn_test.json
```

Both detectors are scored by the **same script, through the same data loading,
the same labelling rule and the same region-recall code**. That is what makes
the comparison a claim rather than an anecdote — the two paths even receive
byte-identical 11-band Tiles, the FDI simply ignoring the seven bands it does
not use.

### Held-out MARIDA test split, 359 patches

| | FDI baseline | **CNN** |
|---|---|---|
| Candidates emitted | 6074 | **795** |
| Scored (carry a label) | 336 | 204 |
| Detector precision | 0.2381 | **0.6716** |
| Detector F1 | 0.3846 | **0.8035** |
| \+ Verification precision | 0.6230 | **0.7514** |
| \+ Verification F1 | 0.7525 | **0.8387** |
| **Region recall** | **0.4068** (96/236) | **0.7034** (166/236) |

**Headline: region recall 0.407 → 0.703 (+0.296).** The detector now finds 166
of 236 annotated debris regions instead of 96, and does it while emitting 7.6×
*fewer* candidates — 795 against 6074.

This is the number FR-1.4 existed to move. Everywhere else in this document
region recall is the figure that had to be quoted alongside the headline
precision gain to keep it honest; it is no longer the embarrassing one.

### Where the improvement actually comes from

The FDI's false positives largely disappear rather than being filtered out
later. Candidates by MARIDA truth class, test split:

| Truth class | FDI candidates | CNN candidates |
|---|---|---|
| Marine Debris | 80 | **137** |
| Clouds | 73 | **1** |
| Waves | 47 | 25 |
| Turbid Water | 39 | **0** |
| Ship | 38 | 13 |
| Sparse + Dense Sargassum | 33 | **0** |
| Foam | 4 | **0** |

**Corrected 2026-09-02.** Three CNN cells previously read 112 / 19 / 12. They
were a mis-transcription of this table, not a bad run. `eval/detector_cnn_test.json`
gives 137 / 25 / 13, and it is the self-consistent artefact: its per-class
candidates sum to exactly 204, which is both its own `n_labelled` and its
`detections_total` (795) minus `detections_unlabelled_excluded` (591). The prose
figures reconciled with nothing. Every other CNN number here — region recall
0.7034, detector precision 0.6716, F1 0.8035, the +0.0799 verification delta —
was already exact. Caught by the PRD §12 write-up cross-checking prose against
the committed JSON, which is the reason that check exists.

Training multi-class rather than debris-vs-rest is what did this. MARIDA
separately labels the exact things the Verification Agent has to rule out, so
the network learns Sargassum, cloud and turbid water as their own classes
instead of inheriting the index's confusion between them.

### The finding that matters for PRD §12

**The CNN substantially subsumes the Verification Agent.** Its measured
contribution collapses when the detector improves:

| Detector | Verification precision gain | Verification F1 gain |
|---|---|---|
| FDI | **+0.3849** | +0.3679 |
| CNN | **+0.0799** | +0.0352 |

That is a real overlap between two agents and must be reported, not hidden. The
PRD §7 design test — removing any one agent should *break* the system — is
weaker for verification once the CNN is the detector: it still adds precision
(+0.080), still rejects 73.7% of waves and still catches 100% of the one cloud
that survives, but it is no longer the difference between usable and unusable
output that it is over the FDI.

The honest framing for the report: verification is load-bearing **for the
spectral baseline**, and becomes a smaller safety net once a learned detector
has already excluded most confusers. Both numbers above should be quoted.

### Model and training

Plain 4-level U-Net, 7.77 M parameters, 11 input bands → 16 classes, written in
PyTorch with no dependency beyond torch (see `requirements-gpu.txt` for why smp
and torchvision were deliberately not installed).

| | |
|---|---|
| Train / val patches | 694 / 328 |
| Epochs | 60 (best at 51), 6.4 min on an RTX 5070 |
| Loss | Cross-entropy, `ignore_index=0`, inverse-sqrt class weights |
| Selection | **val debris F1** — never accuracy, which is meaningless here |
| Best val debris | P 0.8213 R 0.8679 **F1 0.8440**, macro F1 0.7226 |
| Checkpoint | `models/detector_v1.pt`, 31 MB, **not committed** |

### Probability threshold — calibrated on val, never on test

`DEFAULT_PROB_THRESHOLD = 0.40`. Chosen to maximise **region recall**, which is
what FR-1.4 exists to fix. The two objectives genuinely conflict:

| Threshold | Detector precision | Detector F1 | Region recall |
|---|---|---|---|
| 0.20 | 0.7825 | 0.8780 | 0.7038 |
| 0.30 | 0.8219 | 0.9022 | 0.7350 |
| **0.40** | 0.8626 | 0.9262 | **0.7550** |
| 0.50 | 0.8885 | 0.9410 | 0.7127 |
| 0.60 | 0.8915 | 0.9426 | 0.6169 |
| 0.70 | 0.9031 | 0.9491 | 0.4989 |

Precision climbs monotonically with the threshold while region recall peaks at
0.40 and then collapses. **Tuning on precision alone would have produced a
better-looking table and found less debris** — 0.70 reads as the best row and
misses half the regions.

### Caveats — read before quoting any of this

1. **204 scored candidates on test.** MARIDA is sparsely annotated, so 591 of
   795 CNN detections land on unlabelled pixels and are excluded rather than
   assumed wrong. The precision figures rest on a small sample; region recall,
   which uses all 236 annotated regions, is the more robust number.
2. **Val is not independent.** Both the training epoch and the probability
   threshold were selected on val, so val figures are optimistic by
   construction. Test was touched once, after both were fixed — quote test.
3. **It still misses 70 of 236 regions (29.7%).** Better, not solved.
4. **Trained on MARIDA's 12 global regions**, not on the Gulf of Honduras
   specifically. The demo AOI overlaps MARIDA's 16PCC annotations, so the demo
   water is represented in training but the model is not tuned to it.
5. **These are within-tile numbers.** 327 of the 359 test patches (91%) sit on
   MGRS tiles that also appear in train, because MARIDA splits by patch rather
   than by tile. The cost of a genuinely unseen region is measured separately —
   see *Geographic generalisation* below: −0.072 debris F1, almost all of it
   recall.
6. **The checkpoint is not committed** (31 MB, MACHINE-WORKFLOW.md sync rule 2).
   A machine without `models/detector_v1.pt` cannot run the CNN path;
   `load_detector` raises and names the command that produces it.

### One bug this work exposed

Loading 11-band Tiles silently broke verification, because
`BandWindow.brightness` and `.flatness` averaged over *whatever bands the dict
happened to hold*. The thresholds were fitted against four. Feeding 11-band
tiles through them dropped held-out precision from 0.623 to 0.447 and cloud
rejection from 91.8% to 69.9% — with no error anywhere. Both statistics are now
pinned to `REQUIRED_BANDS`, and the FDI numbers above reproduce exactly. A
threshold is only meaningful against a fixed basis.


### Geographic generalisation — does it work on a region it has never seen?

Run 2026-09-02, workstation. Reproduce with:

```
python scripts/train_cnn.py --holdout-tile 18QYF --out models/detector_holdout_18QYF.pt
python scripts/train_cnn.py --eval-only --holdout-tile 18QYF \
    --out models/detector_holdout_18QYF.pt --json eval/holdout_18QYF.json
python scripts/train_cnn.py --eval-only --holdout-tile 18QYF \
    --out models/detector_v1.pt --json eval/holdout_18QYF_leaky.json
```

**Why this was needed: MARIDA's published splits are by patch, not by tile.** Six
of the eight MGRS tiles in the test split also appear in train, so **327 of 359
test patches (91%) sit on ground the model trained on**. Every number in the
section above is therefore a *within-tile* result. It is a fair comparison — the
FDI baseline is scored through the identical path — but it says nothing about a
new region, which is the first thing an operator would ask.

So a second detector was trained with **18QYF (Gulf of Gonâve, Haiti) withheld
from both train and val** — val too, because model selection is on val debris F1
and leaving it in would pick the checkpoint that best fits the supposedly unseen
region. 635 train / 305 val patches, otherwise identical recipe, seed and
epoch budget to `detector_v1`.

**The paired comparison, over the identical 84 18QYF patches:**

| Marine Debris, 84 patches / 1112 labelled px | Precision | Recall | F1 |
|---|---|---|---|
| `detector_v1` — **trained on** 18QYF | 0.9355 | 0.9254 | 0.9304 |
| holdout model — **never saw** 18QYF | 0.9085 | 0.8129 | 0.8581 |
| **cost of the region being unseen** | **−0.0270** | **−0.1125** | **−0.0723** |

**The detector loses about 7 F1 points on an unseen region, and the loss is
almost entirely recall.** Precision barely moves (−0.027): what it flags on new
water is still trustworthy, it just finds less — it misses roughly one debris
pixel in nine that the region-trained model catches. For a screening system
feeding a verification agent that is the better failure direction of the two,
and it is the strongest evidence available that the detector has learned a
spectral signature of debris rather than memorising four tiles of Caribbean
water.

#### One number in this experiment must not be quoted

`--eval-only --holdout-tile` also prints the holdout model's score on the rest
of the test split (debris F1 0.6637). **Subtracting that from the 18QYF score is
not a generalisation gap and the script now says so on its face**, because the
two arms differ in task difficulty far more than in geography:

| | debris px / patch |
|---|---|
| 18QYF | 13.24 |
| test minus 18QYF | 0.98 |

18QYF is MARIDA's densest debris region by an order of magnitude, so a model
scores *higher* there whether or not it trained on it. The naive subtraction
gives −0.194 — the wrong sign and a meaningless magnitude. Only the paired table
above, where both models see identical patches, isolates the effect of the
region being unseen.

#### Caveats

1. **One region, one seed, no repeats.** 18QYF was chosen because it is the
   documented secondary/stretch region and MARIDA's densest debris; it is not a
   random draw, and −0.072 F1 is a single measurement, not a confidence interval.
2. **The holdout model trained on 8.5% less data** (635 vs 694 patches). Part of
   the −0.072 is less training data rather than the region being unseen, so the
   figure is an upper bound on the true generalisation cost.
3. **Haiti is the same current system and water type as the demo region.** This
   measures generalisation to an unseen *tile* in the western Caribbean, not to
   a different ocean. Southeast Asian tiles would be the harder test.
4. **It does not license the Gulf of Gonâve stretch goal on its own** — it says
   detection would likely transfer, nothing about drift, attribution or the
   region's own extracts.
5. `models/detector_holdout_18QYF.pt` is **not committed** (31 MB, sync rule 2).
   It is an experiment artefact; `detector_v1.pt` remains the pipeline's
   detector, unchanged by this work.

---

## Multi-temporal consistency (FR-2.2) — measured, and it does not yet earn its place

Run 2026-08-15, workstation. Reproduce with:

```bash
python scripts/eval_multitemporal.py --json eval/multitemporal.json
```

This was the last unmeasured verification check. `scripts/eval_marida.py` cannot
touch it — MARIDA patches carry no repeat pass, so the check reports itself
inconclusive throughout. The harness therefore streams two real L2A acquisitions
onto one fixed grid (so pixel `(r, c)` is the same ground position on both
dates) and rasterises MARIDA's masks onto that grid for ground truth.

**Result: no measurable contribution on any labelled repeat pair, and on the one
pair where the check acted it removed a true detection and no false positive.**

| Pair | Cand. A | Labelled | ΔPrecision | ΔRecall | ΔF1 | True debris lost |
|---|---|---|---|---|---|---|
| 16PCC 2020-09-18 → 09-23 | 144 | 12 | +0.000 | **−0.250** | **−0.167** | **1** |
| 18QYF 2020-03-14 → 03-19 | 21 | 7 | 0.000 | 0.000 | 0.000 | 0 |
| 18QYF 2020-11-29 → 12-04 | 22 | 0 | — | — | — | 0 |
| 16PCC 2018-09-14 → 09-19 | 0 | 0 | — | — | — | — |

Deltas are measured against the four spectral checks, so they isolate what
multi-temporal adds on top of them.

### Three reasons, and only one of them is the check's fault

**1. It is structurally dependent on the Drift Agent (FR-3), which is unwritten.**
`check_persistence` allows a displacement of `current_speed × Δt + 5 km`. With no
OSCAR field loaded, `current_speed_ms` is `None`, so the envelope collapses to the
5 km base tolerance — while genuine debris drifting at only 0.1 m/s covers ~43 km
in the 5 days between passes. The check therefore calls real drift "incoherent
motion". Measured directly as a sensitivity analysis:

| Assumed current | Incoherent rejections | True debris lost | ΔF1 |
|---|---|---|---|
| none (5 km envelope) | 6 | 1 | −0.167 |
| 0.10 m/s (assumed) | **0** | **0** | 0.000 |

Every false rejection disappears once the envelope is realistic. **FR-2.2 cannot
be fairly evaluated until FR-3.1 supplies a real current field.** The 0.10 m/s
figure is an assumption for sensitivity only and is not a result.

**2. Zero transients in every pair — the check's strongest signal never fires.**
"Appears once and vanishes" is what separates foam and glint from a debris raft.
But repeats are built by nearest-neighbour matching, and with 9–130 candidates in
an AOI something is always within the search radius: 144/144, 21/21 and 22/22
candidates were "re-observed". Nearest-neighbour matching cannot distinguish *this
patch persisting* from *some other detection existing nearby*. A defensible
implementation needs identity-preserving matching — drift-predicted position plus
a spectral-similarity gate — not proximity alone.

**3. The labelled samples are tiny.** 12 and 7 scored candidates on the two
usable pairs. MARIDA annotates sparsely and the two dates' annotation footprints
barely overlap, so none of these deltas would survive a significance test. They
are indicative, not conclusive.

### What this means for the PRD §12 ablation

The design test in PRD §7 is that removing any single agent should *break* the
system. On this evidence, removing multi-temporal verification today would not
degrade the pipeline at all — it would slightly improve recall. That should be
reported honestly rather than papered over: it is a finding about the current
build, not about the idea. The check is sound in principle and is standard in the
literature; it is inert here because the current field it depends on does not
exist yet.

**Do not quote FR-2.2 as a contribution in the report.** Quote it as a measured
dependency: the multi-temporal check is blocked on FR-3.1, with the numbers above
as evidence.

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

CNN variant (FR-1.4): **built and measured** — see the CNN section. Both traps
from `data/README.md` were handled explicitly (class 0 is unlabelled not
background at 99.1% of pixels; masks load as float32).

## Drift Agent accuracy (FR-3) — vs. NOAA Global Drifter Program

_No runs yet._ `drift.load_oscar_field()` is written and tested (2026-08-26), and
the **buoy ground truth is now downloaded** (2026-08-27): 10 401 observations
from 226 drifters, 1980–2025, via `python scripts/fetch_drifters.py`. What is
still missing is the current field to predict *with* — OSCAR is not downloaded on
either machine and `EARTHDATA_TOKEN` does not exist yet.

Two things about the drifter coverage that will shape how this is reported, both
measured rather than assumed:

- **No drifter passed through the Gulf of Honduras bbox during the
  2018-02-01…2018-10-01 demo window — zero observations.** So this validation
  cannot be contemporaneous with the demo run. It has to be reported as a model
  check over the years the region does have, exactly as the MARIDA benchmark is
  independent of the demo window. Do not let the report imply the buoys validate
  the demo run itself.
- The bare region bbox holds only 553 observations from 13 drifters, in 1999,
  2000, 2007, 2013 and 2014 — too thin to validate against. The fetch therefore
  defaults to a **300 km buffer** over the same current system. Quote the buffer
  alongside the result; it is a western-Caribbean sample, not a
  Gulf-of-Honduras-only one.

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
