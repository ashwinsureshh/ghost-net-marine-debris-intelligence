"""Data contracts passed between the six agents.

These types are the interface the LangGraph orchestration wires together
(see ``ghostnet.pipeline``). They exist so that each agent can be developed,
tested and ablated independently (PRD §7) without the other five being
finished — a stub that returns a well-formed ``VerificationResult`` is a valid
placeholder; a stub that returns a bare dict is not.

Two PRD §8 non-functional requirements are encoded structurally rather than
left to convention:

* **Explainability** — every artefact carries ``evidence``: the specific tile,
  current field or vessel record that produced it. Nothing here has a score
  without a trail back to the data behind it.
* **Auditability** — rejections are values, not omissions. A rejected detection
  becomes a ``VerificationResult`` with ``verified=False`` and the reason that
  disqualified it; it is never silently dropped from the pipeline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EvidenceKind = Literal[
    "sentinel2_tile",
    "current_field",
    "drifter_track",
    "river_table",
    "vessel_record",
    "mpa_boundary",
    "derived",
]


class Evidence(BaseModel):
    """A pointer back to the data that produced a claim (PRD §8, §12)."""

    model_config = ConfigDict(frozen=True)

    kind: EvidenceKind
    ref: str = Field(description="Tile ID, file path, dataset row key or API record ID")
    detail: str = ""


class Detection(BaseModel):
    """A candidate debris patch from the Satellite Detection Agent (FR-1.3)."""

    id: str
    tile_id: str
    acquired_at: datetime
    lon: float
    lat: float
    area_px: int
    area_km2: float
    fdi_mean: float
    ndvi_mean: float
    confidence: float = Field(ge=0.0, le=1.0, description="Raw detector confidence")
    detector: Literal["fdi", "cnn"] = "fdi"
    evidence: list[Evidence] = Field(default_factory=list)


class CheckResult(BaseModel):
    """One documented false-positive mode, tested against one detection (FR-2.1)."""

    name: str
    disqualified: bool
    reason: str
    detail: dict[str, float] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    """Verified/rejected label with the specific reason, never a bare flag (FR-2.3)."""

    detection_id: str
    verified: bool
    checks: list[CheckResult] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)

    @property
    def rejection_reasons(self) -> list[str]:
        return [c.reason for c in self.checks if c.disqualified]


class TrajectoryPoint(BaseModel):
    """One step of a modelled trajectory, with its uncertainty (FR-3.3)."""

    t: datetime
    lon: float
    lat: float
    uncertainty_km: float = Field(
        ge=0.0, description="Radius of the ensemble spread at this step"
    )


class Trajectory(BaseModel):
    """A backward (FR-3.1) or forward (FR-3.2) drift path with an envelope."""

    detection_id: str
    direction: Literal["backward", "forward"]
    horizon_days: float
    points: list[TrajectoryPoint]
    ensemble_size: int
    seed: int = Field(description="RNG seed — the run is reproducible (PRD §8)")
    current_field: str = Field(description="Which current field drove this run")
    evidence: list[Evidence] = Field(default_factory=list)

    @property
    def endpoint(self) -> TrajectoryPoint:
        return self.points[-1]


class RiverCandidate(BaseModel):
    """One candidate source river with its posterior probability (FR-4.2)."""

    name: str
    lon: float
    lat: float
    emission_tonnes_yr: float
    distance_km: float
    probability: float = Field(ge=0.0, le=1.0)


class SourceAttribution(BaseModel):
    """A ranked distribution, never a single confident claim (PRD §13)."""

    detection_id: str
    candidates: list[RiverCandidate] = Field(default_factory=list)
    note: str = ""
    evidence: list[Evidence] = Field(default_factory=list)

    @property
    def top(self) -> RiverCandidate | None:
        return self.candidates[0] if self.candidates else None


class VesselDetection(BaseModel):
    """A SAR-detected vessel, matched or unmatched against AIS (FR-5.2)."""

    id: str
    lon: float
    lat: float
    detected_at: datetime
    length_m: float | None = None
    matched_ais_mmsi: str | None = None
    ais_matched: bool | None = None
    detection_count: int = Field(default=1, ge=1)
    position_resolution_deg: float | None = Field(default=None, gt=0)
    source: str | None = None

    @property
    def is_dark(self) -> bool:
        if self.ais_matched is not None:
            return not self.ais_matched
        return self.matched_ais_mmsi is None


class VesselCorrelation(BaseModel):
    """A research signal linking dark-vessel activity to a detection (FR-5.3).

    Deliberately *not* an accusation — PRD §5.2 puts enforcement action out of
    scope, so the disclaimer travels with the data rather than living only in
    the report template.
    """

    detection_id: str
    dark_vessels: list[VesselDetection] = Field(default_factory=list)
    matched_vessels: int = 0
    correlation_strength: float = Field(ge=0.0, le=1.0, default=0.0)
    disclaimer: str = (
        "Research signal for investigation only, not an accusation of illegal "
        "activity (PRD §5.2)."
    )
    evidence: list[Evidence] = Field(default_factory=list)


class PriorityScore(BaseModel):
    """A single ranked score whose components stay visible (FR-6.1, PRD §8)."""

    detection_id: str
    score: float = Field(ge=0.0, le=1.0)
    components: dict[str, float] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    nearest_mpa_km: float | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class DispatchAssignment(BaseModel):
    """One site on the bounded plan, with an operator-readable rationale."""

    rank: int
    detection_id: str
    vessel_id: str
    lon: float
    lat: float
    score: float
    rationale: str
    rationale_source: Literal["llm", "template"] = "template"
    evidence: list[Evidence] = Field(default_factory=list)


class DispatchPlan(BaseModel):
    """The capacity-constrained plan, pending human review (FR-6.2, FR-6.4)."""

    region_id: str
    generated_at: datetime
    vessel_capacity: int
    planning_horizon_days: int
    assignments: list[DispatchAssignment] = Field(default_factory=list)
    deferred: list[str] = Field(
        default_factory=list,
        description="Detection IDs that scored but did not fit the capacity bound",
    )
    approved: bool = False
    approved_by: str | None = None
    caveats: list[str] = Field(default_factory=list)

    def approve(self, reviewer: str) -> DispatchPlan:
        """Explicit human checkpoint — FR-6.4. No output is final without it."""
        if not reviewer.strip():
            raise ValueError("A human reviewer must be named to approve a plan.")
        return self.model_copy(update={"approved": True, "approved_by": reviewer})
