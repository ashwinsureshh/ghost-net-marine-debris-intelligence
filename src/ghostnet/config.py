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

    def __init__(
        self,
        dataset_key: str,
        path: Path,
        purpose: str = "",
        *,
        message: str | None = None,
    ) -> None:
        self.dataset_key = dataset_key
        self.path = path
        # `message` overrides the default wording for the cases where the data
        # is present but unusable — an ambiguous region extract, say. Saying
        # "is not available" there would send the reader looking for a download
        # they already have.
        if message is None:
            message = (
                f"Dataset '{dataset_key}' is not available at {path}. "
                f"{purpose + ' ' if purpose else ''}"
                f"Run `python scripts/fetch_data.py --status` to confirm, then "
                f"`python scripts/fetch_data.py --instructions --dataset {dataset_key}` "
                f"for how to obtain it. Do not assume the workstation's copy is here."
            )
        super().__init__(message)


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


def region_dataset_file(
    key: str,
    *,
    region_id: str | None,
    suffix: str,
    purpose: str = "",
    rebuild_hint: str = "",
) -> Path:
    """Pick the file in a dataset directory that belongs to ``region_id``.

    ``scripts/build_region_extracts.py`` names every extract ``<region_id>``
    plus ``suffix``, so the right file is addressable by name. Resolving it by
    ``sorted(glob(...))[0]`` instead — which is what the loaders used to do —
    silently loads whichever region sorts first the moment a second extract
    exists: run Gulf of Gonâve, score against Honduras's reserves and rivers,
    and nothing anywhere reports an error. A wrong answer delivered confidently
    is the worst failure this pipeline can have, so ambiguity raises here
    rather than picking.
    """
    directory = dataset_path(key, required=True, purpose=purpose)
    candidates = sorted(directory.glob(f"*{suffix}"))
    hint = f" {rebuild_hint}" if rebuild_hint else ""

    if region_id is not None:
        wanted = directory / f"{region_id}{suffix}"
        if wanted.is_file():
            return wanted
        found = ", ".join(p.name for p in candidates) or "no extracts at all"
        raise DataUnavailableError(
            key,
            directory,
            message=(
                f"No '{key}' extract for region {region_id!r}: expected "
                f"{wanted.name} in {directory}, found {found}.{hint}"
            ),
        )

    if not candidates:
        raise DataUnavailableError(
            key,
            directory,
            f"No '*{suffix}' extract found in the directory.{hint}",
        )

    if len(candidates) > 1:
        names = ", ".join(p.name for p in candidates)
        raise DataUnavailableError(
            key,
            directory,
            message=(
                f"{len(candidates)} region extracts are present in {directory} "
                f"({names}) and no region was named, so the right one cannot be "
                f"chosen. Pass region_id. Loading one arbitrarily would score a "
                f"run against another region's data and report nothing wrong."
            ),
        )

    return candidates[0]


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
