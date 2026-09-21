"""FR-1.1 — Sentinel-2 L2A ingestion.

Network-free by design: every test here exercises the grid maths, the
reflectance scaling and the repeat-pass pairing, which is where the silent
errors live. Actually reading a product needs the STAC catalogue and is
workstation work; that path is exercised by running
``scripts/export_run.py --region gulf_of_honduras``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from ghostnet.ingest import (
    BOA_ADD_OFFSET,
    QUANTIFICATION,
    IngestError,
    _deduplicate_acquisitions,
    _reflectance_scaling,
    build_grid,
    repeat_pairs,
)

AOI = (-88.86, 15.88, -88.36, 16.28)


def test_reprocessed_products_are_not_repeat_observations():
    from types import SimpleNamespace

    when = datetime(2020, 12, 22, 15, 36, 19, tzinfo=UTC)
    def item(name, baseline, time=when, tile="18QYF"):
        return SimpleNamespace(id=name, datetime=time,
                               properties={"s2:mgrs_tile": tile,
                                           "s2:processing_baseline": baseline})
    old = item("old", "02.12")
    new = item("new", "03.00")
    revisit = item("later", "03.00", when + timedelta(days=5))
    adjacent = item("adjacent", "03.00", tile="18QYG")
    result = _deduplicate_acquisitions([revisit, old, adjacent, new])
    assert {i.id for i in result} == {"new", "later", "adjacent"}
    assert result == _deduplicate_acquisitions([new, adjacent, old, revisit])


def test_processing_ties_have_a_stable_product_choice():
    from types import SimpleNamespace

    def item(name):
        return SimpleNamespace(id=name, datetime=datetime(2020, 1, 1),
            properties={"s2:mgrs_tile": "18QYF", "s2:processing_baseline": "03.00"})
    assert _deduplicate_acquisitions([item("product_202105"), item("product_202107")])[0].id == (
        "product_202107")


@dataclass
class FakeItem:
    """Minimal stand-in for a pystac Item."""

    properties: dict[str, Any]
    datetime: datetime


@dataclass
class FakeTile:
    tile_id: str
    acquired_at: datetime


# --- grid -----------------------------------------------------------------


def test_grid_is_north_up_and_covers_the_aoi():
    grid = build_grid(AOI, resolution_m=20.0)
    assert grid.lat_step < 0, "rows must increase southwards"
    assert grid.lon_step > 0
    transform = grid.transform
    assert transform.c == pytest.approx(AOI[0])
    assert transform.f == pytest.approx(AOI[3])
    # Ground spacing should be the requested resolution to within a percent.
    assert grid.height * abs(grid.lat_step) == pytest.approx(AOI[3] - AOI[1], rel=1e-3)
    assert grid.width * grid.lon_step == pytest.approx(AOI[2] - AOI[0], rel=1e-3)


def test_grid_longitude_step_is_widened_by_latitude():
    """A degree of longitude is shorter than a degree of latitude off-equator."""
    grid = build_grid(AOI, resolution_m=20.0)
    assert grid.lon_step > abs(grid.lat_step)


def test_the_pixel_budget_refuses_a_region_sized_request():
    """The full region bbox at 20 m is ~67 M pixels — a guard, not a limit."""
    full_region = (-88.8556, 15.6832, -86.1292, 16.5204)
    with pytest.raises(IngestError, match="pixel budget"):
        build_grid(full_region, resolution_m=20.0)


def test_the_pixel_budget_can_be_raised_deliberately():
    full_region = (-88.8556, 15.6832, -86.1292, 16.5204)
    grid = build_grid(full_region, resolution_m=20.0, max_pixels=200_000_000)
    assert grid.pixels > 25_000_000


def test_a_degenerate_bbox_is_rejected():
    with pytest.raises(IngestError, match="Degenerate"):
        build_grid((10.0, 5.0, 10.0, 5.0))


# --- reflectance scaling --------------------------------------------------


def test_pre_baseline_4_products_have_no_offset():
    """The chosen 2018 demo window predates the offset."""
    item = FakeItem({"s2:processing_baseline": "02.12"}, datetime(2018, 2, 24, tzinfo=UTC))
    scale, offset = _reflectance_scaling(item)
    assert offset == 0.0
    assert scale == pytest.approx(1 / QUANTIFICATION)


def test_baseline_4_products_carry_the_boa_offset():
    """From 2022-01-25 L2A reflectance needs -1000 before scaling."""
    item = FakeItem({"s2:processing_baseline": "04.00"}, datetime(2022, 3, 1, tzinfo=UTC))
    _, offset = _reflectance_scaling(item)
    assert offset == BOA_ADD_OFFSET


def test_a_missing_baseline_is_inferred_from_the_acquisition_date():
    """Silently assuming 'no offset' would shift every band by 0.1 reflectance."""
    recent = FakeItem({}, datetime(2023, 6, 1, tzinfo=UTC))
    old = FakeItem({}, datetime(2018, 6, 1, tzinfo=UTC))
    assert _reflectance_scaling(recent)[1] == BOA_ADD_OFFSET
    assert _reflectance_scaling(old)[1] == 0.0


def test_the_offset_moves_reflectance_by_a_tenth():
    """Guards the magnitude: getting this wrong wrecks the FDI, quietly."""
    scale, offset = _reflectance_scaling(
        FakeItem({"s2:processing_baseline": "05.00"}, datetime(2024, 1, 1, tzinfo=UTC))
    )
    raw = 2000.0
    assert raw * scale - (raw + offset) * scale == pytest.approx(0.1)


# --- repeat passes (FR-2.2) ----------------------------------------------


def _tile(mgrs: str, day: int) -> FakeTile:
    when = datetime(2018, 2, day)
    return FakeTile(tile_id=f"S2-{mgrs}-{when:%Y%m%d}", acquired_at=when)


def test_repeat_pairs_are_found_within_the_same_mgrs_tile():
    tiles = [_tile("16PCC", 19), _tile("16PCC", 24), _tile("16PCC", 26)]
    pairs = repeat_pairs(tiles)
    assert [(a.acquired_at.day, b.acquired_at.day) for a, b in pairs] == [(19, 24), (24, 26)]


def test_passes_over_different_tiles_are_not_a_repeat():
    """FR-2.2 needs a revisit over the same water, not two nearby scenes."""
    tiles = [_tile("16PCC", 19), _tile("16PDC", 20)]
    assert repeat_pairs(tiles) == []


def test_passes_too_far_apart_are_not_paired():
    tiles = [_tile("16PCC", 1), _tile("16PCC", 28)]
    assert repeat_pairs(tiles, max_gap_days=15) == []


def test_repeat_pairs_are_ordered_oldest_first():
    tiles = [_tile("16PCC", 26), _tile("16PCC", 19)]
    (earlier, later), = repeat_pairs(tiles)
    assert earlier.acquired_at < later.acquired_at


def test_a_single_pass_yields_no_pairs():
    assert repeat_pairs([_tile("16PCC", 19)]) == []


def test_same_timestamp_is_not_a_repeat():
    """A duplicated product is not a second observation."""
    when = datetime(2018, 2, 19)
    tiles = [
        FakeTile("S2-16PCC-20180219", when),
        FakeTile("S2-16PCC-20180219", when + timedelta(minutes=5)),
    ]
    assert repeat_pairs(tiles) == []
