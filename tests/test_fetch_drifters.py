"""NOAA Global Drifter Program fetch (PRD §3, §12 ground truth).

Network-free. What is tested is the query encoding and the fill-value handling,
because both fail *quietly*: a badly encoded URL returns an HTML error page that
looks like a dataset problem, and an unhandled sentinel becomes a velocity of
-999999 cm/s that no schema would reject.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "fetch_drifters", REPO_ROOT / "scripts" / "fetch_drifters.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_drifters"] = module
    spec.loader.exec_module(module)
    return module


FD = _load()
BBOX = (-91.6747, 12.9805, -83.3101, 19.2231)


# --- query construction ---------------------------------------------------


def test_comparison_operators_are_percent_encoded():
    """The regression this file exists for.

    AOML's ERDDAP accepts raw `<` and `>`, but the Tomcat in front of it returns
    a bare HTTP 400 with an HTML body — which reads as a broken dataset rather
    than a broken URL, and cost real time to diagnose.
    """
    url = FD.build_query(BBOX)
    query = url.split("?", 1)[1]
    assert "<" not in query and ">" not in query
    assert "%3E=" in query and "%3C=" in query


def test_the_query_carries_every_column_we_rely_on():
    url = FD.build_query(BBOX)
    for column in ("ID", "time", "latitude", "longitude", "ve", "vn"):
        assert column in url


def test_the_bbox_becomes_four_constraints():
    query = FD.build_query(BBOX).split("?", 1)[1]
    # The projection names them too, so count the constraints specifically.
    assert query.count("latitude%3E=") == 1
    assert query.count("latitude%3C=") == 1
    assert query.count("longitude%3E=") == 1
    assert query.count("longitude%3C=") == 1


def test_time_constraints_appear_only_when_asked_for():
    assert "time%3E=" not in FD.build_query(BBOX)
    windowed = FD.build_query(BBOX, start="2018-02-01", end="2018-10-01")
    assert "time%3E=2018-02-01T00%3A00%3A00Z" in windowed
    assert "time%3C=2018-10-01T00%3A00%3A00Z" in windowed


# --- fill values ----------------------------------------------------------


def test_the_sentinel_velocity_becomes_an_empty_cell():
    """-999999.0 is 'no measurement', not a 10 000 km/h current."""
    rows = FD.blank_fill_values([{"ve": "-999999.0", "vn": "-999999.0"}])
    assert rows[0]["ve"] == "" and rows[0]["vn"] == ""


def test_a_real_velocity_survives_untouched():
    rows = FD.blank_fill_values([{"ve": "-12.5", "vn": "3.75"}])
    assert rows[0]["ve"] == "-12.5" and rows[0]["vn"] == "3.75"


def test_unparseable_velocities_are_treated_as_missing():
    assert FD._is_fill("") and FD._is_fill("NaN") and FD._is_fill(None)


def test_positions_are_never_blanked():
    """Only velocities carry the sentinel; a blanked latitude would be silent."""
    rows = FD.blank_fill_values([{"latitude": "-999999.0", "ve": "-999999.0"}])
    assert rows[0]["latitude"] == "-999999.0"
    assert rows[0]["ve"] == ""


# --- coverage summary -----------------------------------------------------


def _rows():
    return [
        {"ID": "a", "time": "2014-03-01T00:00:00Z", "ve": "1.0"},
        {"ID": "a", "time": "2014-03-01T06:00:00Z", "ve": ""},
        {"ID": "b", "time": "1999-08-11T00:00:00Z", "ve": "2.0"},
    ]


def test_summary_counts_distinct_drifters_not_observations():
    stats = FD.summarise(_rows())
    assert stats["observations"] == 3
    assert stats["drifters"] == 2


def test_summary_reports_how_many_carry_a_velocity():
    assert FD.summarise(_rows())["with_velocity"] == 2


def test_summary_buckets_by_year():
    assert FD.summarise(_rows())["years"] == {"1999": 1, "2014": 2}


def test_an_empty_result_summarises_without_raising():
    """ERDDAP returns 404 for an empty result set; that is data, not an error."""
    stats = FD.summarise([])
    assert stats["observations"] == 0 and stats["drifters"] == 0


def test_the_default_buffer_is_wide_enough_to_be_worth_running():
    """The bare bbox holds 13 drifters across 5 scattered years — too thin to
    validate against, which is the whole reason a buffer exists."""
    assert FD.DEFAULT_BUFFER_KM >= 100.0


@pytest.mark.parametrize("column", ["ID", "time", "latitude", "longitude"])
def test_required_columns_are_declared(column):
    assert column in FD.COLUMNS
