# Evidence traceability — the walk-through

**PRD §12, last acceptance bullet:**

> *Every output in the demo can be traced back to its underlying evidence on
> request (imagery tile, current field, vessel record).*

The console makes two different kinds of claim, and they need two different
traces. Conflating them is the mistake this document exists to prevent.

| Claim | Example | Traces back to |
|---|---|---|
| **About this run** | "Rank 1, priority 0.83, most likely source Demo Kali" | The run artefact's `evidence` refs and `provenance` |
| **About measured quality** | "verification precision 0.238 → 0.623" | A committed `eval/*.json`, via `ghostnet.provenance` |

The second is the one that had no trace until now, and its absence had already
cost twice — a mis-transcribed CNN candidate table, and three FR-2.2 arms quoted
with no committed artefact. Both were found by hand. §2 makes that check
repeatable.

---

## 1. Trace A — a dispatch line back to imagery, current field and vessel record

Every artefact object carries an `evidence` list of typed refs. There are four
kinds, and they are exactly the three the PRD names plus the river table:

| `kind` | `ref` looks like | Produced by |
|---|---|---|
| `sentinel2_tile` | `SYNTHETIC-T44PLT-20260314` | FR-1 detection, FR-2 verification |
| `current_field` | `synthetic-westward` | FR-3 drift, and anything using drift |
| `vessel_record` | `gfw:SYN-SAR-1` | FR-5 dark-vessel correlation |
| `river_table` | `synthetic` | FR-4 source attribution |

### The chain, for one detection

Taking `…-d0001`, the rank-1 site in the committed run:

```
detection  d0001
  evidence  sentinel2_tile SYNTHETIC-T44PLT-20260314
            "acquired 2026-03-14T05:30:00+00:00"
  |
  +-- verification (verified, 5 checks, each with its own reason)
  |     evidence  sentinel2_tile SYNTHETIC-T44PLT-20260314
  |               "25px spectral window at 2026-03-14T05:30"
  |
  +-- backward trajectory        <- FR-3
  |     evidence  current_field synthetic-westward
  |               "48-member RK4 ensemble, 6.0h steps, seed 20260814, sigma 0.25"
  |
  +-- attribution                <- FR-4
  |     evidence  current_field synthetic-westward
  |               river_table synthetic  "3 rivers in the emission ranking"
  |     candidates  Demo Kali p=0.9388 (30.0 km), Demo Creek …
  |
  +-- vessel correlation         <- FR-5
        evidence  vessel_record gfw:SYN-SAR-1
                  "SAR detection at (79.970, 12.120) 2026-03-12, no AIS match"
                  vessel_record gfw:SYN-SAR-2
                  current_field synthetic-westward
```

Every clause of the rationale on screen resolves to one of those lines. "Most
likely source Demo Kali (p=0.94)" is the attribution's top candidate; "2
AIS-silent vessel(s)" is the two `vessel_record` refs; "7-day forward track,
envelope 66 km" is the forward trajectory, which names the current field, the
ensemble size and **the seed** — so the envelope is reproducible, not just
plausible.

### Run-level provenance

`provenance` on the artefact answers "under what conditions":

```
git_commit             dc08257
tile_ids               ['SYNTHETIC-T44PLT-20260314']
fdi_threshold          0.025          <- compared against the benchmark's
min_pixels             3
verification_thresholds  {glint_swir_min: 0.02, …}   <- the fitted values, in full
drift_ensemble_size    48
drift_seed             20260814
inputs_are_synthetic   True           <- rendered on the console's face
```

The console compares `provenance.fdi_threshold` against the threshold the
benchmark was measured at and shows a warning if they differ — so a run computed
at a different threshold cannot be silently described by numbers measured at
another.

### Rejections are traceable too, which is the point of FR-2.3

