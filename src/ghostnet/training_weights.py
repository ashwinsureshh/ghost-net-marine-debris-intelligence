"""Training-only class priors; unlabelled pixels never determine weights."""

import numpy as np


def weights_from_counts(counts):
    counts = np.asarray(counts, dtype=float)
    if (counts.ndim != 1 or len(counts) < 2 or not np.isfinite(counts).all()
            or (counts < 0).any() or (counts != np.floor(counts)).any()):
        raise ValueError("Class counts must be finite nonnegative integers")
    if counts[1] == 0:
        raise ValueError("No labelled marine debris in retained training data")
    # An absent class uses a one-pixel floor, defined before any evaluation.
    values = 1 / np.sqrt(np.maximum(counts[1:], 1))
    return (values / values.mean()).tolist()
