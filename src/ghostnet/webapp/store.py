"""Artefact loading and the FR-6.4 approval record.

Both are deliberately file-backed rather than a database: PRD §8 caps this
project at free-tier resources, and a run artefact is already an immutable file
the workstation produced. Adding a database would add an operational dependency
that buys nothing the demo needs.

**Approvals are the exception worth reading carefully.** FR-6.4 requires an
explicit human checkpoint before a plan is treated as final, so an approval has
to be recorded somewhere. Free-tier hosts have ephemeral disks, so a recorded
approval may not survive a restart — the API says so in its response rather
than implying durability it does not have.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from ghostnet.config import REPO_ROOT
from ghostnet.export import RunArtefact, discover_artefacts, load_artefact

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = REPO_ROOT / "webapp_data"
APPROVALS_FILE = "approvals.json"


class ApprovalRecord(BaseModel):
    """One human sign-off on one plan (FR-6.4)."""

    run_id: str
    reviewer: str
    approved_at: datetime
    vessel_capacity: int
    ablated: list[str] = Field(default_factory=list)
    detection_ids: list[str] = Field(default_factory=list)
    note: str = ""
    durable: bool = Field(
        default=False,
        description="False when the store is on an ephemeral free-tier disk.",
    )


class ArtefactStore:
    """Loads run artefacts from a directory and caches them by mtime."""

    def __init__(self, directory: Path | None = None) -> None:
        env_dir = os.environ.get("GHOSTNET_DATA_DIR", "").strip()
        self.directory = Path(directory or env_dir or DEFAULT_DATA_DIR)
        self._cache: dict[str, tuple[float, RunArtefact]] = {}
        self._lock = threading.Lock()

    # -- artefacts ---------------------------------------------------------

    def paths(self) -> dict[str, Path]:
        return {p.name.split(".run.json")[0]: p for p in discover_artefacts(self.directory)}

    def run_ids(self) -> list[str]:
        return sorted(self.paths())

    def get(self, run_id: str) -> RunArtefact | None:
        path = self.paths().get(run_id)
        if path is None:
            return None
        mtime = path.stat().st_mtime
        with self._lock:
            cached = self._cache.get(run_id)
            if cached and cached[0] == mtime:
                return cached[1]
        artefact = load_artefact(path)
        with self._lock:
            self._cache[run_id] = (mtime, artefact)
        return artefact

    def summaries(self) -> list[dict]:
        out = []
        for run_id in self.run_ids():
            try:
                artefact = self.get(run_id)
            except (ValueError, OSError) as exc:
                # A malformed or stale-schema artefact must not take down the
                # whole listing — surface it as unreadable and keep going.
                logger.warning("Skipping unreadable artefact %s: %s", run_id, exc)
                out.append({"run_id": run_id, "unreadable": True, "error": str(exc)})
                continue
            if artefact is not None:
                out.append(artefact.summary())
        return out

    # -- approvals ---------------------------------------------------------

    @property
    def approvals_path(self) -> Path:
        return self.directory / APPROVALS_FILE

    @property
    def storage_is_durable(self) -> bool:
        """Whether an approval is expected to survive a restart.

        Free-tier PaaS filesystems are ephemeral. Rather than guess per host,
        this is opt-in: set GHOSTNET_DURABLE_STORAGE=1 where the disk persists.
        """
        return os.environ.get("GHOSTNET_DURABLE_STORAGE", "").strip() in {"1", "true", "yes"}

    def approvals(self, run_id: str | None = None) -> list[ApprovalRecord]:
        path = self.approvals_path
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Approval log unreadable (%s); treating as empty.", exc)
            return []
        records = [ApprovalRecord.model_validate(r) for r in raw]
        if run_id is not None:
            records = [r for r in records if r.run_id == run_id]
        return sorted(records, key=lambda r: r.approved_at, reverse=True)

    def record_approval(
        self,
        *,
        run_id: str,
        reviewer: str,
        vessel_capacity: int,
        ablated: list[str],
        detection_ids: list[str],
        note: str = "",
    ) -> ApprovalRecord:
        if not reviewer.strip():
            raise ValueError("A human reviewer must be named to approve a plan (FR-6.4).")

        record = ApprovalRecord(
            run_id=run_id,
            reviewer=reviewer.strip(),
            approved_at=datetime.now(UTC),
            vessel_capacity=vessel_capacity,
            ablated=sorted(ablated),
            detection_ids=list(detection_ids),
            note=note.strip(),
            durable=self.storage_is_durable,
        )

        with self._lock:
            existing = []
            if self.approvals_path.exists():
                try:
                    existing = json.loads(
                        self.approvals_path.read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, OSError):
                    existing = []
            existing.append(json.loads(record.model_dump_json()))
            self.approvals_path.parent.mkdir(parents=True, exist_ok=True)
            self.approvals_path.write_text(
                json.dumps(existing, indent=2), encoding="utf-8"
            )

        return record
