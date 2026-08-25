"""FR-1.1 — Sentinel-2 L2A ingestion.

Turns real Copernicus Sentinel-2 Level-2A products into the ``Tile`` contract in
:mod:`ghostnet.agents.detection`, so the FDI detector and everything downstream
run on real imagery with no changes anywhere else.
:func:`ghostnet.agents.detection.load_tiles` delegates here.

WORKSTATION work per MACHINE-WORKFLOW.md: reading a region's worth of L2A is
bandwidth- and memory-heavy and is not something to run on the Air.

Where the data comes from
-------------------------
Products are pulled from Microsoft Planetary Computer's STAC API, which serves
the **same Copernicus Sentinel-2 L2A products** as the Copernicus Data Space
Ecosystem named in PRD FR-1.1, as cloud-optimised GeoTIFFs, with anonymous
access and no account. That keeps PRD §8's free-tier constraint satisfied
*and* removes a credential from the demo path — a Copernicus login is one more
thing that can fail in a viva. ``earth-search`` (AWS Open Data) is a drop-in
alternative catalogue; it uses common-band asset names (``red``, ``rededge2``,
``nir``, ``swir16``) instead of ``B04``/``B06``/``B08``/``B11``.

Four things here are easy to get silently wrong
-----------------------------------------------
1. **Processing-baseline offset.** From baseline 04.00 (2022-01-25) L2A
   reflectance carries ``BOA_ADD_OFFSET = -1000`` before the 1/10000 scaling.
   Applying the wrong one shifts every band by 0.1 reflectance, which would
   quietly wreck the FDI. Handled per item from ``s2:processing_baseline``.
   The chosen demo window (2018) predates it, so this is latent until someone
   picks a recent window — which is exactly when it would be missed.
2. **Land.** FDI keys off a NIR shoulder, and vegetation on land has an
   enormous one. Run unmasked over this region and land swamps the water
   detections completely. Non-water pixels (SCL class 6 is water) are zeroed,
   which puts their FDI at exactly 0.0, below any sane threshold.
3. **Band resolution.** B04/B08 are 10 m natively but B06/B11 are 20 m. The FDI
   needs all four, so 20 m is the honest working resolution — upsampling the
   SWIR to 10 m invents detail the instrument never recorded.
4. **View geometry is not in STAC.** Solar zenith/azimuth are, view angles are
   not, so :func:`ghostnet.agents.verification._specular_angle_deg` returns
   ``None`` and ``bright_swir_target`` reports "cloud, vessel or specular
   reflection" rather than naming sun glint. That is honest: it still
   disqualifies on the spectral signature, and it marks itself inconclusive.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

from ghostnet.config import GhostNetError, get_region

STAC_API = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"

# Planetary Computer keeps the native Sentinel-2 band names.
# The FDI needs four; the CNN variant (FR-1.4) needs all eleven MARIDA bands,
# so `bands=` selects. Extra bands are harmless to the FDI path - Tile only
# requires the four to be present, not that nothing else is.
FDI_BANDS = ("B04", "B06", "B08", "B11")
MARIDA_BANDS = (
    "B01", "B02", "B03", "B04", "B05", "B06",
    "B07", "B08", "B8A", "B11", "B12",
)

# Scene Classification Layer classes (ESA L2A ATBD table 3).
SCL_NODATA = 0
SCL_SATURATED = 1
SCL_CLOUD_SHADOW = 3
SCL_WATER = 6
SCL_CLOUD_MED = 8
SCL_CLOUD_HIGH = 9
SCL_CIRRUS = 10
SCL_CLOUD_CLASSES = (SCL_CLOUD_SHADOW, SCL_CLOUD_MED, SCL_CLOUD_HIGH, SCL_CIRRUS)

QUANTIFICATION = 10000.0
BASELINE_WITH_OFFSET = 4.00
BOA_ADD_OFFSET = -1000.0

# Guard against accidentally asking for a continent. 25M px at 20 m is roughly
# a 100 x 100 km box, which is a demo-sized area and a ~400 MB working set.
DEFAULT_MAX_PIXELS = 25_000_000
DEFAULT_RESOLUTION_M = 20.0

METRES_PER_DEG_LAT = 110_574.0
METRES_PER_DEG_LON = 111_320.0


class IngestError(GhostNetError):
    """Raised when L2A ingestion cannot proceed."""


@dataclass(frozen=True)
class Grid:
    """Target EPSG:4326 raster grid for one run."""

    bbox: tuple[float, float, float, float]
    resolution_m: float
    lon_step: float
    lat_step: float          # negative: rows increase southwards
    width: int
    height: int

    @property
    def transform(self):  # -> affine.Affine
        from affine import Affine

        return Affine(self.lon_step, 0.0, self.bbox[0], 0.0, self.lat_step, self.bbox[3])

    @property
    def pixels(self) -> int:
        return self.width * self.height


def build_grid(
    bbox: tuple[float, float, float, float],
    *,
    resolution_m: float = DEFAULT_RESOLUTION_M,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> Grid:
    """North-up lon/lat grid at approximately ``resolution_m`` ground spacing."""
    min_lon, min_lat, max_lon, max_lat = bbox
    if not (max_lon > min_lon and max_lat > min_lat):
        raise IngestError(f"Degenerate bbox {bbox}")

    mid_lat = (min_lat + max_lat) / 2.0
    lat_step = resolution_m / METRES_PER_DEG_LAT
    lon_step = resolution_m / (METRES_PER_DEG_LON * max(math.cos(math.radians(mid_lat)), 1e-6))

    width = int(round((max_lon - min_lon) / lon_step))
    height = int(round((max_lat - min_lat) / lat_step))
    if width < 1 or height < 1:
        raise IngestError(f"bbox {bbox} is smaller than one {resolution_m} m pixel")

    grid = Grid(tuple(bbox), resolution_m, lon_step, -lat_step, width, height)
    if grid.pixels > max_pixels:
        area_km2 = (width * resolution_m / 1000) * (height * resolution_m / 1000)
        raise IngestError(
            f"Requested area is {width}x{height} = {grid.pixels:,} pixels "
            f"(~{area_km2:,.0f} km²) at {resolution_m} m, above the {max_pixels:,} "
            "pixel budget. Narrow the region's `aoi_bbox` in config/regions.yaml, "
            "raise resolution_m, or pass a larger max_pixels deliberately."
        )
    return grid


def _configure_gdal() -> None:
    """Make GDAL's HTTP reader behave for COGs over the network."""
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.TIF,.jp2")
    os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
    os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "1")
    os.environ.setdefault("VSI_CACHE", "TRUE")


