# Ablation study — how much each agent is worth

**Status: DRAFT.** Synthesis for the PRD §12 acceptance bullet:

> *An ablation study exists showing pipeline output degrades in a specific,
> explainable way when each agent is individually removed.*

This document is prose over numbers that live elsewhere. Nothing here is
re-measured — it is assembled from runs already recorded in
[`eval/results.md`](../eval/results.md) and the machine-readable
`eval/*.json` beside it.

**Every figure in this document was cross-checked against the committed JSON
artefacts, not transcribed from prose.** That is the MACHINE-WORKFLOW.md rule —
no number is quoted that cannot be derived and defended. Two things did not
reconcile; both are flagged in place (§4.1, §5.1) rather than silently carried
forward.

---

## 1. What is actually measured, and what is not

The PRD §7 design test is that **removing any one agent should break the system,
not merely degrade it slightly.** That test can only be applied where there is a
measurement. Current state:

| Agent | Contribution measured? | On what data |
|---|---|---|
| Detection (FR-1), incl. CNN variant (FR-1.4) | **Yes** | Held-out MARIDA test/val |
| False-Positive Verification (FR-2), spectral checks (FR-2.4) | **Yes** | Held-out MARIDA test/val |
| Verification — multi-temporal check (FR-2.2) | **Yes — negative** | Real Sentinel-2 L2A repeat passes |
| Drift (FR-3) | No | Buoy ground truth downloaded; no current field yet |
| Source Attribution (FR-4) | No | Blocked on the river table |
| Dark Vessel Correlation (FR-5) | No | Blocked on `GFW_API_TOKEN` |
| Response Prioritisation (FR-6) | Structure only | `run_ablation_study()` runs, synthetic inputs only |

So the study is **complete for the detection/verification half of the pipeline
and provisional for the rest.** The gap is not code — every reader is written
and `run_ablation_study()` executes end to end — it is data: OSCAR currents and
GFW detections need free-tier credentials nobody has created, and Protected
Planet plus the river table need downloading and clipping. Ownership and the
current blocker list are in
[`MACHINE-WORKFLOW.md`](../MACHINE-WORKFLOW.md).

The honest one-line summary for the viva: **two agents are proven load-bearing
on real data; a third is proven to be inert *today* and why; the remaining
three have a working ablation harness but only synthetic numbers.**

---

## 2. Method

### 2.1 How ablation works in the pipeline

The six agents run as a **linear LangGraph**
(`detection → verification → drift → attribution → vessels → prioritisation`,
[`src/ghostnet/pipeline.py`](../src/ghostnet/pipeline.py)). Linear is
deliberate: the dependencies genuinely are sequential (attribution needs the
backward trajectory; prioritisation needs everything), so removing one node
leaves a **visible, explainable hole** downstream rather than a silently
rerouted path.

`PipelineConfig.ablate` names agents to disable. An ablated node **does not
vanish** — it runs a stub that records *why* its output is absent, and each
downstream node records how it degraded as a result. `run_ablation_study()`
returns `{"full": run, "without_detection": run, …}`, one run per agent removed.
The graph topology never changes between arms, so a difference in output is a
difference in **agent behaviour**, not in wiring.

Two scoring rules matter for reading the results:

- **A missing dataset degrades the run, it never crashes it** — the run
  completes and its `degradations` list carries the `fetch_data.py` command that
  would fix it.
- **A signal that cannot be measured is dropped and its weight redistributed,
  never scored zero.** Scoring an absent ecological-risk signal as 0 would
  silently mark every site as safe; instead FR-6.1's weight is spread over the
  signals that are present and the plan is flagged provisional.

### 2.2 Threshold calibration (so the baseline is not a strawman)

Every threshold started as a literature-informed value. For the FR-2.4 result
they were then **fitted on the train split only**, detector first — maximising
the *baseline detector's own* F1 — and then the verification thresholds by
coordinate descent with the detector held fixed. Fitting the baseline first
matters: it means the verification gain reported below is measured against the
best the spectral index can do, not against a deliberately weak one. Literature
values are retained in code (`LITERATURE_THRESHOLDS`, `LITERATURE_FDI_THRESHOLD`)
so the "before" arm stays reproducible.

