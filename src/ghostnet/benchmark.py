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
RESULTS_DOC = "eval/results.md"

DATASET = "MARIDA"
DATASET_VERSION = "v1.0.0"
DATASET_DOI = "10.5281/zenodo.5151941"

#: Read before quoting any of this on screen. Lifted from `eval/results.md` so
#: the console and the report say the same thing about the same numbers.
CAVEATS = [
    "Measured on the held-out MARIDA test split (12 global regions), not on this "
    "run's region or imagery. Thresholds were fitted on the train split only.",
    "Region recall is the detector's alone and is unaffected by verification: the "
    "FDI baseline lands on 96 of 236 annotated debris regions. Improving it is the "
    "CNN variant's job (FR-1.4), which is not built.",
    "Precision and recall are conditioned on the candidates the detector emitted, "
    "so baseline recall reads 1.0 by construction. Region recall is the meaningful "
    "detector-recall number — quote the two together.",
    "Multi-temporal consistency (FR-2.2) is unmeasured: MARIDA patches carry no "
    "repeat passes, so that check is inconclusive throughout and contributes "
    "nothing to the gain shown here.",
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
    detector: DetectorRecall | None = None
    verification: VerificationDelta | None = None
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

    return BenchmarkReport(
        available=True,
        fdi_threshold=_as_float(fitted.get("fdi_threshold", raw.get("fitted_fdi_threshold"))),
        detector=detector,
        verification=verification,
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
