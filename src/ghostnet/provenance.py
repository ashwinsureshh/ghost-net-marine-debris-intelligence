"""Where every number the console serves actually comes from — PRD §12.

The last PRD §12 acceptance bullet asks that *every output in the demo can be
traced back to its underlying evidence on request*. For the run artefact that
trace is structural: detections carry ``evidence`` refs and the artefact carries
``provenance``. For the **measured** numbers — the metrics strip, which is the
only place the console makes a quality claim — there was no such trace, and its
absence has already cost twice:

* the CNN candidate table in ``eval/results.md`` disagreed with
  ``eval/detector_cnn_test.json`` in three cells, and
* three FR-2.2 arms were quoted with no committed artefact behind them.

Both were caught by cross-checking prose against JSON **by hand**, once. This
module makes that check repeatable: every field :mod:`ghostnet.benchmark` puts
on the wire is declared here against the artefact and JSON pointer it claims to
come from, and :func:`reconcile` fails loudly when the two drift apart.

Two rules this module obeys, because breaking either would defeat the point:

* **It never re-derives a measured quantity.** ``eval/results.md`` and the
  committed ``eval/*.json`` are the authority. A :class:`Claim` with a
  ``pointer`` asserts *agreement* with a recorded number; it does not compute
  one from data.
* **Derived fields are checked as identities, not as measurements.** The UI
  shows ``precision_gain``; that is a subtraction of two values which are
  themselves JSON-backed. Verifying the subtraction is arithmetic consistency,
  not a second source of truth — and where the eval script recorded the delta
  itself (``metrics.precision_delta``) the identity is cross-checked against
  that too, so drift in either direction is caught.

Every artefact under ``eval/`` must also be *accounted for* — either surfaced on
the console (and therefore reconciled) or explicitly registered in
:data:`CHECKED_NOT_SURFACED` with the reason it is not. A number no artefact
backs, or an artefact nothing checks, is exactly what this bullet exists to
stop.

Run it directly for the viva walk-through::

    python -m ghostnet.provenance
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from ghostnet.config import REPO_ROOT

EVAL_DIR = REPO_ROOT / "eval"

#: Floats are written to the artefacts already rounded, and the served value is
#: the same number round-tripped through JSON and pydantic. Anything beyond this
#: is a real disagreement, not representation noise.
TOLERANCE = 5e-7

#: Slack for the one comparison that spans two rounding stages: a *derived*
#: field checked against a delta the eval script *recorded*.
#:
#: The scripts compute a delta at full precision and then round it to 4 dp; the
#: console subtracts two values that were each already rounded to 4 dp. Those
#: disagree in the last digit whenever the roundings fall opposite ways. It
#: happens once in the committed set — the CNN verification gain is 0.0799
#: recorded and 0.7514 - 0.6716 = 0.0798 derived — and both display as +0.080,
#: so no published claim is affected. Anything larger than a last-digit
#: disagreement still fails.
#:
#: Direct reads are NOT given this slack; they stay on TOLERANCE.
ROUNDING_TOLERANCE = 5e-4


@dataclass(frozen=True)
class Claim:
    """One number the console serves, and the evidence behind it.

    ``pointer`` is a dotted path into ``source``'s JSON (``metrics.baseline_f1``).
    ``compute`` states a derived field as an identity over other served fields.
    A claim may carry both: the identity is then also cross-checked against the
    recorded value, which is the strongest form available here.
    """

    field: str
    source: str | None = None
    pointer: str | None = None
    derived_from: tuple[str, ...] = ()
    compute: Callable[..., float] | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.pointer is None and self.compute is None:
            raise ValueError(f"{self.field}: a claim needs a pointer, a compute, or both")
        if self.pointer is not None and self.source is None:
            raise ValueError(f"{self.field}: a pointer needs a source file")


@dataclass
class Mismatch:
    """A served number that no longer agrees with its evidence."""

    field: str
    served: Any
    recorded: Any
    source: str
    detail: str = ""

    def __str__(self) -> str:
        head = (
            f"{self.field}: console serves {self.served!r}, "
            f"{self.source} records {self.recorded!r}"
        )
        return f"{head} — {self.detail}" if self.detail else head


def _resolve(payload: Any, path: str) -> Any:
    """Walk a dotted path with ``[i]`` list indices. Missing -> KeyError."""
    node = payload
    for part in path.split("."):
        name, _, idx = part.partition("[")
        if name:
            if not isinstance(node, dict) or name not in node:
                raise KeyError(path)
            node = node[name]
        if idx:
            i = int(idx.rstrip("]"))
            if not isinstance(node, list) or i >= len(node):
                raise KeyError(path)
            node = node[i]
    return node


def _equal(a: Any, b: Any, tolerance: float = TOLERANCE) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, int | float) and isinstance(b, int | float):
        return abs(float(a) - float(b)) <= tolerance
    return a == b


# ---------------------------------------------------------------------------
# The declarations
# ---------------------------------------------------------------------------

_FDI = "eval/detector_fdi_test.json"
_CNN = "eval/detector_cnn_test.json"
_ABLATION = "eval/marida_ablation.json"
_MULTI = "eval/multitemporal.json"
_GEN_TRAINED = "eval/holdout_18QYF_leaky.json"
_GEN_UNSEEN = "eval/holdout_18QYF.json"


def _verification_claims(prefix: str, source: str, block: str) -> list[Claim]:
    """The six read figures plus five derived ones, for one detector's block."""
    b = f"{block}." if block else ""
    return [
        Claim(f"{prefix}.scored", source, f"{b}metrics.n_labelled"),
        Claim(f"{prefix}.excluded_unlabelled", source, f"{b}detections_unlabelled_excluded"),
        Claim(f"{prefix}.baseline_precision", source, f"{b}metrics.baseline_precision"),
        Claim(f"{prefix}.verified_precision", source, f"{b}metrics.verified_precision"),
        Claim(f"{prefix}.baseline_recall", source, f"{b}metrics.baseline_recall"),
        Claim(f"{prefix}.verified_recall", source, f"{b}metrics.verified_recall"),
        Claim(f"{prefix}.baseline_f1", source, f"{b}metrics.baseline_f1"),
        Claim(f"{prefix}.verified_f1", source, f"{b}metrics.verified_f1"),
        # Derived, and cross-checked against the delta the eval script recorded.
        Claim(
            f"{prefix}.precision_gain",
            source,
            f"{b}metrics.precision_delta",
            derived_from=(f"{prefix}.verified_precision", f"{prefix}.baseline_precision"),
            compute=lambda v, base: v - base,
            note="verified - baseline, cross-checked against the recorded delta",
        ),
        Claim(
            f"{prefix}.f1_gain",
            derived_from=(f"{prefix}.verified_f1", f"{prefix}.baseline_f1"),
            compute=lambda v, base: v - base,
        ),
        Claim(
            f"{prefix}.recall_cost",
            derived_from=(f"{prefix}.baseline_recall", f"{prefix}.verified_recall"),
            compute=lambda base, v: base - v,
            note="positive = recall given up to buy precision",
        ),
        # Deliberately NOT read from `false_positive_rate_drop`: that field is a
        # signed delta whose name reads backwards and has misled once already.
        Claim(
            f"{prefix}.baseline_false_positive_rate",
            derived_from=(f"{prefix}.baseline_precision",),
            compute=lambda p: 1.0 - p,
            note="1 - precision; not read from false_positive_rate_drop, "
            "whose sign reads backwards",
        ),
        Claim(
            f"{prefix}.verified_false_positive_rate",
            derived_from=(f"{prefix}.verified_precision",),
            compute=lambda p: 1.0 - p,
        ),
    ]


