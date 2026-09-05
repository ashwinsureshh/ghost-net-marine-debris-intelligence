# Console redesign brief — for an external design tool

**Scope: visual only.** You are restyling an operator console that is already
functionally complete and whose numbers are load-bearing. Everything in §3 is a
correctness constraint, not a style preference — each one is enforced by a test
that will fail if the redesign breaks it.

Read §3 before writing any markup.

---

## 1. What this is

A marine-debris response console. Satellite imagery is screened for floating
debris and ghost fishing nets; candidate detections are verified against
false-positive modes (cloud, sun glint, foam, Sargassum), drift-modelled, traced
to likely river sources, and ranked into a capacity-constrained dispatch plan
that a vessel operator acts on.

It is an academic project under assessment. Its evaluators are marine-science
and ML assessors who will interrogate every number on screen. **The console's
job is to be honest about what the system does and does not do**, and much of
its current design exists to stop it overstating results. That is what you are
restyling around.

## 2. What you may and may not touch

| | |
|---|---|
| **Yours** | `frontend/src/index.css` (191 lines), `frontend/src/components/*.tsx`, `frontend/src/components/ui/*`, `frontend/index.html` |
| **Not yours** | `src/ghostnet/**` — the Python backend and the API payload shape |
| **Not yours** | `eval/*.json`, `eval/results.md` — the measured results and their authority |
| **Not yours** | Any test under `tests/` |

The seven components: `Header`, `MetricsStrip`, `MapView`, `DispatchPanel`,
`RejectedPanel`, `EvidencePanel`, `ControlPanel`.

`src/ghostnet/benchmark.py` deliberately **reads and reshapes** rather than
computing — a second implementation of the arithmetic could disagree with
`eval/results.md`, which is the authority. Do not move any calculation into the
frontend for convenience.

## 3. Invariants — the redesign is wrong if any of these break

These are not preferences. Each is a claim the console makes truthfully today
and could easily be made to make falsely by a purely visual change.

### 3.1 Two numbers must always appear together, at equal weight

The headline is **verification precision 0.238 → 0.623 (+0.385)**. On its own it
reads as "this system works". It is conditioned on candidates the detector
emitted, so baseline recall is 1.0 *by construction*. The number that corrects
it is **detector region recall 0.407 — it misses 140 of 236 annotated debris
regions.**

They are currently rendered at the same size, in the same row. Do not put region
recall behind a "show more", in a smaller type scale, in a muted colour, or
below the fold. The endpoint is tested to refuse to serve one without the other.

> Guarded by `test_benchmark_never_serves_the_gain_without_the_region_recall`

### 3.2 One pairing must never appear on screen

The generalisation experiment produced a holdout model scored two ways. Showing
its **18QYF score (F1 0.8581)** beside its **rest-of-test score (F1 0.6637)** as
a before/after is invalid: 18QYF carries 13.24 debris px/patch against 0.98 for
the rest of test, so that pairing measures *task difficulty*, not distribution
shift — and it comes out backwards, making the unseen region look easier.

Only the paired table over identical patches is meaningful:

| 84 identical 18QYF patches | F1 |
|---|---|
| `detector_v1` — trained on 18QYF | 0.9304 |
| holdout — never saw 18QYF | 0.8581 |
| cost of the region being unseen | **−0.072** |

Do not introduce a layout that invites the reader to compute the bad
subtraction — e.g. putting both scores adjacent in a summary row.

> Guarded by `test_benchmark_never_serves_the_pairing_that_reads_backwards`
> and `test_the_generalisation_caveats_warn_off_the_bad_pairing`

### 3.3 Region recall 0.703 must always carry "within-tile"

MARIDA splits by patch, not tile: 327 of 359 test patches (91%) sit on tiles the
model trained on. The CNN's 0.703 is therefore a within-tile number and is not
evidence of generalisation. Wherever 0.703 appears, that qualifier appears.

### 3.4 The shipped detector is `detector_v1`, not the holdout model

