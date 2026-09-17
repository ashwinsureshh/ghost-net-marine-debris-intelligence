# GhostNet — project status

Updated 2026-09-09 on the MacBook Air from committed evidence at `1c9ff5c`.
This snapshot does not include unpushed workstation work. No results were
re-measured for this update.

## Release update — 2026-09-17

The sections below retain the **main-branch evidence snapshot** from September 9.
The workstation has since pushed a reviewed, unmerged stack:
**#14 → #13 → #15 → #16**, ending at `e58118e`.

- GFW acquisition and scoped caches are implemented in #14. Honduras and
  Gonave have GFW-backed exports in #13; SAR grid observations are not individual
  vessels, and AIS-unmatched does not establish wrongdoing.
- #15 adds the marine atlas console. #16 adds coverage navigation and the
  Puducherry pilot. Counts are detection records, not confirmed ghost nets.
- Reviewed artifacts: Honduras 826 candidates / 443 verified; Gonave 247 / 65;
  Puducherry 117 / 6. Puducherry lacks GFW and local ground truth; it is explicitly
  partial, not an all-six-input Indian Ocean validation.
- Two fixes remain assigned to the workstation: normalize malformed GFW cache
  failures to `DataUnavailableError`, and avoid downloading every full artifact
  just to render coverage metadata. #13 and #15 had no blocking findings.
- The existing [live console](https://ghostnet-operator-console.onrender.com)
  was checked on September 17: health OK, two runs (older Honduras + synthetic).
  It does **not** yet contain the new PR stack. Deployment already exists;
  updating and verifying it after integration remains.
- An 8.8 MiB offline preview was built from the reviewed stack, containing
  three real runs and one synthetic demo. Rebuild after the workstation fixes.

See [release readiness and demo steps](release-readiness.md). No benchmarks
were re-measured and no acceptance criterion was promoted by this update.

## Acceptance criteria (PRD §12) — main-branch snapshot

The latest workstation log records **four complete, two partial**. Completion
of an evaluation means it was performed, not that the model is operationally
accurate or every agent improves the dispatch plan.

| Criterion | State | Evidence and remaining limit |
|---|---|---|
| Six-agent real-region run → ranked plan | Partial | Five agents use real inputs; GFW is missing. 826 candidates → 443 verified → three dispatch sites |
| Detection and verification benchmark | Complete | FDI precision 0.238 → 0.623, F1 0.385 → 0.753; detector region recall 0.407 |
| Drift compared with NOAA buoy paths | Complete, weak accuracy | 19 tracks from 2014, outside the demo window; poor long-horizon error and envelope coverage |
| Attribution and vessel external comparisons | Partial | Attribution distance check exists; published river-ranking comparison and GFW case-study evaluation remain |
| System ablation | Performed, with limits | Real-input results exist; attribution leaves dispatch unchanged and the vessel row is uninformative without GFW |
| Evidence traceability | Complete for available outputs | Provenance checks cover committed evidence; no real vessel evidence is available yet |

See [PRD §12](../PRD.md#12-evaluation--acceptance-criteria) and
[the measured results](../eval/results.md) for the acceptance wording and scope.

## Current implementation and data

The real Gulf of Honduras artefact includes 826 CNN detections, 443 verified
candidates, 383 rejections, 443 forward trajectories and source attributions,
221 candidate river mouths, and 82 protected areas. Only GFW degrades.

| Component | Current state |
|---|---|
| Sentinel-2 ingestion and detection | Real imagery streamed; FDI and CNN benchmarked |
| Verification | Spectral checks measured; multi-temporal check inert with currents |
| Drift | Real OSCAR inputs; buoy comparison recorded, uncertainty poorly calibrated |
| Attribution | Real river table; behaviour measured by distance, external ranking check pending |
| Dark-vessel correlation | Correlation logic exists; `GlobalFishingWatchClient.sar_detections()` is unimplemented |
| Prioritisation and console | Real protected areas, capacity plan, rationales and named-reviewer approval |

MARIDA, OSCAR, drifter tracks, rivers and protected-area data are recorded as
available on the workstation. GFW inputs remain missing. The handoff records
successful token authentication; credentials were not rechecked for this update.

The **workstation** owns GPU training, large datasets, real evaluations and
exports; its current handoff assigns GFW integration and the published
river-ranking comparison. The **MacBook Air** handles the console, API,
orchestration, tests, documentation and deployment preparation. Raw datasets and
checkpoints stay local: run `python scripts/fetch_data.py --status` before
assuming availability. Coordinate branches and PRs through
[MACHINE-WORKFLOW.md](../MACHINE-WORKFLOW.md).

## Results that need their caveats

- **Pair verification gain with detector recall.** FDI: +0.385 precision and
  0.407 region recall. CNN: +0.080 and **0.703 within-tile**. These benchmark
  figures do not measure the displayed run's accuracy; 91% of MARIDA test
  patches share tiles with training data.
- **FR-2.2 is inert.** Real currents remove the earlier six rejections and one
  true-debris loss; F1 gain remains zero and no transients are found. The
  matching strategy is the limitation, not a missing current field.
- **Drift is a model check outside the demo window.** Mean track error is
  10.46 km at ≤4.5 days and 48.74 km beyond it. Overall envelope coverage is
  24.5%; this does not validate the seven-day demo trajectories.
- **Attribution is not yet externally validated.** Motagua ranks first for
  58% of the 26 detections 15–30 km from its mouth. The 100% result within
  15 km has only two detections. Proximity behaviour does not establish the
  true source or satisfy the published-ranking comparison.
- **Ablation measures dependencies, not dispatch accuracy.** Removing
  attribution leaves dispatch unchanged. Removing vessels cannot demonstrate
  their value while GFW is already absent. Higher priority scores without
  verification do not establish a better plan or independently prove a
  candidate is a false positive.
- **Latency was 15.6 minutes, 90.6% network ingestion.** A cold run was not
  asserted. This is a performance measurement, not an accuracy metric.

## Remaining work

1. Workstation: implement and cache GFW SAR ingestion, evaluate against case
   studies, and complete the published river-ranking comparison.
2. Workstation: export with all six real inputs and repeat the vessel ablation.
3. Team: write and defend the report using [the outline](report-outline.md),
   [viva material](viva-pack.md), and committed evidence. These materials are
   scaffolding, not the finished report.
4. MacBook: verify the updated deployment after the reviewed stack is integrated.
   The existing live service is recorded above. Follow [DEPLOY.md](../DEPLOY.md).

Time-varying currents, uncertainty calibration and identity-preserving temporal
matching remain model improvements, not completed findings.

> No number reaches `eval/results.md` that the person who produced it cannot
> derive and defend.
