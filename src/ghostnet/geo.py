"""Small geodesy helpers shared by the drift, attribution and vessel agents.

Spherical-earth approximations throughout. Over the scales this pipeline cares
about — debris drifting tens to a few hundred km over days — the error against a
proper geodesic is well under the drift model's own uncertainty envelope, and
keeping it dependency-free means these functions work before the geospatial
stack is installed on a given machine.
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088
# Metres per degree of latitude (WGS-84 mean).
M_PER_DEG_LAT = 111_320.0


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def metres_to_degrees(dx_m: float, dy_m: float, lat: float) -> tuple[float, float]:
    """Convert an east/north offset in metres to (dlon, dlat) at ``lat``.

    The cosine term is clamped so a trajectory that wanders towards a pole
    produces a large-but-finite step rather than dividing by zero.
    """
    dlat = dy_m / M_PER_DEG_LAT
    coslat = max(math.cos(math.radians(lat)), 1e-6)
    dlon = dx_m / (M_PER_DEG_LAT * coslat)
    return dlon, dlat


def mean_position(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Mean of (lon, lat) pairs, averaged on the unit sphere.

    Vector averaging rather than arithmetic mean so an ensemble straddling the
    antimeridian does not collapse to a point in the middle of the Pacific.
    """
    if not points:
        raise ValueError("mean_position() needs at least one point")
    x = y = z = 0.0
    for lon, lat in points:
        rlon, rlat = math.radians(lon), math.radians(lat)
        x += math.cos(rlat) * math.cos(rlon)
        y += math.cos(rlat) * math.sin(rlon)
        z += math.sin(rlat)
    n = len(points)
    x, y, z = x / n, y / n, z / n
    hyp = math.hypot(x, y)
    if hyp < 1e-12 and abs(z) < 1e-12:
        return points[0]
    return math.degrees(math.atan2(y, x)), math.degrees(math.atan2(z, hyp))


def spread_km(points: list[tuple[float, float]], centre: tuple[float, float]) -> float:
    """90th-percentile distance from ``centre`` — the uncertainty envelope radius.

    A percentile rather than a max so one runaway ensemble member does not
    define the envelope reported to the operator (FR-3.3).
    """
    if len(points) < 2:
        return 0.0
    distances = sorted(haversine_km(centre[0], centre[1], lon, lat) for lon, lat in points)
    idx = min(len(distances) - 1, int(math.ceil(0.9 * len(distances)) - 1))
    return distances[idx]