---

## 3. Result — Verification Agent, spectral checks (FR-2.4)

**The headline ablation.** MARIDA test split, held out, thresholds fitted on
train only. 359 patches → 6074 detections, 336 carrying a label and scored.

| Configuration | Precision | Recall | F1 |
|---|---|---|---|
| Baseline detector (FDI only) | 0.238 | 1.000 | 0.385 |
| + Verification, **unfitted** thresholds | 0.258 | 0.775 | 0.388 |
| + Verification, **fitted** thresholds | **0.623** | 0.950 | **0.753** |

**Precision 0.238 → 0.623 (+0.385), F1 0.385 → 0.753 (+0.368), for 5 points of
recall.** False-positive rate falls 0.762 → 0.377. Confirmed on a second
held-out split (val): precision 0.535 → 0.767.

Two secondary findings worth stating:

1. **The uncalibrated agent was worth almost nothing** — +0.003 F1 on test — and
   was *actively harmful* on val (F1 0.697 → 0.648). Reporting the agent without
   fitting it would have made a load-bearing component look useless. This is why
   §2.2 exists.
2. **Recall over scored candidates is 1.0 for the baseline by construction** —
   it selects every candidate it emitted. So this table cannot show what the
   detector *misses*; that is region recall (§4), and the two must always be
   quoted together.

### 3.1 What the agent actually rejects

Not a uniform confidence haircut — it rejects specific, named things. MARIDA
test split, fitted thresholds:

| MARIDA truth class | Candidates | Rejected | Rate |
|---|---|---|---|
| Clouds | 73 | 67 | 91.8% |
| Turbid Water | 39 | 39 | 100% |
| Waves | 47 | 40 | 85.1% |
| Ship | 38 | 28 | 73.7% |
| Sparse Sargassum | 24 | 16 | 66.7% |
| Dense Sargassum | 9 | 9 | 100% |
| Foam | 4 | 4 | 100% |
| **Marine Debris (false rejection)** | **80** | **4** | **5.0%** |

The agent removes 90–100% of clouds, turbid water, foam and dense Sargassum
while wrongly rejecting 5% of true debris. This per-class breakdown is what
makes the contribution defensible rather than a black-box score drop.

### 3.2 Caveats

- **Only 3 of the 5 verification checks are exercisable on MARIDA.** Patches
  carry no acquisition geometry and no repeat passes, so the spectral checks
  disqualify on signature but cannot *name* sun glint specifically, and the
  multi-temporal check (FR-2.2) is inconclusive throughout — measured separately
  in §5.
- **Sparse annotation.** MARIDA labels ~0.9% of pixels; 5738 of 6074 detections
  land on unlabelled pixels and are excluded, never assumed wrong.
- **Three of seven fitted values landed on a grid edge.** The true optimum may
  lie outside the search range.
- Fitted on MARIDA's 12 global regions, not on the Gulf of Honduras alone —
  though the demo AOI overlaps MARIDA's 16PCC annotations.

---

## 4. Result — CNN detector (FR-1.4) and the subsumption finding

The FDI baseline's weak number is **region recall** — the fraction of annotated
debris regions any detection lands on. It is purely the detector; verification
does not touch it.

| | FDI baseline | CNN (FR-1.4) |
|---|---|---|
| Candidates emitted | 6074 | **795** |
| Detector precision | 0.238 | **0.672** |
| Detector F1 | 0.385 | **0.804** |
| + Verification precision | 0.623 | **0.751** |
| **Region recall** | **0.407** (96/236) | **0.703** (166/236) |

**Region recall 0.407 → 0.703 (+0.296)**, while emitting **7.6× fewer
candidates**. The FDI misses ~59% of annotated debris regions; the CNN misses
~30%. This is the number FR-1.4 existed to move.

### 4.1 The finding that matters for §12: the CNN substantially subsumes the Verification Agent

The false positives largely stop being *generated* rather than being *filtered
out later*. Candidates by truth class, test split — **read from
`eval/detector_fdi_test.json` and `eval/detector_cnn_test.json`**:

