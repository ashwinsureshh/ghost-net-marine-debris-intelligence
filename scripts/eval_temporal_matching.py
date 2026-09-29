"""Experimental drift-aware repeat association on the four existing MARIDA pairs."""

import argparse
import datetime as dt
import hashlib
import json
import math
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import eval_multitemporal as baseline  # noqa: E402
from ghostnet.agents import drift, verification  # noqa: E402
from ghostnet.agents.detection import GeoTransform, Tile, detect, sample_window  # noqa: E402
from ghostnet.evidence_hash import TEXT_HASH_METHOD, text_evidence_sha256  # noqa: E402
from ghostnet.temporal_matching import TemporalCandidate, associate  # noqa: E402

REFERENCES = ("multitemporal_oscar.json", "multitemporal_oscar_18QYF_2020-03.json",
              "multitemporal_oscar_18QYF_2020-11.json", "multitemporal_oscar_16PCC_2018-09.json")


def cached_tile(pair, date, grid, cache):
    identity = json.dumps({"pair": pair, "date": date.isoformat(), "resolution": 20},
                          sort_keys=True)
    path = cache / (hashlib.sha256(identity.encode()).hexdigest() + ".npz")
    if not path.exists():
        tile = baseline.tile_for_date(pair["bbox"], pair["tile"], date, grid)
        metadata = {k: v for k, v in vars(tile).items() if k not in ("bands", "cloud_mask")}
        metadata["transform"] = asdict(tile.transform)
        metadata["acquired_at"] = tile.acquired_at.isoformat()
        np.savez_compressed(path, metadata=json.dumps(metadata),
                            cloud=tile.cloud_mask, **tile.bands)
    with np.load(path, allow_pickle=False) as stored:
        metadata = json.loads(str(stored["metadata"]))
        metadata["transform"] = GeoTransform(**metadata["transform"])
        metadata["acquired_at"] = dt.datetime.fromisoformat(metadata["acquired_at"])
        tile = Tile(**metadata, cloud_mask=stored["cloud"],
                    bands={k: stored[k] for k in stored.files if k.startswith("B")})
    return tile, hashlib.sha256(path.read_bytes()).hexdigest()


def features(det, tile):
    col, row = tile.transform.to_pixel(det.lon, det.lat)
    height, width = tile.shape
    spectrum = tuple(float(np.mean(tile.bands[b][max(0, row-2):min(height, row+3),
                                                max(0, col-2):min(width, col+3)]))
                     for b in ("B04", "B06", "B08", "B11"))
    return TemporalCandidate(det.id, det.lon, det.lat, det.area_km2, spectrum)


def fully_observed(tile, lon, lat, radius):
    """Conservative: the entire enclosing square must be in clear valid water."""
    dlat = radius / 110.574
    dlon = radius / (111.32 * max(math.cos(math.radians(lat)), 1e-6))
    col0, row0 = tile.transform.to_pixel(lon-dlon, lat+dlat)
    col1, row1 = tile.transform.to_pixel(lon+dlon, lat-dlat)
    col0, row0, col1, row1 = col0-1, row0-1, col1+1, row1+1
    height, width = tile.shape
    if col0 < 0 or row0 < 0 or col1 >= width or row1 >= height:
        return False
    if col1 < col0 or row1 < row0 or tile.cloud_mask is None:
        return False
    region = np.s_[row0:row1+1, col0:col1+1]
    return bool(not tile.cloud_mask[region].any() and all(
        np.isfinite(band[region]).all() and (band[region] > 0).all()
        for band in tile.bands.values()))


