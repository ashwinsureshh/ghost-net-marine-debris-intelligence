"""Config loading, dataset resolution, and the "never assume it's here" rule."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from ghostnet._datasets import DATASET_DIRS
from ghostnet.config import (
    REPO_ROOT,
    CredentialsMissingError,
    DataUnavailableError,
    GhostNetError,
    dataset_path,
    dispatch_config,
    get_region,
    load_regions,
    require_env,
)


def _load_fetch_data():
    spec = importlib.util.spec_from_file_location(
        "_fetch_data", REPO_ROOT / "scripts" / "fetch_data.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_fetch_data"] = module
    spec.loader.exec_module(module)
    return module


def test_dataset_keys_stay_in_step_with_the_fetch_script():
    """If a dataset is added to fetch_data.py it must be added here too."""
    fetch_data = _load_fetch_data()
    assert set(DATASET_DIRS) == set(fetch_data.BY_KEY)
    for key, relative in DATASET_DIRS.items():
        expected = fetch_data.BY_KEY[key].local_path
        assert (REPO_ROOT / "data" / relative).resolve() == expected.resolve()


def test_a_missing_dataset_points_at_the_fetch_command():
    """MACHINE-WORKFLOW.md rule 4 — never assume the other machine's copy is here."""
    with pytest.raises(DataUnavailableError) as excinfo:
        dataset_path("oscar", required=True, purpose="test")
    message = str(excinfo.value)
    assert "scripts/fetch_data.py --status" in message
    assert "--dataset oscar" in message
    assert "Do not assume the workstation's copy is here" in message


def test_an_unknown_dataset_key_is_a_programming_error():
    with pytest.raises(KeyError, match="Unknown dataset key"):
        dataset_path("atlantis")


def test_dataset_path_can_be_resolved_without_requiring_content():
    path = dataset_path("oscar", required=False)
    assert path == REPO_ROOT / "data" / "oscar"


def test_regions_file_loads():
    doc = load_regions()
    assert "defaults" in doc and "regions" in doc


def test_the_placeholder_region_fails_loudly_rather_than_querying_nothing():
    """PRD Open Question 1 is unresolved; a null bbox must not silently pass."""
    with pytest.raises(GhostNetError, match="Open Question 1"):
        get_region("candidate_region_a")


def test_an_unknown_region_lists_what_is_known():
    with pytest.raises(GhostNetError, match="candidate_region_a"):
        get_region("no_such_region")


def test_dispatch_config_carries_the_capacity_constraint():
    config = dispatch_config()
    assert config["vessel_capacity"] == 3
    assert config["planning_horizon_days"] == 7


def test_missing_credentials_name_the_variable_and_the_fix(monkeypatch):
    monkeypatch.setattr("ghostnet.config.load_dotenv_if_present", lambda: None)
    monkeypatch.delenv("GFW_API_TOKEN", raising=False)
    with pytest.raises(CredentialsMissingError) as excinfo:
        require_env("GFW_API_TOKEN", "Global Fishing Watch API")
    assert ".env.example" in str(excinfo.value)


def test_credentials_are_read_when_present(monkeypatch):
    monkeypatch.setattr("ghostnet.config.load_dotenv_if_present", lambda: None)
    monkeypatch.setenv("GFW_API_TOKEN", "token-123")
    assert require_env("GFW_API_TOKEN", "GFW") == "token-123"


def test_no_dataset_is_committed_to_git():
    """The repo must stay code-only (MACHINE-WORKFLOW.md sync rule 2)."""
    for relative in DATASET_DIRS.values():
        directory = REPO_ROOT / "data" / relative
        if not directory.is_dir():
            continue
        tracked = [p.name for p in directory.iterdir() if p.name != ".gitkeep"]
        assert tracked == [], f"data/{relative} contains {tracked}"


def test_env_file_is_not_tracked():
    gitignore = (REPO_ROOT / ".gitignore").read_text()
    assert ".env" in gitignore
    assert not (REPO_ROOT / ".env").exists() or ".env" in gitignore


def test_src_layout_is_importable_without_an_editable_install():
    """`pytest` must work on a fresh clone right after requirements-base.txt."""
    assert (REPO_ROOT / "src" / "ghostnet" / "__init__.py").exists()
    assert Path(sys.modules["ghostnet.config"].__file__).is_relative_to(REPO_ROOT / "src")
