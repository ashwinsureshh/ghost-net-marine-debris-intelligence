"""Experimental repeat association; not wired into production verification.

Feature costs rank candidates only. They are not calibrated probabilities or
new spectral rejection thresholds. Non-observation is inconclusive unless the
caller establishes complete clear observation of the predicted search disk.
"""

import math
from dataclasses import dataclass

from ghostnet.geo import haversine_km


@dataclass(frozen=True)
class TemporalCandidate:
    id: str
    lon: float
    lat: float
    area: float
    spectrum: tuple[float, ...]


def _spectrum_valid(spectrum):
    return (bool(spectrum) and all(math.isfinite(v) for v in spectrum)
            and sum(v * v for v in spectrum) > 0)


def associate(
    source: TemporalCandidate, candidates: list[TemporalCandidate], *,
    predicted_lon: float, predicted_lat: float, uncertainty_km: float,
    fully_observed: bool, base_tolerance_km: float = 5.0,
) -> dict:
    """Rank repeats around the drift prediction by distance, spectrum and size.

    The 5 km tolerance is the existing persistence floor; ensemble spread comes
    from the existing drift model. Equal-weight costs are exploratory and fixed
    before measurement, not fitted on the evaluation labels.
    """
    if (not all(math.isfinite(v) for v in
                (predicted_lon, predicted_lat, uncertainty_km, base_tolerance_km))
            or not -180 <= predicted_lon <= 180 or not -90 <= predicted_lat <= 90
            or uncertainty_km < 0 or base_tolerance_km <= 0):
        raise ValueError("Invalid predicted search envelope")
    radius = base_tolerance_km + uncertainty_km
    output = {"predicted_lon": predicted_lon, "predicted_lat": predicted_lat,
              "radius_km": radius, "fully_observed": fully_observed}
    if not _spectrum_valid(source.spectrum) or not math.isfinite(source.area) or source.area <= 0:
        return {**output, "status": "inconclusive", "reason": "source features unavailable"}
    scored, missing = [], False
    for candidate in candidates:
        if not (math.isfinite(candidate.lon) and math.isfinite(candidate.lat)):
            missing = True
            continue
        distance = haversine_km(predicted_lon, predicted_lat, candidate.lon, candidate.lat)
        if distance > radius:
            continue
        if (not _spectrum_valid(candidate.spectrum) or candidate.area <= 0
                or not math.isfinite(candidate.area)
                or len(candidate.spectrum) != len(source.spectrum)):
            missing = True
            continue
        cosine = sum(a * b for a, b in zip(source.spectrum, candidate.spectrum, strict=True))
        cosine /= math.sqrt(sum(a * a for a in source.spectrum)
                            * sum(b * b for b in candidate.spectrum))
        angle = math.acos(max(-1., min(1., cosine)))
        size_cost = abs(math.log(candidate.area / source.area))
        score = (distance / radius) ** 2 + angle / math.pi + size_cost
        scored.append((score, candidate.id, {"candidate_id": candidate.id,
                       "residual_km": distance, "spectral_angle_radians": angle,
                       "log_area_ratio": size_cost, "cost": score}))
    if scored:
        scored.sort(key=lambda row: (row[0], row[1]))
        return {**output, "status": "matched", **scored[0][2]}
    status = "not_reobserved" if fully_observed and not missing else "inconclusive"
    return {**output, "status": status,
            "reason": "no usable repeat in predicted envelope"}
