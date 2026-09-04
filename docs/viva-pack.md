# Viva defence pack

**The rule this document exists to enforce:** *no number reaches the report that
the person quoting it cannot derive and defend.* An evaluator asking "why is
this 0.703?" is asking **you**, not the tool. Everything below is therefore
written as *claim → artefact → derivation → the answer you give out loud*.

Assembled by reading committed `eval/*.json`. Nothing here was re-run — the
MacBook Air has no MARIDA and no GPU — and §6 lists what could not be verified
from a committed artefact, rather than quoting it anyway.

Companion documents: [`ablation-study.md`](ablation-study.md) is the results
narrative; [`evidence-traceability.md`](evidence-traceability.md) is the
provenance walk-through.

---

## 1. The claims ledger

Every number the project may state. If it is not in this table, it is not a
result.

### FR-2.4 — the Verification Agent's contribution

| | |
|---|---|
| **Claim** | Precision 0.238 → 0.623, F1 0.385 → 0.753, on held-out MARIDA test |
| **Artefact** | `eval/marida_ablation.json` → `held_out_fitted.metrics` |
| **Sample** | 359 patches → 6074 candidates emitted, **336 scored** (5738 excluded as unlabelled) |
| **Derivation** | Thresholds fitted on the **train split only**, detector first (maximising the *baseline's own* F1), then verification by coordinate descent with the detector fixed |
| **Defence** | "The baseline is not a strawman — I fitted it first, so the gain is measured against the best the spectral index can do. The 'before' arm restores `LITERATURE_THRESHOLDS`, so it is reproducible rather than being the calibrated agent compared against itself." |

**The follow-up you will get:** *"Recall is 1.000 for the baseline — does it find
everything?"* No. That recall is conditioned on candidates the detector emitted,
so it is 1.0 **by construction**. The detector's real recall is region recall,
below. The two must always be quoted together.

### FR-1.4 — the CNN detector

| | |
|---|---|
| **Claim** | Region recall 0.407 → **0.703**, while emitting **7.6× fewer** candidates |
| **Artefact** | `eval/detector_fdi_test.json`, `eval/detector_cnn_test.json` |
| **Sample** | Same 359 test patches, **236 annotated debris regions**; FDI hits 96, CNN hits 166 |
| **Derivation** | Both detectors scored by the same script, same loading, same labelling rule, same region-recall code. They receive byte-identical 11-band tiles; the FDI ignores the seven bands it does not use |
| **Defence** | "It is a claim rather than an anecdote because only the detector changed. Region recall counts annotated debris regions any detection lands on — 166 of 236 — and it is unaffected by verification, so it is the detector's number alone." |

**Why 0.703 and not higher:** the probability threshold is 0.40, chosen on
**val** to maximise region recall. It still misses 70 of 236 regions (29.7%).
Better, not solved. *(See §6 — the sweep supporting this choice is prose-only.)*

### The subsumption finding

| | |
|---|---|
| **Claim** | Verification's precision gain falls from **+0.385 over the FDI** to **+0.080 over the CNN** |
| **Artefact** | `metrics.precision_delta` in each detector file |
| **Derivation** | Read, not recomputed. Same verification agent, same thresholds, different detector ahead of it |
| **Defence** | "Training multi-class is why. MARIDA separately labels the confusers verification exists to reject, so the network learns them as classes instead of inheriting the index's confusion — 73 cloud candidates under FDI become 1 under the CNN; turbid water and Sargassum go to zero." |

**This is a PRD §7 result, not an embarrassment.** Verification is load-bearing
**for the spectral baseline** and becomes a smaller safety net behind a learned
detector. It still adds +0.080 precision and still rejects 73.7% of waves.
**Never quote +0.385 alone once the CNN is the detector.**

### Geographic generalisation

| | |
|---|---|
| **Claim** | **−0.072 debris F1** on an unseen region, almost all of it recall |
| **Artefact** | `eval/holdout_18QYF_leaky.json` (trained), `eval/holdout_18QYF.json` (unseen) |
| **Sample** | **The identical 84 patches**, 13.24 debris px/patch in both arms |
| **Derivation** | Second detector trained with 18QYF withheld from train **and val** — val too, because selection is on val debris F1 |
| **Numbers** | trained F1 0.9304 → unseen F1 0.8581; P −0.027, R −0.113 |
| **Defence** | "The pairing is the experiment: both models see the same patches, so the only variable is whether the region was in training. Almost all the loss is recall — it finds less on new water, but what it flags stays trustworthy, which is the better failure direction for a screening stage feeding verification." |

**Why region recall 0.703 needs this beside it:** MARIDA splits by patch, not by
tile, so **327 of 359 test patches (91%) sit on tiles the model trained on**.
0.703 is a *within-tile* number. On its own it reads as evidence of
generalisation, and it is not.

### FR-2.2 — multi-temporal consistency, a measured negative

| | |
|---|---|
| **Claim** | It contributes **nothing** today: F1 0.500 → 0.333 on the one pair where it acted, removing one true detection and no false positive |
| **Artefact** | `eval/multitemporal.json` and four per-arm files |
| **Sample** | 144 candidates, **12 labelled**, on 16PCC 2020-09-18 → 09-23 |
| **Derivation** | Two real L2A acquisitions streamed onto one fixed grid, MARIDA masks rasterised for truth. Deltas measured on top of the four spectral checks |
| **Defence** | "It is blocked on FR-3.1. The coherence test allows `current_speed × Δt + 5 km`; with no OSCAR field that collapses to the 5 km floor, while real debris at 0.1 m/s covers ~43 km between passes five days apart. So it rejects genuine drift as incoherent motion. At an assumed 0.10 m/s the false rejections go to zero — that is the sensitivity arm, not a result." |

**Report it as a dependency on FR-3.1, never as a contribution.** PRD §12
records it as a measured exception to the every-agent-is-load-bearing test.
Keep that framing — it is a finding about this build, not about the idea.

---

## 2. Numbers that must travel together

Quoting either alone misleads. The console enforces all three pairings; so
should you.

| Never say this alone | Without this |
|---|---|
| Verification precision gain +0.385 | Detector region recall 0.407 |
| +0.385 (over FDI) | +0.080 (over CNN), once the CNN is the detector |
| Region recall 0.703 | It is **within-tile**; unseen-region cost −0.072 |
| "Every agent is load-bearing" | FR-2.2 is the measured exception |

---

## 3. Questions you will be asked

**"Why is region recall only 0.703? / Why did the FDI only get 0.407?"**
The FDI keys off a spectral shoulder that many things share — cloud, Sargassum,
turbid water, wakes. It emits 6074 candidates on 359 patches and lands on 96 of
236 annotated regions. The CNN reaches 166 of 236 while emitting 795. It still
misses 30%; that is stated, not hidden.

**"Isn't your Verification Agent redundant now?"**
Subsumed, not redundant — and the distinction is measured. Over the CNN it still
adds +0.080 precision and still removes what survives the detector. The honest
version is that its value depends on what runs ahead of it, which is itself a
result about the architecture.

**"How do I know the verification gain isn't just a badly-tuned baseline?"**
Because the baseline was tuned first, on train only, maximising its own F1. And
because the uncalibrated agent was worth +0.003 F1 on test and was *actively
harmful* on val (0.697 → 0.648) — reporting it uncalibrated would have made a
load-bearing component look useless.

**"Your sample is 336 candidates out of 6074. Is that enough?"**
It is what MARIDA supports: it is sparsely annotated, so 5738 candidates land on
unlabelled pixels and are **excluded, never assumed wrong**. Region recall,
which uses all 236 annotated regions, is the more robust number and is why it is
always quoted alongside.

**"Did you validate the drift model?"**
**No.** See §4 — this is the answer to give, not one to improvise.

**"Does it work anywhere other than where you trained it?"**
Measured: −0.072 F1 on a held-out region, almost all recall. Caveated three
ways — one region, one seed; the holdout model saw 8.5% less data so it is an
**upper bound**; and Haiti shares the demo region's current system, so it is an
unseen *tile in the western Caribbean*, not a different ocean.

**"Why should I believe any of these numbers?"**
`python -m ghostnet.provenance` — every figure the console serves, its artefact
and its JSON pointer, checked in CI. It also pins the published headline figures
so an edited artefact fails. Break one on purpose and it names the field, both
values and the source.

**"What would change your conclusions?"**
Two free-tier credentials. `EARTHDATA_TOKEN` gives OSCAR, which unblocks FR-2.2's
re-measurement and drift; `GFW_API_TOKEN` unblocks FR-5. Neither needs a GPU.

---

## 4. What must not be claimed

Each of these is a sentence you may be tempted into. Do not say it.

**Drift validation.** The buoy ground truth is downloaded — 10 401 observations
from 226 drifters — but **zero drifters passed through the Gulf of Honduras bbox
during the 2018 demo window**. If the backtest is ever run it is a model check
over *other years*, on a western-Caribbean sample at a 300 km buffer, and it
never validates the demo run. Say "not validated", not "validated on other
years", unless it has actually been run.

**Any end-to-end run on real data.** Still blocked on four datasets. Every
artefact in the repo is synthetic, `provenance.inputs_are_synthetic` is `true`,
and the console says so on its face. The *path* is real; the inputs are not.

**Anything from `run_pipeline_demo.py`.** Synthetic, illustrative, not results.
Its numbers must never enter `eval/results.md` or the report.

**Source attribution or dark-vessel accuracy.** No runs. FR-4 and FR-5 have
readers and, for FR-5, one unimplemented query; neither has been measured.

**End-to-end latency.** Not measured — it needs a real run.

**The system-level ablation on real inputs.** `run_ablation_study()` executes,
but only on synthetic inputs. The FR-2.4 ablation is the one measured on real
data.

**That the shipped detector is the holdout model.** `detector_v1.pt` is the
pipeline's detector and is unchanged; `detector_holdout_18QYF.pt` is an
uncommitted experiment artefact that never ran the pipeline.

---

## 5. The demonstration, in order

1. **Say the framing first.** Research prototype; this run's inputs are
   synthetic and the console says so. The path is what is being shown.
2. **Metrics strip.** Precision 0.238 → 0.623; region recall 0.407 marked
   `within-tile`; unseen-region cost −0.072; FR-2.2 marked *blocked on FR-3*.
   Note the *MARIDA test — not this run* badge.
3. **Rank 1 → evidence trail.** Tile ID, the five verification checks with
   reasons, drift envelope with its **seed**, ranked source rivers, SAR vessel
   records with the investigation-signal disclaimer.
4. **Rejected tab.** Four detections and why each was disqualified. This is the
   Verification Agent's contribution made visible.
5. **Controls → ablate an agent, re-plan.** The plan changes and a named
   degradation appears.
6. **`python -m ghostnet.provenance`.** Every number traced; then break one and
   show it fail.
7. **Approve.** FR-6.4 — nothing is final without a named human.

**Fallback, not optional.** Free-tier hosts sleep and venue wifi fails. Build
`static_export/index.html` beforehand and carry it: it opens from `file://` with
no server and no network. It is read-only by design — approval and live ablation
need the server, and it says so rather than faking them.

---

## 6. Gaps in our own evidence — read before quoting

Found while assembling this pack, by checking each figure against a committed
artefact rather than against prose.

1. **The CNN probability-threshold sweep is prose-only.** `eval/results.md`
   carries the 0.20–0.70 table that justifies `DEFAULT_PROB_THRESHOLD = 0.40`,
   but **no committed artefact holds it** — no `eval/*.json` contains those
   rows. "Why 0.40?" is a likely question and the answer currently rests on
   prose that cannot be re-derived. *Action, workstation: re-run the sweep to
   its own `--json`.* Until then, defend the choice by its reasoning (region
   recall peaks at 0.40 and collapses by 0.70) and say the table is not yet
   backed by an artefact.
2. **`fdi_sweep` in `marida_ablation.json` is the TRAIN fit, not test.** At
   threshold 0.025 it reads precision 0.4144 and region recall 0.5541 over
   n=835; the held-out **test** figures are 0.2381 and 0.4068 over n=336.
   Quoting the sweep as a test result would overstate the detector by 15 points
   of region recall. The two are in the same file — do not mix them.

3. **"Your JSON says 0.7525 — why does the report say 0.753?"** Because 0.7525
   is rounded **half-up**, and several languages round half-to-even and give
   0.752. The console hit exactly this: `toFixed(3)` rendered the verified F1 as
   0.752 because 0.7525's nearest double sits just below it, and the metrics
   strip was changed to round half-up so all ten displayed figures match
   `eval/results.md`. Not a discrepancy — a rounding convention, and the answer
   if someone has the artefact open beside the report.

Neither of the first two affects a headline. All three are the kind of thing
that only surfaces by checking prose against artefacts, which is why §1 is
written the way it is.
