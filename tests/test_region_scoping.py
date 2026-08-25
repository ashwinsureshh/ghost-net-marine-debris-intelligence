"""Two regions' extracts must never cross-contaminate.

Both loaders used to resolve their file with ``sorted(glob(...))[0]``. That is
correct only while exactly one extract exists — and the project already has a
second region queued (Gulf of Gonâve is the stretch candidate in
config/regions.yaml). The moment its extract lands, a Haiti run would have
loaded Honduras's rivers and Honduras's reserves, attributed debris to the
Motagua, scored ecological risk against the Mesoamerican reef, and reported
nothing wrong anywhere. That is the failure this file exists to prevent: not a
crash, a confident wrong answer.

Everything is written to `tmp_path` and pointed at through the loaders' own
path/region arguments — no dataset is touched.
"""

from __future__ import annotations

import csv
import json

import pytest

from ghostnet.agents.attribution import load_river_table
from ghostnet.agents.prioritisation import load_protected_areas
from ghostnet.config import DataUnavailableError, region_dataset_file

HONDURAS = "gulf_of_honduras"
HAITI = "gulf_of_gonave"


@pytest.fixture
def two_regions(tmp_path, monkeypatch):
    """A rivers dir and an MPA dir, each holding two regions' extracts."""
    rivers = tmp_path / "rivers"
    mpa = tmp_path / "protected_planet"
    rivers.mkdir()
    mpa.mkdir()

    def write_rivers(name, rows):
        with (rivers / f"{name}.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["name", "lon", "lat", "emission_tonnes_yr", "country"]
            )
            writer.writeheader()
            writer.writerows(rows)

    write_rivers(
        HONDURAS,
        [
            {
                "name": "Rio Motagua",
                "lon": -88.2,
                "lat": 15.75,
                "emission_tonnes_yr": 20000.0,
                "country": "GT",
            }
        ],
    )
    write_rivers(
        HAITI,
        [
            {
                "name": "Riviere de la Grande Anse",
                "lon": -73.8,
                "lat": 18.65,
                "emission_tonnes_yr": 640.0,
                "country": "HT",
            }
        ],
    )

    (mpa / f"{HONDURAS}.json").write_text(
        json.dumps(
            [{"name": "Mesoamerican Barrier Reef", "lon": -87.4, "lat": 15.9, "radius_km": 15.0}]
        )
    )
    (mpa / f"{HAITI}.json").write_text(
        json.dumps(
            [{"name": "Baie de Gonave Reserve", "lon": -72.9, "lat": 18.8, "radius_km": 9.0}]
        )
    )

    # Point the dataset resolver at the temp dirs rather than data/.
    import ghostnet.config as config

    real = config.dataset_path

    def fake(key, *, required=True, purpose=""):
        override = {"rivers": rivers, "mpa": mpa}.get(key)
        return override or real(key, required=required, purpose=purpose)

    monkeypatch.setattr(config, "dataset_path", fake)
    return rivers, mpa


# ------------------------------------------------------- the real bug -----


def test_haiti_does_not_load_honduras_rivers(two_regions):
    """`gulf_of_gonave` sorts before `gulf_of_honduras`, so the old
    sorted()[0] would have returned Haiti for BOTH regions — this asserts the
    Honduras run gets Honduras."""
    table = load_river_table(HONDURAS)
    assert [r.name for r in table.rivers] == ["Rio Motagua"]


def test_honduras_does_not_load_haiti_rivers(two_regions):
    table = load_river_table(HAITI)
    assert [r.name for r in table.rivers] == ["Riviere de la Grande Anse"]


def test_each_region_gets_its_own_protected_areas(two_regions):
    honduras = load_protected_areas(region_id=HONDURAS)
    haiti = load_protected_areas(region_id=HAITI)
    assert [a.name for a in honduras] == ["Mesoamerican Barrier Reef"]
    assert [a.name for a in haiti] == ["Baie de Gonave Reserve"]


# ------------------------------------------------- ambiguity is loud ------


def test_omitting_the_region_with_two_extracts_raises_rather_than_guessing(two_regions):
    """The heart of it. Silently picking one is what produced a wrong answer
    with no error; refusing is the honest behaviour."""
    with pytest.raises(DataUnavailableError) as exc:
        load_river_table()
    message = str(exc.value)
    assert "no region was named" in message
    assert f"{HONDURAS}.csv" in message and f"{HAITI}.csv" in message


def test_the_ambiguity_error_does_not_claim_the_data_is_missing(two_regions):
    """Both extracts are right there. Telling the reader to go download
    something would send them chasing a file they already have."""
    with pytest.raises(DataUnavailableError) as exc:
        load_protected_areas()
    assert "is not available" not in str(exc.value)


def test_a_single_extract_still_loads_without_a_region(tmp_path, monkeypatch):
    """Backwards compatible: one extract is unambiguous, so callers that
    predate region scoping keep working."""
    rivers = tmp_path / "rivers"
    rivers.mkdir()
    with (rivers / f"{HONDURAS}.csv").open("w", newline="") as handle:
        handle.write("name,lon,lat,emission_tonnes_yr,country\nRio Motagua,-88.2,15.75,20000,GT\n")

    import ghostnet.config as config

    monkeypatch.setattr(config, "dataset_path", lambda key, **kw: rivers)
    assert [r.name for r in load_river_table().rivers] == ["Rio Motagua"]


# ------------------------------------------------- missing extract --------


def test_a_missing_region_extract_names_the_file_and_the_build_command(two_regions):
    with pytest.raises(DataUnavailableError) as exc:
        load_river_table("bay_of_bengal")
    message = str(exc.value)
    assert "bay_of_bengal.csv" in message
    assert "build_region_extracts.py" in message
    # and it says what IS there, so the typo is obvious
    assert f"{HONDURAS}.csv" in message


def test_an_explicit_path_still_wins_for_protected_areas(two_regions):
    """Tests and one-off inspection point at a file directly; that path must
    not go through region resolution at all."""
    _, mpa = two_regions
    areas = load_protected_areas(mpa / f"{HAITI}.json")
    assert [a.name for a in areas] == ["Baie de Gonave Reserve"]


def test_resolver_reports_an_empty_directory_distinctly(tmp_path, monkeypatch):
    empty = tmp_path / "rivers"
    empty.mkdir()
    import ghostnet.config as config

    monkeypatch.setattr(config, "dataset_path", lambda key, **kw: empty)
    with pytest.raises(DataUnavailableError) as exc:
        region_dataset_file("rivers", region_id=None, suffix=".csv")
    assert "No '*.csv' extract found" in str(exc.value)
