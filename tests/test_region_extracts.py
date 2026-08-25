"""Building the region-clipped extracts the agents read.

Every input here is fabricated in `tmp_path` — no WDPA download, no Ocean
Cleanup table, no network. What these tests actually pin down is the two
decisions that are easy to get quietly wrong: that the clip is a *buffered*
bbox (a river just outside the box is still a candidate, because debris drifts
to it), and that a multipart reef becomes one circle per patch rather than one
continent-sized circle centred on open water.

The two round-trip tests are the load-bearing ones — they run the extract back
through the real loaders, so a change to either side that breaks the contract
fails here rather than at export time on the workstation.
"""

from __future__ import annotations

import csv
import json

import pytest

from ghostnet.agents.attribution import RiverTable
from ghostnet.agents.prioritisation import load_protected_areas
from scripts.build_region_extracts import build_mpa, build_rivers

REGION = "gulf_of_honduras"
# config/regions.yaml: bbox [-88.8556, 15.6832, -86.1292, 16.5204]
MOTAGUA = (-88.20, 15.75)  # inside the bbox — the region's named source river
NEARBY = (-85.50, 16.00)  # ~67 km east of the bbox: outside it, well inside 250 km
FAR = (-70.00, 18.00)  # Hispaniola — outside any plausible backtrack


def _write_source(tmp_path, rows, header=None):
    path = tmp_path / "rivers_global.csv"
    header = header or ["name", "lon", "lat", "emission_tonnes_yr", "country"]
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


# ------------------------------------------------------------- rivers -----


def test_a_river_outside_the_bbox_but_within_drift_reach_is_kept(tmp_path):
    """The whole reason the clip is buffered. Clipping to the bare bbox would
    drop a source the Drift Agent's backtrack actually reaches."""
    source = _write_source(
        tmp_path,
        [
            ["Rio Motagua", *MOTAGUA, 20000.0, "GT"],
            ["Rio Ulua", *NEARBY, 5000.0, "HN"],
            ["Rio Yaque", *FAR, 9000.0, "DO"],
        ],
    )
    _, kept = build_rivers(source, REGION, out_dir=tmp_path / "out")
    names = {r["name"] for r in kept}
    assert "Rio Ulua" in names, "a river just outside the bbox must survive the buffer"
    assert "Rio Yaque" not in names, "Hispaniola is not a candidate source for this region"


def test_the_buffer_is_what_keeps_it(tmp_path):
    """Same input, no buffer — the nearby river drops out. Pins the mechanism
    rather than trusting the default."""
    source = _write_source(
        tmp_path,
        [["Rio Motagua", *MOTAGUA, 20000.0, "GT"], ["Rio Ulua", *NEARBY, 5000.0, "HN"]],
    )
    _, kept = build_rivers(source, REGION, buffer_km=0.0, out_dir=tmp_path / "out")
    assert {r["name"] for r in kept} == {"Rio Motagua"}


def test_the_extract_is_ranked_by_emission(tmp_path):
    """FR-4.2 outputs a ranked distribution and `matches_published_ranking`
    compares against the publisher's order, so write it already ranked."""
    source = _write_source(
        tmp_path,
        [
            ["Small", -88.3, 15.9, 100.0, "GT"],
            ["Largest", *MOTAGUA, 20000.0, "GT"],
            ["Middle", -87.0, 16.1, 800.0, "HN"],
        ],
    )
    _, kept = build_rivers(source, REGION, out_dir=tmp_path / "out")
    assert [r["name"] for r in kept] == ["Largest", "Middle", "Small"]


def test_the_river_extract_loads_through_the_real_reader(tmp_path):
    """The contract that matters: what this writes, `RiverTable` reads."""
    source = _write_source(tmp_path, [["Rio Motagua", *MOTAGUA, 20000.0, "GT"]])
    out_path, _ = build_rivers(source, REGION, out_dir=tmp_path / "out")

    table = RiverTable.from_csv(out_path)
    assert len(table) == 1
    river = table.rivers[0]
    assert river.name == "Rio Motagua"
    assert river.emission_tonnes_yr == pytest.approx(20000.0)
    assert river.country == "GT"


def test_alternative_column_spellings_are_accepted(tmp_path):
    """Distributions of the Meijer data differ in their headers; the script
    should not care which one the user downloaded."""
    source = _write_source(
        tmp_path,
        [["Rio Motagua", *MOTAGUA, 20000.0]],
        header=["River", "longitude", "latitude", "dwm_tonnes_yr"],
    )
    _, kept = build_rivers(source, REGION, out_dir=tmp_path / "out")
    assert kept[0]["name"] == "Rio Motagua"
    assert kept[0]["emission_tonnes_yr"] == pytest.approx(20000.0)


def test_an_unrecognised_header_fails_naming_what_it_found(tmp_path):
    """An opaque KeyError three frames down is the failure mode to avoid — the
    user needs to see their own header to fix the download."""
    source = _write_source(
        tmp_path, [["Rio Motagua", 1.0]], header=["waterway", "plastic_index"]
    )
    with pytest.raises(SystemExit) as exc:
        build_rivers(source, REGION, out_dir=tmp_path / "out")
    message = str(exc.value)
    assert "waterway" in message and "plastic_index" in message


