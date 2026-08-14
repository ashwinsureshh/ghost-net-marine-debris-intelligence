"""The six agents.

Nothing is implemented yet — this package documents the intended module layout
so that orchestration work on the MacBook Air has a stable set of names to wire
against. Each agent must be independently testable and independently ablatable
(PRD §7): removing any one of them should break the pipeline, not merely
degrade it.

Planned modules, with the machine each is primarily built on
(per MACHINE-WORKFLOW.md):

    detection.py      FR-1  Satellite Detection Agent
                            Spectral-index (FDI) baseline    -> either machine
                            CNN variant (FR-1.4, stretch)    -> WORKSTATION
    verification.py   FR-2  False-Positive Verification Agent -> either
    drift.py          FR-3  Drift Agent                       -> either
    attribution.py    FR-4  Source Attribution Agent          -> either
    vessels.py        FR-5  Dark Vessel Correlation Agent     -> either
    prioritisation.py FR-6  Response Prioritisation Agent     -> either

Orchestration (LangGraph wiring) lives in ``ghostnet.pipeline`` and is
MacBook Air work.

Two invariants apply to every agent:

* Explainability — each output carries the specific evidence that produced it
  (imagery tile, current field, vessel record). No unexplained scores.
* Auditability — rejected detections are logged with their rejection reason,
  never discarded silently.
"""