`…-d0005` is *rejected*. It still carries its `sentinel2_tile` ref and all five
checks with their reasons, including the ones that passed. It has no trajectory,
attribution or vessel correlation — the pipeline runs those downstream of
verification. **That absence is itself traceable**: the Rejected tab shows the
disqualifying check and its reason rather than the detection simply vanishing.

---

## 2. Trace B — a metrics-strip number back to a committed artefact

The strip is where the console makes quality claims, and until now nothing tied
those to the files they came from. `src/ghostnet/provenance.py` declares every
served number against the artefact and JSON pointer behind it:

```bash
python -m ghostnet.provenance
```

It prints each served field with its source and pointer, the artefact
accounting, and a pass/fail. It is also enforced in the suite
(`tests/test_provenance.py`), so a drift fails CI rather than a viva.

**What it asserts:**

1. Every declared field still equals what its artefact records — a mismatch
   names the field, both values and the source file.
2. **No undeclared number reached the wire.** Adding a figure to the report
   without declaring its evidence fails the suite. This is the direction that
   catches an unbacked number.
3. Every `eval/*.json` is accounted for — surfaced, or registered as
   checked-not-surfaced *with the reason*.
4. Unsurfaced artefacts are held to their recorded invariants, so a supporting
   result cannot change unnoticed just because nothing renders it.
5. **The published headline figures are pinned.** See below — this is the one
   that catches a doctored artefact.

### The gap that (1) alone leaves, and how it is closed

Reconciliation compares what the console serves against what the artefact
records — but the console *reads* that artefact, so editing the JSON moves both
sides together and they still agree. That is correct behaviour: the artefact is
the source of truth. It does leave the published figures tamper-blind, and those
are exactly the ones quoted in a report and a viva.

`PUBLISHED` closes it: 18 pins holding the headline numbers `eval/results.md`
and `docs/` actually publish — the FR-2.4 precision pair, both detectors' region
recall, the FR-2.2 before/after, and the paired holdout arms. Nothing is
computed; they are the machine-readable form of *"eval/results.md is the
authority"*. An artefact that stops recording what the report published fails,
naming both values and pointing at the prose. Changing a pin is a deliberate act
that belongs in the same commit as the prose it changes.

### Two things it will not do

It **never re-derives a measured quantity.** `eval/results.md` is the authority;
the check confirms agreement. Where a field is derived (a gain, a missed-region
count), it is verified as an *arithmetic identity over JSON-backed inputs*, and
where the eval script also recorded the delta, against that too.

It **does not treat rounding as agreement.** Direct reads are held to 5e-7. The
one comparison that spans two rounding stages — a derived gain against a
recorded delta — gets 5e-4, documented in the module, because the scripts round
a full-precision delta while the console subtracts two already-rounded values.
That happens exactly once in the committed set: the CNN verification gain is
`0.0799` recorded and `0.7514 − 0.6716 = 0.0798` derived. Both display as
+0.080, so no published claim is affected. **Finding that was the check's first
useful act.**

### Artefact accounting, as it stands

| Artefact | Status |
|---|---|
| `marida_ablation.json` | surfaced — FR-2.4 headline |
| `detector_fdi_test.json` | surfaced — FDI arm |
| `detector_cnn_test.json` | surfaced — CNN arm |
| `multitemporal.json` | surfaced — FR-2.2 headline pair |
| `holdout_18QYF_leaky.json` | surfaced — generalisation, trained arm |
| `holdout_18QYF.json` | surfaced — generalisation, unseen arm |
| `multitemporal_sensitivity_010.json` | checked, not surfaced |
| `multitemporal_18QYF_2020-03.json` | checked, not surfaced |
| `multitemporal_18QYF_2020-11.json` | checked, not surfaced |
| `multitemporal_16PCC_2018-09.json` | checked, not surfaced |

**Why the two holdout files were promoted to surfaced.** The strip already shows
region recall, which is a *within-tile* number — MARIDA splits by patch, so 91%
of test patches sit on tiles the model trained on. Alone it reads as evidence
the detector generalises. That is the same defect `docs/ablation-study.md` §4
was corrected for, and the console had it too. It now shows the paired holdout
beside it: **F1 0.930 → 0.858, −0.072 on an unseen region**, with the wrong-sign
subtraction warned against in the caveats.

