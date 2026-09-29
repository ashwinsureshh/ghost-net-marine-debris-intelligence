"""FR-6.4 approval persistence behind one small interface.

Run artefacts stay immutable files. Approvals are the only state the API
writes, and they are an audit trail, so the rules here are stricter than for
anything else in the web app:

* **Never discard existing records.** An unreadable log is an incident to
  surface, not an empty list to overwrite. Writes refuse (``ApprovalStoreError``)
  until a person inspects the file; reads report the problem rather than
  pretending there were no approvals.
* **Writes are atomic.** A crash mid-write must leave the previous log intact,
  so the file backend writes a sibling temp file, fsyncs it and ``os.replace``s
  it into place.
* **Durability is declared, not assumed.** Free-tier disks are ephemeral; the
  ``durable`` flag on each record comes from configuration, never from the
  backend's own optimism.

Backends: ``file`` (default, JSON array — what existing deployments already
have) and ``sqlite`` (``GHOSTNET_APPROVAL_BACKEND=sqlite``). PostgreSQL would
implement the same two methods; it is intentionally not a dependency here.
Both are single-process safe; neither claims multi-writer safety across hosts.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError


class ApprovalStoreError(RuntimeError):
    """The approval log cannot be trusted; nothing was written."""


class ApprovalBackend(Protocol):
    name: str

    def load(self) -> list[dict]: ...

    def append(self, record: dict) -> None: ...

    def check(self) -> tuple[bool, str]: ...


class JsonFileBackend:
    """A JSON array on disk, replaced atomically on every append."""

    name = "file"

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            raise ApprovalStoreError(
                f"Approval log {self.path.name} is unreadable ({exc}). Existing "
                "records were left untouched; inspect or restore the file before "
                "recording new approvals."
            ) from exc
        if not isinstance(raw, list) or not all(isinstance(r, dict) for r in raw):
            raise ApprovalStoreError(
                f"Approval log {self.path.name} is not a list of records; left untouched."
            )
        return raw

    def append(self, record: dict) -> None:
        with self._lock:
            records = self.load()  # raises rather than silently starting over
            records.append(record)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(records, handle, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, self.path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise

    def check(self) -> tuple[bool, str]:
        try:
            self.load()
        except ApprovalStoreError as exc:
            return False, str(exc)
        directory = self.path.parent
        if directory.exists() and not os.access(directory, os.W_OK):
            return False, f"{directory} is not writable"
        return True, "ok"


class SqliteBackend:
    """One row per approval; the JSON record is stored verbatim."""

    name = "sqlite"

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS approvals ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, record TEXT NOT NULL)"
        )
        return conn

    def load(self) -> list[dict]:
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute("SELECT record FROM approvals ORDER BY id").fetchall()
        except sqlite3.DatabaseError as exc:
            raise ApprovalStoreError(f"Approval database unreadable: {exc}") from exc
        return [json.loads(row[0]) for row in rows]

    def append(self, record: dict) -> None:
        try:
            with self._lock, self._connect() as conn:
                conn.execute("INSERT INTO approvals (record) VALUES (?)", (json.dumps(record),))
        except sqlite3.DatabaseError as exc:
            raise ApprovalStoreError(f"Approval database write failed: {exc}") from exc

    def check(self) -> tuple[bool, str]:
        try:
            self.load()
        except ApprovalStoreError as exc:
            return False, str(exc)
        return True, "ok"


def backend_from_env(directory: Path) -> ApprovalBackend:
    kind = os.environ.get("GHOSTNET_APPROVAL_BACKEND", "file").strip().lower() or "file"
    if kind == "file":
        return JsonFileBackend(Path(directory) / "approvals.json")
    if kind == "sqlite":
        return SqliteBackend(Path(directory) / "approvals.sqlite3")
    raise ValueError(f"Unknown GHOSTNET_APPROVAL_BACKEND {kind!r}; use 'file' or 'sqlite'.")


def validate_records(records: list[dict], model) -> tuple[list, int]:
    """Parse what is valid; count what is not instead of failing the listing."""
    valid, invalid = [], 0
    for raw in records:
        try:
            valid.append(model.model_validate(raw))
        except ValidationError:
            invalid += 1
    return valid, invalid