The generalisation figures come from an experiment checkpoint that is not
committed and never ran the pipeline. Nothing on screen may suggest the run was
produced by it.

> Guarded by `test_the_console_never_implies_the_holdout_model_is_the_shipped_detector`

### 3.5 Negative results stay visually prominent

Two findings are deliberately warning-toned and must stay that way:

- **FR-2.2 multi-temporal consistency contributes nothing.** It is a measured
  negative, reported as such rather than hidden.
- **The CNN substantially subsumes the verification agent** — its contribution
  falls from +0.385 over the spectral baseline to +0.080 over the CNN.

A redesign that harmonises these into neutral body text destroys the point of
showing them.

> Guarded by `test_benchmark_warns_that_the_cnn_subsumes_verification`

### 3.6 Synthetic runs must say so on their face

The current artefact is synthetic. The console states this. Do not demote the
badge to a tooltip or an icon without text.

> Guarded by `test_a_synthetic_run_says_so_on_the_plan`

### 3.7 Rounding is half-up, deliberately

```ts
const f3 = (v: number) => (Math.round(v * 1000) / 1000).toFixed(3);
```

**Do not replace this with `toFixed(3)`.** The verified F1 is 0.7525, whose
nearest double sits just below the true value, so `toFixed` renders **0.752**
while the report says **0.753**. That mismatch was a real bug, found in the
browser. All ten displayed figures currently match `eval/results.md` exactly.

## 4. Known constraints that will bite a redesign

1. **Leaflet z-index.** The map assigns its panes z-index 400–800 and its
   controls up to 1000. Tailwind's `z-50` is 50. Any overlay, modal or dropdown
   must clear Leaflet explicitly — the approval modal once rendered *behind* the
   map.
2. **Do not re-fit the map on selection.** Selecting a site used to re-frame the
   map to the drift envelope, yanking the view and losing the sites being
   compared. The map frames once per run, on detections and MPAs only.
3. **375px is a hard floor.** The dispatch list once collapsed to zero height
   there. The metrics strip must **wrap, not scroll horizontally** — a scrolling
   row pushed region recall off the right edge below ~1000px, which is precisely
   the number §3.1 says must never be hidden.
4. **Basemap tiles must degrade gracefully.** Three failed tiles and the map
   falls back to a graticule, keeping every marker, track and MPA. Venue wifi is
   assumed hostile.
5. **Fonts are self-hosted via fontsource, not a CDN.** There is an offline
   export that must render with no network. Do not introduce a font `<link>`.
6. **Dark and light both ship.** Theming is CSS variables on `:root` + `.dark`,
   shadcn-style, with cva variants and no hardcoded palette values.

## 5. Acceptance — how we know the redesign is safe

From the repo root:

```bash
python -m pytest
python -m ruff check .
```

From `frontend/`:

```bash
npm run lint     # tsc --noEmit
npm run build    # tsc -b && vite build
```

**All four must pass, and the pytest count must not drop.** A failure in
`tests/test_webapp.py` or `tests/test_benchmark.py` means the redesign broke an
honesty invariant in §3 — that is the guardrail doing its job, not a flaky test.
Fix the markup, never the test.

Then check by eye, in the browser, both themes, at 1440px and 375px:

- Precision gain and region recall are the same size, in the same row, both visible without interaction
- 0.703 is labelled within-tile
- The FR-2.2 and subsumption notes still read as warnings
- The synthetic badge is legible text
- Ten displayed figures still match `eval/results.md`

## 6. Working agreement

Work on a branch, not `main`:

```bash
git checkout -b console-redesign
```

Do not commit anything under `data/` or `models/`. Do not modify
`MACHINE-WORKFLOW.md`'s Status Log — that file is the cross-machine record and
is appended to by each session, never edited.

**The one rule that governs this whole project:** no number reaches the screen
that the person showing it cannot derive and defend. Every figure the console
displays traces to a committed artefact under `eval/`, and
`python -m ghostnet.provenance` (run with `PYTHONPATH=src`) verifies that. If a
redesign needs a number that is not in the payload, the answer is not to
hardcode it.
