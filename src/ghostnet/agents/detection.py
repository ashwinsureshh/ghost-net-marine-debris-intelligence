"""FR-1 — Satellite Detection Agent (spectral-index baseline).

Implements the Floating Debris Index of Biermann et al. (2020), which is the
published baseline the PRD's §3 metrics table benchmarks against:

    FDI  = R_NIR - R'_NIR
    R'_NIR = R_RE2 + (R_SWIR1 - R_RE2) * ((λ_NIR - λ_RED) / (λ_SWIR1 - λ_RED)) * 10

with Sentinel-2 bands B08 (NIR, 833 nm), B06 (red edge 2, 740 nm), B11
(SWIR1, 1610 nm) and B04 (red, 665 nm) — the four bands `config/regions.yaml`
restricts downloads to.

Machine note (MACHINE-WORKFLOW.md): this module is CPU-only and runs anywhere.
The CNN variant (FR-1.4) is a separate module and **workstation only** — the
contract it must satisfy is this module's :func:`detect` signature, so it can be
swapped in behind the same ``Detection`` output without touching orchestration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from scipy import ndimage

from ghostnet.schemas import Detection, Evidence

# Sentinel-2 central wavelengths, nanometres.
WAVELENGTHS = {"B04": 665.0, "B06": 740.0, "B08": 833.0, "B11": 1610.0}
REQUIRED_BANDS = ("B04", "B06", "B08", "B11")

# FITTED against MARIDA on the workstation 2026-08-14 (was 0.006, the published
# starting point). Fitted on the train split only, by maximising the baseline
# detector's own F1; see eval/results.md for the sweep and the held-out result.
#
# 0.006 fired on open water: marine water's own FDI is ~0.013 at MARIDA's class
# mean, so the old default made the detector trigger before it saw any debris.
# Still region-tunable — re-check once the demo region is settled.
DEFAULT_FDI_THRESHOLD = 0.025
DEFAULT_MIN_PIXELS = 3

# The published starting point, kept addressable so the 'before' arm of the
# FR-2.4 ablation stays reproducible after the default was recalibrated.
# Without this, re-running scripts/eval_marida.py --fit would compare the
# fitted detector against itself and report a delta of zero.
LITERATURE_FDI_THRESHOLD = 0.006


@dataclass(frozen=True)
class GeoTransform:
    """Minimal north-up affine mapping pixel indices to lon/lat.

    Real L2A products are UTM; ``rasterio``/``pyproj`` handle that at ingest and
    hand this agent a reprojected grid. Keeping the in-memory representation
    this simple is what lets the detection maths be tested on synthetic arrays
    with no GDAL stack and no downloaded tile.
    """

    lon_origin: float
    lat_origin: float
    lon_step: float
    lat_step: float  # normally negative: row index increases southwards

    def to_lonlat(self, col: float, row: float) -> tuple[float, float]:
        return (
            self.lon_origin + (col + 0.5) * self.lon_step,
            self.lat_origin + (row + 0.5) * self.lat_step,
        )

    def to_pixel(self, lon: float, lat: float) -> tuple[int, int]:
        col = int(round((lon - self.lon_origin) / self.lon_step - 0.5))
        row = int(round((lat - self.lat_origin) / self.lat_step - 0.5))
        return col, row

    @property
    def pixel_area_km2(self) -> float:
        lat = self.lat_origin
        km_per_deg_lat = 110.574
        km_per_deg_lon = 111.320 * max(math.cos(math.radians(lat)), 1e-6)
        return abs(self.lon_step * km_per_deg_lon) * abs(self.lat_step * km_per_deg_lat)


@dataclass
class Tile:
    """One Sentinel-2 acquisition over the monitored region.

    ``bands`` holds surface reflectance in [0, 1] keyed by Sentinel-2 band name.
    Acquisition geometry is optional and only used by the verification agent's
    sun-glint check (FR-2.1); when absent that check reports itself as
    inconclusive rather than silently passing.
    """

    tile_id: str
    acquired_at: datetime
    bands: dict[str, np.ndarray]
    transform: GeoTransform
    sun_zenith_deg: float | None = None
    sun_azimuth_deg: float | None = None
    view_zenith_deg: float | None = None
    view_azimuth_deg: float | None = None
    cloud_mask: np.ndarray | None = None
    source: str = "synthetic"

    def __post_init__(self) -> None:
        missing = [b for b in REQUIRED_BANDS if b not in self.bands]
        if missing:
            raise ValueError(
                f"Tile {self.tile_id} is missing band(s) {missing}; the FDI needs "
                f"{list(REQUIRED_BANDS)}."
            )
        shapes = {b: self.bands[b].shape for b in REQUIRED_BANDS}
        if len(set(shapes.values())) != 1:
            raise ValueError(f"Tile {self.tile_id} has mismatched band shapes: {shapes}")

    @property
    def shape(self) -> tuple[int, int]:
        return self.bands["B08"].shape

    def evidence(self) -> Evidence:
        return Evidence(
            kind="sentinel2_tile",
            ref=self.tile_id,
            detail=f"acquired {self.acquired_at.isoformat()} ({self.source})",
        )


def floating_debris_index(
    red: np.ndarray, red_edge2: np.ndarray, nir: np.ndarray, swir1: np.ndarray
) -> np.ndarray:
    """Biermann et al. (2020) FDI. Positive values indicate floating material."""
    lam = WAVELENGTHS
    factor = ((lam["B08"] - lam["B04"]) / (lam["B11"] - lam["B04"])) * 10.0
    baseline = red_edge2 + (swir1 - red_edge2) * factor
    return nir - baseline


def ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    denom = nir + red
    return np.divide(nir - red, denom, out=np.zeros_like(denom), where=denom != 0)


def _confidence(fdi_mean: float, threshold: float, area_px: int) -> float:
    """Map FDI margin and patch size onto a raw [0, 1] detector confidence.

    Deliberately a smooth monotone squash, not a calibrated probability — FR-1.3
    asks for a raw score, and the honest calibration step is the MARIDA
    benchmark on the workstation, not a constant invented here.
    """
    margin = max(fdi_mean - threshold, 0.0)
    strength = 1.0 - math.exp(-margin / max(threshold, 1e-6))
    size = 1.0 - math.exp(-area_px / 8.0)
    return round(min(1.0, 0.65 * strength + 0.35 * size), 4)


def detect(
    tile: Tile,
    *,
    fdi_threshold: float = DEFAULT_FDI_THRESHOLD,
    min_pixels: int = DEFAULT_MIN_PIXELS,
    max_detections: int = 200,
) -> list[Detection]:
    """Run the spectral-index detector over one tile (FR-1.2, FR-1.3)."""
    fdi = floating_debris_index(
        tile.bands["B04"], tile.bands["B06"], tile.bands["B08"], tile.bands["B11"]
    )
    veg = ndvi(tile.bands["B04"], tile.bands["B08"])

    mask = fdi > fdi_threshold
    if tile.cloud_mask is not None:
        mask &= ~tile.cloud_mask.astype(bool)

    labelled, count = ndimage.label(mask)
    pixel_area = tile.transform.pixel_area_km2
    tile_evidence = tile.evidence()

    detections: list[Detection] = []
    for label_id in range(1, count + 1):
        component = labelled == label_id
        area_px = int(component.sum())
        if area_px < min_pixels:
            continue
        rows, cols = np.nonzero(component)
        centroid_row = float(rows.mean())
        centroid_col = float(cols.mean())
        lon, lat = tile.transform.to_lonlat(centroid_col, centroid_row)
        fdi_mean = float(fdi[component].mean())
        detections.append(
            Detection(
                id=f"{tile.tile_id}-d{label_id:04d}",
                tile_id=tile.tile_id,
                acquired_at=tile.acquired_at,
                lon=round(lon, 6),
                lat=round(lat, 6),
                area_px=area_px,
                area_km2=round(area_px * pixel_area, 6),
                fdi_mean=round(fdi_mean, 6),
                ndvi_mean=round(float(veg[component].mean()), 6),
                confidence=_confidence(fdi_mean, fdi_threshold, area_px),
                detector="fdi",
                evidence=[tile_evidence],
            )
        )

    detections.sort(key=lambda d: d.confidence, reverse=True)
    return detections[:max_detections]


@dataclass
class BandWindow:
    """Mean reflectance per band in a small window around a detection.

    Produced here and consumed by the verification agent so that FR-2's checks
    never have to re-open a tile or know the transform.
    """

    detection_id: str
    tile_id: str
    acquired_at: datetime
    band_means: dict[str, float]
    fdi: float
    ndvi: float
    window_px: int
    cloud_fraction: float = 0.0
    geometry: dict[str, float] = field(default_factory=dict)

    def _statistic_bands(self) -> list[float]:
        """The bands brightness and flatness are defined over.

        Deliberately fixed to REQUIRED_BANDS rather than "every band present".
        A ``Tile`` may legitimately carry more — the CNN variant (FR-1.4) needs
        all eleven MARIDA bands — and averaging over whatever happens to be in
        the dict would silently redefine both statistics, and with them every
        verification threshold fitted against them. Measured: feeding 11-band
        tiles through the 4-band-fitted thresholds dropped held-out precision
        from 0.623 to 0.447 and cloud rejection from 91.8% to 69.9%, with no
        error anywhere. Thresholds are only meaningful against a fixed basis.
        """
        return [self.band_means[b] for b in REQUIRED_BANDS if b in self.band_means]

    @property
    def brightness(self) -> float:
        return float(np.mean(self._statistic_bands()))

    @property
    def flatness(self) -> float:
        """Coefficient of variation across bands; low means spectrally flat."""
        values = np.array(self._statistic_bands(), dtype=float)
        mean = float(values.mean())
        if mean <= 0:
            return 0.0
        return float(values.std() / mean)


def sample_window(tile: Tile, detection: Detection, *, half_width: int = 2) -> BandWindow:
    """Extract the spectral neighbourhood of a detection from a tile."""
    col, row = tile.transform.to_pixel(detection.lon, detection.lat)
    n_rows, n_cols = tile.shape
    r0, r1 = max(0, row - half_width), min(n_rows, row + half_width + 1)
    c0, c1 = max(0, col - half_width), min(n_cols, col + half_width + 1)
    if r0 >= r1 or c0 >= c1:
        raise ValueError(
            f"Detection {detection.id} at ({detection.lon}, {detection.lat}) falls "
            f"outside tile {tile.tile_id}."
        )

    means = {name: float(arr[r0:r1, c0:c1].mean()) for name, arr in tile.bands.items()}
    fdi = float(
        floating_debris_index(
            np.array(means["B04"]),
            np.array(means["B06"]),
            np.array(means["B08"]),
            np.array(means["B11"]),
        )
    )
    veg = float(ndvi(np.array(means["B04"]), np.array(means["B08"])))
    cloud = 0.0
    if tile.cloud_mask is not None:
        cloud = float(tile.cloud_mask[r0:r1, c0:c1].astype(bool).mean())

    geometry: dict[str, float] = {}
    for key in ("sun_zenith_deg", "sun_azimuth_deg", "view_zenith_deg", "view_azimuth_deg"):
        value = getattr(tile, key)
        if value is not None:
            geometry[key] = float(value)

    return BandWindow(
        detection_id=detection.id,
        tile_id=tile.tile_id,
        acquired_at=tile.acquired_at,
        band_means=means,
        fdi=fdi,
        ndvi=veg,
        window_px=(r1 - r0) * (c1 - c0),
        cloud_fraction=cloud,
        geometry=geometry,
    )


def load_tiles(region_id: str, **kwargs) -> list[Tile]:
    """Load Sentinel-2 L2A tiles for a configured region (FR-1.1).

    Implemented in :mod:`ghostnet.ingest`; imported lazily so this module stays
    importable without a network stack. Products are **streamed** as
    cloud-optimised GeoTIFFs from a public STAC catalogue rather than
    downloaded to ``data/raw/sentinel2`` first — same Copernicus L2A products,
    no credential, and no multi-GB local archive to keep in sync between the
    two machines. That directory remains available as an optional local cache.

    Bandwidth- and memory-heavy: this is workstation work per
    MACHINE-WORKFLOW.md. See :func:`ghostnet.ingest.load_tiles` for the
    resolution, area-budget and water-masking options.
    """
    from ghostnet.ingest import load_tiles as _load_tiles

    return _load_tiles(region_id, **kwargs)
