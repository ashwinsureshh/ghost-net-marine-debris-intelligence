"""Run artefacts — the contract between the workstation and the deployed app.

PRD §9.1: the datasets cannot be deployed (MARIDA ~5.5 GB, tiles larger, free
tier only), so the workstation runs the expensive half of the pipeline offline
over real imagery and exports **one JSON artefact per region/window**. The
deployed server reads that artefact and recomputes only prioritisation
(FR-6.1/6.2) live.

**This module is the schema both sides code against.** The workstation writes
with :func:`export_run`; the server reads with :func:`load_artefact`. Changing a
field here changes what the other machine must produce, so bump
:data:`SCHEMA_VERSION` and say so in the Status Log.

What an artefact deliberately does and does not carry:

* **Carries everything needed to explain a decision** — detections, every
  verification check with its reason (including the rejections), trajectories
  with their envelopes, attributions, vessel correlations, and the evidence
  refs behind all of it. PRD §8 makes the evidence trail and the rejected
  detections first-class, so they travel with the artefact rather than being
  reconstructable only on the workstation.
* **Carries its own provenance** — thresholds, detector settings, dataset
  sources, code version, and whether inputs were real or synthetic. An operator
  looking at a plan must be able to see which run produced it and under what
  settings (PRD §8 reproducibility).
* **Does NOT carry a dispatch plan.** The plan is a function of vessel capacity
  and which agents are active, both of which the operator changes in the UI.
  Freezing one here would make the app a static page; recomputing it live is
  what keeps real work server-side.
* **Does NOT carry imagery.** No pixels, no band arrays — only the derived
  detections. That is what keeps an artefact a few hundred KB instead of GB.
"""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ghostnet.agents.detection import DEFAULT_FDI_THRESHOLD, DEFAULT_MIN_PIXELS
from ghostnet.agents.prioritisation import ProtectedArea
from ghostnet.agents.verification import DEFAULT_THRESHOLDS, VerificationThresholds
from ghostnet.schemas import (
    Detection,
    SourceAttribution,
    Trajectory,
    VerificationResult,
    VesselCorrelation,
)

# 1.1 added ProtectedArea.circle_fit — how well a centroid-and-radius circle
# stands in for the real WDPA polygon. Additive and optional, so a 1.0 artefact
# still reads (load_artefact gates on the major version only).
SCHEMA_VERSION = "1.1"
ARTEFACT_SUFFIX = ".run.json"


class RunProvenance(BaseModel):
    """Where this run came from and under what settings — PRD §8."""

    generated_at: datetime
    generated_on: str = Field(description="Machine role that produced it: workstation | laptop")
    ghostnet_version: str
    git_commit: str | None = None

    inputs_are_synthetic: bool = Field(
        description="True for demo/fixture runs. The UI must say so on its face."
    )
    tile_ids: list[str] = Field(default_factory=list)
    tile_count: int = 0
    dataset_sources: dict[str, str] = Field(
        default_factory=dict,
        description="Dataset key -> how it was obtained, e.g. {'oscar': 'PO.DAAC 2026-03'}",
    )

    fdi_threshold: float = DEFAULT_FDI_THRESHOLD
    min_pixels: int = DEFAULT_MIN_PIXELS
    verification_thresholds: dict[str, float] = Field(default_factory=dict)
    drift_ensemble_size: int = 0
    drift_seed: int = 0

    notes: list[str] = Field(
        default_factory=list,
        description="Anything an operator should know: degradations, missing inputs, caveats.",
    )


class RunRegion(BaseModel):
    """The monitored region and time window this run covers."""

    id: str
    name: str = ""
    bbox: tuple[float, float, float, float] | None = Field(
        default=None, description="[min_lon, min_lat, max_lon, max_lat]"
    )
    window_start: datetime | None = None
    window_end: datetime | None = None


