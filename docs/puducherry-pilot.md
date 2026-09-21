# Puducherry coastal pilot and coverage atlas

Completed on the workstation, September 16–17, 2026. Branch:
`codex/coverage-indian-ocean`, stacked on the UI PR #15.

## Measured output

Artifact: `webapp_data/puducherry_coast.run.json`.

| Property | Recorded result |
|---|---|
| Requested AOI | 79.78–79.98° E, 11.80–12.02° N |
| Historical window | January 21–February 1, 2021 |
| Ingested acquisitions | S2-44PLU-20210125, S2-44PLU-20210130 |
| Detector | Existing CNN, `models/detector_v1.pt` |
| Model detections | 117 |
| Passed verification | 6 |
| Rejected | 111 |
| Forward/backward trajectories | 6 each |
| Attributions | 6 |
| Protected areas in regional extract | 1 |
| Vessel correlations | Unavailable, not zero observed vessels |

These are pipeline outputs, **not confirmed ghost nets or an accuracy score**.
There is no independent local ground truth. Detector training exposure is not
established by the checkpoint sidecar; the export preserves that caveat. This
is a small coastal pilot, not a survey of the Indian Ocean.

## Inputs and reproducibility

The region was chosen before detector execution. A STAC metadata survey found
January 5–20 scenes 71–100% cloudy; January 25 and 30 had 17% and 32% scene cloud.
The configured 40% scene filter admits these two scenes. Existing per-AOI cloud
and water screening and all detector/verification thresholds were unchanged.

OSCAR January files were reused. The field is a time mean; 12-hour RK4 steps
change numerical integration, not just display sampling. The Meijer global
table produced 71 river mouths within the existing 250 km buffer. Protected
Planet's September 2026 marine geodatabase yielded Thillai Vanam within 100 km;
its circle fit is 0.30, so ecological distances are approximate. These modern
reference datasets are context for historical imagery, not a claim of historical
river emissions or protected-area status validation.

GFW requests used the required 100 km spatial and seven-day temporal buffers.
Both seven-day chunks and a single full-window request failed report parsing.
The captured response was a named SAR dataset with a null payload. The adapter
correctly refused to create a cache. No parser relaxation, invented observations,
or zero-vessel assumption was introduced. The export explicitly degrades FR-5;
the live plan drops the missing component and redistributes weights. Restoring
GFW requires resolving the provider response, then refreshing this run.

Reproduction (Python 3.11, local checkpoint and source datasets required):

```text
py -3.11 scripts/build_region_extracts.py rivers --region puducherry_coast --source data/rivers/meijer2021_global.csv
py -3.11 scripts/build_region_extracts.py mpa --region puducherry_coast --source <marine.gdb> --layer WDPA_WDOECM_poly_Sep2026_marine
py -3.11 scripts/fetch_gfw.py --region puducherry_coast --chunk-days 31
py -3.11 scripts/export_run.py --region puducherry_coast --detector cnn --step-hours 12 --allow-degraded
```

The served artifact adds explicit pilot, cloud-selection and failed-GFW notes
after export. Its original pipeline-code commit and generation time are
preserved; a note records that the new region config was added on this branch.
Acquisition logs and failed responses stay in ignored `data/local-surveys/`.
No existing downloads or exports were restarted or overwritten.

- Checkpoint SHA-256: `2decbcc61263e8ac53a3aefea6acc083ffac8ad6d2852e4508f676b27ea5f2a9`
- Served artifact SHA-256: `67abfe7aca2820349b7933ea917f7752a373ee05148a7e2bf5ae82ee48631d11`

## Coverage experience

Coverage opens an atlas of all readable real runs, with clickable regions,
historical windows and detection-record counts. Synthetic demos remain separate.
Puducherry is marked as partial. Each regional map shows its requested AOI and
date window, with an explicit explanation that areas outside the run have not
been analysed. Masks leave observation gaps even inside the requested rectangle.
Older artifacts without AOI metadata show a labelled study-region fallback;
detection extents are never used to invent observed coverage.

Coastal framing remains the default. At broad zoom, Return to coastal detail
restores useful context. Mobile overview labels separate with leader lines and
the region list remains available. Existing APIs, schemas, scoring and human
approval requirements are unchanged.

## Validation

- Artifact schema, unique IDs, AOI bounds and evidence checked; all six verified
  IDs have forward/backward trajectories and attributions.
- Live planning returns three assignments with vessel evidence unavailable;
  no human approval was submitted.
- Ten frontend tests cover clustering and coverage metadata, including invalid
  bounds, synthetic runs, missing AOI, zero detections and partial inputs.
- Full Python suite: 408 passed. Provenance reconciliation passed.
- TypeScript and Vite production build passed.
- Browser: 1440×900 and 390×844; regional/world switching, map and list links,
  dates, boundaries, all 117 records represented, partial-input disclosure,
  broad-zoom return, light/dark themes and no horizontal overflow checked.
- Existing Vite bundle-size, NumPy binary-size and Starlette/httpx warnings remain.