def test_it_warns_when_the_regions_named_source_river_is_missing(tmp_path, capsys):
    """The region was chosen because FR-4 has a citable answer here. Losing the
    Motagua to the clip silently would make that check impossible to run."""
    source = _write_source(tmp_path, [["Rio Chamelecon", -87.5, 16.2, 900.0, "HN"]])
    build_rivers(source, REGION, out_dir=tmp_path / "out")
    assert "Motagua" in capsys.readouterr().err


def test_an_empty_clip_says_what_probably_went_wrong(tmp_path):
    source = _write_source(tmp_path, [["Rio Yaque", *FAR, 9000.0, "DO"]])
    with pytest.raises(SystemExit) as exc:
        build_rivers(source, REGION, out_dir=tmp_path / "out")
    assert "0-360" in str(exc.value)  # names the most likely cause


# ---------------------------------------------------------------- mpa -----


@pytest.fixture
def wdpa(tmp_path):
    """A fabricated WDPA-shaped file: one compact reserve, one two-part reef."""
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import MultiPolygon, box

    compact = box(-88.0, 16.0, -87.8, 16.2)
    # Two separate reef patches, delivered as one MultiPolygon row the way WDPA
    # ships a reef system. Long and thin, and far apart.
    reef = MultiPolygon([box(-88.5, 15.9, -86.5, 15.92), box(-87.0, 16.4, -86.2, 16.42)])

    frame = gpd.GeoDataFrame(
        {
            "NAME": ["Bay Islands Reserve", "Mesoamerican Barrier Reef"],
            "DESIG_ENG": ["Marine Reserve", "World Heritage Site"],
            "geometry": [compact, reef],
        },
        crs="EPSG:4326",
    )
    path = tmp_path / "wdpa_marine.gpkg"
    frame.to_file(path, driver="GPKG")
    return path


def test_a_multipart_reef_becomes_one_circle_per_patch(wdpa, tmp_path):
    """One centroid for a 200 km reef system would sit in open water far from
    any reef. Exploding the parts is what stops that."""
    _, records = build_mpa(wdpa, REGION, out_dir=tmp_path / "out")
    reef_parts = [r for r in records if r["name"] == "Mesoamerican Barrier Reef"]
    assert len(reef_parts) == 2, "the MultiPolygon should not collapse to one record"
    assert len(records) == 3


def test_radius_is_an_equal_area_circle_in_kilometres(wdpa, tmp_path):
    """Catches the classic metres-vs-kilometres slip: the compact reserve is
    ~0.2 deg square near 16N, roughly 22 km a side, so ~12 km equivalent radius."""
    _, records = build_mpa(wdpa, REGION, out_dir=tmp_path / "out")
    compact = next(r for r in records if r["name"] == "Bay Islands Reserve")
    assert 10.0 < compact["radius_km"] < 15.0


def test_an_elongated_area_is_flagged_as_a_poor_circle(wdpa, tmp_path):
    """The honesty record. A square scores 2/pi; a long thin reef scores far
    lower, and that is what makes its distances approximate."""
    _, records = build_mpa(wdpa, REGION, out_dir=tmp_path / "out")
    compact = next(r for r in records if r["name"] == "Bay Islands Reserve")
    reef = min(records, key=lambda r: r["circle_fit"])

    assert compact["circle_fit"] == pytest.approx(2 / 3.14159, abs=0.02)
    assert reef["circle_fit"] < 0.1
    assert reef["name"] == "Mesoamerican Barrier Reef"


def test_the_mpa_extract_loads_through_the_real_reader(wdpa, tmp_path):
    """Round-trip: what this writes, `load_protected_areas` reads — including
    the new circle_fit field, which would raise a TypeError if the dataclass
    and the writer ever drift apart."""
    out_path, records = build_mpa(wdpa, REGION, out_dir=tmp_path / "out")

    areas = load_protected_areas(out_path)
    assert len(areas) == len(records)
    assert {a.name for a in areas} == {"Bay Islands Reserve", "Mesoamerican Barrier Reef"}

    compact = next(a for a in areas if a.name == "Bay Islands Reserve")
    assert compact.designation == "Marine Reserve"
    assert compact.radius_km > 0
    assert compact.circle_fit is not None


def test_areas_far_outside_the_region_are_not_written(tmp_path):
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import box

    frame = gpd.GeoDataFrame(
        {
            "NAME": ["In region", "Pacific"],
            "DESIG_ENG": ["Marine Reserve", "Marine Reserve"],
            "geometry": [box(-88.0, 16.0, -87.8, 16.2), box(-130.0, 30.0, -129.8, 30.2)],
        },
        crs="EPSG:4326",
    )
    path = tmp_path / "wdpa.gpkg"
    frame.to_file(path, driver="GPKG")

    _, records = build_mpa(path, REGION, out_dir=tmp_path / "out")
    assert [r["name"] for r in records] == ["In region"]


def test_the_written_json_is_exactly_the_dataclass_fields(wdpa, tmp_path):
    """Guards the schema from both directions: nothing extra, nothing missing."""
    out_path, _ = build_mpa(wdpa, REGION, out_dir=tmp_path / "out")
    raw = json.loads(out_path.read_text())
    expected = {"name", "lon", "lat", "radius_km", "designation", "circle_fit"}
    assert all(set(record) == expected for record in raw)
