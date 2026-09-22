# Geographic validation extension — frozen before new training

September 22 split-file audit (patch counts, not positive-label counts):

| Candidate held-out tile | Train | Validation | Test | Total |
|---|---:|---:|---:|---:|
| 18QYF — historical experiment | 59 | 23 | 2 | 84 |
| 16PDC — additional Caribbean tile | 81 | 30 | 71 | 182 |
| 48PZC — additional Southeast Asian tile | 9 | 27 | 17 | 53 |

Frozen workstation protocol:

1. Audit labelled debris support per candidate tile using masks, not imagery
   inference. Report sparse unlabelled pixels separately, never as negatives.
2. Exclude the evaluation tile from both training and model-selection validation.
3. Recompute class-frequency weights AND band-normalization statistics from
   retained training data only. Store both in each checkpoint and verify the
   retained-patch population hash before training and reuse.
   The existing trainer imports fixed weights estimated over the original train
   split, including train patches subsequently withheld in holdout experiments.
   Historical models excluded the tile's images but reused those aggregate class
   priors and global image normalization. Preserve the old results and disclose
   both methodological boundaries.
4. Fix seeds 20260825, 20260826 and 20260827 and the existing 60-epoch schedule
   before seeing held-out outcomes. Select checkpoints on retained validation
   debris F1 only. Do not adjust probability thresholds on held-out labels.
5. Report each tile/seed separately with precision, recall, F1, labelled counts
   and training-set size. Do not pool pixel and region/candidate metrics.
6. Compare the legacy and strict-training-only protocols explicitly; changed training
   sizes remain a confound. A new tile is not automatically a wholly unseen ocean.

The mask audit is complete: 16PDC has 143 debris pixels in 37 positive patches;
48PZC has 24 in 8 and is exploratory. Their held-out patch totals are 182 and 53.
No new region accuracy is claimed for Puducherry, which has no local labels.

The first partial training attempt on September 22 was stopped before evaluation
because it retained global image normalization. Its local checkpoint/logs are
preserved but excluded. The corrected six jobs use geo_strict_v2 identifiers.
Latency measurement finished before these GPU jobs. Results remain pending.
