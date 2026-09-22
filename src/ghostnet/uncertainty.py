"""Internal held-out calibration of reported radii, not ensemble dynamics."""

from __future__ import annotations

import hashlib
import math

import numpy as np


def split_buoys(ids: list[str]) -> tuple[list[str], list[str]]:
    """Fixed ID-only split; no observations or errors influence membership."""
    unique = sorted(set(ids), key=lambda value: hashlib.sha256(value.encode()).hexdigest())
    if len(unique) < 3 or len(unique) != len(ids):
        raise ValueError("Need at least three distinct buoy IDs")
    count = max(1, len(unique) // 3)
    return unique[:count], unique[count:]


def fit_radius_multiplier(errors: list[float], radii: list[float], target: float = .90) -> float:
    """Empirical calibration quantile, with no held-out coverage guarantee.

    Pool calibration observations only; long tracks consequently have greater
    weight. This post-hoc dilation must be reported with its resulting widths.
    """
    if not errors or len(errors) != len(radii) or not 0 < target < 1:
        raise ValueError("Need paired calibration observations and a target between zero and one")
    if any(not math.isfinite(e) or not math.isfinite(r) or e < 0 or r <= 0
           for e, r in zip(errors, radii, strict=True)):
        raise ValueError("Errors must be finite/nonnegative and radii finite/positive")
    ratios = [e/r for e, r in zip(errors, radii, strict=True)]
    return max(1., float(np.quantile(ratios, target, method="higher")))