def _detector_claims(i: int, source: str) -> list[Claim]:
    p = f"detectors[{i}]"
    return [
        Claim(f"{p}.detector", source, "detector"),
        Claim(f"{p}.candidates_emitted", source, "detections_total"),
        Claim(f"{p}.detector_precision", source, "metrics.baseline_precision"),
        Claim(f"{p}.regions", source, "debris_regions"),
        Claim(f"{p}.regions_hit", source, "debris_regions_hit"),
        Claim(f"{p}.region_recall", source, "region_recall"),
        Claim(
            f"{p}.regions_missed",
            derived_from=(f"{p}.regions", f"{p}.regions_hit"),
            compute=lambda total, hit: total - hit,
        ),
        *_verification_claims(f"{p}.verification", source, block=""),
    ]


CLAIMS: tuple[Claim, ...] = (
    Claim("fdi_threshold", _ABLATION, "held_out_fitted.fdi_threshold"),
    # The legacy top-level FDI pair. Kept because the report has always carried
    # it; the console renders from `detectors` instead.
    Claim("detector.split", _ABLATION, "held_out_fitted.split"),
    Claim("detector.regions", _ABLATION, "held_out_fitted.debris_regions"),
    Claim("detector.regions_hit", _ABLATION, "held_out_fitted.debris_regions_hit"),
    Claim("detector.region_recall", _ABLATION, "held_out_fitted.region_recall"),
    Claim(
        "detector.regions_missed",
        derived_from=("detector.regions", "detector.regions_hit"),
        compute=lambda total, hit: total - hit,
    ),
    *_verification_claims("verification", _ABLATION, block="held_out_fitted"),
    # One entry per measured detector, in the order benchmark.py emits them.
    *_detector_claims(0, _FDI),
    *_detector_claims(1, _CNN),
    # FR-2.2, the measured negative.
    Claim("multi_temporal.tile", _MULTI, "pair.tile"),
    Claim("multi_temporal.date_a", _MULTI, "pair.date_a"),
    Claim("multi_temporal.date_b", _MULTI, "pair.date_b"),
    Claim("multi_temporal.candidates_labelled", _MULTI, "candidates_labelled"),
    Claim("multi_temporal.baseline_f1", _MULTI, "spectral_only.f1"),
    Claim("multi_temporal.with_check_f1", _MULTI, "with_multi_temporal.f1"),
    Claim("multi_temporal.baseline_recall", _MULTI, "spectral_only.recall"),
    Claim("multi_temporal.with_check_recall", _MULTI, "with_multi_temporal.recall"),
    Claim("multi_temporal.rejections", _MULTI, "marginal_rejections"),
    Claim("multi_temporal.true_debris_lost", _MULTI, "marginal_true_debris_lost"),
    Claim("multi_temporal.transients_found", _MULTI, "transient"),
    Claim("multi_temporal.current_speed_ms", _MULTI, "current_speed_ms"),
    Claim(
        "multi_temporal.f1_delta",
        derived_from=("multi_temporal.with_check_f1", "multi_temporal.baseline_f1"),
        compute=lambda after, before: after - before,
        note="negative today; that is the finding, not an arithmetic bug",
    ),
    Claim(
        "multi_temporal.recall_delta",
        derived_from=("multi_temporal.with_check_recall", "multi_temporal.baseline_recall"),
        compute=lambda after, before: after - before,
    ),
    Claim(
        "multi_temporal.contributes",
        derived_from=("multi_temporal.f1_delta",),
        compute=lambda d: d > 0,
    ),
    # Geographic generalisation. The two arms come from DIFFERENT artefacts on
    # purpose: the whole claim is that they were scored on the same patches by
    # two different models, so each side must trace to its own model's file.
    Claim("generalisation.region", _GEN_UNSEEN, "holdout_tiles[0]"),
    Claim("generalisation.patches", _GEN_TRAINED, "holdout.patches"),
    Claim("generalisation.debris_px_per_patch", _GEN_TRAINED, "holdout.debris_px_per_patch"),
    Claim("generalisation.trained_precision", _GEN_TRAINED, "holdout.debris_precision"),
    Claim("generalisation.trained_recall", _GEN_TRAINED, "holdout.debris_recall"),
    Claim("generalisation.trained_f1", _GEN_TRAINED, "holdout.debris_f1"),
    Claim("generalisation.unseen_precision", _GEN_UNSEEN, "holdout.debris_precision"),
    Claim("generalisation.unseen_recall", _GEN_UNSEEN, "holdout.debris_recall"),
    Claim("generalisation.unseen_f1", _GEN_UNSEEN, "holdout.debris_f1"),
    # The pairing is the experiment. If these two ever diverge the table is
    # measuring task difficulty, not geography — so it is asserted, not assumed.
    Claim(
        "generalisation.patches",
        _GEN_UNSEEN,
        "holdout.patches",
        note="both arms must score the identical patch set",
    ),
    Claim(
        "generalisation.debris_px_per_patch",
        _GEN_UNSEEN,
        "holdout.debris_px_per_patch",
        note="identical debris density confirms the arms are paired",
    ),
    Claim(
        "generalisation.precision_cost",
        derived_from=("generalisation.unseen_precision", "generalisation.trained_precision"),
        compute=lambda unseen, trained: unseen - trained,
    ),
    Claim(
        "generalisation.recall_cost",
        derived_from=("generalisation.unseen_recall", "generalisation.trained_recall"),
        compute=lambda unseen, trained: unseen - trained,
        note="the bulk of the generalisation cost is here, not in precision",
    ),
    Claim(
        "generalisation.f1_cost",
        derived_from=("generalisation.unseen_f1", "generalisation.trained_f1"),
        compute=lambda unseen, trained: unseen - trained,
    ),
)


