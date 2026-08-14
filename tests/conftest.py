"""Synthetic fixtures — small, in-memory, and never a real dataset.

MACHINE-WORKFLOW.md limits tests to "a small cached sample of tiles/data, never
the full dataset". These fixtures go further: nothing here touches disk except a
few hundred bytes of CSV/JSON written to tmp_path, so the whole suite runs on a
fresh clone with no downloaded data and no credentials.

The spectral signatures below are constructed so each one exercises exactly one
of the verification agent's documented false-positive modes. They are physically
plausible orders of magnitude, not measured spectra — the real calibration is
the MARIDA benchmark on the workstation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from ghostnet.agents.detection import GeoTransform, Tile

BASE_TIME = datetime(2026, 3, 14, 5, 30, tzinfo=UTC)

# Surface reflectance per Sentinel-2 band. See tests/README-signatures for how
# each interacts with the FDI (Biermann et al. 2020).
SIGNATURES: dict[str, dict[str, float]] = {
    # Clean coastal water: FDI ~ 0, nothing detected.
    "water": {"B04": 0.030, "B06": 0.004, "B08": 0.002, "B11": 0.003},
    # Floating plastic: strong NIR shoulder, modest NDVI -> a true positive.
    "debris": {"B04": 0.045, "B06": 0.020, "B08": 0.050, "B11": 0.010},
    # Sun glint: bright and spectrally flat, including SWIR.
    "glint": {"B04": 0.090, "B06": 0.090, "B08": 0.090, "B11": 0.080},
    # Foam / whitecap: bright in the visible, no vegetation-like red edge.
    "foam": {"B04": 0.150, "B06": 0.100, "B08": 0.120, "B11": 0.030},
    # Kelp / Sargassum: vegetation NDVI dominating the FDI response.
    "kelp": {"B04": 0.020, "B06": 0.050, "B08": 0.100, "B11": 0.050},
    # Cloud shadow: anomalously dark across every band.
    "shadow": {"B04": 0.005, "B06": 0.005, "B08": 0.010, "B11": 0.002},
}

TRANSFORM = GeoTransform(
    lon_origin=80.000, lat_origin=12.000, lon_step=0.001, lat_step=-0.001
)


def make_tile(
    patches: dict[tuple[int, int], str],
    *,
    tile_id: str = "T44PLT-20260314",
    acquired_at: datetime | None = None,
    size: int = 40,
    patch_px: int = 7,
    transform: GeoTransform = TRANSFORM,
    geometry: dict[str, float] | None = None,
) -> Tile:
    """Build a water tile with square patches of the named signatures.

    ``patches`` maps a top-left ``(row, col)`` to a key of :data:`SIGNATURES`.
    Patches are ``patch_px`` square so a default 5x5 sampling window sits wholly
    inside one and is not diluted by surrounding water.
    """
    bands = {
        name: np.full((size, size), value, dtype=float)
        for name, value in SIGNATURES["water"].items()
    }
    for (row, col), kind in patches.items():
        signature = SIGNATURES[kind]
        for band, value in signature.items():
            bands[band][row : row + patch_px, col : col + patch_px] = value

    return Tile(
        tile_id=tile_id,
        acquired_at=acquired_at or BASE_TIME,
        bands=bands,
        transform=transform,
        source="synthetic-fixture",
        **(geometry or {}),
    )


@pytest.fixture
def water_tile() -> Tile:
    """Featureless water — the detector should find nothing at all."""
    return make_tile({})


@pytest.fixture
def debris_tile() -> Tile:
    """One genuine debris patch."""
    return make_tile({(10, 10): "debris"})


@pytest.fixture
def mixed_tile() -> Tile:
    """One true positive plus one of each documented false-positive mode."""
    return make_tile(
        {
            (5, 5): "debris",
            (5, 25): "glint",
            (20, 5): "foam",
            (20, 25): "kelp",
            (30, 15): "shadow",
        }
    )


@pytest.fixture
def river_csv(tmp_path: Path) -> Path:
    """A three-row stand-in for The Ocean Cleanup emission ranking."""
    path = tmp_path / "rivers.csv"
    path.write_text(
        "name,lon,lat,emission_tonnes_yr,country\n"
        # Close to the fixture tile, high emitter -> should dominate.
        "Test Kali,79.900,11.900,4200,India\n"
        # Similar distance, tiny emitter -> should rank below.
        "Small Creek,79.905,11.905,12,India\n"
        # Far away, huge emitter -> proximity must beat raw emission.
        "Distant Delta,90.000,20.000,120000,Elsewhere\n"
    )
    return path


@pytest.fixture
def mpa_json(tmp_path: Path) -> Path:
    path = tmp_path / "mpas.json"
    path.write_text(
        json.dumps(
            [
                {
                    "name": "Test Marine Reserve",
                    "lon": 80.20,
                    "lat": 11.95,
                    "radius_km": 5.0,
                    "designation": "Marine National Park",
                }
            ]
        )
    )
    return path


def hours(n: float) -> timedelta:
    return timedelta(hours=n)
