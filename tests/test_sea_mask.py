"""Open-sea mask: rivers, lagoons, cloud over land and swath edges are excluded."""

from __future__ import annotations

from datetime import datetime

import numpy as np

from ghostnet.agents.detection import GeoTransform, Tile, detect
from ghostnet.sea_mask import open_sea_mask

LAND, WATER, CLOUD, NODATA = 4, 6, 9, 0
RES = 100.0  # 100 m pixels, so 1 km^2 = 100 px


def _scene():
    scl = np.full((100, 100), LAND, dtype=np.uint8)
    scl[:, 50:] = WATER            # sea: 50 x 100 px = 50 km^2
    scl[10:14, 10:14] = WATER      # lagoon on land: 0.16 km^2
    scl[40:60, 5:8] = WATER        # river: 0.6 km^2
    return scl


def test_sea_is_kept_and_lagoon_and_river_are_not():
    mask = open_sea_mask(_scene(), RES, min_sea_water_km2=25, edge_buffer_m=0)
    assert mask[50, 75]
    assert not mask[12, 12]
    assert not mask[50, 6]
    assert not mask[50, 25]  # land


def test_a_one_pixel_sand_bar_separates_a_lagoon_from_the_sea():
    scl = _scene()
    scl[20:30, 40:49] = WATER   # lagoon ending one pixel short of the sea
    assert not open_sea_mask(scl, RES, edge_buffer_m=0)[25, 45]
    scl[20:30, 49] = WATER      # open the inlet
    assert open_sea_mask(scl, RES, edge_buffer_m=0)[25, 45]


def test_cloud_cannot_split_the_sea_into_lakes():
    scl = _scene()
    scl[:, 70:73] = CLOUD  # a cloud band cutting the sea in two
    mask = open_sea_mask(scl, RES, min_sea_water_km2=25, edge_buffer_m=0)
    assert mask[50, 60] and mask[50, 90]
    assert not mask[50, 71]  # cloud itself is never "sea"


def test_cloud_over_land_cannot_make_a_lake_count_as_sea():
    scl = _scene()
    scl[0:100, 15:45] = CLOUD     # 30 km^2 of cloud over land ...
    scl[10:14, 10:16] = WATER     # ... touching the small lagoon
    mask = open_sea_mask(scl, RES, min_sea_water_km2=25, edge_buffer_m=0)
    assert not mask[12, 12]
    assert mask[50, 75]


def test_pixels_near_the_swath_edge_are_dropped():
    scl = _scene()
    scl[:, 95:] = NODATA
    mask = open_sea_mask(scl, RES, edge_buffer_m=300)
    assert not mask[50, 93]       # within 3 px of no-data
    assert mask[50, 80]


def test_detection_respects_the_sea_mask():
    shape = (100, 100)
    bright = {b: np.full(shape, 0.02, dtype="float32") for b in ("B04", "B06", "B08", "B11")}
    bright["B08"][45:55, 20:30] = 0.30  # an FDI-positive patch on land
    bright["B08"][45:55, 70:80] = 0.30  # and one at sea
    tf = GeoTransform(lon_origin=0.0, lat_origin=1.0, lon_step=0.001, lat_step=-0.001)
    sea = open_sea_mask(_scene(), RES, edge_buffer_m=0)
    tile = Tile("t", datetime(2020, 1, 1), bright, tf, sea_mask=sea)
    unmasked = Tile("t", datetime(2020, 1, 1), bright, tf)
    assert len(detect(unmasked)) == 2
    kept = detect(tile)
    assert len(kept) == 1 and kept[0].lon > 0.05