# ---------------------------------------------------------------------------
# Artefact accounting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Artefact:
    """One committed ``eval/*.json``, and what the console does with it.

    ``surfaced`` files are reconciled field by field through :data:`CLAIMS`.
    Unsurfaced ones still have to justify themselves and are held to their
    ``invariants`` — the specific facts the write-ups lean on — so a re-run that
    changed them could not pass silently just because nothing renders them.
    """

    path: str
    surfaced: bool
    reason: str
    invariants: tuple[tuple[str, Any], ...] = ()


ARTEFACTS: tuple[Artefact, ...] = (
    Artefact(_ABLATION, True, "FR-2.4 headline ablation and the fitted threshold."),
    Artefact(_FDI, True, "FDI detector arm of the metrics strip."),
    Artefact(_CNN, True, "CNN detector arm of the metrics strip."),
    Artefact(_MULTI, True, "FR-2.2 headline pair — the measured negative."),
    Artefact(
        "eval/holdout_18QYF_leaky.json",
        True,
        "Generalisation: detector_v1 scored on the 84 18QYF patches it trained on.",
    ),
    Artefact(
        "eval/holdout_18QYF.json",
        True,
        "Generalisation: the holdout model on the identical 84 patches. Surfaced "
        "because the strip already shows region recall, which is a WITHIN-TILE "
        "number (91% of test patches sit on trained-on tiles) and reads as "
        "generalisation evidence when it is not — the same defect docs/"
        "ablation-study.md §4 was corrected for.",
    ),
    # --- checked, deliberately not surfaced -------------------------------
    Artefact(
        "eval/multitemporal_oscar.json",
        False,
        "FR-2.2's headline pair RE-MEASURED with the real OSCAR current field "
        "(2026-09-04, first download). This is the arm that changes the FR-2.2 "
        "conclusion: the envelope grows from the 5 km floor to ~11 km, all 6 "
        "incoherent-motion rejections disappear and the 1 true debris loss with "
        "them. NOT YET SURFACED, and that is a live gap — the console still "
        "reads eval/multitemporal.json (no field) and still says the check is "
        "blocked on FR-3.1. That claim is now stale: FR-3.1's data exists. "
        "Surfacing this is the next console change, and it needs the caveat "
        "rewritten, not just the number swapped.",
        invariants=(
            ("current_speed_source", "oscar"),
            ("incoherent_motion", 0),
            ("marginal_true_debris_lost", 0),
            # Still zero, and still the reason FR-2.2 earns nothing: a real
            # current field fixes the false rejections and does not give the
            # check anything to find.
            ("transient", 0),
        ),
    ),
    Artefact(
        "eval/multitemporal_oscar_18QYF_2020-03.json",
        False,
        "Supporting FR-2.2 pair, re-measured with the real field. Its 0.0001 m/s "
        "is NOT a measurement of Gulf of Gonave's circulation: the AOI spans "
        "0.48 x 0.19 of an OSCAR grid cell, so every sample interpolates between "
        "the same few nodes. Quote it as sub-grid, or not at all.",
        invariants=(("current_speed_source", "oscar"), ("transient", 0)),
    ),
    Artefact(
        "eval/multitemporal_oscar_18QYF_2020-11.json",
        False,
        "Supporting FR-2.2 pair, re-measured. Its 0.0907 m/s against the same "
        "AOI's 0.0001 m/s eight months earlier is a 900x swing that shows the "
        "field is poorly constrained at this scale, not seasonal variability we "
        "have resolved.",
        invariants=(("current_speed_source", "oscar"), ("transient", 0)),
    ),
    Artefact(
        "eval/multitemporal_oscar_16PCC_2018-09.json",
        False,
        "Supporting FR-2.2 pair, re-measured. No candidates on either date, so "
        "it carries no delta either way; kept so all four pairs have a "
        "with-field artefact and the table is complete.",
        invariants=(("current_speed_source", "oscar"), ("transient", 0)),
    ),
    Artefact(
        "eval/cnn_prob_sweep_val.json",
        False,
        "The calibration behind DEFAULT_PROB_THRESHOLD = 0.40. Not surfaced "
        "because the console reports the detector's performance, not how its "
        "cut-off was chosen — but 'why 0.40?' is a likely viva question, and "
        "until this existed the answer rested on eval/results.md prose that no "
        "artefact backed. Swept on VAL: the threshold was selected there and "
        "--prob-sweep refuses --split test, because sweeping an objective over "
        "the held-out split is how it stops being held out.",
        invariants=(
            # Pins the two facts every write-up leans on: 0.40 is still the
            # region-recall optimum, and precision peaks somewhere else. If a
            # re-run moved either, the claim that the objectives conflict — and
            # the choice made because of it — would need rewriting, not
            # re-quoting.
            ("split", "val"),
            ("objective", "region_recall"),
            ("default_prob_threshold", 0.40),
            ("selected_prob_threshold", 0.40),
            ("max_precision_prob_threshold", 0.70),
            ("prob_sweep[2].prob_threshold", 0.40),
            ("prob_sweep[2].region_recall", 0.7550),
            ("prob_sweep[5].detector_precision", 0.9031),
            ("prob_sweep[5].region_recall", 0.4989),
        ),
    ),
    Artefact(
        "eval/multitemporal_sensitivity_010.json",
        False,
        "The 0.10 m/s arm that proves FR-2.2's dependency on FR-3.1. The console "
        "already states that dependency in multi_temporal_caveats and the claim "
        "is correct, so this adds evidence rather than correcting anything. It "
        "is the strongest candidate to surface next — it would turn that caveat "
        "from an assertion into a number.",
        invariants=(
            ("current_speed_ms", 0.10),
            ("marginal_rejections", 0),
            ("marginal_true_debris_lost", 0),
        ),
    ),
    Artefact(
        "eval/multitemporal_18QYF_2020-03.json",
        False,
        "Supporting FR-2.2 pair. A null result — the check neither helped nor "
        "hurt — already represented by the headline pair on screen. The full "
        "four-pair table lives in eval/results.md and docs/ablation-study.md §5.",
        invariants=(("transient", 0), ("marginal_true_debris_lost", 0)),
    ),
    Artefact(
        "eval/multitemporal_18QYF_2020-11.json",
        False,
        "Supporting FR-2.2 pair. No labelled candidates, so it carries no delta.",
        invariants=(("transient", 0), ("marginal_true_debris_lost", 0)),
    ),
    Artefact(
        "eval/multitemporal_16PCC_2018-09.json",
        False,
        "Supporting FR-2.2 pair. No candidates on either date.",
        invariants=(("transient", 0), ("marginal_true_debris_lost", 0)),
    ),
)


