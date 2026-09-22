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

Selected benchmark claims. Additional measured checks are documented in
[the report draft](report-draft.md) with their committed sources.

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
Better, not solved. The sweep behind that choice is in
`eval/cnn_prob_sweep_val.json`: precision rises monotonically to 0.9031 at 0.70
while region recall peaks at 0.40 and collapses to 0.4989 — the objectives
conflict, and we chose the one FR-1.4 exists to fix.

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
| **Defence** | "Both models are evaluated on the same patches. Training size differs, and historical weights and normalization retain aggregate information from withheld patches. The observed difference does not isolate geographic transfer; the new strict study excludes those aggregates too." |

**Why region recall 0.703 needs this beside it:** MARIDA splits by patch, not by
tile, so **327 of 359 test patches (91%) sit on tiles the model trained on**.
0.703 is a *within-tile* number. On its own it reads as evidence of
generalisation, and it is not.

### FR-2.2 — real-current remeasurement, still a measured negative

It contributes **nothing** measurable with real OSCAR currents. In
`eval/multitemporal_oscar.json`, the headline pair has F1 0.500 with and without
the check, zero marginal rejections and zero true debris lost. The earlier
no-current arm (`eval/multitemporal.json`) reduced F1 from 0.500 to 0.333.
The dependency was supplied: harmful rejections disappeared, but contribution
remained zero. Do not say it is still blocked on an absent current field.
The PRD exception remains; implementation is not proof of usefulness.

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
A model check exists in `eval/drift.json`: 19 tracks and 406 observations in
2014, mean track error 34.639 km and mean envelope inclusion 24.52%. The demo
window is **not validated**. Error is 10.46 km for tracks up to 4.5 days and
48.74 km beyond, with small groups of 7 and 12 tracks. Explain the horizon
split and undercoverage, rather than presenting the mean as operational accuracy.

**"Does it work anywhere other than where you trained it?"**
Historical image holdout: −0.072 F1, mostly recall, on one tile and seed.
Training size differs; fixed class priors and normalization include withheld
patches. This is not a causal estimate or an upper bound. The stricter two-tile,
three-seed study excludes the evaluation tile from both aggregates too.

**"Why should I believe any of these numbers?"**
`python -m ghostnet.provenance` — every figure the console serves, its artefact
and its JSON pointer, checked in CI. It also pins the published headline figures
so an edited artefact fails. Break one on purpose and it names the field, both
values and the source.

**"What would change your conclusions?"**
Independent local labels, river-ranking/reference comparisons and vessel-context
validation could change the conclusions. Credentials and real-input integration
are now complete for Honduras and Gonave. Puducherry GFW remains unavailable.
The September 22 full-input repeat shows vessel evidence affects scoring;
independent correctness remains unmeasured.

---

## 4. What must not be claimed

Each of these is a sentence you may be tempted into. Do not say it.

**Demo-window drift accuracy.** There were zero drifters in the 2018 demo
window. The completed 2014 check does not validate that run or debris windage.

**Confirmed ghost nets or unique objects.** Exported detection records are
candidates, potentially repeated across acquisitions. Verification is algorithmic.

**Anything from `run_pipeline_demo.py`.** Synthetic, illustrative, not results.

**Source attribution or dark-vessel accuracy.** Real input integration exists;
independent reference accuracy remains unmeasured. Hourly grid observations and
SAR aggregate counts are not counts of distinct AIS-silent vessels. Unmatched
AIS does not prove illegality or a pollution source.

**Cold-run latency.** The new full-input measurement is 1017.24 seconds including
serialization; `cold_run_asserted` is false. Do not extrapolate it globally.

**Every agent improves accuracy.** The full-input ablation now includes GFW and
shows scoring dependence, not independently labelled correctness. Attribution
leaves ranking unchanged, and FR-2.2 remains inert even with real currents.

**One checkpoint for every run.** `detector_v1.pt` benchmark results do not
establish the accuracy of every exported region. Check each artifact's detector
provenance; Gonave has a geographic-holdout note, not independent local labels.

---

## 5. The demonstration, in order

1. State research-prototype framing and the selected historical region/window.
2. Show coverage: three real regions; blank areas are unanalysed. Synthetic is separate.
3. Open a verified and rejected candidate; trace recorded evidence, not ground truth.
4. Show Puducherry's partial-input label: GFW unavailable means unknown evidence.
5. Present paired benchmark numbers: CNN +0.080 verification gain with 0.703
   within-tile region recall; explain the holdout and FR-2.2 exceptions.
6. Show the plan's human-review requirement without recording a demonstration approval.
7. Show `static_export/release-2026-09-21/index.html`, the four-run offline copy.
   Direct-file acceptance remains manual; approval/live ablation require the
   server and map tiles may require connectivity.

See [release readiness](release-readiness.md) for the release record and
[report draft](report-draft.md) for the current evidence narrative.

---

## 6. Gaps in our own evidence — read before quoting

Found while assembling this pack, by checking each figure against a committed
artefact rather than against prose.

1. ~~**The CNN probability-threshold sweep is prose-only.**~~ **CLOSED
   2026-09-04 (workstation).** You were right that no `eval/*.json` held the
   0.20–0.70 table justifying `DEFAULT_PROB_THRESHOLD = 0.40`. It now lives in
   **`eval/cnn_prob_sweep_val.json`**, and all eighteen published cells
   reproduced exactly. Re-derive with:

   ```bash
   python scripts/eval_marida.py --prob-sweep --detector cnn --split val \
       --json eval/cnn_prob_sweep_val.json
   ```

   **You can now answer "why 0.40?" with the artefact rather than the
   reasoning.** The answer is that the objectives genuinely conflict: detector
   precision climbs monotonically (0.7825 at 0.20 to 0.9031 at 0.70) while
   region recall peaks at 0.40 (0.7550) and collapses to 0.4989 by 0.70.
   Tuning on precision would have produced the better-looking table and found
   half the debris. Two safeguards are in the tool: `--prob-sweep` **refuses
   `--split test`** (sweeping an objective over the held-out split is how it
   stops being held out), and it warns if the sweep's optimum ever stops
   matching the configured constant, so the code and the table cannot drift.
   Registered in `ghostnet.provenance` with the sweep's own optimum pinned as
   an invariant.
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
