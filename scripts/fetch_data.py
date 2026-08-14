"""Documented, on-demand fetcher for the datasets this pipeline needs.

None of these datasets are committed to git (see .gitignore). This script is
the single source of truth for *where each dataset must live locally* and *how
to obtain it*, so a fresh clone on either machine can be brought up to date.

    python scripts/fetch_data.py --status          # what's present vs missing
    python scripts/fetch_data.py --instructions    # how to obtain each dataset
    python scripts/fetch_data.py --init            # create the directory layout

Access notes
------------
Every source below is free, but most need an account and credentials placed in
`.env` (copy `.env.example`). Automated download is deliberately NOT run
without an explicit dataset argument: Copernicus and Global Fishing Watch both
rate-limit free-tier access, and MARIDA is a multi-GB download that belongs on
the workstation only (see MACHINE-WORKFLOW.md).
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"


@dataclasses.dataclass(frozen=True)
class Dataset:
    key: str
    name: str
    local_path: Path
    purpose: str
    source_url: str
    credentials: str | None
    workstation_only: bool
    how: str


DATASETS: tuple[Dataset, ...] = (
    Dataset(
        key="sentinel2",
        name="Copernicus Sentinel-2 L2A tiles",
        local_path=DATA_ROOT / "raw" / "sentinel2",
        purpose="Debris detection (FR-1) and multi-temporal verification (FR-2.2)",
        source_url="https://dataspace.copernicus.eu/",
        credentials="COPERNICUS_USER / COPERNICUS_PASSWORD in .env",
        workstation_only=True,
        how=(
            "Register on the Copernicus Data Space Ecosystem, then query by AOI "
            "and date window using the STAC/OData API (openEO or pystac-client). "
            "Download L2A products for the monitored region defined in "
            "config/regions.yaml. Keep only the bands the FDI needs "
            "(B04, B06, B08, B11) to limit disk use."
        ),
    ),
    Dataset(
        key="marida",
        name="MARIDA marine debris benchmark",
        local_path=DATA_ROOT / "marida",
        purpose="Labelled benchmark for detection/verification evaluation (FR-1.4, FR-2.4)",
        source_url="https://marida.aiia.csd.auth.gr/",
        credentials=None,
        workstation_only=True,
        how=(
            "Download the MARIDA archive and extract it here, preserving the "
            "upstream patches/ and splits/ layout. Multi-GB — workstation only; "
            "never sync to the MacBook Air."
        ),
    ),
    Dataset(
        key="oscar",
        name="NOAA OSCAR surface currents",
        local_path=DATA_ROOT / "oscar",
        purpose="Backward/forward drift trajectory modelling (FR-3)",
        source_url="https://podaac.jpl.nasa.gov/dataset/OSCAR_L4_OC_NRT_V2.0",
        credentials="EARTHDATA_TOKEN in .env",
        workstation_only=False,
        how=(
            "Fetch NetCDF current fields from PO.DAAC for the demo time window "
            "only. A single region-month is small enough for the Air."
        ),
    ),
    Dataset(
        key="drifters",
        name="NOAA Global Drifter Program buoy tracks",
        local_path=DATA_ROOT / "drifters",
        purpose="Ground truth for validating the Drift Agent's trajectories",
        source_url="https://www.aoml.noaa.gov/global-drifter-program/",
        credentials=None,
        workstation_only=False,
        how=(
            "Download the interpolated 6-hourly drifter dataset, subset to the "
            "monitored region's bounding box before saving."
        ),
    ),
    Dataset(
        key="rivers",
        name="The Ocean Cleanup river emission rankings",
        local_path=DATA_ROOT / "rivers",
        purpose="Source attribution over candidate rivers (FR-4)",
        source_url="https://theoceancleanup.com/sources/",
        credentials=None,
        workstation_only=False,
        how=(
            "Small tabular dataset of ranked river plastic emissions. Small "
            "enough that a trimmed CSV may live in tests/fixtures/ for tests."
        ),
    ),
    Dataset(
        key="gfw",
        name="Global Fishing Watch SAR detections + AIS",
        local_path=DATA_ROOT / "gfw",
        purpose="Dark-vessel correlation (FR-5)",
        source_url="https://globalfishingwatch.org/our-apis/",
        credentials="GFW_API_TOKEN in .env",
        workstation_only=False,
        how=(
            "Request a free API token, then query the 4Wings / vessel-detections "
            "endpoints for the detection's space-time window. Cache responses to "
            "disk — the free tier is rate-limited."
        ),
    ),
    Dataset(
        key="mpa",
        name="UNEP-WCMC Protected Planet MPA boundaries",
        local_path=DATA_ROOT / "protected_planet",
        purpose="Ecological-risk scoring for prioritisation (FR-6.1)",
        source_url="https://www.protectedplanet.net/en/thematic-areas/marine-protected-areas",
        credentials=None,
        workstation_only=False,
        how=(
            "Download the WDPA marine subset as a shapefile/geopackage and clip "
            "to the monitored region before use — the global file is large."
        ),
    ),
)

BY_KEY = {d.key: d for d in DATASETS}


def _is_populated(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(p.name != ".gitkeep" for p in path.iterdir())


def cmd_init() -> int:
    for dataset in DATASETS:
        dataset.local_path.mkdir(parents=True, exist_ok=True)
        keep = dataset.local_path / ".gitkeep"
        if not keep.exists():
            keep.touch()
    print(f"Created {len(DATASETS)} dataset directories under {DATA_ROOT}")
    return 0


def cmd_status() -> int:
    print(f"Data root: {DATA_ROOT}\n")
    missing = 0
    for dataset in DATASETS:
        present = _is_populated(dataset.local_path)
        if not present:
            missing += 1
        mark = "present" if present else "MISSING"
        flag = "  [workstation-only]" if dataset.workstation_only else ""
        rel = dataset.local_path.relative_to(REPO_ROOT)
        print(f"  {mark:8}  {dataset.key:12}  {rel}{flag}")
    print()
    if missing:
        print(
            f"{missing} dataset(s) missing. Run with --instructions for how to "
            "obtain them. Do NOT assume a dataset exists locally just because a "
            "previous session on the other machine downloaded it."
        )
    else:
        print("All datasets present.")
    return 0


def cmd_instructions(keys: list[str] | None) -> int:
    selected = [BY_KEY[k] for k in keys] if keys else list(DATASETS)
    for dataset in selected:
        print("=" * 72)
        print(f"{dataset.name}  [{dataset.key}]")
        print("=" * 72)
        print(f"  purpose     : {dataset.purpose}")
        print(f"  lives at    : {dataset.local_path.relative_to(REPO_ROOT)}")
        print(f"  source      : {dataset.source_url}")
        print(f"  credentials : {dataset.credentials or 'none required'}")
        if dataset.workstation_only:
            print("  NOTE        : workstation only — too large for the MacBook Air")
        print(f"\n  {dataset.how}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init", action="store_true", help="create directory layout")
    parser.add_argument("--status", action="store_true", help="show what is present")
    parser.add_argument(
        "--instructions", action="store_true", help="how to obtain datasets"
    )
    parser.add_argument(
        "--dataset",
        action="append",
        choices=sorted(BY_KEY),
        help="limit --instructions to specific dataset(s)",
    )
    args = parser.parse_args()

    if not (args.init or args.status or args.instructions):
        parser.print_help()
        return 1

    rc = 0
    if args.init:
        rc |= cmd_init()
    if args.status:
        rc |= cmd_status()
    if args.instructions:
        rc |= cmd_instructions(args.dataset)
    return rc


if __name__ == "__main__":
    sys.exit(main())
