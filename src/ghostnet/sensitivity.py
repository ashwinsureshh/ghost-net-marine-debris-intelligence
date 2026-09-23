"""Deterministic weight perturbations; stability is not evidence of correctness."""

from __future__ import annotations

import math


def weight_variants(weights: dict[str, float]) -> dict[str, dict[str, float]]:
    """One weight at a time, relative +/-10/25/50%, then normalise.

    Downstream scoring still drops unavailable components and renormalises
    per detection. Zero weights remain zero; this does not add missing evidence.
    """
    if not weights or any(not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError("Weights must be finite, nonnegative and nonempty")
    if sum(weights.values()) <= 0:
        raise ValueError("At least one weight must be positive")
    variants = {}
    for name in sorted(weights):
        for change in (-0.50, -0.25, -0.10, 0.10, 0.25, 0.50):
            values = dict(weights)
            values[name] *= 1 + change
            total = sum(values.values())
            variants[f"{name}:{change:+.0%}"] = {k: v / total for k, v in values.items()}
    return variants


def compare_rankings(baseline: list[str], changed: list[str], capacity: int) -> dict:
    """Compare a fixed candidate universe with deterministic tie-breaking.

    Spearman here compares ordinal positions (ties broken by detection ID by
    the planner), not tied raw scores. Empty/singleton correlations are undefined.
    """
    if (len(set(baseline)) != len(baseline) or len(set(changed)) != len(changed)
            or set(baseline) != set(changed)):
        raise ValueError("Rankings must contain the same unique candidate IDs")
    if capacity < 0:
        raise ValueError("Capacity must be nonnegative")
    positions = {item: index for index, item in enumerate(changed)}
    shifts = [abs(i - positions[item]) for i, item in enumerate(baseline)]
    n = len(baseline)
    k = min(3, n)
    return {
        "top1_unchanged": baseline[0] == changed[0] if n else None,
        "top3_overlap_fraction": len(set(baseline[:k]) & set(changed[:k])) / k if k else None,
        "dispatch_set_unchanged": set(baseline[:capacity]) == set(changed[:capacity]),
        "dispatch_order_unchanged": baseline[:capacity] == changed[:capacity],
        "max_rank_shift": max(shifts, default=0),
        "mean_rank_shift": sum(shifts) / n if n else None,
        "spearman_ordinal": 1 - 6 * sum(d*d for d in shifts) / (n*(n*n-1)) if n > 1 else None,
    }
