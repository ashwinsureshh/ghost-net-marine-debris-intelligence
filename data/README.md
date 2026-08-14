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

## Two rules

1. **Never assume a dataset is here** because a previous session downloaded it —
   that session may have been on the other machine. Check first; if it's absent,
   say so rather than proceeding as though it exists.
2. **The two workstation-only datasets must not be synced to the MacBook Air.**
   Use a small cached sample there instead.

Small trimmed fixtures for tests belong in `tests/fixtures/`, not here.