| Truth class | FDI candidates | CNN candidates |
|---|---|---|
| Marine Debris | 80 | **137** |
| Clouds | 73 | **1** |
| Waves | 47 | 25 |
| Turbid Water | 39 | **0** |
| Ship | 38 | 13 |
| Sparse + Dense Sargassum | 33 | **0** |
| Foam | 4 | **0** |

Training multi-class (rather than debris-vs-rest) is why: MARIDA separately
labels the exact confusers the Verification Agent has to rule out, so the
network learns them as their own classes instead of inheriting the index's
confusion.

> **Discrepancy — `eval/results.md` needs a correction here.** The equivalent
> table in `eval/results.md` gives the CNN column as Marine Debris 112, Waves 19
> and Ship 12. The committed JSON gives 137, 25 and 13. The JSON is the
> self-consistent artefact: its per-class candidate counts sum to exactly 204,
> which is its own `n_labelled`, whereas the prose figures do not. Every *other*
> CNN number in `eval/results.md` — region recall 0.7034, detector precision
> 0.6716, F1 0.8035, the +0.0799 verification delta — reconciles exactly, so
> this looks like a mis-transcription of one table rather than a bad run. The
> numbers above are the JSON's. Owner of that section should confirm and correct
> `eval/results.md` (see §9).

The consequence for the design test:

| Detector | Verification precision gain | Verification F1 gain |
|---|---|---|
| FDI | **+0.385** | +0.368 |
| CNN | **+0.080** | +0.035 |

**Verification is load-bearing for the spectral baseline and becomes a smaller
safety net once a learned detector has already excluded most confusers.** It
still adds precision (+0.080), still rejects 73.7% of waves, still catches the
one cloud that survives — but over the CNN it is no longer the difference
between usable and unusable output. Both numbers must be quoted; quoting +0.385
alone once the CNN is the detector overstates the agent.

This is a genuine overlap between two agents, reported rather than hidden. It
does not fail the §12 criterion — removing verification over the CNN still
degrades precision measurably — but it qualifies how the criterion is met.

---

## 5. Result — multi-temporal consistency (FR-2.2): a measured *dependency*, not a contribution

This is the recorded exception to the §12 "removing any agent breaks the system"
criterion. Run on real Sentinel-2 L2A repeat passes (MARIDA patches carry none),
two acquisitions streamed onto one fixed grid with masks rasterised for ground
truth.

| Repeat pair | Candidates | Labelled | ΔPrecision | ΔRecall | ΔF1 | True debris lost |
|---|---|---|---|---|---|---|
| 16PCC 2020-09-18 → 09-23 | 144 | 12 | +0.000 | **−0.250** | **−0.167** | **1** |
| 18QYF 2020-03-14 → 03-19 | 21 | 7 | 0.000 | 0.000 | 0.000 | 0 |
| 18QYF 2020-11-29 → 12-04 | 22 | 0 | — | — | — | 0 |
| 16PCC 2018-09-14 → 09-19 | 0 | 0 | — | — | — | — |

**On the one pair where the check acted, it removed a true detection and no
false positive.** Deltas are measured on top of the four spectral checks, so
they isolate what multi-temporal adds.

### 5.1 Provenance — only the first row is reproducible from a committed artefact

`eval/multitemporal.json` holds **one pair only** (16PCC 2020-09-18 → 09-23, at
`current_speed_ms: null`) and it verifies exactly: 144 candidates, 12 labelled,
spectral-only F1 0.5000 → with-multi-temporal F1 0.3333, 144 re-observed, 0
transient, 6 incoherent-motion rejections, 1 true debris lost.

The other three pairs and the 0.10 m/s sensitivity row exist in
`eval/results.md` but **were not saved to a committed JSON** —
`scripts/eval_multitemporal.py` takes `--tile/--date-a/--date-b` and
`--current-speed-ms` and writes whichever run it was last given, so the extra
arms were run and their output overwritten. They are not fabricated, but they
cannot currently be re-derived without re-running on the workstation (needs
MARIDA and L2A access).

This does not change the conclusion — the headline pair is the only one where
the check acted at all, and it is the one that *is* reproducible. But the
supporting arms should be re-run to per-arm JSON files before they go in the
report. Logged in §9.

