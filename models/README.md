# Model checkpoints

**Nothing in this directory is committed to git** (see `.gitignore`). Checkpoints
live only on the machine that produced them — in practice, the workstation.

If you are on the MacBook Air and a checkpoint is referenced but absent, that is
expected: it was trained on the workstation and was never synced. Do not assume
it exists — check, and fall back to the spectral-index baseline or say so
explicitly.

## Expected layout

```
models/
  detector_v1.pt        # CNN detector (FR-1.4), trained on MARIDA
  detector_v1.json      # metadata: commit hash, MARIDA split, hyperparameters,
                        # eval metrics, torch/CUDA version used
```

## Convention

Every checkpoint must be paired with a `.json` sidecar recording the git commit
it was trained from, the dataset split, and the resulting precision/recall — so
a result in `eval/results.md` can always be traced back to a reproducible run.
Commit the sidecar's *contents* into `eval/results.md`; the weights stay local.
