# Report outline — what is evidence-backed, and what still has to be written

A section-by-section plan for the final report, marking for each: **what
evidence already exists**, and **what a person still has to write**. The split
matters, because roughly half this report can be assembled from committed
artefacts and the other half cannot be assembled at all.

Status key: **[E]** evidence exists and is committed · **[W]** must be written
by a person · **[B]** blocked on data nobody has downloaded.

Source material: [`ablation-study.md`](ablation-study.md) is the results
narrative, [`viva-pack.md`](viva-pack.md) the defence and the do-not-claim list,
[`evidence-traceability.md`](evidence-traceability.md) the provenance argument,
and `eval/results.md` the authority for every number.

---

## 1. Introduction and problem statement — **[W]**

PRD §1–2 has the framing: detection from Sentinel-2 is a mature area, and the
unbuilt layer is everything *after* detection. Nothing here needs measurement;
it needs writing, plus citations the team must gather.

The one sentence that must survive from the PRD: this is a **decision-support
research prototype validated on historical and published data**, not an
operational tool. PRD §8 makes that a requirement, and it has to hold in the
report as much as in the UI.

## 2. Related work — **[W]**

Entirely to be written. The claim to support is the PRD §1.3 one: over 100
published studies since 2020 on detection, and comparatively little on
verification, attribution or response. The team should be able to name the
FDI's origin and the MARIDA paper at minimum.

**Do not** let this section imply the project competes with the detection
literature. It builds a pipeline *after* detection; the detector is a means.

## 3. Requirements and scope — **[E]**

Lift from PRD §5–8, which is already precise about in-scope, out-of-scope and
the non-functional requirements. Two decisions worth reproducing with their
reasoning, because both were made on measured evidence rather than preference:

- **Demo region: Gulf of Honduras (Río Motagua).** Chosen from MARIDA on the
  workstation, not from a literature guess. Four reasons, three measured — see
  PRD §14 Q1 and `config/regions.yaml`, which also keeps the rejected
  alternatives so the decision stays auditable.
- **Deployed web app** as the operator output — PRD §9.1, including the
  constraint that drives the whole architecture: **the data cannot be
  deployed.**

## 4. System architecture — **[E]**

Six agents, linear LangGraph. `src/ghostnet/pipeline.py`'s module docstring
explains *why* linear: the dependencies genuinely are sequential, and a linear
graph makes the ablation mean something — removing a node leaves a visible hole
rather than a silently rerouted path.

Worth a subsection: **ablation is a first-class feature, not a test hook.** An
ablated node still runs and records why its output is absent, and each
downstream node records how it degraded. That design decision is what makes
§7 possible.

Also reproduce the two scoring rules, both of which prevent a specific wrong
answer:
- a missing dataset **degrades** the run and names the fix; it never crashes and
  never silently proceeds;
- an unmeasurable signal is **dropped and its weight redistributed**, never
  scored zero — scoring zero would quietly mark every site as ecologically safe.

## 5. Implementation — **[E]** with **[W]** framing

Per agent, from the source. The parts worth writing up rather than listing:

- **Ingestion.** Streams L2A from Planetary Computer's STAC API anonymously —
  no credential, no local archive. Four documented traps handled, including the
  processing-baseline offset (latent: it bites whoever first picks a post-2022
  window) and that scene cloud cover is not AOI cloud cover.
- **Detector.** FDI baseline plus the CNN variant: plain 4-level U-Net, 7.77 M
  parameters, 11 bands → 16 classes, written in plain PyTorch. The dependency
  decision is defensible and should be stated: `segmentation-models-pytorch`
  and `torchvision` pin against released torch ABIs, and the only GPU in the
  project runs a nightly build carrying `sm_120` kernels for the RTX 5070.
- **Verification.** Five checks. Two were renamed for the *signature* they
  measure rather than one of its causes, after fitting showed them firing well
  outside their named modes — decisions were right, labels were wrong.