def search_l2a(
    bbox: tuple[float, float, float, float],
    start: str,
    end: str,
    *,
    max_cloud_cover_pct: float = 20.0,
    mgrs_tiles: list[str] | None = None,
    limit: int | None = None,
) -> list[Any]:
    """STAC search for L2A products over a bbox and window (FR-1.1).

    Returned oldest-first so repeat passes read in acquisition order, which is
    what the multi-temporal check (FR-2.2) needs.
    """
    try:
        import planetary_computer
        import pystac_client
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise IngestError(
            "pystac-client and planetary-computer are required for L2A ingestion; "
            "they are in requirements-base.txt."
        ) from exc

    catalog = pystac_client.Client.open(STAC_API, modifier=planetary_computer.sign_inplace)
    search = catalog.search(
        collections=[COLLECTION],
        bbox=list(bbox),
        datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": max_cloud_cover_pct}},
    )
    items = list(search.items())

    if mgrs_tiles:
        wanted = {t.upper() for t in mgrs_tiles}
        items = [i for i in items if str(i.properties.get("s2:mgrs_tile", "")).upper() in wanted]

    items.sort(key=lambda i: i.datetime)
    return items[:limit] if limit else items


def _reflectance_scaling(item: Any) -> tuple[float, float]:
    """Return (scale, offset) for this product's processing baseline."""
    raw = item.properties.get("s2:processing_baseline")
    try:
        baseline = float(raw)
    except (TypeError, ValueError):
        # Unknown baseline: infer from the acquisition date, which is when the
        # offset was introduced. Better than silently assuming no offset.
        cutover = datetime(2022, 1, 25, tzinfo=item.datetime.tzinfo)
        baseline = 4.00 if item.datetime >= cutover else 0.0
    offset = BOA_ADD_OFFSET if baseline >= BASELINE_WITH_OFFSET else 0.0
    return 1.0 / QUANTIFICATION, offset


