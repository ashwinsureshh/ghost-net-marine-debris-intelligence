"""Restrict detection to open sea, from the Sentinel-2 scene classification (SCL).

Why this exists. SCL class 6 ("water") includes rivers, lagoons and ponds, and
the CNN detector fires along the boundary between zeroed land and water. A
recurrence audit of the served runs (2026-11-07) found 40% of Gulf of Honduras
and 48% of Gulf of Gonave detections on land or inland water, and 10% of
Honduras detections touching an image's no-data edge. None of these is
floating ocean debris, and the verification checks do not look for them.

The mask keeps a pixel only when it is:

* SCL water (class 6);
* part of a connected region holding at least ``min_sea_water_km2`` of water
  pixels. Cloud and cloud shadow may *connect* water (so a cloud bank cannot
  split the sea into fake lakes), but only true water pixels count towards the
  area (so a cloud bank over land joined to a lake cannot pass as sea);
* more than ``edge_buffer_m`` from SCL no-data (the scene's swath edge).

Connectivity is 4-neighbour, so a beach or sand bar one pixel wide separates a
lagoon from the sea. This is an approximation from one scene's classification,
not a coastline dataset: a tidal lagoon open to the sea counts as sea, and very
turbid sea classified as something other than water is excluded.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

SCL_NODATA = 0
SCL_WATER = 6
SCL_CONNECTORS = (3, 8, 9, 10)  # cloud shadow, medium/high cloud, cirrus

DEFAULT_MIN_SEA_WATER_KM2 = 25.0
DEFAULT_EDGE_BUFFER_M = 300.0


def open_sea_mask(
    scl: np.ndarray,
    resolution_m: float,
    *,
    min_sea_water_km2: float = DEFAULT_MIN_SEA_WATER_KM2,
    edge_buffer_m: float = DEFAULT_EDGE_BUFFER_M,
) -> np.ndarray:
    """Boolean mask of open-sea pixels for one scene's SCL raster."""
    if resolution_m <= 0 or min_sea_water_km2 < 0 or edge_buffer_m < 0:
        raise ValueError("resolution, sea area and edge buffer must be positive")
    scl = np.asarray(scl)
    water = scl == SCL_WATER
    connectable = water | np.isin(scl, SCL_CONNECTORS)
    labels, count = ndimage.label(connectable)  # 4-connectivity by default
    if count == 0:
        return np.zeros(scl.shape, dtype=bool)

    px_km2 = (resolution_m * resolution_m) / 1e6
    water_km2 = np.bincount(labels[water], minlength=count + 1) * px_km2
    sea_labels = np.flatnonzero(water_km2 >= min_sea_water_km2)
    sea_labels = sea_labels[sea_labels > 0]
    mask = water & np.isin(labels, sea_labels)

    buffer_px = int(round(edge_buffer_m / resolution_m))
    nodata = scl == SCL_NODATA
    if buffer_px > 0 and nodata.any():
        near_edge = ndimage.maximum_filter(nodata, size=2 * buffer_px + 1)
        mask &= ~near_edge
    return mask
