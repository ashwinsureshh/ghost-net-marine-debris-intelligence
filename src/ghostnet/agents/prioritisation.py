"""FR-6 — Response Prioritisation Agent.

Combines the five upstream signals into one ranked score (FR-6.1), applies the
cleanup-vessel capacity constraint from ``config/regions.yaml`` (FR-6.2),
attaches a human-readable rationale per site (FR-6.3), and returns a plan that
is explicitly *not* approved until a named human approves it (FR-6.4).

Two design choices carry the PRD's non-functional requirements:

* **Missing signals are not zeros.** If Protected Planet boundaries are not on
  this machine, ecological risk is not scored 0 — it is dropped from the score
  and its weight redistributed over the components that *were* computed, with a
  caveat recorded on the plan. Scoring an unmeasured component as zero would
  quietly rank every site as ecologically safe, which is the most dangerous
  failure this agent could have.
* **Every score keeps its components.** ``PriorityScore.components`` and
  ``.weights`` survive into the output, so "why is this site first?" is
  answerable from the artefact without re-running anything (PRD §8).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ghostnet.config import dispatch_config, region_dataset_file
from ghostnet.geo import haversine_km
from ghostnet.llm import RationaleRequest, RationaleWriter
from ghostnet.schemas import (
    Detection,
    DispatchAssignment,
    DispatchPlan,
    Evidence,
    PriorityScore,
    SourceAttribution,
    Trajectory,
    VerificationResult,
    VesselCorrelation,
)

DEFAULT_WEIGHTS = {
    "detection_confidence": 0.30,
    "drift_urgency": 0.25,
    "ecological_risk": 0.30,
    "dark_vessel_signal": 0.15,
}
# Ecological risk decays with distance to the nearest MPA on this scale.
MPA_RISK_SCALE_KM = 50.0


@dataclass(frozen=True)
class ProtectedArea:
    """A Marine Protected Area, reduced to a centroid and an effective radius.

    A point-and-radius stand-in for the WDPA polygon: enough for ecological-risk
    ranking without pulling geopandas into the scoring path. Swap in real
    polygon containment when the Protected Planet extract is on the machine —
    :func:`nearest_protected_area` is the only function that would change.

    ``circle_fit`` records how much that stand-in costs on this particular area:
    polygon area over the area of its minimum bounding circle, so ~1.0 is a
    compact reserve the circle describes well and a low value is something long
    and thin — a barrier reef — whose modelled distances are approximate.
    ``scripts/build_region_extracts.py`` computes it; it is ``None`` for areas
    hand-written in fixtures or demos. It travels with the run artefact so an
    operator can see which ecological-risk numbers rest on a poor fit.
    """

    name: str
    lon: float
    lat: float
    radius_km: float = 0.0
    designation: str = ""
    circle_fit: float | None = None


def load_protected_areas(
    path: Path | None = None, *, region_id: str | None = None
) -> list[ProtectedArea]:
    """Load MPA boundaries from ``data/protected_planet`` (FR-6.1).

    ``path`` still wins when given, so tests and one-off inspection can point
    at a file directly. Otherwise pass ``region_id``: omitting it is only safe
    while a single extract exists, and with two present this raises rather than
    scoring a run against another region's reserves (see
    :func:`ghostnet.config.region_dataset_file`).
    """
    if path is None:
        path = region_dataset_file(
            "mpa",
            region_id=region_id,
            suffix=".json",
            purpose="Ecological-risk scoring (FR-6.1).",
            rebuild_hint=(
                "Build it with `python scripts/build_region_extracts.py mpa "
                "--region <id> --source <wdpa.gpkg>`."
            ),
        )
    with Path(path).open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return [ProtectedArea(**record) for record in raw]


def nearest_protected_area(
    lon: float, lat: float, areas: list[ProtectedArea]
) -> tuple[ProtectedArea | None, float]:
    """Return the closest MPA and the distance to its boundary in km."""
    best: tuple[ProtectedArea | None, float] = (None, float("inf"))
    for area in areas:
        distance = max(0.0, haversine_km(lon, lat, area.lon, area.lat) - area.radius_km)
        if distance < best[1]:
            best = (area, distance)
    return best


def _drift_urgency(
    forward: Trajectory | None, areas: list[ProtectedArea], horizon_days: float
) -> tuple[float, float | None, str]:
    """How soon does this patch reach something we care about?

    With MPAs loaded, urgency is time-to-MPA over the planning horizon. Without
    them, it falls back to projected displacement — a patch moving fast is more
    urgent than a stationary one because the search box grows either way.
    """
    if forward is None:
        return 0.0, None, "no forward trajectory (Drift Agent unavailable)"

    if areas:
        for point in forward.points:
            area, distance = nearest_protected_area(point.lon, point.lat, areas)
            if area is not None and distance <= point.uncertainty_km:
                days = abs((point.t - forward.points[0].t).total_seconds()) / 86400
                urgency = 1.0 - min(days / max(horizon_days, 1e-6), 1.0)
                return (
                    round(urgency, 4),
                    round(distance, 2),
                    f"projected to reach {area.name} in ~{days:.1f} days",
                )

    start, end = forward.points[0], forward.points[-1]
    displacement = haversine_km(start.lon, start.lat, end.lon, end.lat)
    # 100 km over the horizon saturates the component.
    urgency = min(displacement / 100.0, 1.0)

    # Ceiling on the displacement fallback. If MPAs *are* loaded and the track
    # intercepts none of them, we positively know nothing protected is
    # threatened, so a fast-moving patch must not outrank one actually heading
    # into a reserve. With no MPA data we know nothing, so no ceiling applies —
    # under-stating urgency there would hide a real risk.
    ceiling = 0.5 if areas else 1.0
    urgency = min(urgency, ceiling)
    basis = (
        f"projected {displacement:.0f} km displacement over "
        f"{forward.horizon_days:.0f} days"
    )
    if areas:
        basis += "; no protected area on the projected track"
    return round(urgency, 4), None, basis


def score_detection(
    detection: Detection,
    *,
    verification: VerificationResult | None,
    forward: Trajectory | None,
    attribution: SourceAttribution | None,
    correlation: VesselCorrelation | None,
    protected_areas: list[ProtectedArea] | None,
    weights: dict[str, float] | None = None,
    horizon_days: float = 7.0,
) -> PriorityScore:
    """Combine the upstream signals into one ranked priority score (FR-6.1)."""
    weights = dict(weights or DEFAULT_WEIGHTS)
    components: dict[str, float] = {}
    evidence: list[Evidence] = []

    confidence = verification.confidence if verification else detection.confidence
    components["detection_confidence"] = round(confidence, 4)
    if verification:
        evidence.extend(verification.evidence)

    areas = protected_areas or []
    urgency, mpa_km_on_track, urgency_note = _drift_urgency(forward, areas, horizon_days)
    components["drift_urgency"] = urgency
    if forward:
        evidence.extend(forward.evidence)

    nearest_km: float | None = None
    if areas:
        area, distance = nearest_protected_area(detection.lon, detection.lat, areas)
        nearest_km = round(min(distance, mpa_km_on_track or distance), 2)
        components["ecological_risk"] = round(
            math.exp(-nearest_km / MPA_RISK_SCALE_KM), 4
        )
        if area is not None:
            evidence.append(
                Evidence(
                    kind="mpa_boundary",
                    ref=area.name,
                    detail=f"{nearest_km} km from the detection ({area.designation or 'MPA'})",
                )
            )
    else:
        # Not measurable here -> drop the component rather than score it zero.
        weights.pop("ecological_risk", None)

    if correlation is not None:
        components["dark_vessel_signal"] = correlation.correlation_strength
        evidence.extend(correlation.evidence)
    else:
        weights.pop("dark_vessel_signal", None)

    if attribution is not None:
        evidence.extend(attribution.evidence)

    # Renormalise over whatever was actually measurable.
    active = {k: w for k, w in weights.items() if k in components}
    total_weight = sum(active.values())
    if total_weight <= 0:
        score = 0.0
        active = {}
    else:
        active = {k: round(w / total_weight, 4) for k, w in active.items()}
        score = sum(components[k] * w for k, w in active.items())

    return PriorityScore(
        detection_id=detection.id,
        score=round(min(1.0, max(0.0, score)), 4),
        components=components,
        weights=active,
        nearest_mpa_km=nearest_km,
        evidence=evidence + [Evidence(kind="derived", ref="prioritisation", detail=urgency_note)],
    )


def build_plan(
    region_id: str,
    detections: dict[str, Detection],
    scores: list[PriorityScore],
    *,
    verifications: dict[str, VerificationResult] | None = None,
    forwards: dict[str, Trajectory] | None = None,
    attributions: dict[str, SourceAttribution] | None = None,
    correlations: dict[str, VesselCorrelation] | None = None,
    vessel_capacity: int | None = None,
    planning_horizon_days: int | None = None,
    rationale_writer: RationaleWriter | None = None,
    caveats: list[str] | None = None,
    now: datetime | None = None,
) -> DispatchPlan:
    """Rank, bound by vessel capacity, and attach rationales (FR-6.2 – FR-6.4)."""
    config = dispatch_config()
    capacity = vessel_capacity if vessel_capacity is not None else int(config["vessel_capacity"])
    horizon = (
        planning_horizon_days
        if planning_horizon_days is not None
        else int(config["planning_horizon_days"])
    )

    ranked = sorted(scores, key=lambda s: (-s.score, s.detection_id))
    selected = ranked[:capacity]
    deferred = [s.detection_id for s in ranked[capacity:]]

    writer = rationale_writer or RationaleWriter()
    requests = []
    for score in selected:
        attribution = (attributions or {}).get(score.detection_id)
        correlation = (correlations or {}).get(score.detection_id)
        verification = (verifications or {}).get(score.detection_id)
        forward = (forwards or {}).get(score.detection_id)
        requests.append(
            RationaleRequest(
                detection_id=score.detection_id,
                score=score.score,
                components=score.components,
                verification_summary=(
                    f"passed {len(verification.checks)} false-positive checks"
                    if verification and verification.verified
                    else ""
                ),
                drift_summary=(
                    f"{forward.horizon_days:.0f}-day forward track, envelope "
                    f"{forward.endpoint.uncertainty_km:.0f} km"
                    if forward
                    else ""
                ),
                top_rivers=[
                    (c.name, c.probability)
                    for c in (attribution.candidates[:2] if attribution else [])
                ],
                dark_vessel_count=sum(v.position_resolution_deg is None
                                      for v in correlation.dark_vessels) if correlation else 0,
                unmatched_grid_observation_count=sum(v.position_resolution_deg is not None
                                      for v in correlation.dark_vessels) if correlation else 0,
                unmatched_grid_detection_count=sum(v.detection_count
                    for v in correlation.dark_vessels if v.position_resolution_deg is not None
                ) if correlation else 0,
                nearest_mpa_km=score.nearest_mpa_km,
            )
        )

    rationales = writer.write(requests)

    assignments: list[DispatchAssignment] = []
    for rank, score in enumerate(selected, start=1):
        detection = detections[score.detection_id]
        text, source = rationales.get(score.detection_id, ("", "template"))
        assignments.append(
            DispatchAssignment(
                rank=rank,
                detection_id=score.detection_id,
                vessel_id=f"vessel-{rank}",
                lon=detection.lon,
                lat=detection.lat,
                score=score.score,
                rationale=text,
                rationale_source=source,  # type: ignore[arg-type]
                evidence=score.evidence,
            )
        )

    plan_caveats = list(caveats or [])
    plan_caveats.append(
        "Decision-support research prototype validated on historical and "
        "published data — not operational-grade (PRD §8)."
    )
    if any(a.rationale_source == "template" for a in assignments):
        plan_caveats.append(
            "One or more rationales were generated offline from the deterministic "
            "template (no ANTHROPIC_API_KEY, or the API was unavailable)."
        )

    return DispatchPlan(
        region_id=region_id,
        generated_at=now or datetime.now(UTC),
        vessel_capacity=capacity,
        planning_horizon_days=horizon,
        assignments=assignments,
        deferred=deferred,
        approved=False,
        caveats=plan_caveats,
    )