**Why the other four are not.** They are supporting or null results already
represented by what is on screen; the full tables live in `eval/results.md` and
`docs/ablation-study.md` §5. The sensitivity arm is the strongest candidate to
promote next — it would turn the "blocked on FR-3.1" caveat from an assertion
into a number. All four are still checked against their recorded invariants.

---

## 3. The viva walk-through

The sequence to actually be walked through, roughly seven minutes.

**1 — Open the console. Read the framing first.**
The header says *research prototype*, and the run picker says **Synthetic run**.
Say so before anything else: these inputs are generated. The point of the demo
is the *path*, and the path is identical for real inputs.

**2 — Pick rank 1 from the dispatch list.**
Read the rationale aloud. Every clause is a claim to be traced.

**3 — Open the evidence trail. Trace the imagery.**
`sentinel2_tile SYNTHETIC-T44PLT-20260314`, with the acquisition time. On a real
run this is the MGRS tile ID and the L2A product the detection came from.

**4 — Trace the verification.** Five checks, each with a reason, including those
that passed. This is FR-2.3: a verified detection says *what it survived*.

**5 — Trace the drift.** `current_field synthetic-westward`, and with it the
ensemble size, step, sigma and **seed**. Ask "could you reproduce this
envelope?" — yes, and the seed is why.

**6 — Trace the source and the vessels.** `river_table` gives the ranked
candidates with probabilities, not one confident claim. `vessel_record` gives
two SAR IDs with positions, times and "no AIS match within tolerance", carrying
the disclaimer that this is an investigation signal, never an accusation.

**7 — Switch to the Rejected tab.** Four detections that did not survive, each
with the check that disqualified it. This is the Verification Agent's measured
contribution made visible — and it is the thing the interface leads with rather
than hides.

**8 — Now the other kind of claim. Expand the metrics strip.**
Precision 0.238 → 0.623, region recall 0.407, the unseen-region cost −0.072, the
FR-2.2 negative. Note these are labelled *MARIDA test — not this run*.

**9 — Ask where those numbers come from, and run the check.**

```bash
python -m ghostnet.provenance
```

Every figure, its artefact and its JSON pointer; the artefact accounting; and
*PASS — every served number traces to a committed artefact.*

**10 — Then break it on purpose.** Edit `region_recall` in
`eval/detector_cnn_test.json` and re-run:

```
numbers that disagree with their evidence: 1
  - eval/detector_cnn_test.json:region_recall: console serves 0.95,
    eval/results.md (published) records 0.7034 — the artefact no longer records
    the published figure.
FAIL
```

A check that cannot be made to fail proves nothing. Worth saying which guard
caught it: reconciliation alone would *not* have, because the console reads that
same file — it is the published-figure pin that fires. That distinction is the
honest answer if an evaluator pushes on it.

---

## 4. Where this stops, honestly

- **The run is synthetic** and says so — in `provenance.inputs_are_synthetic`, in
  the run picker, and in the header. A real artefact is blocked on datasets
  nobody has downloaded (`EARTHDATA_TOKEN`, `GFW_API_TOKEN`, Protected Planet,
  the river table), not on any of this code. When one exists, the refs point at
  real MGRS tiles, a real OSCAR field and real GFW SAR records — **the schema and
  the trace do not change**.
- **A ref is an identifier, not the pixels.** The trace resolves to "which tile,
  acquired when, what window" — enough to go and re-read the source. The console
  deliberately carries no imagery; that constraint is what makes it deployable
  at all (PRD §9.1).
- **Trace B covers the metrics strip**, which is where the console makes quality
  claims. Prose in `eval/results.md` and `docs/` is not machine-checked against
  the JSON; that reconciliation is still done by hand, and it is how the two
  known defects were found.