- **Console.** PRD §9.1's split: workstation exports a run artefact, the server
  recomputes prioritisation live and generates rationales, the browser renders
  evidence.

## 6. Evaluation methodology — **[E]**

The section that earns the results. Three things to make explicit:

1. **Threshold calibration.** Fitted on train only, detector first — maximising
   the *baseline's own* F1, so the ablation is not measured against a strawman.
   Literature values are retained in code so the "before" arm stays
   reproducible; restoring them fixed a bug where re-running would have compared
   the calibrated agent against itself and reported a delta of zero.
2. **Sparse annotation.** MARIDA labels ~1% of pixels. Unlabelled candidates are
   **excluded, never assumed negative** — 5738 of 6074 on test. Say so, and say
   why region recall is the more robust number.
3. **Held-out discipline.** Val selected the epoch and the probability
   threshold, so val is optimistic by construction; test was touched once, after
   both were fixed. Quote test.

## 7. Results — **[E]**

`docs/ablation-study.md` is this chapter in draft. Order it so the honest
framing survives:

1. FR-2.4 verification ablation — precision 0.238 → 0.623, F1 0.385 → 0.753,
   with the per-failure-mode table that makes it defensible rather than a
   confidence haircut.
2. FR-1.4 detector — region recall 0.407 → 0.703 at 7.6× fewer candidates,
   **flagged as within-tile**.
3. The subsumption finding — +0.385 over FDI, +0.080 over CNN. Both, always.
4. Geographic generalisation — −0.072 F1 on an unseen region, almost all recall,
   with the wrong-sign subtraction warned against explicitly.
5. FR-2.2 — the measured negative, as a dependency on FR-3.1.

Every figure in that document is checked against a committed artefact. Keep that
property: `viva-pack.md` §6 lists the two figures that are *not* yet artefact-
backed, and neither should be quoted as though it were.

## 8. Discussion — **[W]**

The interesting material is the negative results, and a report that leads with
them reads as more competent, not less:

- **A learned detector subsumes a hand-built verification stage.** Measured, not
  asserted. It qualifies the multi-agent premise honestly.
- **An agent can be inert because a *different* agent is missing.** FR-2.2 is
  sound in principle and standard in the literature; it is dead here because its
  current field does not exist. That is a statement about dependency structure.
- **Calibration decided whether a component looked useful at all.** Unfitted,
  verification was worth +0.003 F1 and was harmful on val.
- **A benchmark's split strategy can flatter a result.** MARIDA splits by patch,
  so 91% of test patches share tiles with train.

## 9. Limitations — **[W]**, informed by **[B]**

Take the do-not-claim list in `viva-pack.md` §4 wholesale. The honest summary:
detection and verification are measured on real data; drift, attribution and
dark-vessel correlation are implemented but unmeasured; no end-to-end run on
real inputs exists. The blocker is **two free-tier signups and two downloads**,
not code.

## 10. Conclusion and future work — **[W]**

Future work is unusually concrete here, because it is enumerated with owners and
blockers in `MACHINE-WORKFLOW.md` and `ablation-study.md` §7. The first item is
not research: obtain `EARTHDATA_TOKEN` and `GFW_API_TOKEN`.

---

## Appendices

| | Status | Source |
|---|---|---|
| A — Full measured results | **[E]** | `eval/results.md`, verbatim |
| B — Evidence traceability | **[E]** | `docs/evidence-traceability.md` |
| C — Reproduction commands | **[E]** | `ablation-study.md` §8 |
| D — Machine split and workflow | **[E]** | `MACHINE-WORKFLOW.md` |
| E — PRD | **[E]** | `PRD.md` |

---

## What this outline deliberately does not do

It does not draft §1, §2, §8 or §10. Those need a person's argument, and the
governing rule applies to prose as much as to figures: **no claim reaches the
report that the person writing it cannot defend.** A generated related-work
section would fail that test on contact with the first question.
