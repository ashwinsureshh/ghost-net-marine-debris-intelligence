"""LangGraph orchestration of the six agents.

    detection -> verification -> drift -> attribution -> vessels -> prioritisation

A linear graph, deliberately. The dependencies really are sequential —
attribution needs the backward trajectory, prioritisation needs everything — and
a linear graph makes the ablation study (PRD §12) mean something: removing one
node leaves a visible, explainable hole downstream rather than a silently
rerouted path.

**Ablation is a first-class feature, not a test hook.** ``PipelineConfig.ablate``
names agents to disable. An ablated node does not vanish; it runs a stub that
records *why* its output is absent, and each downstream node records how it
degraded as a result. The evaluator asked for in PRD §6 can therefore read the
failure mode off the run's ``degradations`` list instead of inferring it from a
worse number.

Machine note (MACHINE-WORKFLOW.md): everything here is CPU-only orchestration —
this is the MacBook Air's assigned work. The graph calls into agents; whether an
agent needs a GPU or a downloaded dataset is that agent's concern, and the
pipeline surfaces such failures as degradations rather than crashing the run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from ghostnet.agents import attribution as attribution_agent
from ghostnet.agents import detection as detection_agent
from ghostnet.agents import drift as drift_agent
from ghostnet.agents import prioritisation as prioritisation_agent
from ghostnet.agents import verification as verification_agent
from ghostnet.agents import vessels as vessels_agent
from ghostnet.llm import RationaleWriter
from ghostnet.schemas import (
    Detection,
    DispatchPlan,
    PriorityScore,
    SourceAttribution,
    Trajectory,
    VerificationResult,
    VesselCorrelation,
)

logger = logging.getLogger(__name__)

AGENT_NAMES = (
    "detection",
    "verification",
    "drift",
    "attribution",
    "vessels",
    "prioritisation",
)


def _merge_lists(left: list, right: list) -> list:
    return [*left, *right]


@dataclass
class PipelineConfig:
    """Everything one run needs, including which agents to switch off.

    Inputs are passed in rather than fetched: the tiles, current field, river
    table, vessel records and MPA extract each come from a dataset that may not
    exist on this machine (MACHINE-WORKFLOW.md rule 4). The caller resolves what
    it can and leaves the rest ``None``; the graph degrades explicitly.
    """

    region_id: str
    tiles: list[detection_agent.Tile] = field(default_factory=list)
    repeat_observations: dict[str, list[verification_agent.RepeatObservation]] = field(
        default_factory=dict
    )
    current_field: drift_agent.CurrentField | None = None
    river_table: attribution_agent.RiverTable | None = None
    vessel_detections: list[Any] = field(default_factory=list)
    protected_areas: list[prioritisation_agent.ProtectedArea] | None = None
    rationale_writer: RationaleWriter | None = None

    ablate: frozenset[str] = frozenset()
    backward_days: float = 5.0
    forward_days: float = 7.0
    ensemble_size: int = drift_agent.DEFAULT_ENSEMBLE
    seed: int = drift_agent.DEFAULT_SEED
    fdi_threshold: float = detection_agent.DEFAULT_FDI_THRESHOLD

    # FR-1.4. "fdi" is the spectral baseline and stays the default: it needs no
    # checkpoint and no torch, so a machine without either still runs the whole
    # pipeline. "cnn" requires models/detector_v1.pt AND tiles carrying all 11
    # MARIDA bands — ghostnet.ingest.load_tiles(..., bands=MARIDA_BANDS). The
    # FDI path loads only four, so passing FDI tiles to the CNN raises rather
    # than silently scoring on a partial stack.
    # Integration step for the drift ensemble. This is the SAMPLING interval of
    # the stored track, and raising it makes the artefact smaller: a 7-day
    # forward track at 6h is 29 points, at 12h it is 15. It is a fidelity knob,
    # not a modelling one -- the RK4 ensemble and its envelope are computed the
    # same way either side of it, we simply keep fewer samples of the result.
    # The export sets this because trajectories dominate a real artefact's size
    # (63% of the first CNN run), and MACHINE-WORKFLOW.md is explicit that
    # trajectory resolution is what to cut before evidence or rejections.
    step_hours: float = drift_agent.DEFAULT_STEP_HOURS

    detector: str = "fdi"
    cnn_checkpoint: Any | None = None
    cnn_prob_threshold: float | None = None

    def __post_init__(self) -> None:
        unknown = set(self.ablate) - set(AGENT_NAMES)
        if unknown:
            raise ValueError(
                f"Cannot ablate unknown agent(s) {sorted(unknown)}; "
                f"known agents are {list(AGENT_NAMES)}."
            )

    def is_ablated(self, agent: str) -> bool:
        return agent in self.ablate


class PipelineState(TypedDict, total=False):
    """State threaded through the graph. Rejections are kept, never dropped."""

    config: PipelineConfig
    detections: list[Detection]
    windows: dict[str, detection_agent.BandWindow]
    verifications: list[VerificationResult]
    verified_ids: list[str]
    backward: dict[str, Trajectory]
    forward: dict[str, Trajectory]
    attributions: dict[str, SourceAttribution]
    correlations: dict[str, VesselCorrelation]
    scores: list[PriorityScore]
    plan: DispatchPlan | None
    degradations: Annotated[list[str], _merge_lists]
    log: Annotated[list[str], _merge_lists]


def _note(state: PipelineState, message: str) -> str:
    logger.info(message)
    return message


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------


def node_detection(state: PipelineState) -> dict:
    """FR-1 — spectral-index detection over every tile in the run."""
    config = state["config"]
    if config.is_ablated("detection"):
        return {
            "detections": [],
            "windows": {},
            "degradations": [
                "detection ABLATED: no candidates enter the pipeline, so every "
                "downstream agent has nothing to act on. This is the expected "
                "total failure — detection is the pipeline's only data source."
            ],
            "log": ["detection: ablated"],
        }

    if not config.tiles:
        return {
            "detections": [],
            "windows": {},
            "degradations": [
                "detection: no Sentinel-2 tiles supplied. Tile ingestion is "
                "workstation work (MACHINE-WORKFLOW.md); run `python "
                "scripts/fetch_data.py --status` to confirm what is local."
            ],
            "log": ["detection: no tiles"],
        }

    detections: list[Detection] = []
    windows: dict[str, detection_agent.BandWindow] = {}

    if config.detector == "cnn":
        # Imported HERE, not at module scope. torch is workstation-only and
        # requirements-deploy.txt deliberately omits it, while this module sits
        # in the deployed server's import graph (webapp.planning imports
        # AGENT_NAMES). A module-level import would break the container build
        # at its smoke check — the same coupling ingest.py and drift.py already
        # handle this way.
        from ghostnet.agents import detection_cnn

        loaded = detection_cnn.load_detector(
            config.cnn_checkpoint or detection_cnn.DEFAULT_CHECKPOINT
        )
        prob = (
            config.cnn_prob_threshold
            if config.cnn_prob_threshold is not None
            else detection_cnn.DEFAULT_PROB_THRESHOLD
        )
        for tile in config.tiles:
            for candidate in detection_cnn.detect(
                tile, detector=loaded, prob_threshold=prob
            ):
                detections.append(candidate)
                # Windows still come from the FDI sampler: verification's
                # thresholds were fitted against REQUIRED_BANDS and are only
                # meaningful on that basis, whichever detector proposed the
                # candidate.
                windows[candidate.id] = detection_agent.sample_window(tile, candidate)
    else:
        for tile in config.tiles:
            for candidate in detection_agent.detect(
                tile, fdi_threshold=config.fdi_threshold
            ):
                detections.append(candidate)
                windows[candidate.id] = detection_agent.sample_window(tile, candidate)

    return {
        "detections": detections,
        "windows": windows,
        "log": [
            _note(
                state,
                f"detection: {len(detections)} candidate(s) from "
                f"{len(config.tiles)} tile(s) via {config.detector.upper()}",
            )
        ],
    }


def node_verification(state: PipelineState) -> dict:
    """FR-2 — disqualify candidates against documented false-positive modes."""
    config = state["config"]
    detections = state.get("detections", [])

    if config.is_ablated("verification"):
        # The ablation the PRD cares most about: everything downstream still
        # runs, but on the raw detector's output, false positives included.
        return {
            "verifications": [],
            "verified_ids": [d.id for d in detections],
            "degradations": [
                "verification ABLATED: raw detector output passes through "
                "unfiltered. Sun glint, foam, kelp and cloud shadow are all still "
                "in the candidate set, so drift, attribution and dispatch are "
                "being computed for patches that may not be debris at all. This "
                "is the FR-2.4 baseline arm of the ablation study."
            ],
            "log": ["verification: ablated (raw detections pass through)"],
        }

    results: list[VerificationResult] = []
    windows = state.get("windows", {})
    for detection in detections:
        window = windows.get(detection.id)
        if window is None:
            continue
        speed = None
        if config.current_field is not None:
            speed = drift_agent.implied_speed_ms(
                config.current_field, detection.lon, detection.lat, detection.acquired_at
            )
        results.append(
            verification_agent.verify(
                detection,
                window,
                repeats=config.repeat_observations.get(detection.id, []),
                current_speed_ms=speed,
            )
        )

    verified = [r.detection_id for r in results if r.verified]
    rejected = len(results) - len(verified)
    degradations = []
    if config.current_field is None and results:
        degradations.append(
            "verification: no current field supplied, so the multi-temporal "
            "coherence check (FR-2.2) could only test persistence, not whether "
            "motion matched the local current."
        )

    return {
        "verifications": results,
        "verified_ids": verified,
        "degradations": degradations,
        "log": [
            _note(
                state,
                f"verification: {len(verified)} verified, {rejected} rejected "
                "(rejections retained for audit)",
            )
        ],
    }


def _verified_detections(state: PipelineState) -> list[Detection]:
    wanted = set(state.get("verified_ids", []))
    return [d for d in state.get("detections", []) if d.id in wanted]


def node_drift(state: PipelineState) -> dict:
    """FR-3 — backward and forward trajectories with uncertainty envelopes."""
    config = state["config"]
    detections = _verified_detections(state)

    if config.is_ablated("drift"):
        return {
            "backward": {},
            "forward": {},
            "degradations": [
                "drift ABLATED: no trajectories. Source attribution has no "
                "backtrack to cross-reference (FR-4.1 cannot run at all), and "
                "prioritisation loses its drift-urgency component — the plan can "
                "no longer say whether a patch is heading for a protected area."
            ],
            "log": ["drift: ablated"],
        }

    if config.current_field is None:
        return {
            "backward": {},
            "forward": {},
            "degradations": [
                "drift: no current field available. NOAA OSCAR data is not on "
                "this machine — run `python scripts/fetch_data.py "
                "--instructions --dataset oscar`."
            ],
            "log": ["drift: no current field"],
        }

    backward: dict[str, Trajectory] = {}
    forward: dict[str, Trajectory] = {}
    for detection in detections:
        backward[detection.id] = drift_agent.run_trajectory(
            detection,
            config.current_field,
            direction="backward",
            horizon_days=config.backward_days,
            step_hours=config.step_hours,
            ensemble_size=config.ensemble_size,
            seed=config.seed,
        )
        forward[detection.id] = drift_agent.run_trajectory(
            detection,
            config.current_field,
            direction="forward",
            horizon_days=config.forward_days,
            step_hours=config.step_hours,
            ensemble_size=config.ensemble_size,
            seed=config.seed,
        )

    return {
        "backward": backward,
        "forward": forward,
        "log": [_note(state, f"drift: {len(backward)} backward + {len(forward)} forward")],
    }


def node_attribution(state: PipelineState) -> dict:
    """FR-4 — ranked probability distribution over candidate source rivers."""
    config = state["config"]

    if config.is_ablated("attribution"):
        return {
            "attributions": {},
            "degradations": [
                "attribution ABLATED: the plan can say where debris is going but "
                "not where it came from, so the emission-source findings the "
                "marine-researcher persona needs (PRD §6) are gone entirely."
            ],
            "log": ["attribution: ablated"],
        }

    backward = state.get("backward", {})
    if not backward:
        return {
            "attributions": {},
            "degradations": [
                "attribution: no backward trajectories to cross-reference "
                "(FR-4.1 depends on the Drift Agent's output)."
            ],
            "log": ["attribution: no backward trajectories"],
        }
    if config.river_table is None:
        return {
            "attributions": {},
            "degradations": [
                "attribution: no river-emission table available — run `python "
                "scripts/fetch_data.py --instructions --dataset rivers`."
            ],
            "log": ["attribution: no river table"],
        }

    attributions = {
        detection_id: attribution_agent.attribute(track, config.river_table)
        for detection_id, track in backward.items()
    }
    return {
        "attributions": attributions,
        "log": [_note(state, f"attribution: ranked sources for {len(attributions)} site(s)")],
    }


def node_vessels(state: PipelineState) -> dict:
    """FR-5 — dark-vessel correlation as an investigation signal."""
    config = state["config"]

    if config.is_ablated("vessels"):
        return {
            "correlations": {},
            "degradations": [
                "vessels ABLATED: no dark-vessel correlation, so the ghost-gear "
                "signal that distinguishes abandoned fishing gear from generic "
                "river-borne plastic is absent from the ranking."
            ],
            "log": ["vessels: ablated"],
        }

    if not config.vessel_detections:
        return {
            "correlations": {},
            "degradations": [
                "vessels: no GFW SAR detections supplied — run `python "
                "scripts/fetch_data.py --instructions --dataset gfw`."
            ],
            "log": ["vessels: no SAR records"],
        }

    backward = state.get("backward", {})
    correlations = {
        detection.id: vessels_agent.correlate(
            detection,
            config.vessel_detections,
            backward_trajectory=backward.get(detection.id),
        )
        for detection in _verified_detections(state)
    }
    dark = sum(len(c.dark_vessels) for c in correlations.values())
    return {
        "correlations": correlations,
        "log": [
            _note(
                state,
                f"vessels: {dark} unmatched SAR observation(s) across "
                f"{len(correlations)} site(s)",
            )
        ],
    }


def node_prioritisation(state: PipelineState) -> dict:
    """FR-6 — ranked, capacity-constrained plan awaiting human approval."""
    config = state["config"]

    if config.is_ablated("prioritisation"):
        return {
            "scores": [],
            "plan": None,
            "degradations": [
                "prioritisation ABLATED: no ranked, capacity-bounded plan. The "
                "operator is handed an unordered pile of verified detections and "
                "must decide unaided — which is the pre-existing state of the art "
                "this project exists to improve on (PRD §2)."
            ],
            "log": ["prioritisation: ablated"],
        }

    detections = {d.id: d for d in _verified_detections(state)}
    verifications = {v.detection_id: v for v in state.get("verifications", [])}
    forwards = state.get("forward", {})
    attributions = state.get("attributions", {})
    correlations = state.get("correlations", {})
    areas = config.protected_areas

    degradations: list[str] = []
    if not areas:
        degradations.append(
            "prioritisation: no Protected Planet MPA data on this machine, so "
            "ecological risk was dropped from the score and its weight "
            "redistributed (it is NOT scored zero). Ranking is provisional until "
            "`python scripts/fetch_data.py --instructions --dataset mpa` is done."
        )

    scores = [
        prioritisation_agent.score_detection(
            detection,
            verification=verifications.get(detection_id),
            forward=forwards.get(detection_id),
            attribution=attributions.get(detection_id),
            correlation=correlations.get(detection_id),
            protected_areas=areas,
            horizon_days=config.forward_days,
        )
        for detection_id, detection in detections.items()
    ]

    plan = prioritisation_agent.build_plan(
        config.region_id,
        detections,
        scores,
        verifications=verifications,
        forwards=forwards,
        attributions=attributions,
        correlations=correlations,
        rationale_writer=config.rationale_writer,
        caveats=state.get("degradations", []) + degradations,
    )

    return {
        "scores": scores,
        "plan": plan,
        "degradations": degradations,
        "log": [
            _note(
                state,
                f"prioritisation: {len(plan.assignments)} site(s) assigned, "
                f"{len(plan.deferred)} deferred (capacity {plan.vessel_capacity})",
            )
        ],
    }


# --------------------------------------------------------------------------
# Graph
# --------------------------------------------------------------------------

NODES = {
    "detection": node_detection,
    "verification": node_verification,
    "drift": node_drift,
    "attribution": node_attribution,
    "vessels": node_vessels,
    "prioritisation": node_prioritisation,
}


def build_graph():
    """Compile the six-agent LangGraph.

    The graph shape never changes with ablation — ablated nodes still run and
    still report. That keeps one compiled graph valid for every arm of the
    ablation study, so a difference in output is a difference in agent
    behaviour rather than in topology.
    """
    graph = StateGraph(PipelineState)
    for name, fn in NODES.items():
        graph.add_node(name, fn)

    graph.add_edge(START, "detection")
    order = list(NODES)
    for upstream, downstream in zip(order, order[1:], strict=False):
        graph.add_edge(upstream, downstream)
    graph.add_edge("prioritisation", END)
    return graph.compile()


@dataclass
class PipelineRun:
    """One complete pipeline execution, ready for review or comparison."""

    region_id: str
    started_at: datetime
    ablated: list[str]
    detections: list[Detection]
    verifications: list[VerificationResult]
    backward: dict[str, Trajectory]
    forward: dict[str, Trajectory]
    attributions: dict[str, SourceAttribution]
    correlations: dict[str, VesselCorrelation]
    scores: list[PriorityScore]
    plan: DispatchPlan | None
    degradations: list[str]
    log: list[str]

    @property
    def verified(self) -> list[VerificationResult]:
        return [v for v in self.verifications if v.verified]

    @property
    def rejected(self) -> list[VerificationResult]:
        """Retained, with reasons — PRD §8 auditability."""
        return [v for v in self.verifications if not v.verified]

    def summary(self) -> str:
        lines = [
            f"Region {self.region_id} — {self.started_at.isoformat()}",
            f"  ablated      : {', '.join(self.ablated) or 'none'}",
            f"  detections   : {len(self.detections)}",
            f"  verified     : {len(self.verified)} ({len(self.rejected)} rejected)",
            f"  trajectories : {len(self.backward)} backward / {len(self.forward)} forward",
            f"  attributions : {len(self.attributions)}",
            f"  correlations : {len(self.correlations)}",
        ]
        if self.plan is None:
            lines.append("  plan         : none (prioritisation ablated)")
        else:
            lines.append(
                f"  plan         : {len(self.plan.assignments)} assigned, "
                f"{len(self.plan.deferred)} deferred, "
                f"approved={self.plan.approved}"
            )
        for note in self.degradations:
            lines.append(f"  ! {note}")
        return "\n".join(lines)


def run_pipeline(config: PipelineConfig) -> PipelineRun:
    """Execute the full six-agent pipeline for one region."""
    started = datetime.now(UTC)
    app = build_graph()
    final: dict = app.invoke(
        {"config": config, "degradations": [], "log": []},
    )
    return PipelineRun(
        region_id=config.region_id,
        started_at=started,
        ablated=sorted(config.ablate),
        detections=final.get("detections", []),
        verifications=final.get("verifications", []),
        backward=final.get("backward", {}),
        forward=final.get("forward", {}),
        attributions=final.get("attributions", {}),
        correlations=final.get("correlations", {}),
        scores=final.get("scores", []),
        plan=final.get("plan"),
        degradations=final.get("degradations", []),
        log=final.get("log", []),
    )


def run_ablation_study(config: PipelineConfig) -> dict[str, PipelineRun]:
    """PRD §12 — run the full pipeline, then once per agent removed.

    Returns ``{"full": run, "without_detection": run, ...}``. The point is not
    just that scores drop but that each run's ``degradations`` names the
    specific capability that went missing, which is what makes the architecture
    demonstrably load-bearing rather than decorative.
    """
    runs = {"full": run_pipeline(config)}
    for agent in AGENT_NAMES:
        variant = PipelineConfig(
            **{
                **{k: v for k, v in vars(config).items() if k != "ablate"},
                "ablate": frozenset({agent}),
            }
        )
        runs[f"without_{agent}"] = run_pipeline(variant)
    return runs
