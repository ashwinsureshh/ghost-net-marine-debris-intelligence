# Release readiness — 2026-09-17

## Versions and evidence

The live service is https://ghostnet-operator-console.onrender.com.
Read-only checks on September 17 returned health `ok`, schema `1.1`, and two
runs: `gulf_of_honduras` (826 candidates, 443 verified, GFW unavailable) and
`synthetic-coastal-demo`. This confirms API availability, not a fresh browser
acceptance check of the deployed UI.

The reviewed release candidate is PR #16 at
`e58118e74c6dcefd114d22f0ad9ed82297be5d21`, stacked on #15, #13, then #14.
It remains unmerged. The Mac review found two P2 issues, assigned to the
workstation: malformed GFW caches escaping degraded-mode handling (#14), and
coverage fetching full run payloads for metadata (#16).

The reviewed candidate passed the frontend production build, 10 frontend
tests, and provenance audit. Python review: 392 passed, one skipped, and one
environment-only failure because the archive lacked `.git` for the tracked-data
check. Rerun the suite in a real checkout after fixes. No new GPU work or model
evaluation was performed on the Mac.

## Offline preview

The Mac built a local 8.8 MiB bundle at
`static_export/review-2026-09-17/index.html`. It contains four runs:

| Run | Candidates | Verified | Input caveat |
|---|---:|---:|---|
| Gulf of Honduras | 826 | 443 | GFW observations are aggregated grid records |
| Gulf of Gonave | 247 | 65 | Held-out geography does not supply local accuracy labels |
| Puducherry coast | 117 | 6 | GFW unavailable; no independent local ground truth |
| Synthetic coastal demo | 7 | 3 | Illustrative only |

Generated assets are ignored by Git. This is a preview of the reviewed commit,
not the final corrected release. Rebuild after fixes using DEPLOY.md. Static
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

## Remaining release sequence

1. Workstation pushes both fixes and updates the descendant branches.
2. Mac reviews the new diff and reruns affected tests in a real checkout.
3. Confirm integration of #14 → #13 → #15 → #16 in dependency order; check each
   PR base after integration. Current instructions retain the merge hold.
4. Rebuild the offline bundle from the final integrated revision.
5. After deployment settles, verify health, expected run IDs, benchmark
   availability, evidence panels, coverage, partial-input labels and mobile UI.
   Record the actual deployed revision and date; do not infer them from health.
6. Complete the academic report and final presentation with the team. Existing
   report/viva documents are supporting material. External evaluation gaps and
   model limitations remain unless backed by new committed measurements.

No production change or merge was performed during this Mac preparation.