#: The headline figures `eval/results.md` and `docs/` publish, pinned.
#:
#: :func:`reconcile` on its own cannot catch a *doctored artefact*: the console
#: reads the same JSON, so editing it moves both sides together and they still
#: agree. That is correct behaviour — the artefact IS the source of truth — but
#: it leaves the published numbers tamper-blind, and those are the ones quoted
#: in a report and a viva.
#:
#: These pins close that. They are not a second derivation: nothing here is
#: computed. They are the machine-readable form of "eval/results.md is the
#: authority", so an artefact that stops saying what the report published fails
#: rather than quietly redefining the result. Changing one is a deliberate act
#: that should land in the same commit as the prose it changes.
PUBLISHED: tuple[tuple[str, str, Any], ...] = (
    # FR-2.4 headline ablation, held-out MARIDA test.
    (_ABLATION, "held_out_fitted.metrics.baseline_precision", 0.2381),
    (_ABLATION, "held_out_fitted.metrics.verified_precision", 0.623),
    (_ABLATION, "held_out_fitted.metrics.verified_f1", 0.7525),
    (_ABLATION, "held_out_fitted.region_recall", 0.4068),
    # FR-1.4 detector comparison.
    (_FDI, "region_recall", 0.4068),
    (_FDI, "debris_regions_hit", 96),
    (_CNN, "region_recall", 0.7034),
    (_CNN, "debris_regions_hit", 166),
    (_CNN, "detections_total", 795),
    (_CNN, "metrics.baseline_precision", 0.6716),
    # FR-2.2, the measured negative.
    (_MULTI, "spectral_only.f1", 0.5),
    (_MULTI, "with_multi_temporal.f1", 0.3333),
    (_MULTI, "marginal_true_debris_lost", 1),
    (_MULTI, "transient", 0),
    # Geographic generalisation, the paired arms.
    (_GEN_TRAINED, "holdout.debris_f1", 0.9304),
    (_GEN_UNSEEN, "holdout.debris_f1", 0.8581),
    (_GEN_TRAINED, "holdout.patches", 84),
    (_GEN_UNSEEN, "holdout.patches", 84),
)


