# GhostNet — guide progress update

23 September 2026 · Released baseline: main `4d7304b`; research additions pending review

**Current outcome:** A released geospatial decision-support prototype connects
six implemented agents to an evidence console and named human review. It is not
an operational monitoring service; candidates are not confirmed ghost nets.

## Implemented and released

- Satellite ingestion, FDI/CNN detection, verification, drift, river attribution,
  GFW vessel context and prioritised recommendations.
- Three historical real runs: Honduras **826** candidates, Gonave **247**,
  Puducherry **117**; plus a separate synthetic demo. Puducherry remains partial
  because GFW evidence is unavailable, not because there are zero vessels.
- Coverage atlas, evidence/rejection inspection, benchmarks and offline export.
  All five release PRs merged. September 21 live-console checks were reported
  complete by the release handoff; no deployment was repeated for this update.

## Measured, with boundaries

- FDI verification precision **0.238 to 0.623**, F1 **0.385 to 0.753**;
  FDI region recall is **0.407**.
- CNN region recall **0.703**, explicitly within-tile. Verification adds
  **+0.080** precision behind CNN. These are MARIDA results, not local accuracy.
- Strict geographic tests completed: two additional areas, three training seeds
  each. Mean F1 **0.626 / 0.741**; only **143 / 24** labelled debris pixels,
  so this is limited evidence of transfer, especially in the second area.
- Real-current FR-2.2 adds **no measured improvement**.
- Drift check: **19 tracks in 2014**, not the demo window; mean envelope
  inclusion only **24.52%**. Longer-horizon predictions remain weak.
- Full-input ablation now includes GFW and demonstrates its scoring contribution,
  not independently validated vessel or dispatch accuracy.
- Full-input latency **17.0 minutes**, including serialization; one workstation
  run without a cold-start guarantee, not a production SLA.
- Sensitivity: changing priority weights changes dispatch membership in **10/24**
  Honduras, **1/24** Gonave and **2/24** Puducherry variants.
- Interpolated six-day currents did **not** consistently improve drift. Internal
  uncertainty calibration needs very wide radii; neither change is deployed.

## Remaining

Independent local ground truth; published river-ranking comparison; external
vessel-correlation validation; broader geographic evidence and assessment of
drift uncertainty's practical usefulness. Team work: literature citations, report formatting,
final slides and manual opening of the September 21 offline demo file.

**Software checks:** 460 workstation Python tests; 12 frontend tests and build
pass. Research evidence registered in the provenance audit.

**Delivery target: October 10.** Freeze features October 7–9 for acceptance and
rehearsal. Paper suitability remains the guide's decision.

[Report draft](report-draft.md) · [Measured evidence](../eval/results.md) ·
[Run artifacts](../webapp_data/) · [Release record](release-readiness.md)
