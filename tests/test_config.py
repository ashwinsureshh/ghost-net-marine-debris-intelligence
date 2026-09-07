"""Config loading, dataset resolution, and the "never assume it's here" rule."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from ghostnet import config
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


def test_a_missing_dataset_points_at_the_fetch_command(tmp_path, monkeypatch):
    """MACHINE-WORKFLOW.md rule 4 — never assume the other machine's copy is here.

    Pointed at an EMPTY tmp DATA_ROOT rather than at whichever dataset happens
    to be undownloaded. This test used to assert that ``oscar`` was absent and
    started failing the moment OSCAR was actually downloaded (2026-09-04) — a
    test that passes only on the machine missing the data is the same broken
    shape as one that passes only on the machine holding it.
    """
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    with pytest.raises(DataUnavailableError) as excinfo:
        dataset_path("oscar", required=True, purpose="test")
    message = str(excinfo.value)
    assert "scripts/fetch_data.py --status" in message
    assert "--dataset oscar" in message
    assert "Do not assume the workstation's copy is here" in message


def test_a_present_dataset_resolves_instead_of_raising(tmp_path, monkeypatch):
    """The other half of the same contract, and it had no test until now."""
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    populated = tmp_path / "oscar"
    populated.mkdir()
    (populated / "oscar_currents_final_20200918.nc").write_bytes(b"stub")
    assert dataset_path("oscar", required=True, purpose="test") == populated


def test_a_directory_holding_only_gitkeep_still_counts_as_missing(tmp_path, monkeypatch):
    """data/*/.gitkeep is committed, so presence of the DIRECTORY proves nothing."""
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    (tmp_path / "oscar").mkdir()
    (tmp_path / "oscar" / ".gitkeep").touch()
    with pytest.raises(DataUnavailableError):
        dataset_path("oscar", required=True, purpose="test")


def test_an_unknown_dataset_key_is_a_programming_error():
    with pytest.raises(KeyError, match="Unknown dataset key"):
        dataset_path("atlantis")


def test_dataset_path_can_be_resolved_without_requiring_content():
    path = dataset_path("oscar", required=False)
    assert path == REPO_ROOT / "data" / "oscar"


def test_regions_file_loads():
    doc = load_regions()
    assert "defaults" in doc and "regions" in doc


def test_the_selected_region_is_usable():
    """PRD Open Question 1 resolved 2026-08-14 — Gulf of Honduras."""
    region = get_region("gulf_of_honduras")
    assert region["status"] == "selected"
    assert len(region["bbox"]) == 4
    assert region["time_window"]["start"] and region["time_window"]["end"]
    # Defaults must merge in, or tile queries lose their band/cloud limits.
    assert region["bands"] == ["B04", "B06", "B08", "B11"]
    assert region["revisit_days"] == 5


def test_a_region_without_a_bbox_still_fails_loudly():
    """A rejected/candidate entry must not silently produce an empty query."""
    with pytest.raises(GhostNetError, match="Open Question 1"):
        get_region("jakarta_bay")


def test_an_unknown_region_lists_what_is_known():
    with pytest.raises(GhostNetError, match="gulf_of_honduras"):
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
    """The repo must stay code-only (MACHINE-WORKFLOW.md sync rule 2).

    Asks git what it *tracks*, not what is on disk. The workstation is supposed
    to hold MARIDA and Sentinel-2 tiles locally; an on-disk check would fail on
    exactly the machine the data belongs on, which is the opposite of the rule
    being enforced here.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "data/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    allowed = {".gitkeep", "README.md"}
    offenders = [p for p in tracked if Path(p).name not in allowed]
    assert offenders == [], f"datasets committed to git: {offenders}"


def test_env_file_is_not_tracked():
    gitignore = (REPO_ROOT / ".gitignore").read_text()
    assert ".env" in gitignore
    assert not (REPO_ROOT / ".env").exists() or ".env" in gitignore


def test_src_layout_is_importable_without_an_editable_install():
    """`pytest` must work on a fresh clone right after requirements-base.txt."""
    assert (REPO_ROOT / "src" / "ghostnet" / "__init__.py").exists()
    assert Path(sys.modules["ghostnet.config"].__file__).is_relative_to(REPO_ROOT / "src")


def test_region_names_survive_the_platform_encoding():
    """The demo region's name has an em dash. It has to come back as ONE char.

    `open()` defaults to the platform encoding — cp1252 on the Windows
    workstation, UTF-8 on the Air and in the Linux container. Read as cp1252,
    the UTF-8 em dash (E2 80 94) silently becomes three characters: 'a-hat',
    'euro', 'right-double-quote'. That travelled into the first real run
    artefact, the console's run selector, and would have reached the report.

    This asserts on CODEPOINTS, not on the printed string. A terminal renders
    the mojibake close enough to an em dash to fool a person reading output —
    it fooled me twice before this test existed.
    """
    name = get_region("gulf_of_honduras")["name"]
    assert "\u2014" in name, f"em dash missing: {name!r}"
    for bad in ("\u00e2", "\u20ac", "\u201d", "\u00c3"):
        assert bad not in name, f"mojibake {bad!r} in {name!r}"


def test_every_region_name_is_clean():
    """Gonave carries a circumflex; the same trap, a different codepoint."""
    doc = load_regions()
    for entry in doc["regions"]:
        name = entry.get("name") or ""
        for bad in ("\u00e2\u20ac", "\u00c3\u00a2", "\u00c3\u00b4"):
            assert bad not in name, f"mojibake in region {entry['id']}: {name!r}"