def published_drift() -> list[Mismatch]:
    """Artefacts that no longer record what the write-ups published."""
    drifted: list[Mismatch] = []
    cache: dict[str, dict[str, Any]] = {}
    for source, pointer, expected in PUBLISHED:
        if source not in cache:
            cache[source] = _load(source)
        try:
            actual = _resolve(cache[source], pointer)
        except KeyError:
            actual = "<absent>"
        if not _equal(actual, expected):
            drifted.append(
                Mismatch(
                    field=f"{source}:{pointer}",
                    served=actual,
                    recorded=expected,
                    source="eval/results.md (published)",
                    detail=(
                        "the artefact no longer records the published figure. If the "
                        "measurement genuinely changed, update the prose and this pin "
                        "in the same commit."
                    ),
                )
            )
    return drifted


def committed_artefacts() -> list[str]:
    """Every ``eval/*.json`` on disk, repo-relative."""
    return sorted(f"eval/{p.name}" for p in EVAL_DIR.glob("*.json"))


def unaccounted_artefacts() -> list[str]:
    """Artefacts nothing in this module says anything about."""
    known = {a.path for a in ARTEFACTS}
    return [p for p in committed_artefacts() if p not in known]


def missing_artefacts() -> list[str]:
    """Registered artefacts that are not on disk."""
    return [a.path for a in ARTEFACTS if not (REPO_ROOT / a.path).exists()]


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------


