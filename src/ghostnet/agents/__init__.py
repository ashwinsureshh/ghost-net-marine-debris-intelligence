"""The six agents.

Each agent is independently testable and independently ablatable (PRD §7):
removing any one of them should break the pipeline, not merely degrade it. The
orchestration that wires them together lives in ``ghostnet.pipeline``, and the
data contracts they exchange live in ``ghostnet.schemas``.

Modules, with the machine each is primarily built on (per MACHINE-WORKFLOW.md)
and current status:

    detection.py      FR-1  Satellite Detection Agent
                            FDI spectral-index baseline      -> either   IMPLEMENTED
                            L2A tile reader (FR-1.1)         -> WORKSTATION  todo
                            CNN variant (FR-1.4, stretch)    -> WORKSTATION  todo
    verification.py   FR-2  False-Positive Verification Agent -> either  IMPLEMENTED
    drift.py          FR-3  Drift Agent                       -> either  IMPLEMENTED
                            OSCAR NetCDF reader               -> either  todo
    attribution.py    FR-4  Source Attribution Agent          -> either  IMPLEMENTED
    vessels.py        FR-5  Dark Vessel Correlation Agent     -> either  IMPLEMENTED
                            GFW live API query (FR-5.1)       -> either  todo (needs token)
    prioritisation.py FR-6  Response Prioritisation Agent     -> either  IMPLEMENTED

"IMPLEMENTED" means the agent's logic is written and unit-tested against small
synthetic fixtures. Every loader that needs a real dataset raises
``DataUnavailableError`` naming the ``scripts/fetch_data.py`` command to run —
no agent silently proceeds on absent data.

Two invariants apply to every agent:

* Explainability — each output carries the specific evidence that produced it
  (imagery tile, current field, vessel record). No unexplained scores.
* Auditability — rejected detections are logged with their rejection reason,
  never discarded silently.
"""
