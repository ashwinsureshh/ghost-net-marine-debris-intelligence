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
from ghostnet.evidence_hash import validate_text_evidence

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
_MULTI = "eval/multitemporal_oscar.json"       # what the console reports
_MULTI_NOFIELD = "eval/multitemporal.json"     # the arm before OSCAR existed
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
    Claim("multi_temporal.current_speed_source", _MULTI, "current_speed_source"),
    # The before/after that shows the dependency was tested and closed. These
    # trace to the OTHER arm on purpose: the whole claim is that two different
    # runs of the same pair disagree, so each side must cite its own artefact.
    Claim("multi_temporal.rejections_without_field", _MULTI_NOFIELD, "marginal_rejections"),
    Claim(
        "multi_temporal.true_debris_lost_without_field",
        _MULTI_NOFIELD,
        "marginal_true_debris_lost",
    ),
    Claim("multi_temporal.baseline_f1_without_field", _MULTI_NOFIELD, "spectral_only.f1"),
    Claim(
        "multi_temporal.with_check_f1_without_field",
        _MULTI_NOFIELD,
        "with_multi_temporal.f1",
    ),
    Claim(
        "multi_temporal.f1_delta_without_field",
        derived_from=(
            "multi_temporal.with_check_f1_without_field",
            "multi_temporal.baseline_f1_without_field",
        ),
        compute=lambda after, before: after - before,
        note="what the check cost before OSCAR existed; -0.167 here",
    ),
    Claim(
        "multi_temporal.harm_removed",
        derived_from=("multi_temporal.rejections", "multi_temporal.rejections_without_field"),
        compute=lambda now, before: bool(before and now == 0 and before > 0),
    ),
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
    Artefact(
        "eval/river_rankings.json", False,
        "Published emission-prior agreement; circular consistency, not source accuracy.",
        invariants=(("independent_accuracy_measured", False),
                    ("regions.gulf_of_honduras.attributed", 443),
                    ("regions.gulf_of_honduras.global_top_1000_count", 18),
                    ("regions.gulf_of_honduras.global_top_1000_fraction", 0.0406),
                    ("regions.gulf_of_gonave.attributed", 65),
                    ("regions.gulf_of_gonave.global_top_1000_count", 13),
                    ("regions.gulf_of_gonave.global_top_1000_fraction", 0.2),
                    ("regions.puducherry_coast.attributed", 6),
                    ("regions.puducherry_coast.global_top_1000_count", 6),
                    ("regions.puducherry_coast.global_top_1000_fraction", 1.0),
                    ),
    ),
    Artefact(
        "eval/geographic_candidates.json", False,
        "PR-AUC and production-rule candidate counts for the same six strict "
        "holdouts. Candidate precision is a bound (unlabelled = unverifiable); "
        "label 'objects' are sparse annotation fragments, not debris items.",
        invariants=(
            ("protocol", "strict-holdout-candidates-v1"),
            ("tiles.16PDC.summary.pr_auc_mean", 0.5812),
            ("tiles.16PDC.summary.debris_prevalence", 0.000996),
            ("tiles.48PZC.summary.pr_auc_mean", 0.9233),
            ("tiles.48PZC.summary.debris_prevalence", 0.002065),
            ("tiles.16PDC.runs[0].published_pixel_counts_reproduced", True),
            ("tiles.16PDC.runs[0].candidates.label_fragments_under_min_pixels", 101),
            ("tiles.16PDC.runs[0].candidates.labelled_debris_objects", 105),
            ("tiles.16PDC.summary.object_recall_mean", 0.4032),
            ("tiles.48PZC.summary.object_recall_mean", 0.8975),
        ),
    ),
    Artefact(
        "eval/rejection_breakdown.json", False,
        "Which verification checks reject candidates per served run; explains "
        "rejections (Puducherry: cloud in every shadow rejection), not their accuracy.",
        invariants=(
            ("runs.puducherry_coast.verified", 6),
            ("runs.puducherry_coast.candidates", 117),
            ("runs.puducherry_coast.checks.cloud_shadow.disqualifies", 75),
            ("runs.puducherry_coast.cloud_shadow_rejections.with_cloud_in_window", 75),
            ("runs.puducherry_coast.cloud_shadow_rejections.median_cloud_fraction", 0.28),
            ("runs.puducherry_coast.checks.kelp_sargassum.disqualifies", 4),
            ("runs.gulf_of_honduras.checks.kelp_sargassum.disqualifies", 166),
            ("runs.gulf_of_honduras.cloud_shadow_rejections.with_cloud_in_window", 100),
        ),
    ),
    Artefact(
        "eval/geographic_validation.json", False,
        "Six strict training-only holdouts; sparse labelled pixel metrics, "
        "not local-export accuracy or independently confirmed nets.",
        invariants=(
            ("protocol", "strict-training-only-v2"),
            ("seeds", [20260825, 20260826, 20260827]),
            ("tiles.16PDC.summary.debris_precision.mean", 0.5602),
            ("tiles.16PDC.summary.debris_precision.sample_std", 0.0822),
            ("tiles.16PDC.summary.debris_precision.min", 0.4826),
            ("tiles.16PDC.summary.debris_precision.max", 0.6464),
            ("tiles.16PDC.summary.debris_recall.mean", 0.711),
            ("tiles.16PDC.summary.debris_recall.sample_std", 0.0952),
            ("tiles.16PDC.summary.debris_recall.min", 0.6364),
            ("tiles.16PDC.summary.debris_recall.max", 0.8182),
            ("tiles.16PDC.summary.debris_f1.mean", 0.6257),
            ("tiles.16PDC.summary.debris_f1.sample_std", 0.0846),
            ("tiles.16PDC.summary.debris_f1.min", 0.564),
            ("tiles.16PDC.summary.debris_f1.max", 0.7222),
            ("tiles.48PZC.summary.debris_precision.mean", 0.5941),
            ("tiles.48PZC.summary.debris_precision.sample_std", 0.0441),
            ("tiles.48PZC.summary.debris_precision.min", 0.5455),
            ("tiles.48PZC.summary.debris_precision.max", 0.6316),
            ("tiles.48PZC.summary.debris_recall.mean", 0.9861),
            ("tiles.48PZC.summary.debris_recall.sample_std", 0.0241),
            ("tiles.48PZC.summary.debris_recall.min", 0.9583),
            ("tiles.48PZC.summary.debris_recall.max", 1.0),
            ("tiles.48PZC.summary.debris_f1.mean", 0.7407),
            ("tiles.48PZC.summary.debris_f1.sample_std", 0.0342),
            ("tiles.48PZC.summary.debris_f1.min", 0.7059),
            ("tiles.48PZC.summary.debris_f1.max", 0.7742),
        ),
    ),
    Artefact(
        "eval/geographic_split_audit.json", False,
        "Pre-training mask support audit for two additional tile holdouts; "
        "counts are labelled pixels and patches, not independently confirmed objects.",
        invariants=(
            ("tiles.16PDC.heldout_patches", 182),
            ("tiles.16PDC.debris_pixels", 143),
            ("tiles.16PDC.debris_positive_patches", 37),
            ("tiles.48PZC.heldout_patches", 53),
            ("tiles.48PZC.debris_pixels", 24),
            ("tiles.48PZC.debris_positive_patches", 8),
        ),
    ),
    Artefact(
        "eval/latency_full_inputs.json", False,
        "Single workstation run with all inputs present, including local "
        "serialization. Cold cache not established; not a deployment SLA.",
        invariants=(
            ("inputs_degraded", []), ("cold_run_asserted", False),
            ("detections", 826), ("verified", 443),
            ("seconds.ingest", 844.92), ("seconds.pipeline_total", 172.27),
            ("seconds.export", 0.05), ("seconds.total", 1017.24),
            ("meets_target", True),
        ),
    ),
    Artefact(
        "eval/ablation_system_full_inputs.json", False,
        "Full-input Honduras pipeline ablation, including GFW. Changes measure "
        "capability and scoring dependence, not independently labelled correctness.",
        invariants=(
            ("inputs_degraded_before_ablation", []),
            ("runs.full.detections", 826),
            ("runs.full.verified", 443),
            ("runs.full.top_score", 0.841),
            ("runs.without_vessels.top_score", 0.8511),
            ("runs.without_attribution.attributions", 0),
        ),
    ),
    Artefact(
        "eval/drift_temporal.json", False,
        "Paired 2014 buoy comparison with approximately six-day current snapshots; "
        "time interpolation did not improve seven-day errors. Not demo validation.",
        invariants=(
            ("window_is_demo_window", False), ("n_paired_tracks", 19),
            ("paired_exclusions", []),
            ("horizons_hours.168.mean.n_tracks", 7),
            ("horizons_hours.168.mean.mean_endpoint_error_km", 74.49191352861706),
            ("horizons_hours.168.temporal.mean_endpoint_error_km", 79.55259943029856),
        ),
    ),
    Artefact(
        "eval/temporal_matching.json", False,
        "Experimental drift-predicted + spectral/size repeat association on the "
        "four existing FR-2.2 pairs. Baseline reproduced; experimental arm "
        "identical on every pair. Production verification unchanged.",
        invariants=(
            ("production_enabled", False),
            ("pairs[0].baseline_reproduced", True),
            ("pairs[0].metrics.experimental.f1", 0.5),
            ("pairs[0].metrics.baseline.f1", 0.5),
            ("pairs[0].statuses.matched", 144),
            ("pairs[1].baseline_reproduced", True),
            ("pairs[1].metrics.experimental.f1", 0.5),
            ("pairs[2].labelled", 0),
            ("pairs[3].candidates_a", 0),
        ),
    ),
    Artefact(
        "eval/drift_calibration.json", False,
        "Internal disjoint-buoy calibration of reported radii. Coverage gains "
        "come with large widths; mean paths unchanged and calibration not deployed.",
        invariants=(
            ("arms.mean.calibration_observations", 129),
            ("arms.mean.evaluation_observations", 277),
            ("arms.mean.calibrated_track_mean_coverage", 0.8865265169612996),
            ("arms.temporal.calibrated_track_mean_coverage", 0.950989010989011),
        ),
    ),
    Artefact(
        "eval/priority_sensitivity.json", True,
        "One-at-a-time priority weight sensitivity on fixed real-run evidence; "
        "served per run by /api/runs/{id}/robustness only when the artefact hash matches; "
        "ranking robustness, not validation of detection accuracy or dispatch correctness.",
        invariants=(
            ("runs[0].region", "gulf_of_honduras"),
            ("runs[0].summary.variants", 24),
            ("runs[0].summary.top1_changed", 4),
            ("runs[0].summary.dispatch_set_changed", 10),
            ("runs[1].region", "gulf_of_gonave"),
            ("runs[1].summary.top1_changed", 0),
            ("runs[1].summary.dispatch_set_changed", 1),
            ("runs[2].region", "puducherry_coast"),
            ("runs[2].summary.top1_changed", 0),
            ("runs[2].summary.dispatch_set_changed", 2),
        ),
    ),
    Artefact(
        "eval/aoi_gonave.json", False,
        "Coarse SCL coverage survey used to choose the eastern coastal export AOI; "
        "not a detector accuracy measurement or an operator metric.",
        invariants=(
            ("region", "gulf_of_gonave"),
            ("resolution_m", 200.0),
            ("candidates[1].bbox", [-73.0618, 18.3363, -72.5618, 18.7363]),
            ("candidates[1].usable_water_pct", 56.2),
            ("candidates[1].nodata_pct", 16.4),
            ("candidates[1].scenes_used", 4),
        ),
    ),
    Artefact(_ABLATION, True, "FR-2.4 headline ablation and the fitted threshold."),
    Artefact(_FDI, True, "FDI detector arm of the metrics strip."),
    Artefact(_CNN, True, "CNN detector arm of the metrics strip."),
    Artefact(
        _MULTI,
        True,
        "FR-2.2 headline pair as the console reports it: re-measured against the "
        "real OSCAR field. The measured negative, and since 2026-09-04 an INERT "
        "one rather than a blocked one — the harm is gone and the contribution "
        "is still exactly zero.",
    ),
    Artefact(
        _MULTI_NOFIELD,
        True,
        "The same pair before OSCAR existed. Surfaced because the CHANGE is the "
        "finding: the console shows what the check cost when its dependency was "
        "missing (6 rejections, 1 true debris lost, dF1 -0.167) beside what it "
        "costs now (0, 0, 0.000). Showing only the current arm would state that "
        "the check is inert without evidence that the dependency was ever the "
        "problem.",
    ),
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
        "eval/latency.json",
        False,
        "PRD §8 end-to-end latency for one region. Not surfaced because it "
        "describes how long the run TOOK to produce, which an operator reading "
        "a finished plan does not need and cannot act on. It belongs in the "
        "report's performance section.",
        invariants=(
            # The finding, pinned: the system is I/O-bound. If a re-run moves
            # this split materially, the report's "a faster GPU would not help"
            # claim needs rewriting rather than re-quoting.
            ("seconds.ingest", 845.96),
            ("seconds.detection", 37.91),
            ("seconds.drift", 49.54),
            # The headline itself, so prose quoting "15.6 minutes" cannot
            # drift from the artefact the way the split alone would allow.
            ("seconds.total", 934.03),
            ("meets_target", True),
            # Records that ingest is a lower bound, so the number is never
            # quoted as a cold-start measurement.
            ("cold_run_asserted", False),
        ),
    ),
    Artefact(
        "eval/ablation_system.json",
        False,
        "PRD §12 bullet 5 — every agent removed in turn, on the real Gulf of "
        "Honduras inputs. Not surfaced because it describes the ARCHITECTURE, "
        "not the run on screen: the console shows one pipeline configuration, "
        "and six counterfactual ones beside it would be noise. It belongs in "
        "the report, where the argument it supports is being made.",
        invariants=(
            # The row that carries the argument: removing verification RAISES
            # the top score, because the quality gate is what was removed. If a
            # re-run makes every ablation merely worse, the strongest version
            # of this result is gone and the write-up needs revisiting.
            ("runs.full.top_score", 0.8511),
            ("runs.without_verification.top_score", 0.9295),
            ("runs.without_verification.verified", 0),
            ("runs.without_drift.top_score", 0.557),
            ("runs.without_drift.attributions", 0),
            # Detection is the only data source; its removal must be total.
            ("runs.without_detection.detections", 0),
            # Recorded so the vessels row is never read as "this agent does not
            # matter" when it means "this agent had no data".
            ("inputs_degraded_before_ablation", ["gfw"]),
        ),
    ),
    Artefact(
        "eval/drift.json",
        False,
        "FR-3 drift validation against NOAA Global Drifter Program buoys "
        "(PRD §12 bullet 3). Not surfaced because it describes the MODEL over "
        "2014, not the run on screen: zero drifters crossed this region during "
        "the demo window, so it can never be presented as validating the "
        "displayed trajectories. Surfacing it beside them would imply exactly "
        "the thing the measurement cannot support.",
        invariants=(
            # The framing that must not drift: this is a model check over
            # another period, and the artefact says so structurally.
            ("window_is_demo_window", False),
            ("region", "gulf_of_honduras"),
            # The headline, and the envelope figure that qualifies it. An
            # envelope containing the truth a quarter of the time is a finding,
            # not a footnote — if a re-run moves it, the write-up needs redoing.
            ("n_tracks", 19),
            ("mean_track_error_km", 34.639),
            ("mean_fraction_within_envelope", 0.2452),
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
    # FR-2.2 as the console now reports it: the real-OSCAR arm.
    (_MULTI, "spectral_only.f1", 0.5),
    (_MULTI, "with_multi_temporal.f1", 0.5),
    (_MULTI, "marginal_true_debris_lost", 0),
    (_MULTI, "marginal_rejections", 0),
    (_MULTI, "current_speed_source", "oscar"),
    # Still zero WITH a real field. This is the pin that carries the finding:
    # the dependency arrived and the check still has nothing to find.
    (_MULTI, "transient", 0),
    # The prior arm, pinned so the before/after cannot drift either.
    (_MULTI_NOFIELD, "with_multi_temporal.f1", 0.3333),
    (_MULTI_NOFIELD, "marginal_true_debris_lost", 1),
    (_MULTI_NOFIELD, "marginal_rejections", 6),
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


TEXT_EVIDENCE_LINKS = (
    ("eval/geographic_validation.json", "eval/geographic_split_audit.json", "audit"),
    ("eval/geographic_candidates.json", "eval/geographic_validation.json", "reference"),
    ("eval/drift_calibration.json", "eval/drift_temporal.json", "source"),
)


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

    for output, source, prefix in TEXT_EVIDENCE_LINKS:
        raw = _load(output)
        try:
            validate_text_evidence(REPO_ROOT / source, raw.get(f"{prefix}_sha256"),
                                   raw.get(f"{prefix}_hash_method"))
        except (ValueError, OSError) as exc:
            mismatches.append(Mismatch(
                field=f"{output}:{prefix}_sha256", served="(not surfaced)",
                recorded=raw.get(f"{prefix}_sha256"), source=source, detail=str(exc),
            ))


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