def _load(source: str) -> dict[str, Any]:
    return json.loads((REPO_ROOT / source).read_text(encoding="utf-8"))


def reconcile(payload: dict[str, Any] | None = None) -> list[Mismatch]:
    """Check every served number against the artefact it claims to come from.

    Returns the mismatches; empty means the console and the committed evidence
    agree. Pass ``payload`` to check a specific response (a test fixture, or a
    deployed ``/api/benchmark`` body); the default reads the live report.
    """
    if payload is None:
        from ghostnet.benchmark import cached_benchmark

        payload = cached_benchmark().model_dump()

    if not payload.get("available", False):
        return [
            Mismatch(
                field="available",
                served=False,
                recorded=True,
                source="eval/",
                detail=str(payload.get("unavailable_reason") or "benchmark unavailable"),
            )
        ]

    cache: dict[str, dict[str, Any]] = {}
    mismatches: list[Mismatch] = []

    for claim in CLAIMS:
        try:
            served = _resolve(payload, claim.field)
        except KeyError:
            mismatches.append(
                Mismatch(
                    field=claim.field,
                    served="<absent>",
                    recorded="declared",
                    source=claim.source or "(derived)",
                    detail="declared in provenance.CLAIMS but the console serves no such field",
                )
            )
            continue

        if claim.pointer is not None:
            assert claim.source is not None
            if claim.source not in cache:
                cache[claim.source] = _load(claim.source)
            try:
                recorded = _resolve(cache[claim.source], claim.pointer)
            except KeyError:
                mismatches.append(
                    Mismatch(
                        field=claim.field,
                        served=served,
                        recorded="<absent>",
                        source=claim.source,
                        detail=f"pointer {claim.pointer!r} not present in the artefact",
                    )
                )
            else:
                # A claim with both a pointer and a compute is a derived field
                # cross-checked against a recorded delta: two rounding stages,
                # so it gets ROUNDING_TOLERANCE. A plain read does not.
                spans_rounding = claim.compute is not None
                tol = ROUNDING_TOLERANCE if spans_rounding else TOLERANCE
                if not _equal(served, recorded, tol):
                    mismatches.append(
                        Mismatch(
                            field=claim.field,
                            served=served,
                            recorded=recorded,
                            source=f"{claim.source}:{claim.pointer}",
                            detail=claim.note,
                        )
                    )

        if claim.compute is not None:
            try:
                inputs = [_resolve(payload, name) for name in claim.derived_from]
            except KeyError as exc:
                mismatches.append(
                    Mismatch(
                        field=claim.field,
                        served=served,
                        recorded="<absent>",
                        source="(derived)",
                        detail=f"input {exc.args[0]!r} is not served",
                    )
                )
                continue
            expected = claim.compute(*inputs)
            if not _equal(served, expected):
                mismatches.append(
                    Mismatch(
                        field=claim.field,
                        served=served,
                        recorded=expected,
                        source="(derived) " + " , ".join(claim.derived_from),
                        detail=claim.note or "derived field no longer matches its inputs",
                    )
                )

    mismatches.extend(published_drift())

    for artefact in ARTEFACTS:
        if artefact.surfaced or not artefact.invariants:
            continue
        raw = _load(artefact.path)
        for pointer, expected in artefact.invariants:
            try:
                actual = _resolve(raw, pointer)
            except KeyError:
                actual = "<absent>"
            if not _equal(actual, expected):
                mismatches.append(
                    Mismatch(
                        field=f"{artefact.path}:{pointer}",
                        served="(not surfaced)",
                        recorded=actual,
                        source=artefact.path,
                        detail=(
                            f"recorded invariant expected {expected!r}; the write-ups "
                            "lean on this value"
                        ),
                    )
                )

    return mismatches


