"""Repo paths, region config, credentials, and the two errors agents raise.

MACHINE-WORKFLOW.md §"Sync workflow" rule 4: never assume a file exists locally
just because a previous session on the other machine created it. Every loader
here checks, and raises :class:`DataUnavailableError` naming both the expected
path and the ``scripts/fetch_data.py`` command that explains how to obtain it —
rather than failing later with an opaque ``FileNotFoundError`` deep in an agent.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data"
CONFIG_ROOT = REPO_ROOT / "config"
REGIONS_FILE = CONFIG_ROOT / "regions.yaml"


class GhostNetError(Exception):
    """Base class for every error this package raises deliberately."""


class DataUnavailableError(GhostNetError):
    """A required dataset is not present on *this* machine."""

    def __init__(self, dataset_key: str, path: Path, purpose: str = "") -> None:
        self.dataset_key = dataset_key
        self.path = path
        super().__init__(
            f"Dataset '{dataset_key}' is not available at {path}. "
            f"{purpose + ' ' if purpose else ''}"
            f"Run `python scripts/fetch_data.py --status` to confirm, then "
            f"`python scripts/fetch_data.py --instructions --dataset {dataset_key}` "
            f"for how to obtain it. Do not assume the workstation's copy is here."
        )


class CredentialsMissingError(GhostNetError):
    """A required API credential is absent from the environment/.env."""

    def __init__(self, var: str, service: str) -> None:
        self.var = var
        super().__init__(
            f"{service} needs {var}, which is unset. Copy .env.example to .env "
            f"and fill it in (see README step 3). .env is gitignored."
        )


def load_dotenv_if_present() -> None:
    """Load .env if python-dotenv is installed and the file exists.

    Optional on purpose: the non-credentialled parts of the pipeline (spectral
    index maths, drift integration, scoring, tests on fixtures) must import and
    run without any credentials at all.
    """
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - optional dependency
        return
    load_dotenv(env_file)


def require_env(var: str, service: str) -> str:
    load_dotenv_if_present()
    value = os.environ.get(var, "").strip()
    if not value:
        raise CredentialsMissingError(var, service)
    return value


def dataset_path(key: str, *, required: bool = True, purpose: str = "") -> Path:
    """Resolve a dataset directory, checking it actually has content here."""
    # Imported lazily so `ghostnet` stays importable if scripts/ ever moves.
    from ghostnet._datasets import DATASET_DIRS

    if key not in DATASET_DIRS:
        raise KeyError(f"Unknown dataset key {key!r}; known: {sorted(DATASET_DIRS)}")
    path = DATA_ROOT / DATASET_DIRS[key]
    populated = path.is_dir() and any(p.name != ".gitkeep" for p in path.iterdir())
    if required and not populated:
        raise DataUnavailableError(key, path, purpose)
    return path


def load_regions() -> dict[str, Any]:
    if not REGIONS_FILE.exists():
        raise GhostNetError(f"Missing {REGIONS_FILE}")
    with REGIONS_FILE.open() as handle:
        return yaml.safe_load(handle) or {}


def get_region(region_id: str) -> dict[str, Any]:
    """Return one region entry, merged over ``defaults``.

    Raises if the region is still a placeholder. PRD Open Question 1 (which
    coastline the demo uses) is unresolved, so ``config/regions.yaml`` currently
    holds a candidate with ``bbox``/``time_window`` set to null. Loading it
    should fail loudly here rather than produce an empty tile query later.
    """
    doc = load_regions()
    defaults = doc.get("defaults", {}) or {}
    for entry in doc.get("regions", []) or []:
        if entry.get("id") == region_id:
            merged = {**defaults, **entry}
            if merged.get("bbox") is None:
                raise GhostNetError(
                    f"Region {region_id!r} has no bbox — it is a documented "
                    "candidate, not a selected region. PRD Open Question 1 must "
                    "be settled and config/regions.yaml updated before tile "
                    "ingestion (status: 'selected')."
                )
            return merged
    known = [e.get("id") for e in doc.get("regions", []) or []]
    raise GhostNetError(f"No region {region_id!r} in regions.yaml; known: {known}")


def dispatch_config() -> dict[str, Any]:
    """Cleanup-vessel capacity constraint for the prioritisation agent (FR-6.2)."""
    doc = load_regions()
    return doc.get("dispatch", {}) or {"vessel_capacity": 3, "planning_horizon_days": 7}
