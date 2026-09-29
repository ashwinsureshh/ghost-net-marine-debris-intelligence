"""Serve the measured priority-weight sensitivity for one run, honestly.

``eval/priority_sensitivity.json`` was measured on specific artefact files
(recorded by ``input_sha256``) at one capacity and horizon. This module hands
the console exactly that measurement for a run, and says so when it does not
apply:

* ``measured``      — the served artefact is byte-identical (LF-normalised) to
  the one measured;
* ``stale``         — a run with that id was measured, but the served file has
  changed since, so the old numbers describe a different plan;
* ``not_measured``  — no sensitivity run exists for this id.

Nothing is recomputed here. Stability under weight changes is not accuracy.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ghostnet.config import REPO_ROOT
from ghostnet.evidence_hash import text_evidence_sha256

SENSITIVITY_FILE = REPO_ROOT / "eval" / "priority_sensitivity.json"
RESULTS_DOC = "eval/results.md#priority-robustness--weight-sensitivity-2026-09-22"


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sensitivity(path: Path) -> dict | None:
    if not path.exists():
        return None
    return _load(str(path), path.stat().st_mtime)


def robustness_for(run_id: str, artefact_path: Path | None,
                   *, source: Path = SENSITIVITY_FILE) -> dict[str, Any]:
    data = _sensitivity(source)
    base = {"run_id": run_id, "source_file": "eval/priority_sensitivity.json",
            "results_doc": RESULTS_DOC}
    if data is None:
        return {**base, "status": "not_measured",
                "reason": "No priority sensitivity artefact is available."}

    run = next((r for r in data.get("runs", [])
                if r.get("input_file") == f"{run_id}.run.json"), None)
    if run is None:
        return {**base, "status": "not_measured",
                "reason": "Priority-weight sensitivity was not measured for this run."}

    exists = artefact_path is not None and artefact_path.exists()
    served = text_evidence_sha256(artefact_path) if exists else None
    if served != run["input_sha256"]:
        return {**base, "status": "stale",
                "reason": "This run's artefact changed after sensitivity was measured, so "
                          "the recorded numbers describe a different plan. Re-run "
                          "scripts/eval_sensitivity.py before quoting them."}

    variants = run.get("variants", {})
    summary = run["summary"]
    return {
        **base,
        "status": "measured",
        "measured_at": {"vessel_capacity": run["vessel_capacity"],
                        "planning_horizon_days": run["planning_horizon_days"]},
        "candidates": run["candidate_count"],
        "inputs_degraded": run.get("inputs_degraded", []),
        "baseline_weights": run["baseline_weights"],
        "variants": summary["variants"],
        "top1_changed": summary["top1_changed"],
        "dispatch_set_changed": summary["dispatch_set_changed"],
        "min_spearman": round(min(v["spearman_ordinal"] for v in variants.values()), 4)
        if variants else None,
        "caveats": run.get("caveats", []),
    }
