# Geographic validation extension — frozen before new training

September 22 split-file audit (patch counts, not positive-label counts):

| Candidate held-out tile | Train | Validation | Test | Total |
|---|---:|---:|---:|---:|
| 18QYF — historical experiment | 59 | 23 | 2 | 84 |
| 16PDC — additional Caribbean tile | 81 | 30 | 71 | 182 |
| 48PZC — additional Southeast Asian tile | 9 | 27 | 17 | 53 |

Next workstation steps:

1. Audit labelled debris support per candidate tile using masks, not imagery
   inference. Report sparse unlabelled pixels separately, never as negatives.
2. Exclude the evaluation tile from both training and model-selection validation.
3. Recompute class-frequency weights from the retained training masks only.
   The existing trainer imports fixed weights estimated over the original train
   split, including train patches subsequently withheld in holdout experiments.
   Historical models excluded the tile's images but reused those aggregate class
   priors. Preserve the old results and disclose that methodological boundary.
4. Fix seeds 20260825, 20260826 and 20260827 and the existing 60-epoch schedule
   before seeing held-out outcomes. Select checkpoints on retained validation
   debris F1 only. Do not adjust probability thresholds on held-out labels.
5. Report each tile/seed separately with precision, recall, F1, labelled counts
   and training-set size. Do not pool pixel and region/candidate metrics.
6. Compare the legacy and strict-weight protocols explicitly; changed training
   sizes remain a confound. A new tile is not automatically a wholly unseen ocean.

These are proposed experiments, not completed evaluations. GPU jobs must wait
until the current latency measurement finishes. No new region accuracy is
claimed for the existing Puducherry run, which has no independent local labels.
