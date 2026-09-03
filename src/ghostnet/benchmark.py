"""The measured benchmark numbers, in a shape the console can render.

`eval/results.md` is the authority on what the system actually scores; this
module reads its machine-readable companion, `eval/marida_ablation.json`, and
hands the operator console the two numbers that have to be quoted **together**:

* the **Verification Agent's precision gain** (FR-2.4) — the project's headline
  result, precision 0.238 -> 0.623 on the held-out MARIDA test split; and
* the **detector's region recall** — 0.407, i.e. the FDI baseline never sees
  ~59% of annotated debris regions at all.

The second exists here because of a specific way the first can mislead. The
precision/recall table is conditioned on candidates the detector emitted, so
baseline recall in it is 1.0 *by construction*. A console that showed only the
precision gain would let a reader conclude the system finds nearly all the
debris. It does not. `eval/results.md` states that both numbers must be quoted
together; putting only one of them on screen would break that in the one place
an evaluator actually looks.

Two things this module deliberately does **not** do:

* **It does not compute anything.** Recomputing a metric here would create a
  second source of truth that could silently disagree with `eval/results.md`.
  It reads, reshapes, and attaches caveats.
* **It does not claim these numbers describe the run on screen.** They were
  measured on MARIDA's 12 global regions with fitted thresholds, not on
  whatever region the loaded artefact covers. Every field that reaches the UI
  carries that framing, and the UI compares the artefact's own detector
  threshold against :attr:`BenchmarkReport.fdi_threshold` so a mismatch shows
  rather than passing unnoticed.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ghostnet.config import REPO_ROOT

logger = logging.getLogger(__name__)

BENCHMARK_FILE = REPO_ROOT / "eval" / "marida_ablation.json"
MULTITEMPORAL_FILE = REPO_ROOT / "eval" / "multitemporal.json"
RESULTS_DOC = "eval/results.md"

#: One measured result per detector. Both were scored through the same script
#: on the same held-out split, so they are directly comparable.
DETECTOR_FILES: dict[str, Path] = {
    "fdi": REPO_ROOT / "eval" / "detector_fdi_test.json",
    "cnn": REPO_ROOT / "eval" / "detector_cnn_test.json",
}

DETECTOR_LABELS = {
    "fdi": "FDI spectral index",
    "cnn": "CNN (MARIDA-trained)",
}

#: The paired geographic-generalisation experiment. Both models are scored on
#: the *identical* 84 18QYF patches; the only variable is whether the model saw
#: that region in training.
GENERALISATION_TRAINED_FILE = REPO_ROOT / "eval" / "holdout_18QYF_leaky.json"
GENERALISATION_UNSEEN_FILE = REPO_ROOT / "eval" / "holdout_18QYF.json"

#: The PRD §12 finding that the console must not let a reader miss: the
#: Verification Agent's contribution is measured *over whichever detector
#: precedes it*, and the two answers are an order of magnitude apart.
VERIFICATION_OVERLAP_NOTE = (
    "The Verification Agent's contribution depends on which detector runs ahead "
    "of it. Over the FDI baseline it is +0.385 precision; over the CNN it is "
    "+0.080, because the network already declines to emit most of the clouds, "
    "Sargassum and turbid water the checks existed to reject — 73 cloud "
    "candidates under FDI become 1 under the CNN, and turbid water and Sargassum "
    "disappear entirely. The agent is substantially subsumed, not redundant: it "
    "still removes what survives. Quoting +0.385 beside a CNN run overstates it."
)

DATASET = "MARIDA"
DATASET_VERSION = "v1.0.0"
DATASET_DOI = "10.5281/zenodo.5151941"

#: Read before quoting any of this on screen. Lifted from `eval/results.md` so
#: the console and the report say the same thing about the same numbers.
CAVEATS = [
    "Measured on the held-out MARIDA test split (12 global regions), not on this "
    "run's region or imagery. Thresholds were fitted on the train split only.",
    "Region recall is the detector's alone and is unaffected by verification. The "
    "FDI baseline lands on 96 of 236 annotated debris regions; the CNN variant "
    "(FR-1.4) reaches 166 of 236 while emitting 7.6x fewer candidates. The figure "
    "shown is for whichever detector produced the run on screen.",
    "Precision and recall are conditioned on the candidates the detector emitted, "
    "so baseline recall reads 1.0 by construction. Region recall is the meaningful "
    "detector-recall number — quote the two together.",
    "Multi-temporal consistency (FR-2.2) is measured and currently contributes "
    "nothing — it costs recall. It is blocked on FR-3.1, not broken: without a "
    "current field its coherence envelope collapses to a 5 km floor. Report it as "
    "a dependency, never as a contribution.",
]


class DetectorRecall(BaseModel):
    """How much of the annotated debris the detector ever sees. The weak number."""

    split: str
    regions: int = Field(description="Annotated Marine Debris regions in the split")
    regions_hit: int = Field(description="Regions any detection landed on")
    region_recall: float

    @property
    def regions_missed(self) -> int:
        return self.regions - self.regions_hit


class VerificationDelta(BaseModel):
    """FR-2.4: what the Verification Agent is worth, before vs after."""

    split: str
    scored: int = Field(description="Labelled candidates the metrics are computed over")
    excluded_unlabelled: int = Field(
        default=0,
        description="Candidates dropped because MARIDA leaves them unlabelled — never "
        "assumed negative.",
    )

    baseline_precision: float
    verified_precision: float
    baseline_recall: float
    verified_recall: float
    baseline_f1: float
    verified_f1: float

    @property
    def precision_gain(self) -> float:
        return self.verified_precision - self.baseline_precision

    @property
    def f1_gain(self) -> float:
        return self.verified_f1 - self.baseline_f1

    @property
    def recall_cost(self) -> float:
        """Positive number = recall given up to buy the precision."""
        return self.baseline_recall - self.verified_recall

    # False-positive rate is 1 - precision over the scored candidates. Derived
    # rather than read: `precision_recall_delta` reports it as a *signed delta*
    # whose name reads backwards (an improvement is negative), and that has
    # already misled once — see the Status Log entry for 2026-08-14.
    @property
    def baseline_false_positive_rate(self) -> float:
        return 1.0 - self.baseline_precision

    @property
    def verified_false_positive_rate(self) -> float:
        return 1.0 - self.verified_precision


class DetectorBenchmark(BaseModel):
    """One detector's measured result, with the verification delta *over it*.

    Bundled deliberately. Region recall and the verification gain are only
    meaningful as a pair for the same detector — the console picks the entry
    matching the run on screen rather than showing one detector's recall beside
    another's gain.
    """

    detector: str
    label: str
    candidates_emitted: int
    detector_precision: float

    regions: int
    regions_hit: int
    region_recall: float
    verification: VerificationDelta

    @property
    def regions_missed(self) -> int:
        return self.regions - self.regions_hit


class MultiTemporalResult(BaseModel):
    """FR-2.2, measured — and the measured answer is that it contributes nothing.

    The console shows this next to the FR-2.4 gain for the same reason it shows
    region recall next to precision: an evaluator seeing only the gain would
    assume every verification check is carrying weight. One is not. Reported as
    a *dependency on FR-3.1*, never as a contribution — the check is standard in
    the literature and sound in principle; it is inert here because the current
    field it needs does not exist yet.
    """

    tile: str
    date_a: str
    date_b: str
    candidates_labelled: int

    baseline_f1: float
    with_check_f1: float
    baseline_recall: float
    with_check_recall: float

    rejections: int = Field(description="Candidates the check disqualified")
    true_debris_lost: int = Field(description="Of those, ones that were real debris")
    transients_found: int = Field(
        description="Detections seen once and gone — the signal the check exists to catch"
    )
    current_speed_ms: float | None = Field(
        default=None,
        description="Current speed available to the coherence test. None is the "
        "whole problem: the envelope collapses to its 5 km floor.",
    )

    @property
    def f1_delta(self) -> float:
        """Negative today. That is the finding, not a bug in the arithmetic."""
        return self.with_check_f1 - self.baseline_f1

    @property
    def recall_delta(self) -> float:
        return self.with_check_recall - self.baseline_recall

    @property
    def contributes(self) -> bool:
        return self.f1_delta > 0


#: Why FR-2.2 measures as it does. Straight from eval/results.md, which is the
#: authority — this module reads, it never re-derives.
MULTITEMPORAL_CAVEATS = [
    "Structurally blocked on FR-3.1. The coherence test allows current_speed x "
    "dt + 5 km, and with no OSCAR field loaded that collapses to the 5 km floor "
    "— while real debris at 0.1 m/s covers ~43 km between passes 5 days apart. "
    "It rejects genuine drift as incoherent motion.",
    "Zero transients in every pair, so the check's strongest signal never fired. "
    "Nearest-neighbour pairing re-observed everything, which cannot separate "
    "'this patch persisted' from 'some other detection is nearby'.",
    "Tiny samples — 12 and 7 labelled candidates on the two usable pairs. None "
    "of these deltas would survive a significance test.",
    "For PRD 12: on current evidence removing this check would not degrade the "
    "pipeline, it would slightly improve recall. That contradicts the "
    "every-agent-is-load-bearing design test and is stated rather than hidden.",
]


class GeneralisationResult(BaseModel):
    """What an unseen region costs the detector — the qualifier region recall needs.

    Region recall is a **within-tile** number: MARIDA splits by patch, not by
    tile, so 327 of the 359 test patches sit on ground the model trained on. On
    its own it reads as evidence that the detector generalises, which it is not.
    This is the paired measurement that says what generalisation actually costs,
    and it belongs beside region recall for the same reason region recall
    belongs beside the precision gain.
    """

    region: str = Field(description="MGRS tile withheld from train and val")
    patches: int = Field(description="Patches both models were scored on — identical set")
    debris_px_per_patch: float

    trained_precision: float
    trained_recall: float
    trained_f1: float

    unseen_precision: float
    unseen_recall: float
    unseen_f1: float

    @property
    def precision_cost(self) -> float:
        return self.unseen_precision - self.trained_precision

    @property
    def recall_cost(self) -> float:
        return self.unseen_recall - self.trained_recall

    @property
    def f1_cost(self) -> float:
        return self.unseen_f1 - self.trained_f1


#: Straight from eval/results.md. The first entry is the one an evaluator is
#: most likely to get wrong unaided, so it leads.
GENERALISATION_CAVEATS = [
    "Do not subtract the holdout model's rest-of-test score from its 18QYF "
    "score. 18QYF carries 13.24 debris px/patch against 0.98 for the rest of "
    "test, so that subtraction measures task difficulty rather than "
    "distribution shift, and it comes out the wrong sign (-0.194). Only the "
    "paired table here, where both models see identical patches, isolates the "
    "effect of the region being unseen.",
    "The holdout model trained on 8.5% less data (635 vs 694 patches), so part "
    "of the cost is less training data rather than the region being unseen. "
    "The figure is an UPPER bound on the true generalisation cost.",
    "Haiti shares the demo region's current system and water type. This "
    "measures generalisation to an unseen TILE in the western Caribbean, not to "
    "a different ocean. Southeast Asian tiles would be the harder test.",
    "One region, one seed, no repeats. 18QYF was chosen as the documented "
    "stretch region and MARIDA's densest debris, not drawn at random, so this "
    "is a single measurement rather than a confidence interval.",
    "It does not on its own license the Gulf of Gonave stretch goal — it says "
    "detection would likely transfer, and nothing about drift or attribution.",
]


class BenchmarkReport(BaseModel):
    """Everything the console needs to show measured quality honestly."""

    available: bool
    unavailable_reason: str | None = None

    dataset: str = DATASET
    dataset_version: str = DATASET_VERSION
    dataset_doi: str = DATASET_DOI
    source_file: str = "eval/marida_ablation.json"
    results_doc: str = RESULTS_DOC

    fdi_threshold: float | None = Field(
        default=None,
        description="Detector threshold these numbers were measured at. Compare "
        "against a run artefact's provenance.fdi_threshold before reading them as "
        "descriptive of that run.",
    )
    # The FDI ablation. Correct, and correct *for the FDI* — kept as the
    # baseline pair the report has always carried. The console renders from
    # `detectors` instead, so a CNN run is never described by these.
    detector: DetectorRecall | None = None
    verification: VerificationDelta | None = None

    detectors: list[DetectorBenchmark] = Field(
        default_factory=list,
        description="One entry per measured detector. The console selects the "
        "one matching the run being displayed.",
    )
    verification_overlap: str | None = None

    multi_temporal: MultiTemporalResult | None = None
    multi_temporal_caveats: list[str] = Field(default_factory=list)
    generalisation: GeneralisationResult | None = None
    generalisation_caveats: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialise with the derived gains included.

        The UI needs `precision_gain`, `regions_missed` and the false-positive
        rates; recomputing them in TypeScript would be a second place for the
        arithmetic to be wrong.
        """
        data = super().model_dump(**kwargs)
        if self.detector is not None:
            data["detector"]["regions_missed"] = self.detector.regions_missed
        for entry, dumped in zip(self.detectors, data.get("detectors", []), strict=False):
            dumped["regions_missed"] = entry.regions_missed
            dumped["verification"].update(
                precision_gain=entry.verification.precision_gain,
                f1_gain=entry.verification.f1_gain,
                recall_cost=entry.verification.recall_cost,
                baseline_false_positive_rate=entry.verification.baseline_false_positive_rate,
                verified_false_positive_rate=entry.verification.verified_false_positive_rate,
            )
        if self.multi_temporal is not None:
            data["multi_temporal"].update(
                f1_delta=self.multi_temporal.f1_delta,
                recall_delta=self.multi_temporal.recall_delta,
                contributes=self.multi_temporal.contributes,
            )
        if self.generalisation is not None:
            data["generalisation"].update(
                precision_cost=self.generalisation.precision_cost,
                recall_cost=self.generalisation.recall_cost,
                f1_cost=self.generalisation.f1_cost,
            )
        if self.verification is not None:
            data["verification"].update(
                precision_gain=self.verification.precision_gain,
                f1_gain=self.verification.f1_gain,
                recall_cost=self.verification.recall_cost,
                baseline_false_positive_rate=self.verification.baseline_false_positive_rate,
                verified_false_positive_rate=self.verification.verified_false_positive_rate,
            )
        return data


