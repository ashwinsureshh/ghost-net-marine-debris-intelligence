"""Live prioritisation over a precomputed run artefact (FR-6.1/6.2).

This is the work the deployed server actually does. Everything upstream —
detection, verification, drift, attribution, vessel correlation — was computed
on the workstation against data that cannot be deployed; prioritisation is pure
scoring over those outputs, so it is cheap enough to run per request on a free
tier and it is what the operator's controls change.

**Ablation semantics must match ``ghostnet.pipeline`` exactly.** The app lets an
evaluator switch agents off (PRD §12), and if "verification off" meant something
different here than in the offline pipeline, the demo would contradict
eval/results.md. So each ablation below drops the same information the pipeline
node would have failed to produce, and emits the same kind of explicit
degradation note rather than silently scoring differently.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ghostnet.agents.prioritisation import DEFAULT_WEIGHTS, build_plan, score_detection
from ghostnet.export import RunArtefact
from ghostnet.llm import RationaleWriter
from ghostnet.pipeline import AGENT_NAMES
from ghostnet.schemas import DispatchPlan, PriorityScore

# Agents an operator can switch off in the deployed app. `detection` is
# excluded on purpose: with it off there is nothing to serve at all, which is a
# true but useless screen — the offline ablation study in the pipeline covers
# that arm, and eval/results.md reports it.
ABLATABLE = tuple(a for a in AGENT_NAMES if a != "detection")


@dataclass
class PlanningRequest:
    vessel_capacity: int = 3
    planning_horizon_days: int = 7
    ablate: frozenset[str] = frozenset()
    weights: dict[str, float] | None = None
    include_rationales: bool = True

    def __post_init__(self) -> None:
        unknown = set(self.ablate) - set(ABLATABLE)
        if unknown:
            raise ValueError(
                f"Cannot ablate {sorted(unknown)} here; the deployed app can "
                f"switch off {list(ABLATABLE)}. Detection is excluded because "
                "with it off there is no run to serve."
            )
        if self.vessel_capacity < 0:
            raise ValueError("vessel_capacity cannot be negative")
        if self.planning_horizon_days < 1:
            raise ValueError("planning_horizon_days must be at least 1")


@dataclass
class PlanningResult:
    plan: DispatchPlan | None
    scores: list[PriorityScore] = field(default_factory=list)
    degradations: list[str] = field(default_factory=list)
    considered: int = 0
    ablated: list[str] = field(default_factory=list)


def plan_from_artefact(
    artefact: RunArtefact,
    request: PlanningRequest,
    *,
    rationale_writer: RationaleWriter | None = None,
) -> PlanningResult:
    """Recompute the ranked, capacity-bounded dispatch plan for one artefact."""
    ablate = set(request.ablate)
    degradations = list(artefact.degradations)

    if "prioritisation" in ablate:
        degradations.append(
            "prioritisation ABLATED: no ranked, capacity-bounded plan. The "
            "operator is handed an unordered pile of verified detections and "
            "must decide unaided — the pre-existing state of the art this "
            "project exists to improve on (PRD §2)."
        )
        return PlanningResult(
            plan=None, degradations=degradations, ablated=sorted(ablate)
        )

    detections_by_id = artefact.detections_by_id()
    verifications = artefact.verifications_by_id()

    if "verification" in ablate:
        # Same as the pipeline's baseline arm: the raw detector's output passes
        # through, false positives included.
        candidate_ids = [d.id for d in artefact.detections]
        verifications = {}
        degradations.append(
            "verification ABLATED: raw detector output passes through "
            "unfiltered. On this run that is "
            f"{len(candidate_ids)} candidates instead of "
            f"{len(artefact.verified_ids)} — the extra ones are the bright SWIR "
            "targets, bright water surfaces, floating vegetation and cloud the "
            "agent would have disqualified."
        )

        # Honesty about what this arm can and cannot show. The workstation runs
        # drift, attribution and vessel correlation *downstream* of
        # verification, so an artefact carries those outputs only for
        # detections that passed. Re-admitting the rejected ones here gives
        # them no trajectory and no source, which flatters them less than a
        # true no-verification pipeline run would. Say so rather than let the
        # screen imply this reproduces eval/results.md.
        missing_upstream = sum(
            1
            for detection_id in candidate_ids
            if detection_id not in artefact.verified_ids
            and detection_id not in artefact.forward
        )
        if missing_upstream:
            degradations.append(
                f"CAVEAT on this arm: {missing_upstream} re-admitted candidate(s) "
                "have no drift, source or vessel evidence, because the offline "
                "run computed those only for detections that passed "
                "verification. Their scores here are therefore lower than a "
                "true verification-off pipeline run would give them, which "
                "understates the damage. The measured FR-2.4 result "
                "(precision 0.238 -> 0.623 on MARIDA) is in eval/results.md; "
                "this control is for showing what reaches the plan, not for "
                "re-measuring the agent."
            )
    else:
        candidate_ids = list(artefact.verified_ids)

    forwards = {} if "drift" in ablate else dict(artefact.forward)
    attributions = {} if "attribution" in ablate else dict(artefact.attributions)
    correlations = {} if "vessels" in ablate else dict(artefact.correlations)

    if "drift" in ablate:
        degradations.append(
            "drift ABLATED: no trajectories, so prioritisation loses its "
            "drift-urgency component — the plan can no longer say whether a "
            "patch is heading for a protected area. Source attribution also "
            "has no backtrack to cross-reference (FR-4.1 cannot run)."
        )
        attributions = {}
    if "attribution" in ablate:
        degradations.append(
            "attribution ABLATED: the plan can say where debris is going but "
            "not where it came from — the emission-source finding the "
            "marine-researcher persona needs (PRD §6) is gone."
        )
    if "vessels" in ablate:
        degradations.append(
            "vessels ABLATED: no dark-vessel correlation, so the ghost-gear "
            "signal that distinguishes abandoned fishing gear from generic "
            "river-borne plastic is absent from the ranking."
        )

    areas = list(artefact.protected_areas)
    if not areas:
        degradations.append(
            "No Protected Planet MPA data in this run, so ecological risk was "
            "dropped from the score and its weight redistributed — it is NOT "
            "scored zero. Ranking is provisional."
        )

    detections = {i: detections_by_id[i] for i in candidate_ids if i in detections_by_id}
    scores = [
        score_detection(
            detection,
            verification=verifications.get(detection_id),
            forward=forwards.get(detection_id),
            attribution=attributions.get(detection_id),
            correlation=correlations.get(detection_id),
            protected_areas=areas,
            weights=request.weights or DEFAULT_WEIGHTS,
            horizon_days=float(request.planning_horizon_days),
        )
        for detection_id, detection in detections.items()
    ]

    writer = rationale_writer
    if writer is None and not request.include_rationales:
        writer = RationaleWriter(enabled=False)

    plan = build_plan(
        artefact.region.id,
        detections,
        scores,
        verifications=verifications,
        forwards=forwards,
        attributions=attributions,
        correlations=correlations,
        vessel_capacity=request.vessel_capacity,
        planning_horizon_days=request.planning_horizon_days,
        rationale_writer=writer,
        caveats=degradations,
    )

    if artefact.provenance.inputs_are_synthetic:
        plan.caveats.insert(
            0,
            "This run was computed from GENERATED inputs, not satellite "
            "imagery. It demonstrates the pipeline end to end; it is not a "
            "measured result.",
        )

    return PlanningResult(
        plan=plan,
        scores=sorted(scores, key=lambda s: (-s.score, s.detection_id)),
        degradations=degradations,
        considered=len(detections),
        ablated=sorted(ablate),
    )