Three reasons, only one of them the check's own fault:

1. **Structurally blocked on the Drift Agent (FR-3).** `check_persistence`
   allows a displacement of `current_speed × Δt + 5 km`. With no OSCAR field
   loaded, `current_speed` is `None` and the envelope collapses to the 5 km
   floor — while real debris at 0.1 m/s covers ~43 km in the 5 days between
   passes. The check therefore calls genuine drift "incoherent motion".
   Sensitivity analysis:

   | Assumed current | Incoherent rejections | True debris lost | ΔF1 |
   |---|---|---|---|
   | none (5 km envelope) | 6 | 1 | −0.167 |
   | 0.10 m/s (assumed) | **0** | **0** | 0.000 |

   Every false rejection disappears once the envelope is realistic. The
   0.10 m/s figure is an assumption for the sensitivity check only, not a
   result.
2. **Zero transients in every pair.** "Appears once and vanishes" is the
   check's strongest signal, and it never fired: repeats are paired by nearest
   neighbour, and with 9–130 candidates in an AOI something is always within
   range (144/144, 21/21, 22/22 "re-observed"). Proximity cannot separate *this
   patch persisting* from *some other detection existing nearby*. A defensible
   implementation needs identity-preserving matching — drift-predicted position
   plus a spectral-similarity gate.
3. **Tiny samples** — 12 and 7 labelled candidates on the two usable pairs.
   None of these deltas would survive a significance test.

**For the report:** on current evidence, removing multi-temporal verification
would not degrade the pipeline — it would slightly improve recall. State this
plainly. The check is sound in principle and standard in the literature; it is
inert here because the current field it depends on does not exist yet. Quote
FR-2.2 as a **measured dependency on FR-3.1**, never as a verification
contribution.

---

## 6. The PRD §7 design test, agent by agent

"Removing any one agent should break the system, not merely degrade it." Where
there is no real-data measurement, the column reports the **degradation the
pipeline records** on synthetic inputs — which names the lost capability but
does not quantify it.

| Agent | Evidence | Remove it and… | Verdict |
|---|---|---|---|
| **Detection (FR-1)** | Real (MARIDA) | No candidates enter the pipeline; every downstream agent has nothing to act on. Region recall is the detector's own measured weakness (0.407 FDI → 0.703 CNN). | **Breaks** — it is the only data source. |
| **Verification (FR-2), spectral** | Real (MARIDA) | Over the FDI: precision 0.623 → 0.238, F1 0.753 → 0.385; sun glint, foam, kelp and cloud shadow re-enter and drift/attribution/dispatch run on non-debris. Over the CNN: precision −0.080. | **Breaks over the spectral baseline; degrades over the CNN.** |
| **Verification — multi-temporal (FR-2.2)** | Real (L2A repeats) | Nothing degrades; recall slightly improves. | **Does not break today** — measured dependency on FR-3, see §5. |
| **Drift (FR-3)** | Synthetic only | Source attribution has no backtrack to cross-reference (FR-4.1 cannot run at all); prioritisation loses its drift-urgency term, so the plan can no longer say a patch is heading for a protected area. Buoy ground truth is downloaded (226 drifters, 10 401 obs, 1980–2025) but there is no current field to predict with. | **Expected to break attribution; degrade prioritisation.** Not yet quantified. |
| **Source Attribution (FR-4)** | Synthetic only | The plan can say where debris is going but not where it came from; the emission-source findings the marine-researcher persona needs (PRD §6) are gone. | **Expected to degrade** (removes a capability, not the ranking). Not yet quantified. |
| **Dark Vessel Correlation (FR-5)** | Synthetic only | The ghost-gear signal that distinguishes abandoned fishing gear from generic river-borne plastic is absent from the ranking. | **Expected to degrade.** Not yet quantified. |
| **Response Prioritisation (FR-6)** | Synthetic only | The operator is handed an unordered pile of verified detections and must decide unaided — which is precisely the pre-existing state of the art this project exists to improve on (PRD §2). | **Breaks the product** (there is no plan), by construction. Not yet quantified on real data. |

