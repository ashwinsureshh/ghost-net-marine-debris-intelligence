# Data

**Nothing in this directory is committed to git** except this README and the
`.gitkeep` placeholders that record the expected layout. Datasets are fetched on
demand.

```bash
python scripts/fetch_data.py --status        # what's here vs missing
python scripts/fetch_data.py --instructions  # how to obtain each one
python scripts/fetch_data.py --init          # recreate the layout
```

## Expected layout

| Path | Dataset | Used by |
|---|---|---|
| `raw/sentinel2/` | Copernicus Sentinel-2 L2A tiles **(workstation only)** | FR-1, FR-2.2 |
| `marida/` | MARIDA labelled benchmark **(workstation only, multi-GB)** | FR-1.4, FR-2.4 |
| `oscar/` | NOAA OSCAR surface current fields | FR-3 |
| `drifters/` | NOAA Global Drifter Program buoy tracks | Drift Agent validation |
| `rivers/` | The Ocean Cleanup river emission rankings | FR-4 |
| `gfw/` | Global Fishing Watch SAR detections + AIS | FR-5 |
| `protected_planet/` | UNEP-WCMC MPA boundaries | FR-6.1 |

## MARIDA — downloaded and validated on the workstation (2026-08-14)

Zenodo DOI [10.5281/zenodo.5151941](https://doi.org/10.5281/zenodo.5151941),
CC-BY-4.0, v1.0.0. `MARIDA.zip` is 1.08 GB (md5
`9bf32266f6e3711c9dfa3699b856c76f`), ~5.5 GB extracted. **Workstation only.**

```
marida/
  patches/S2_<D-M-YY>_<MGRStile>/      63 scene folders
      S2_<D-M-YY>_<tile>_<n>.tif       11-band image, 256x256, float32
      S2_<D-M-YY>_<tile>_<n>_cl.tif    class mask, 256x256
      S2_<D-M-YY>_<tile>_<n>_conf.tif  annotation confidence
  splits/{train,val,test}_X.txt        694 / 328 / 359 = 1381 patches
  labels_mapping.txt                   per-patch multi-label vectors (JSON)
```

Split IDs omit the `S2_` prefix: id `1-12-19_48MYU_0` maps to
`patches/S2_1-12-19_48MYU/S2_1-12-19_48MYU_0.tif`. Verified no patch overlap
between train/val/test.

Bands are ACOLITE-corrected surface reflectance (~0.01–0.30), CRS is per-scene
UTM (e.g. EPSG:32748), `nodata` is unset.

### Two traps to avoid when training (FR-1.4)

1. **MARIDA is sparsely annotated — class 0 means *unlabelled*, not
   *background*.** It is 99.6% of all pixels, because only drawn polygons carry
   labels. Training with class 0 as a real class teaches the model to predict
   "nothing" almost everywhere. Mask class 0 out of the loss.
2. **Masks load as `float32`, not an integer type.** Cast before using them as
   class indices or the loss will fail or silently misbehave.

Marine Debris (class 1) is ~0.002% of sampled pixels even before masking, so a
plain unweighted cross-entropy will collapse to the majority class. Expect to
need class weighting or focal loss, and to report precision/recall — never
accuracy — in `eval/results.md`.

Class ids: 1 Marine Debris, 2 Dense Sargassum, 3 Sparse Sargassum, 4 Natural
Organic Material, 5 Ship, 6 Clouds, 7 Marine Water, 8 Sediment-Laden Water,
9 Foam, 10 Turbid Water, 11 Shallow Water, 12 Waves, 13 Cloud Shadows,
14 Wakes, 15 Mixed Water.

Note how directly classes 2/3/5/6/9/12/13/14 map onto the false-positive modes
the Verification Agent must rule out (FR-2.1) — MARIDA can evaluate that agent,
not just the detector.

## Two rules

1. **Never assume a dataset is here** because a previous session downloaded it —
   that session may have been on the other machine. Check first; if it's absent,
   say so rather than proceeding as though it exists.
2. **The two workstation-only datasets must not be synced to the MacBook Air.**
   Use a small cached sample there instead.

Small trimmed fixtures for tests belong in `tests/fixtures/`, not here.