def _read_asset(item: Any, asset_key: str, grid: Grid, *, nearest: bool = False) -> np.ndarray:
    """Read one asset warped onto the target lon/lat grid."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT

    if asset_key not in item.assets:
        raise IngestError(
            f"Item {item.id} has no asset {asset_key!r}; available: "
            f"{sorted(item.assets)[:12]}"
        )

    resampling = Resampling.nearest if nearest else Resampling.bilinear
    with rasterio.open(item.assets[asset_key].href) as src:
        with WarpedVRT(
            src,
            crs="EPSG:4326",
            transform=grid.transform,
            width=grid.width,
            height=grid.height,
            resampling=resampling,
        ) as vrt:
            return vrt.read(1)


def item_to_tile(
    item: Any,
    grid: Grid,
    *,
    water_only: bool = True,
    max_cloud_frac: float | None = None,
    min_water_frac: float = 0.0,
    bands: tuple[str, ...] = FDI_BANDS,
) -> Any | None:
    """Read one L2A product into a :class:`~ghostnet.agents.detection.Tile`.

    Returns ``None`` when the scene is too clouded or too dry over *this AOI*
    to be worth the four band reads.

    The STAC ``eo:cloud_cover`` field is scene-level and a poor proxy for cloud
    over a small AOI: the 2018-02-09 product over this region advertises 17%
    cloud and is 84% clouded over the Motagua AOI. SCL is read first precisely
    so that judgement is made on the AOI before paying for the bands.
    """
    from ghostnet.agents.detection import GeoTransform, Tile

    _configure_gdal()
    scale, offset = _reflectance_scaling(item)

    scl = _read_asset(item, "SCL", grid, nearest=True).astype("uint8")
    cloud = np.isin(scl, SCL_CLOUD_CLASSES)
    invalid = np.isin(scl, (SCL_NODATA, SCL_SATURATED))
    water = scl == SCL_WATER

    if max_cloud_frac is not None and float(cloud.mean()) > max_cloud_frac:
        return None
    if min_water_frac > 0.0 and float(water.mean()) < min_water_frac:
        return None

    stacks: dict[str, np.ndarray] = {}
    for name in bands:
        raw = _read_asset(item, name, grid).astype("float32")
        reflectance = (raw + offset) * scale
        # Negative reflectance is a scaling/atmospheric artefact, not signal.
        np.clip(reflectance, 0.0, 1.6, out=reflectance)
        if water_only:
            # Zero rather than NaN: FDI over zeros is exactly 0.0, which falls
            # below any threshold, and it keeps sample_window's plain .mean()
            # finite. NaN would propagate into confidences.
            reflectance[~water] = 0.0
        reflectance[invalid] = 0.0
        stacks[name] = reflectance

    props = item.properties
    mgrs = props.get("s2:mgrs_tile", "?")
    acquired = item.datetime.replace(tzinfo=None)

    return Tile(
        # Encodes MGRS tile + date so repeat passes over the same tile are
        # identifiable downstream — that is what FR-2.2 pairs on.
        tile_id=f"S2-{mgrs}-{acquired:%Y%m%d}",
        acquired_at=acquired,
        bands=stacks,
        transform=GeoTransform(
            lon_origin=grid.bbox[0],
            lat_origin=grid.bbox[3],
            lon_step=grid.lon_step,
            lat_step=grid.lat_step,
        ),
        sun_zenith_deg=_as_float(props.get("s2:mean_solar_zenith")),
        sun_azimuth_deg=_as_float(props.get("s2:mean_solar_azimuth")),
        # Per-band view angles are not published in STAC; left absent so the
        # verification agent reports the glint geometry as untested rather than
        # inventing an angle.
        view_zenith_deg=None,
        view_azimuth_deg=None,
        cloud_mask=cloud | invalid,
        source=f"sentinel-2-l2a/{item.id}",
    )


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_tiles(
    region_id: str,
    *,
    limit: int | None = None,
    resolution_m: float = DEFAULT_RESOLUTION_M,
    max_pixels: int = DEFAULT_MAX_PIXELS,
    water_only: bool = True,
    max_cloud_cover_pct: float | None = None,
    max_aoi_cloud_frac: float = 0.60,
    min_water_frac: float = 0.05,
    bands: tuple[str, ...] = FDI_BANDS,
    verbose: bool = False,
) -> list[Any]:
    """Load Sentinel-2 L2A tiles for a configured region (FR-1.1).

    Reads the region's ``aoi_bbox`` when present, otherwise its full ``bbox``.
    The AOI exists because a region's bbox is its *definition* while a run has
    to stay demo-sized; see config/regions.yaml.

    Two-stage cloud screening: ``max_cloud_cover_pct`` filters the STAC search
    on scene-level metadata, then ``max_aoi_cloud_frac`` drops what is actually
    clouded over the AOI. The second one does most of the useful work.
    """
    entry = get_region(region_id)
    bbox = tuple(entry.get("aoi_bbox") or entry["bbox"])
    window = entry["time_window"]
    cloud = (
        max_cloud_cover_pct
        if max_cloud_cover_pct is not None
        else float(entry.get("max_cloud_cover_pct", 20))
    )

    grid = build_grid(bbox, resolution_m=resolution_m, max_pixels=max_pixels)
    items = search_l2a(
        bbox,
        str(window["start"]),
        str(window["end"]),
        max_cloud_cover_pct=cloud,
        mgrs_tiles=entry.get("mgrs_tiles"),
    )
    if not items:
        raise IngestError(
            f"No Sentinel-2 L2A products for region {region_id!r} in "
            f"{window['start']}..{window['end']} under {cloud}% cloud. Widen the "
            "window or raise max_cloud_cover_pct in config/regions.yaml."
        )

    tiles: list[Any] = []
    skipped = 0
    for item in items:
        tile = item_to_tile(
            item,
            grid,
            water_only=water_only,
            max_cloud_frac=max_aoi_cloud_frac,
            min_water_frac=min_water_frac,
            bands=bands,
        )
        if tile is None:
            skipped += 1
            if verbose:
                print(f"  skip {item.id[:52]} (cloud/water over AOI)", flush=True)
            continue
        tiles.append(tile)
        if verbose:
            print(f"  read {tile.tile_id} ({len(tiles)} kept)", flush=True)
        if limit and len(tiles) >= limit:
            break

    if not tiles:
        raise IngestError(
            f"All {len(items)} candidate products for {region_id!r} were rejected "
            f"over the AOI (cloud > {max_aoi_cloud_frac:.0%} or water < "
            f"{min_water_frac:.0%}). Scene-level cloud cover is not AOI cloud "
            "cover — widen the time window, or relax max_aoi_cloud_frac."
        )
    if verbose and skipped:
        print(f"  ({skipped} of {len(items)} products skipped on AOI screening)")
    return tiles


def repeat_pairs(tiles: list[Any], *, max_gap_days: float = 15.0) -> list[tuple[Any, Any]]:
    """Pairs of passes over the same MGRS tile close enough to compare (FR-2.2).

    The multi-temporal check needs a genuine revisit over the same water, not
    merely two acquisitions somewhere in the region.
    """
    by_tile: dict[str, list[Any]] = {}
    for tile in tiles:
        by_tile.setdefault(tile.tile_id.rsplit("-", 1)[0], []).append(tile)

    pairs = []
    for group in by_tile.values():
        group.sort(key=lambda t: t.acquired_at)
        for earlier, later in zip(group, group[1:], strict=False):
            gap = abs((later.acquired_at - earlier.acquired_at).days)
            if 0 < gap <= max_gap_days:
                pairs.append((earlier, later))
    return pairs