def evaluate(reference, cache):
    pair = reference["pair"]
    grid = baseline.build_grid(tuple(pair["bbox"]), resolution_m=20)
    a, hash_a = cached_tile(pair, dt.date.fromisoformat(pair["date_a"]), grid, cache)
    b, hash_b = cached_tile(pair, dt.date.fromisoformat(pair["date_b"]), grid, cache)
    earlier, later = detect(a), detect(b)
    print(f"  candidates: {len(earlier)} / {len(later)}", flush=True)
    labels = baseline.marida_label_raster(pair["tile"], a.acquired_at.date(), grid)
    print("  labels rasterised; loading current field", flush=True)
    field = drift.load_oscar_field(dt.datetime.fromisoformat(pair["date_a"]),
                                  dt.datetime.fromisoformat(pair["date_b"]),
                                  bbox=tuple(pair["bbox"]))
    speed = baseline.oscar_speed_for(pair, verbose=False)["mean_ms"]
    target_features = [features(det, b) for det in later]
    rows = []
    for index, det in enumerate(earlier):
        if index % 25 == 0:
            print(f"  matching {index}/{len(earlier)}", flush=True)
        col, row = a.transform.to_pixel(det.lon, det.lat)
        truth = baseline.truth_for(labels[max(0, row-2):row+3, max(0, col-2):col+3])
        window = sample_window(a, det)
        spectral = verification.verify(det, window).verified
        repeats, _ = baseline.build_repeats(det, later, b, search_km=reference["search_km"])
        original = verification.verify(det, window, repeats=repeats,
                                       current_speed_ms=speed).verified
        hours = (b.acquired_at - det.acquired_at).total_seconds() / 3600
        steps = max(1, math.ceil(hours / 12))
        trajectory = drift.run_trajectory(det, field, direction="forward", horizon_days=hours/24,
                                          step_hours=hours/steps)
        end = trajectory.points[-1]
        observed = fully_observed(b, end.lon, end.lat, 5 + end.uncertainty_km)
        match = associate(features(det, a), target_features, predicted_lon=end.lon,
                          predicted_lat=end.lat, uncertainty_km=end.uncertainty_km,
                          fully_observed=observed)
        rows.append({"id": det.id, "truth": truth, "spectral": spectral,
                     "baseline": original,
                     "experimental": spectral and match["status"] != "not_reobserved",
                     "match": match})
    labelled = [r for r in rows if r["truth"] is not None]
    metrics = {arm: baseline._pr(labelled, arm) for arm in ("spectral", "baseline", "experimental")}
    return {"pair": pair, "tile_hashes": [hash_a, hash_b], "current_field": field.name,
            "current_speed_ms": speed, "candidates_a": len(earlier), "candidates_b": len(later),
            "labelled": len(labelled), "metrics": metrics,
            "statuses": dict(Counter(r["match"]["status"] for r in rows)),
            "historical_baseline_metrics": reference["with_multi_temporal"],
            "baseline_reproduced": metrics["baseline"] == reference["with_multi_temporal"],
            "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    cache = ROOT / "data/temporal_matching_cache"
    cache.mkdir(parents=True, exist_ok=True)
    pairs = []
    for filename in REFERENCES:
        path = ROOT / "eval" / filename
        print(f"Evaluating {filename}", flush=True)
        result = evaluate(json.loads(path.read_text("utf-8")), cache)
        result["reference"] = filename
        result["reference_sha256"] = text_evidence_sha256(path)
        pairs.append(result)
        print(result["metrics"], result["statuses"], flush=True)
    output = {"protocol": "experimental-drift-feature-matching-v1",
              "hash_method": TEXT_HASH_METHOD, "production_enabled": False, "pairs": pairs,
              "caveats": [
                  "Exploratory equal-weight feature costs; not calibrated on independent labels.",
                  "MARIDA class labels evaluate verification, not repeat identity ground truth.",
                  "Many-to-one matching retained like baseline; not object tracking accuracy.",
                  "Mean OSCAR and existing ensemble settings retained; no new drift calibration.",
                  "Incomplete clear-water search coverage is inconclusive, never absence evidence.",
                  "Old measured baselines preserved; no promotion without independent validation.",
              ]}
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(output, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
