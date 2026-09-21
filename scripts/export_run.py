"""Export a pipeline run as a deployable artefact (PRD §9.1).

**This is the workstation's half of the web-app contract.** The deployed app
cannot carry the datasets, so the workstation runs detection/verification/drift
over real imagery here and writes one JSON artefact per region/window; the
server then serves it and recomputes only prioritisation live.

    # On the workstation, once real tiles exist:
    python scripts/export_run.py --region <region-id> --out webapp_data/

    # Anywhere, no data needed — regenerates the synthetic demo artefact:
    python scripts/export_run.py --synthetic --out webapp_data/

The synthetic path exists so the app is developable and demonstrable with no
datasets present (the normal state of the MacBook Air) and so the viva has a
fallback that cannot break. Artefacts written from it are flagged
``inputs_are_synthetic: true`` and the UI states that on its face — a run that
came from generated arrays must never be mistaken for a measured result.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402

from ghostnet.agents.attribution import River, RiverTable  # noqa: E402
from ghostnet.agents.detection import (  # noqa: E402
    DEFAULT_FDI_THRESHOLD,
    DEFAULT_MIN_PIXELS,
    GeoTransform,
    Tile,
)
from ghostnet.agents.drift import UniformCurrentField  # noqa: E402
from ghostnet.agents.prioritisation import ProtectedArea  # noqa: E402
from ghostnet.agents.verification import DEFAULT_THRESHOLDS  # noqa: E402
from ghostnet.config import DataUnavailableError, get_region  # noqa: E402
from ghostnet.export import RunRegion, export_run, write_artefact  # noqa: E402
from ghostnet.pipeline import PipelineConfig, run_pipeline  # noqa: E402
from ghostnet.schemas import VesselDetection  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "webapp_data"

# --- synthetic demo scene -------------------------------------------------
# A stretch of coastal water off a high-emission river mouth, with one genuine
# debris raft and the false-positive modes the Verification Agent must reject.
# Signatures match tests/conftest.py, which is fitted to the calibrated
# thresholds from the MARIDA work (eval/results.md).

ACQUIRED = datetime(2026, 3, 14, 5, 30, tzinfo=UTC)
# ~330 m pixels over a ~0.17° box: coarse for Sentinel-2, but it spreads the
# demo scene widely enough that individual sites stay legible on the map
# instead of collapsing into one cluster at the fitted zoom.
TRANSFORM = GeoTransform(lon_origin=80.02, lat_origin=12.16, lon_step=0.003, lat_step=-0.003)

SIGNATURES = {
    "water": {"B04": 0.030, "B06": 0.004, "B08": 0.002, "B11": 0.003},
    "debris": {"B04": 0.045, "B06": 0.020, "B08": 0.050, "B11": 0.010},
    "glint": {"B04": 0.105, "B06": 0.105, "B08": 0.105, "B11": 0.090},
    "foam": {"B04": 0.150, "B06": 0.100, "B08": 0.120, "B11": 0.030},
    "kelp": {"B04": 0.020, "B06": 0.050, "B08": 0.100, "B11": 0.050},
}

SYNTHETIC_PATCHES = {
    (6, 8): "debris",
    (9, 44): "debris",
    (30, 20): "debris",
    (8, 26): "glint",
    (26, 6): "foam",
    (24, 44): "kelp",
    (40, 30): "foam",
}


def synthetic_tile(tile_id: str, acquired_at: datetime, size: int = 56) -> Tile:
    bands = {k: np.full((size, size), v) for k, v in SIGNATURES["water"].items()}
    for (row, col), kind in SYNTHETIC_PATCHES.items():
        for band, value in SIGNATURES[kind].items():
            bands[band][row : row + 7, col : col + 7] = value
    return Tile(
        tile_id=tile_id,
        acquired_at=acquired_at,
        bands=bands,
        transform=TRANSFORM,
        source="synthetic (scripts/export_run.py)",
    )


def synthetic_config() -> tuple[PipelineConfig, RunRegion, list[ProtectedArea]]:
    protected = [
        ProtectedArea(
            name="Palk Bay Marine Reserve",
            lon=79.86,
            lat=12.14,
            radius_km=9.0,
            designation="Marine National Park (illustrative)",
        )
    ]
    region = RunRegion(
        id="synthetic-coastal-demo",
        name="Synthetic coastal demo scene",
        bbox=(79.80, 12.00, 80.20, 12.20),
        window_start=ACQUIRED,
        window_end=ACQUIRED + timedelta(days=5),
    )
    config = PipelineConfig(
        region_id=region.id,
        tiles=[synthetic_tile("SYNTHETIC-T44PLT-20260314", ACQUIRED)],
        current_field=UniformCurrentField(u_ms=-0.22, v_ms=0.06, name="synthetic-westward"),
        river_table=RiverTable(
            rivers=[
                River("Demo Kali", 79.78, 12.16, 4200, "Synthetic"),
                River("Demo Creek", 79.83, 12.05, 90, "Synthetic"),
                River("Far Delta", 88.00, 21.00, 120000, "Synthetic"),
            ],
            source="synthetic",
        ),
        vessel_detections=[
            VesselDetection(
                id="SYN-SAR-1",
                lon=79.97,
                lat=12.12,
                detected_at=ACQUIRED - timedelta(days=2),
                length_m=26.0,
            ),
            VesselDetection(
                id="SYN-SAR-2",
                lon=79.92,
                lat=12.07,
                detected_at=ACQUIRED - timedelta(days=1),
                length_m=41.0,
            ),
        ],
        protected_areas=protected,
        ensemble_size=48,
    )
    return config, region, protected


def real_config(
    region_id: str,
    *,
    allow_degraded: bool = False,
    detector: str = "fdi",
    step_hours: float | None = None,
) -> tuple[PipelineConfig, RunRegion, list[ProtectedArea], list[str]]:
    """Assemble a run from real local datasets.

    Every loader raises with the ``scripts/fetch_data.py`` command to run when
    its dataset is not on this machine (MACHINE-WORKFLOW.md rule 4), so by
    default a missing input fails here with a clear message rather than
    exporting a hollow artefact.

    ``allow_degraded`` relaxes that for the optional inputs only, and exists
    because this function was stricter than the pipeline it feeds.
    :class:`PipelineConfig` takes ``current_field``, ``river_table``,
    ``vessel_detections`` and ``protected_areas`` as ``None``/empty and its
    graph degrades explicitly around each — that is the documented convention
    (MACHINE-WORKFLOW.md: *a missing dataset degrades the run, it never
    crashes*). Requiring all five here meant one absent dataset blocked a run
    the pipeline was built to survive, which is why every artefact so far has
    been synthetic.

    **Tiles are still mandatory.** Without imagery there are no detections and
    the run is not a run; that is a crash, not a degradation.

    Returns the degraded dataset keys alongside the config so the caller can
    stamp them into provenance. A partial run has to say which agents were
    starved, or it reads as a full one.
    """
    from ghostnet.agents.attribution import load_river_table
    from ghostnet.agents.detection import load_tiles
    from ghostnet.agents.drift import load_oscar_field
    from ghostnet.agents.prioritisation import load_protected_areas
    from ghostnet.agents.vessels import load_cached_detections

    entry = get_region(region_id)
    start = entry["time_window"]["start"]
    end = entry["time_window"]["end"]
    region = RunRegion(
        id=region_id,
        name=entry.get("name", region_id),
        bbox=tuple(entry["bbox"]),
        window_start=datetime.fromisoformat(str(start)),
        window_end=datetime.fromisoformat(str(end)),
    )

    # Imagery is not optional: no tiles, no detections, no run.
    #
    # The CNN needs all 11 MARIDA bands; the FDI path loads four. Fetching the
    # wrong set does not fail at load time, it fails inside detect() once the
    # tiles are already streamed, so the band set is chosen HERE from the
    # detector rather than defaulted.
    if detector == "cnn":
        from ghostnet.agents.detection_cnn import MARIDA_BANDS

        tiles = load_tiles(region_id, bands=MARIDA_BANDS)
    else:
        tiles = load_tiles(region_id)

    degraded: list[str] = []

    def optional(key: str, load, fallback):
        """Resolve one optional input, or record that it is missing."""
        try:
            return load()
        except DataUnavailableError as exc:
            if not allow_degraded:
                raise
            degraded.append(key)
            print(f"  DEGRADED  {key}: {str(exc).splitlines()[0]}", file=sys.stderr)
            return fallback

    # Both extracts are region-scoped by name. Passing the id is what stops a
    # second region's extract being loaded silently once one exists.
    protected = optional("mpa", lambda: load_protected_areas(region_id=region_id), [])
    config = PipelineConfig(
        region_id=region_id,
        tiles=tiles,
        detector=detector,
        **({"step_hours": step_hours} if step_hours is not None else {}),
        current_field=optional(
            "oscar",
            lambda: load_oscar_field(
                region.window_start, region.window_end, bbox=region.bbox
            ),
            None,
        ),
        river_table=optional("rivers", lambda: load_river_table(region_id), None),
        vessel_detections=optional(
            "gfw", lambda: load_cached_detections(region_id=region_id,
                bbox=region.bbox,
                start=region.window_start - timedelta(days=7),
                end=region.window_end + timedelta(days=7)), []),
        protected_areas=protected,
    )
    return config, region, protected, degraded


def git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None


def machine_role() -> str:
    try:
        from check_machine import get_profile  # type: ignore
    except ImportError:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from check_machine import get_profile  # type: ignore
    return get_profile().role


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", help="region id from config/regions.yaml")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="export the generated demo scene instead of real data",
    )
    parser.add_argument(
        "--detector",
        choices=["fdi", "cnn"],
        default="fdi",
        help=(
            "FR-1 detector. 'cnn' needs models/detector_v1.pt and loads all 11 "
            "MARIDA bands; it emits ~7.6x fewer candidates at higher region "
            "recall (0.407 -> 0.703), which is both the better result and what "
            "keeps the artefact small enough to commit."
        ),
    )
    parser.add_argument(
        "--step-hours",
        type=float,
        default=None,
        help=(
            "Drift integration step, in hours. Raising it stores fewer points "
            "per track and is the documented first thing to cut when an "
            "artefact is too large (trajectories were 63%% of the first real "
            "CNN run). Fidelity only: the ensemble and its envelope are "
            "computed identically either way."
        ),
    )
    parser.add_argument(
        "--allow-degraded",
        action="store_true",
        help=(
            "Export even when an OPTIONAL dataset is missing, instead of "
            "refusing. The pipeline degrades explicitly around an absent "
            "current field, river table, vessel record or MPA extract; this "
            "lets a real run happen on what is actually here. Imagery is still "
            "mandatory. Every degraded agent is named in the artefact's "
            "provenance notes, so a partial run cannot read as a full one."
        ),
    )
    parser.add_argument("--run-id", help="artefact id (default: derived from the region)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    args = parser.parse_args()

    if not args.synthetic and not args.region:
        parser.error("pass --region <id>, or --synthetic for the generated demo scene")

    if args.synthetic:
        config, region, protected = synthetic_config()
        degraded: list[str] = []
        sources = {"all": "generated in scripts/export_run.py — no real data"}
        notes = [
            "Inputs are generated arrays, not satellite imagery. Every number in "
            "this run demonstrates that the pipeline is wired correctly; none of "
            "it is a measured result. Measured results live in eval/results.md.",
        ]
    else:
        try:
            config, region, protected, degraded = real_config(
                args.region,
                allow_degraded=args.allow_degraded,
                detector=args.detector,
                step_hours=args.step_hours,
            )
        except (DataUnavailableError, NotImplementedError) as exc:
            print(f"Cannot export region {args.region!r}:\n\n{exc}\n", file=sys.stderr)
            print(
                "This machine does not have what the run needs. Export on the "
                "workstation, pass --allow-degraded to run on what IS here "
                "(imagery is still required), or use --synthetic to regenerate "
                "the demo artefact.",
                file=sys.stderr,
            )
            return 2
        sources = {"note": "real datasets resolved from data/ on this machine"}
        notes = []
        if any(v.source for v in config.vessel_detections):
            notes.append(
                "GFW SAR inputs are hourly 0.01-degree grid observations with provider "
                "AIS matching, not exact SAR locations or independently matched raw AIS "
                "tracks. An observation can contain multiple detections; correlation "
                "strength operates on grid observations. Unmatched is an investigation "
                "signal, not evidence of illegal activity or proof of debris origin."
            )
        if degraded:
            # On the artefact's face. A run missing its river table is not a
            # run that found no sources, and the difference has to survive
            # into the console.
            agents = {
                "oscar": "Drift (FR-3) — no current field; trajectories unavailable",
                "rivers": "Source attribution (FR-4) — no river table; sources unattributed",
                "gfw": "Dark-vessel correlation (FR-5) — no SAR/AIS records; no correlation",
                "mpa": "Ecological risk (FR-6.1) — no protected-area extract; that "
                "component is dropped and its weight redistributed",
            }
            notes.append(
                "PARTIAL RUN. Real imagery, detection and verification, but "
                + str(len(degraded))
                + " input(s) were absent on the exporting machine, so the agents "
                "below ran degraded rather than on real data. This is not a "
                "full six-agent result: "
                + "; ".join(agents.get(k, k) for k in degraded)
                + "."
            )
            notes.append(
                "Obtain the missing datasets with `python scripts/fetch_data.py "
                "--instructions`, then re-export without --allow-degraded."
            )

    run = run_pipeline(config)
    run_id = args.run_id or region.id

    artefact = export_run(
        run,
        run_id=run_id,
        region=region,
        generated_on=machine_role(),
        inputs_are_synthetic=args.synthetic,
        dataset_sources=sources,
        protected_areas=protected,
        thresholds=DEFAULT_THRESHOLDS,
        fdi_threshold=DEFAULT_FDI_THRESHOLD,
        min_pixels=DEFAULT_MIN_PIXELS,
        git_commit=git_commit(),
        notes=notes,
    )

    path = write_artefact(artefact, args.out)
    size_kb = path.stat().st_size / 1024
    summary = artefact.summary()

    try:
        shown = path.resolve().relative_to(REPO_ROOT)
    except ValueError:  # --out pointed somewhere outside the repo
        shown = path.resolve()
    print(f"Wrote {shown}  ({size_kb:.0f} KB)")
    print(f"  region      : {summary['region_name']}")
    print(f"  synthetic   : {summary['inputs_are_synthetic']}")
    print(f"  detections  : {summary['detections']}")
    print(f"  verified    : {summary['verified']}")
    print(f"  rejected    : {summary['rejected']}  (shown in the app, with reasons)")
    print(f"  trajectories: {summary['trajectories']}")
    for note in artefact.degradations:
        print(f"  ! {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
