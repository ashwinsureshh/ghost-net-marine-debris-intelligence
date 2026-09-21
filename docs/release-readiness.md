# Release readiness — 2026-09-17

## Versions and evidence

The live service is https://ghostnet-operator-console.onrender.com.
Read-only checks on September 17 returned health `ok`, schema `1.1`, and two
runs: `gulf_of_honduras` (826 candidates, 443 verified, GFW unavailable) and
`synthetic-coastal-demo`. This confirms API availability, not a fresh browser
acceptance check of the deployed UI.

The corrected release was reviewed at #14 `c2aaddd` and #16 `7a47b5b`.
Both P2 findings are resolved. On September 21 the user authorized integration;
#14, #13, #15 and #16 merged in order, producing main `20457c3`.

Mac verification: 407 Python tests passed, with the CNN module skipped because
PyTorch is workstation-only; 12 frontend tests passed; production build and
provenance passed. The runs endpoint returns 2,547 bytes, and offline summaries
match the API. Workstation reported 422 Python tests. No new model evaluation.

## Offline preview

The Mac built a local 8.8 MiB bundle at
`static_export/release-2026-09-21/index.html`. It contains four runs:

| Run | Candidates | Verified | Input caveat |
|---|---:|---:|---|
| Gulf of Honduras | 826 | 443 | GFW observations are aggregated grid records |
| Gulf of Gonave | 247 | 65 | Held-out geography does not supply local accuracy labels |
| Puducherry coast | 117 | 6 | GFW unavailable; no independent local ground truth |
| Synthetic coastal demo | 7 | 3 | Illustrative only |

Generated assets are ignored by Git. Rebuild from the integrated release using
DEPLOY.md. Static
mode permits viewing precomputed plans; approval and live ablation require the
server. Basemap tiles may need network access even when run data is bundled;
carry screenshots for a venue without connectivity. The export build succeeded;
the browser security policy blocked opening the file URL, so visual file-based
validation remains outstanding. Open the local preview manually before the demo.

## Demo sequence

1. Open the latest console and identify the selected region, historical window,
   and real/synthetic input status before discussing results.
2. Open Coverage. Show the three real regions and explain that blank areas are
   unanalysed. Record counts are not counts of unique confirmed debris objects.
3. Open Gonave, select a candidate, and trace verification, trajectories,
   attribution and SAR context in its evidence panel. Show a rejected record
   and its recorded rejection reasons as well.
4. Open Puducherry and show its partial-input label. Missing GFW means unknown
   vessel evidence; it does not mean no vessels were observed.
5. Show the ranked plan and its capacity setting. Explain that river proximity
   is a hypothesis and AIS-unmatched is an investigation signal.
6. Show benchmark caveats: CNN verification precision gain +0.080 with 0.703
   within-tile recall; those benchmark values are not local run accuracy.
7. Demonstrate the offline copy and explain its read-only limitations. Do not
   record a real approval simply to demonstrate the control.

## Release follow-through

The stack and fixes are integrated. Reconcile and merge documentation PR #12,
then verify the settled Render deployment: four expected run IDs, benchmark,
coverage, evidence panels and partial-input labels. Rebuild the final offline
bundle and manually open its file URL before the demo. Health alone does not
identify a deployed commit; compare served frontend assets with the build.

Complete the academic report and final presentation with the team. External
evaluation gaps and model limitations remain unless supported by measurements.