def declared_fields() -> set[str]:
    """Every payload path :data:`CLAIMS` accounts for."""
    return {c.field for c in CLAIMS}


def numeric_leaves(payload: dict[str, Any], prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Every scalar the payload carries, as dotted paths — strings included.

    Used to prove the inverse of :func:`reconcile`: not just that declared
    fields agree, but that no *undeclared* number reached the wire.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            yield from numeric_leaves(value, f"{prefix}.{key}" if prefix else key)
    elif isinstance(payload, list):
        for i, value in enumerate(payload):
            yield from numeric_leaves(value, f"{prefix}[{i}]")
    elif isinstance(payload, int | float) and not isinstance(payload, bool):
        yield prefix, payload


def undeclared_numbers(payload: dict[str, Any] | None = None) -> list[str]:
    """Served numbers that :data:`CLAIMS` does not account for.

    The inverse guard. :func:`reconcile` proves the declared fields agree;
    this proves nothing slipped onto the wire without a declaration — which is
    how an unbacked number would otherwise arrive.
    """
    if payload is None:
        from ghostnet.benchmark import cached_benchmark

        payload = cached_benchmark().model_dump()
    declared = declared_fields()
    return sorted(path for path, _ in numeric_leaves(payload) if path not in declared)


def main() -> int:
    """Print the trace from every served number to its evidence."""
    from ghostnet.benchmark import cached_benchmark

    payload = cached_benchmark().model_dump()

    print("Console numbers -> committed evidence")
    print("=" * 78)
    by_source: dict[str, list[Claim]] = {}
    for claim in CLAIMS:
        by_source.setdefault(claim.source or "(derived from other served fields)", []).append(
            claim
        )
    for source in sorted(by_source):
        print(f"\n{source}")
        for claim in by_source[source]:
            try:
                served = _resolve(payload, claim.field)
            except KeyError:
                served = "<absent>"
            where = f" <- {claim.pointer}" if claim.pointer else ""
            print(f"    {claim.field:<52} = {served!r}{where}")

    print("\n" + "=" * 78)
    print("Artefact accounting")
    for artefact in ARTEFACTS:
        mark = "surfaced" if artefact.surfaced else "checked, not surfaced"
        print(f"  [{mark:^21}] {artefact.path}")
        if not artefact.surfaced:
            print(f"      {artefact.reason}")

    stray = unaccounted_artefacts()
    absent = missing_artefacts()
    undeclared = undeclared_numbers(payload)
    mismatches = reconcile(payload)

    print("\n" + "=" * 78)
    for label, items in (
        ("artefacts nothing accounts for", stray),
        ("registered artefacts missing from disk", absent),
        ("served numbers with no declaration", undeclared),
    ):
        print(f"  {label}: {len(items)}")
        for item in items:
            print(f"      - {item}")
    print(f"  numbers that disagree with their evidence: {len(mismatches)}")
    for mismatch in mismatches:
        print(f"      - {mismatch}")

    ok = not (stray or absent or undeclared or mismatches)
    print("\n" + ("PASS — every served number traces to a committed artefact." if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