def _unavailable(reason: str) -> BenchmarkReport:
    return BenchmarkReport(available=False, unavailable_reason=reason, caveats=[])


def _verification_from_block(block: dict[str, Any], split: str) -> VerificationDelta | None:
    metrics = block.get("metrics") or {}
    if "baseline_precision" not in metrics or "verified_precision" not in metrics:
        return None
    return VerificationDelta(
        split=split,
        scored=int(metrics.get("n_labelled", 0)),
        excluded_unlabelled=int(block.get("detections_unlabelled_excluded", 0)),
        baseline_precision=float(metrics["baseline_precision"]),
        verified_precision=float(metrics["verified_precision"]),
        baseline_recall=float(metrics.get("baseline_recall", 0.0)),
        verified_recall=float(metrics.get("verified_recall", 0.0)),
        baseline_f1=float(metrics.get("baseline_f1", 0.0)),
        verified_f1=float(metrics.get("verified_f1", 0.0)),
    )


def load_detector_benchmarks(
    files: dict[str, Path] | None = None,
) -> list[DetectorBenchmark]:
    """Read the per-detector results, skipping any that are not measured here.

    Missing files are skipped rather than raising: a checkout where only the
    FDI has been evaluated should still show the FDI honestly.
    """
    files = files if files is not None else DETECTOR_FILES
    out: list[DetectorBenchmark] = []
    for key, path in files.items():
        if not Path(path).is_file():
            continue
        try:
            raw = json.loads(Path(path).read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Detector results at %s are unreadable: %s", path, exc)
            continue

        split = str(raw.get("split", "test"))
        verification = _verification_from_block(raw, split)
        if verification is None or raw.get("debris_regions") is None:
            logger.warning("%s has no usable metrics block; skipping.", path)
            continue

        out.append(
            DetectorBenchmark(
                detector=str(raw.get("detector", key)),
                label=DETECTOR_LABELS.get(key, key.upper()),
                candidates_emitted=int(raw.get("detections_total", 0)),
                detector_precision=float((raw.get("metrics") or {})["baseline_precision"]),
                regions=int(raw["debris_regions"]),
                regions_hit=int(raw.get("debris_regions_hit", 0)),
                region_recall=float(raw.get("region_recall", 0.0)),
                verification=verification,
            )
        )
    return out


def load_multitemporal(path: Path | None = None) -> MultiTemporalResult | None:
    """Read the FR-2.2 result, or return None if it has not been measured here.

    Returns None rather than raising: a console without this file should show
    the FR-2.4 gain and say the multi-temporal number is unavailable, not fail
    to boot. Like the rest of this module it reshapes and never recomputes —
    `eval/results.md` is the authority.
    """
    path = Path(path or MULTITEMPORAL_FILE)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Multi-temporal results at %s are unreadable: %s", path, exc)
        return None

    pair = raw.get("pair") or {}
    before = raw.get("spectral_only") or {}
    after = raw.get("with_multi_temporal") or {}
    if "f1" not in before or "f1" not in after:
        logger.warning("%s has no before/after F1 block; skipping.", path)
        return None

    return MultiTemporalResult(
        tile=str(pair.get("tile", "unknown")),
        date_a=str(pair.get("date_a", "")),
        date_b=str(pair.get("date_b", "")),
        candidates_labelled=int(raw.get("candidates_labelled", 0)),
        baseline_f1=float(before["f1"]),
        with_check_f1=float(after["f1"]),
        baseline_recall=float(before.get("recall", 0.0)),
        with_check_recall=float(after.get("recall", 0.0)),
        rejections=int(raw.get("marginal_rejections", 0)),
        true_debris_lost=int(raw.get("marginal_true_debris_lost", 0)),
        transients_found=int(raw.get("transient", 0)),
        current_speed_ms=_as_float(raw.get("current_speed_ms")),
    )


def load_generalisation(
    trained: Path | None = None, unseen: Path | None = None
) -> GeneralisationResult | None:
    """Read the paired holdout experiment. Both arms or nothing.

    The comparison is only meaningful because the two models are scored on the
    same patches, so a pair where that stopped being true is refused rather than
    reported — a mismatched pair would look like a generalisation result and be
    a difference in task difficulty instead.
    """
    trained = trained or GENERALISATION_TRAINED_FILE
    unseen = unseen or GENERALISATION_UNSEEN_FILE

    blocks = {}
    for label, path in (("trained", trained), ("unseen", unseen)):
        if not Path(path).exists():
            logger.info("Generalisation arm %s missing at %s; skipping.", label, path)
            return None
        try:
            raw = json.loads(Path(path).read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Generalisation arm %s at %s is unreadable: %s", label, path, exc)
            return None
        block = raw.get("holdout") or {}
        if "debris_f1" not in block:
            logger.warning("%s carries no holdout block; skipping generalisation.", path)
            return None
        blocks[label] = (raw, block)

    (_, a), (unseen_raw, b) = blocks["trained"], blocks["unseen"]
    if a.get("patches") != b.get("patches"):
        logger.warning(
            "Generalisation arms are not paired (%s vs %s patches); refusing to report.",
            a.get("patches"),
            b.get("patches"),
        )
        return None

    tiles = unseen_raw.get("holdout_tiles") or ["unknown"]
    return GeneralisationResult(
        region=str(tiles[0]),
        patches=int(a.get("patches", 0)),
        debris_px_per_patch=float(a.get("debris_px_per_patch", 0.0)),
        trained_precision=float(a["debris_precision"]),
        trained_recall=float(a["debris_recall"]),
        trained_f1=float(a["debris_f1"]),
        unseen_precision=float(b["debris_precision"]),
        unseen_recall=float(b["debris_recall"]),
        unseen_f1=float(b["debris_f1"]),
    )


def load_benchmark(path: Path | None = None) -> BenchmarkReport:
    """Read the ablation results, or say plainly why there are none.

    A missing or malformed file is not an error the console should die on — the
    app still serves runs, it just cannot claim measured quality. It says so
    instead of showing a blank strip or, worse, zeroes.
    """
    path = Path(path or BENCHMARK_FILE)
    if not path.is_file():
        return _unavailable(
            f"No measured results at {path.name}. Re-run them on the workstation: "
            "`python scripts/eval_marida.py --fit --split test "
            "--json eval/marida_ablation.json` (needs MARIDA, which is "
            "workstation-only)."
        )

    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Benchmark file %s is unreadable: %s", path, exc)
        return _unavailable(f"{path.name} could not be read: {exc}")

    fitted = raw.get("held_out_fitted")
    if not isinstance(fitted, dict):
        return _unavailable(
            f"{path.name} has no `held_out_fitted` block, so the fitted-threshold "
            "result it should carry is missing. Re-run the evaluation."
        )

    metrics = fitted.get("metrics") or {}
    split = str(fitted.get("split", "unknown"))

    detector = None
    if fitted.get("debris_regions") is not None:
        detector = DetectorRecall(
            split=split,
            regions=int(fitted["debris_regions"]),
            regions_hit=int(fitted.get("debris_regions_hit", 0)),
            region_recall=float(fitted.get("region_recall", 0.0)),
        )

    verification = None
    if "baseline_precision" in metrics and "verified_precision" in metrics:
        verification = VerificationDelta(
            split=split,
            scored=int(metrics.get("n_labelled", 0)),
            excluded_unlabelled=int(fitted.get("detections_unlabelled_excluded", 0)),
            baseline_precision=float(metrics["baseline_precision"]),
            verified_precision=float(metrics["verified_precision"]),
            baseline_recall=float(metrics.get("baseline_recall", 0.0)),
            verified_recall=float(metrics.get("verified_recall", 0.0)),
            baseline_f1=float(metrics.get("baseline_f1", 0.0)),
            verified_f1=float(metrics.get("verified_f1", 0.0)),
        )

    if detector is None and verification is None:
        return _unavailable(
            f"{path.name} carries neither a region-recall nor a precision/recall "
            "result. Re-run the evaluation."
        )

    multi_temporal = load_multitemporal()
    generalisation = load_generalisation()
    detectors = load_detector_benchmarks()
    return BenchmarkReport(
        available=True,
        fdi_threshold=_as_float(fitted.get("fdi_threshold", raw.get("fitted_fdi_threshold"))),
        detector=detector,
        verification=verification,
        detectors=detectors,
        # Only meaningful once more than one detector has been measured; before
        # that there is no second number to mistake the first one for.
        verification_overlap=VERIFICATION_OVERLAP_NOTE if len(detectors) > 1 else None,
        multi_temporal=multi_temporal,
        multi_temporal_caveats=list(MULTITEMPORAL_CAVEATS) if multi_temporal else [],
        generalisation=generalisation,
        generalisation_caveats=list(GENERALISATION_CAVEATS) if generalisation else [],
        caveats=list(CAVEATS),
    )


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=4)
def _cached(path: str, mtime: float) -> BenchmarkReport:
    return load_benchmark(Path(path))


def cached_benchmark(path: Path | None = None) -> BenchmarkReport:
    """:func:`load_benchmark`, re-reading only when the file changes on disk."""
    path = Path(path or BENCHMARK_FILE)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return load_benchmark(path)
    return _cached(str(path), mtime)