class RunArtefact(BaseModel):
    """One precomputed pipeline run, everything except the dispatch plan.

    Sized to be served whole over a free-tier connection: a few hundred KB for a
    realistic region/window. If an artefact grows past a megabyte or two, drop
    trajectory step resolution before dropping evidence or rejections — those
    two are the point of the interface (PRD §9.1).
    """

    schema_version: str = SCHEMA_VERSION
    run_id: str
    region: RunRegion
    provenance: RunProvenance

    detections: list[Detection] = Field(default_factory=list)
    verifications: list[VerificationResult] = Field(default_factory=list)
    backward: dict[str, Trajectory] = Field(default_factory=dict)
    forward: dict[str, Trajectory] = Field(default_factory=dict)
    attributions: dict[str, SourceAttribution] = Field(default_factory=dict)
    correlations: dict[str, VesselCorrelation] = Field(default_factory=dict)
    protected_areas: list[ProtectedArea] = Field(
        default_factory=list,
        description="Clipped MPA extract for this region — small, so it travels with the run.",
    )
    degradations: list[str] = Field(default_factory=list)

    # -- convenience accessors used by the server and the tests ------------

    @property
    def verified_ids(self) -> list[str]:
        return [v.detection_id for v in self.verifications if v.verified]

    @property
    def rejected(self) -> list[VerificationResult]:
        """The Verification Agent's measured contribution — never hide these."""
        return [v for v in self.verifications if not v.verified]

    def detections_by_id(self) -> dict[str, Detection]:
        return {d.id: d for d in self.detections}

    def verifications_by_id(self) -> dict[str, VerificationResult]:
        return {v.detection_id: v for v in self.verifications}

    def coverage_summary(self) -> dict[str, Any]:
        """Small map metadata; AOI is a request extent, not cloud-free coverage."""
        def valid(value):
            return (isinstance(value, (list, tuple)) and len(value) == 4
                    and all(type(v) in (int, float) and math.isfinite(v) for v in value)
                    and -180 <= value[0] < value[2] <= 180
                    and -90 <= value[1] < value[3] <= 90)

        bounds, scope = None, "unknown"
        for note in self.provenance.notes:
            match = re.match(r"^Imagery covers AOI (\[[^\]]+\])", note)
            if not match:
                continue
            try:
                value = json.loads(match[1])
            except ValueError:
                continue
            if valid(value):
                bounds, scope = value, "requested-aoi"
                break
        if bounds is None and valid(self.region.bbox):
            bounds, scope = self.region.bbox, "region"
        return {
            "runId": self.run_id, "name": self.region.name or self.region.id,
            "bounds": bounds, "scope": scope,
            "start": self.region.window_start.isoformat() if self.region.window_start else None,
            "end": self.region.window_end.isoformat() if self.region.window_end else None,
            "detections": len(self.detections),
            "synthetic": self.provenance.inputs_are_synthetic,
            "partial": bool(self.degradations),
        }

    def summary(self) -> dict[str, Any]:
        """Counts for the run picker and the header strip."""
        return {
            "run_id": self.run_id,
            "coverage": self.coverage_summary(),
            "input_status": "synthetic" if self.provenance.inputs_are_synthetic else (
                "partial" if self.degradations else "complete"),
            "region_id": self.region.id,
            "region_name": self.region.name or self.region.id,
            "generated_at": self.provenance.generated_at.isoformat(),
            "inputs_are_synthetic": self.provenance.inputs_are_synthetic,
            "detections": len(self.detections),
            "verified": len(self.verified_ids),
            "rejected": len(self.rejected),
            "trajectories": len(self.forward),
            "attributions": len(self.attributions),
            "correlations": len(self.correlations),
            "has_mpa_data": bool(self.protected_areas),
            "degradations": len(self.degradations),
            # Lightweight context for the Regions view, so it never has to load
            # every full artefact. All of it is read off this artefact.
            "degradation_notes": list(self.degradations),
            # Only a note that affirmatively says the checkpoint withheld this
            # region's tiles counts; "NOT ESTABLISHED" and silence both mean no.
            "geographic_holdout": any(
                n.startswith("GEOGRAPHIC HOLDOUT.") for n in self.provenance.notes),
            # Dates on which a candidate was recorded: not every acquisition,
            # so a date missing here is not evidence of a cloudy or empty scene.
            "candidate_dates": self._candidate_dates(),
            "failed_checks": self._failed_check_counts(),
        }

    def _candidate_dates(self) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for detection in self.detections:
            day = detection.acquired_at.date().isoformat()
            counts[day] = counts.get(day, 0) + 1
        return [{"date": day, "candidates": n} for day, n in sorted(counts.items())]

    def _failed_check_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for verification in self.rejected:
            for check in verification.checks:
                if check.disqualified:
                    counts[check.name] = counts.get(check.name, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def export_run(
    run: Any,
    *,
    run_id: str,
    region: RunRegion,
    generated_on: str,
    inputs_are_synthetic: bool,
    dataset_sources: dict[str, str] | None = None,
    protected_areas: list[ProtectedArea] | None = None,
    thresholds: VerificationThresholds = DEFAULT_THRESHOLDS,
    fdi_threshold: float = DEFAULT_FDI_THRESHOLD,
    min_pixels: int = DEFAULT_MIN_PIXELS,
    git_commit: str | None = None,
    notes: list[str] | None = None,
) -> RunArtefact:
    """Turn a :class:`ghostnet.pipeline.PipelineRun` into a portable artefact.

    ``run`` is typed loosely so this module does not import the pipeline (and
    therefore LangGraph) — the workstation exporter needs neither.
    """
    from ghostnet import __version__

    ids = [d.id for d in run.detections]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate detection IDs: fix source acquisition identity before export")

    ensemble = 0
    seed = 0
    any_track = next(iter(run.forward.values()), None) or next(iter(run.backward.values()), None)
    if any_track is not None:
        ensemble, seed = any_track.ensemble_size, any_track.seed

    provenance = RunProvenance(
        generated_at=datetime.now(UTC),
        generated_on=generated_on,
        ghostnet_version=__version__,
        git_commit=git_commit,
        inputs_are_synthetic=inputs_are_synthetic,
        tile_ids=sorted({d.tile_id for d in run.detections}),
        tile_count=len({d.tile_id for d in run.detections}),
        dataset_sources=dataset_sources or {},
        fdi_threshold=fdi_threshold,
        min_pixels=min_pixels,
        verification_thresholds=_thresholds_as_dict(thresholds),
        drift_ensemble_size=ensemble,
        drift_seed=seed,
        notes=list(notes or []),
    )

    return RunArtefact(
        run_id=run_id,
        region=region,
        provenance=provenance,
        detections=list(run.detections),
        verifications=list(run.verifications),
        backward=dict(run.backward),
        forward=dict(run.forward),
        attributions=dict(run.attributions),
        correlations=dict(run.correlations),
        protected_areas=list(protected_areas or []),
        degradations=list(run.degradations),
    )


def _thresholds_as_dict(thresholds: VerificationThresholds) -> dict[str, float]:
    return {
        field: float(getattr(thresholds, field))
        for field in thresholds.__dataclass_fields__  # type: ignore[attr-defined]
    }


def write_artefact(artefact: RunArtefact, directory: Path, *, indent: int | None = None) -> Path:
    """Write ``<run_id>.run.json`` and return the path.

    Compact by default. These files are read by the console and by
    :func:`load_artefact`, never by eye — a real run is hundreds of detections
    with their full check reasoning — and pretty-printing one costs a third of
    its size in whitespace: the first real Gulf of Honduras export was 4.59 MB
    indented against 2.85 MB compact. Since the artefact has to be committed for
    the deployed console to serve it, that third is paid on every clone forever.

    Pass ``indent=2`` when you genuinely want to read one by hand; nothing about
    the content changes, and ``load_artefact`` accepts either.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{artefact.run_id}{ARTEFACT_SUFFIX}"
    # encoding is EXPLICIT, and that is not pedantry. write_text() defaults to
    # the platform encoding: cp1252 on the Windows workstation that produces
    # these files, UTF-8 on the MacBook Air and in the Linux container that
    # consume them. The region name contains an em dash, so an artefact written
    # here round-tripped fine ON THIS MACHINE and was undecodable everywhere
    # else -- the deployed console would have failed on the first real run.
    path.write_text(artefact.model_dump_json(indent=indent), encoding="utf-8")
    return path


def load_artefact(path: Path) -> RunArtefact:
    """Read one artefact, refusing a schema major version we cannot read."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    found = str(raw.get("schema_version", "0"))
    if found.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        raise ValueError(
            f"{path} declares run-artefact schema {found}, but this build reads "
            f"{SCHEMA_VERSION}. Re-export it from the workstation, or check out "
            "the matching commit — silently reading a stale artefact would "
            "misreport what the agents did."
        )
    return RunArtefact.model_validate(raw)


def discover_artefacts(directory: Path) -> list[Path]:
    """All artefacts in a directory, newest filename last."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(directory.glob(f"*{ARTEFACT_SUFFIX}"))