The two verdicts backed by real numbers — Detection breaks, Verification breaks
over the FDI — carry the §12 argument. The rest are structurally sound and the
harness is in place; they are pending data, not pending design.

---

## 7. Not yet measured, and the specific blocker

| Item | Blocked on | Owner (MACHINE-WORKFLOW.md) |
|---|---|---|
| FR-2.2 re-measurement with a real current field | `EARTHDATA_TOKEN` → OSCAR download | Ashwin / whoever holds MARIDA |
| FR-3 drift accuracy vs Global Drifter Program | `EARTHDATA_TOKEN` → OSCAR (buoys already downloaded) | A |
| FR-4 source attribution vs published rankings | river-table download + `build_region_extracts.py` | A |
| FR-5 dark-vessel correlation vs GFW case studies | `GFW_API_TOKEN` | B |
| FR-6.1 ecological-risk scoring | Protected Planet download + clip | B |
| System-level ablation on real inputs | all of the above (a real run artefact) | — |
| End-to-end demo latency | a real end-to-end run | — |

None of these need a GPU. The drift validation also carries two coverage
constraints already measured (`eval/results.md`): no drifter passed through the
Gulf of Honduras bbox during the 2018 demo window, so the validation cannot be
contemporaneous with the demo run; and the usable sample is western-Caribbean at
a 300 km buffer, which must be quoted alongside the result.

---

## 8. Reproduce

```bash
# FR-2.4 headline ablation (fits thresholds on train, scores held-out test)
python scripts/eval_marida.py --fit --split test --json eval/marida_ablation.json

# FR-1.4 detector comparison
python scripts/train_cnn.py
python scripts/eval_marida.py --split test --detector fdi --json eval/detector_fdi_test.json
python scripts/eval_marida.py --split test --detector cnn --json eval/detector_cnn_test.json

# FR-2.2 multi-temporal consistency — DEFAULT PAIR ONLY (see §5.1).
# The other three pairs and the sensitivity arm need explicit flags and
# their own output files, e.g.:
python scripts/eval_multitemporal.py --json eval/multitemporal.json
python scripts/eval_multitemporal.py --tile 18QYF --date-a 2020-03-14 \
    --date-b 2020-03-19 --json eval/multitemporal_18QYF_march.json
python scripts/eval_multitemporal.py --current-speed-ms 0.10 \
    --json eval/multitemporal_sensitivity_010.json
```

All three eval scripts are **workstation-only** — they need MARIDA and, for the
multi-temporal harness, streamed L2A imagery. Neither is present on the MacBook
Air by the sync rules, so this document was assembled by reading the committed
JSON, not by re-running anything.

The system-level ablation harness (`ghostnet.pipeline.run_ablation_study`) runs
today on synthetic inputs via `python scripts/run_pipeline_demo.py --ablation`;
its numbers are illustrative and must not be quoted as results.

---

## 9. Corrections and follow-ups this write-up surfaced

Raised by cross-checking every quoted figure against `eval/*.json`. Neither is
mine to fix — both touch `eval/results.md` sections owned elsewhere and one
needs a workstation re-run.

1. **`eval/results.md` CNN candidate-class table is wrong in three cells**
   (§4.1). Prose says Marine Debris 112 / Waves 19 / Ship 12; committed JSON
   says 137 / 25 / 13, and the JSON sums to its own `n_labelled` of 204 while
   the prose does not. Every other CNN figure reconciles. Most likely a
   mis-transcription of one table. **Action:** confirm against
   `eval/detector_cnn_test.json` and correct the prose — no re-run needed.
2. **FR-2.2's supporting arms have no committed artefact** (§5.1). Three of the
   four repeat pairs and the 0.10 m/s sensitivity row cannot be re-derived;
   `eval/multitemporal.json` holds only the default pair. **Action:** on the
   workstation, re-run each arm to its own `--json` path so the four-pair table
   and the sensitivity analysis become reproducible before the report quotes
   them.

Neither weakens a headline result. The FR-2.4 verification ablation and the
FR-1.4 region-recall figures — the two numbers the project leads with —
reconcile exactly against the JSON, including the full per-failure-mode
rejection table in §3.1.
