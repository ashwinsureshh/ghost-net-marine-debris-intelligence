"""FR-2.2 — the multi-temporal evaluation harness.

Network-free: the pairing logic and the label reduction are where this can go
wrong silently, and neither needs imagery. The full measurement needs MARIDA and
two L2A reads and is run with ``scripts/eval_multitemporal.py`` on the
workstation.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_harness():
    spec = importlib.util.spec_from_file_location(
        "eval_multitemporal", REPO_ROOT / "scripts" / "eval_multitemporal.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["eval_multitemporal"] = module
    spec.loader.exec_module(module)
    return module


MT = _load_harness()


@dataclass
class FakeDet:
    lon: float
    lat: float
    id: str = "d0"


@dataclass
class FakeTile:
    tile_id: str = "S2-16PCC-20200923"
    acquired_at: dt.datetime = dt.datetime(2020, 9, 23)


# --- label reduction ------------------------------------------------------


def test_an_unlabelled_window_has_no_ground_truth():
    """MARIDA class 0 means unlabelled, not background — never a negative."""
    assert MT.truth_for(np.zeros((5, 5), dtype="int16")) is None


def test_the_majority_labelled_class_wins():
    window = np.array([[0, 0, 1], [0, 2, 1], [0, 1, 1]], dtype="int16")
    assert MT.truth_for(window) == 1


def test_zeros_do_not_outvote_a_sparse_label():
    """99% of MARIDA is class 0; counting it would erase every annotation."""
    window = np.zeros((5, 5), dtype="int16")
    window[2, 2] = 5
    assert MT.truth_for(window) == 5


# --- repeat pairing -------------------------------------------------------


def test_the_nearest_later_candidate_becomes_the_repeat():
    det = FakeDet(-88.5, 15.8)
    later = [FakeDet(-88.0, 15.8, "far"), FakeDet(-88.49, 15.8, "near")]
    repeats, moved = MT.build_repeats(det, later, FakeTile(), search_km=50.0)
    assert repeats[0].detected is True
    assert repeats[0].lon == pytest.approx(-88.49)
    assert moved < 2.0


def test_nothing_within_the_search_radius_is_an_explicit_non_observation():
    """A transient must be reported as 'looked and did not find', not omitted."""
    det = FakeDet(-88.5, 15.8)
    repeats, moved = MT.build_repeats(det, [FakeDet(-80.0, 15.8)], FakeTile(), search_km=50.0)
    assert repeats[0].detected is False
    assert repeats[0].lon is None
    assert moved is None


def test_an_empty_later_pass_is_also_a_non_observation():
    repeats, moved = MT.build_repeats(FakeDet(-88.5, 15.8), [], FakeTile(), search_km=50.0)
    assert repeats[0].detected is False
    assert moved is None


def test_the_repeat_carries_the_later_tiles_identity_and_time():
    """check_persistence needs the real gap to compute an allowed displacement."""
    tile = FakeTile(tile_id="S2-16PCC-20200923", acquired_at=dt.datetime(2020, 9, 23))
    repeats, _ = MT.build_repeats(
        FakeDet(-88.5, 15.8), [FakeDet(-88.5, 15.8)], tile, search_km=50.0
    )
    assert repeats[0].tile_id == "S2-16PCC-20200923"
    assert repeats[0].acquired_at == dt.datetime(2020, 9, 23)


def test_the_repeat_is_not_pre_filtered_to_the_checks_own_tolerance():
    """The observation is reported at its true distance so the check can reject
    it. Filtering to the tolerance first would make the check pass everything by
    construction — the whole measurement would be circular."""
    det = FakeDet(-88.5, 15.8)
    # ~32 km away: far beyond the 5 km base tolerance, well inside search_km.
    repeats, moved = MT.build_repeats(det, [FakeDet(-88.2, 15.8)], FakeTile(), search_km=50.0)
    assert repeats[0].detected is True
    assert moved > 5.0


# --- scoring --------------------------------------------------------------


def test_precision_recall_counts_only_labelled_rows():
    rows = [
        {"v": True, "truth": 1},
        {"v": True, "truth": 6},
        {"v": False, "truth": 1},
    ]
    out = MT._pr(rows, "v")
    assert out["tp"] == 1 and out["fp"] == 1 and out["fn"] == 1
    assert out["precision"] == pytest.approx(0.5)
    assert out["recall"] == pytest.approx(0.5)


def test_scoring_is_safe_when_nothing_survives():
    rows = [{"v": False, "truth": 1}]
    out = MT._pr(rows, "v")
    assert out["precision"] == 0.0 and out["f1"] == 0.0
