# Completion plan — October 10, 2026

Agreed September 22: finish a defensible research prototype, stable demo and
guide-ready report. Paper suitability is the guide's subsequent decision.
Dates below are targets, not claims that experiments will improve accuracy.

| Target | Work and acceptance evidence |
|---|---|
| Sep 22–25 | Full-input Honduras ablation and measured latency; retain old degraded baselines. Priority-weight sensitivity across the three real runs, with input hashes and missing-signal caveats. |
| Sep 26–30 | Time-varying current field behind an explicit option; baseline comparison on identical drifter tracks and horizon samples. Separate calibration and evaluation tracks; report envelope coverage and width. |
| Oct 1–3 | Extend geographic holdout where labels permit; assess temporal matching against its unchanged baseline. No regional accuracy claims without independent labels. |
| Oct 4–6 | Reconcile report, figures, evidence and console; targeted usability/accessibility and approval-durability checks. Preserve the existing navigation and partial-input wording. |
| Oct 7–9 | Feature freeze, full tests/build/provenance, deployed and offline acceptance, demo rehearsal, final report/slides and limitations checklist. |
| Oct 10 | Deliver tested release and evidence package to guide. No last-minute unvalidated model changes. |

## Boundaries

- Workstation owns GPU/data processing and research evaluations. Mac owns
  supporting report/console work coordinated through branches and this status log.
- Existing local UI and report edits are preserved; research work starts on
  `codex/research-completion`. Do not stage unrelated edits wholesale.
- Keep baseline artifacts. New experiments get separate files, methods,
  configuration and input provenance; negative results are valid outcomes.
- Independent debris/source/vessel confirmation remains external validation.
  River rankings used as model inputs cannot independently validate attribution.
- Puducherry's missing GFW remains unavailable, never zero vessels. Grid
  observations are not unique vessels; candidates are not confirmed ghost nets.
- No worldwide monitoring, wholesale UI rebuild, new auth platform or autonomous
  dispatch is required for this deadline. Deployment still requires release review.

## Current execution

- September 22: fetched origin; HEAD matches main `4d7304b`; RTX 5070 and
  Python 3.11.9 verified. Existing data available except on-disk Sentinel-2;
  imagery reader streams public COGs as designed.
- Full-input ablation completed with no missing inputs. Removing GFW changes
  the top priority score; this is dependence, not validated recommendation accuracy.
- Full-input latency completed: 1017.24 seconds (17.0 minutes), including
  serialization; cold cache not established. `eval/latency_full_inputs.json`.
- Priority sensitivity completed on three real runs, with input hashes.
- Paired temporal-current comparison completed on 19 historical buoys; no
  consistent accuracy gain, so production remains mean-field. Separate-buoy
  radius calibration trades improved coverage for large 52–58 km mean radii.
- Strict geographic extension complete: two tiles / three seeds;
  `eval/geographic_validation.json`, with small-label-support caveats.
- Next: Mac review of PRs #17 and #18, report/citation completion and external
  validation where feasible. No model promotion or release change yet.
