"""Export a true-colour Sentinel-2 image chip for every detection in the served runs.

The console's evidence panel shows each candidate in the satellite scene it was
detected in. The live server cannot stream imagery (free tier, no Planetary
Computer access at request time), so the chips are cut here on the workstation,
from the SAME scene each detection's evidence names, and written beside the run
artefacts:

    webapp_data/chips/<run_id>/<detection_id>.jpg
    webapp_data/chips/<run_id>/manifest.json

Each chip is CHIP_PX x CHIP_PX pixels at 10 m (Sentinel-2 B04/B03/B02), centred
on the detection, with ONE fixed brightness stretch for every chip so they are
comparable (no per-chip enhancement that could make a patch look more or less
like debris than its neighbours). Synthetic runs are skipped: they have no real
scene.

    python scripts/export_chips.py                 # all served runs
    python scripts/export_chips.py --run gulf_of_honduras

Contains modified Copernicus Sentinel data; the console shows that credit.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghostnet.export import discover_artefacts, load_artefact  # noqa: E402

CHIP_PX = 160                 # 1.6 km across at 10 m
RESOLUTION_M = 10.0
BANDS = ("B04", "B03", "B02")  # true colour: red, green, blue
STRETCH_MAX = 0.20             # reflectance mapped to full brightness
GAMMA = 1.6                    # lifts dark water so surface texture is visible
JPEG_QUALITY = 92
SCENE_RE = re.compile(r"sentinel-2-l2a/(\S+?)\)")


def scene_id(detection) -> str | None:
    """The Sentinel-2 item the detection came from, as recorded in its evidence."""
    for ev in detection.evidence:
        m = SCENE_RE.search(ev.detail or "")
        if m:
            return m.group(1)
    return None


def chip_bbox(lon: float, lat: float, px: int = CHIP_PX, res_m: float = RESOLUTION_M):
    """Lon/lat box of px x px pixels at res_m, centred on (lon, lat)."""
    half_m = px * res_m / 2.0
    dlat = half_m / 111_320.0
    dlon = half_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def to_rgb8(reflectance: np.ndarray) -> np.ndarray:
    """Fixed stretch shared by every chip: reflectance -> 8-bit RGB."""
    x = np.clip(reflectance / STRETCH_MAX, 0.0, 1.0) ** (1.0 / GAMMA)
    return np.round(x * 255).astype(np.uint8)


def centre_crop(img: np.ndarray, px: int = CHIP_PX) -> np.ndarray:
    """Crop (or edge-pad) to exactly px x px around the centre."""
    h, w = img.shape[:2]
    if h < px or w < px:
        pad_h, pad_w = max(0, px - h), max(0, px - w)
        widths = ((pad_h // 2, pad_h - pad_h // 2), (pad_w // 2, pad_w - pad_w // 2), (0, 0))
        img = np.pad(img, widths, mode="edge")
        h, w = img.shape[:2]
    top, left = (h - px) // 2, (w - px) // 2
    return img[top:top + px, left:left + px]


def git_commit() -> str:
    try:
        cmd = ["git", "rev-parse", "--short", "HEAD"]
        done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True)
        return done.stdout.strip()
    except Exception:  # pragma: no cover - outside a checkout
        return "unknown"


def export_run(path: Path, out_root: Path, collection) -> dict:
    from PIL import Image

    from ghostnet.ingest import _read_asset, _reflectance_scaling, build_grid

    artefact = load_artefact(path)
    run_id = path.name.split(".run.json")[0]
    if artefact.provenance.inputs_are_synthetic:
        print(f"{run_id}: synthetic, skipped")
        return {}
    out = out_root / run_id
    out.mkdir(parents=True, exist_ok=True)

    by_scene: dict[str, list] = defaultdict(list)
    missing = []
    for d in artefact.detections:
        sid = scene_id(d)
        (by_scene[sid].append(d) if sid else missing.append(d.id))

    chips = {}
    for k, (sid, dets) in enumerate(sorted(by_scene.items()), 1):
        item = collection.get_item(sid)
        scale, offset = _reflectance_scaling(item)
        for d in dets:
            grid = build_grid(chip_bbox(d.lon, d.lat), resolution_m=RESOLUTION_M)
            bands = [(_read_asset(item, b, grid).astype("float32") * scale + offset) for b in BANDS]
            rgb = centre_crop(to_rgb8(np.dstack(bands)))
            Image.fromarray(rgb).save(out / f"{d.id}.jpg", quality=JPEG_QUALITY)
            chips[d.id] = {"scene": sid, "acquired_at": d.acquired_at.isoformat()}
        print(f"{run_id}: scene {k}/{len(by_scene)} ({len(dets)} chips)", flush=True)

    manifest = {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "code": git_commit(),
        "chip_px": CHIP_PX,
        "resolution_m": RESOLUTION_M,
        "bands": list(BANDS),
        "stretch": {"reflectance_max": STRETCH_MAX, "gamma": GAMMA, "shared_by_all_chips": True},
        "credit": "Contains modified Copernicus Sentinel data",
        "chips": chips,
        "missing_scene": missing,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"{run_id}: {len(chips)} chips, {len(missing)} without a scene reference")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data-dir", type=Path, default=ROOT / "webapp_data")
    ap.add_argument("--run", action="append", help="run id(s); default: every served run")
    args = ap.parse_args()

    import planetary_computer
    import pystac_client

    collection = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    ).get_collection("sentinel-2-l2a")
    for path in discover_artefacts(args.data_dir):
        run_id = path.name.split(".run.json")[0]
        if args.run and run_id not in args.run:
            continue
        export_run(path, args.data_dir / "chips", collection)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
