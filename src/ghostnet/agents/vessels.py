"""FR-5 — Dark Vessel Correlation Agent.

Cross-references Global Fishing Watch SAR vessel detections against AIS
broadcast records to find AIS-silent ("dark") vessels near a debris detection,
as a documented proxy for the unreported fishing activity that produces ghost
gear.

Framing is load-bearing, not decoration. PRD §5.2 puts enforcement action out of
scope and FR-5.3 requires the output be reported as a signal for investigation.
So:

* "Dark" here means *this SAR detection had no AIS record matching it in the
  query window*. That is a data-availability statement. AIS gaps have many
  innocent causes — coverage holes, equipment failure, vessels below carriage
  requirements — and the matching radius below is a tolerance, not a proof.
* :class:`~ghostnet.schemas.VesselCorrelation` carries its disclaimer as a
  field, so the caveat travels with the data into any report or dashboard
  instead of living only in a template someone might not use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ghostnet.config import (
    CredentialsMissingError,
    DataUnavailableError,
    dataset_path,
    require_env,
)
from ghostnet.geo import haversine_km
from ghostnet.schemas import (
    Detection,
    Evidence,
    Trajectory,
    VesselCorrelation,
    VesselDetection,
)

GFW_API_ROOT = "https://gateway.api.globalfishingwatch.org/v3"
# A SAR detection and an AIS position within this distance and time are treated
# as the same vessel. GFW's own published matching uses comparable tolerances.
DEFAULT_MATCH_RADIUS_KM = 1.0
DEFAULT_MATCH_WINDOW_MINUTES = 30
# How near a detection (or its backtrack) a dark vessel must be to count.
DEFAULT_CORRELATION_RADIUS_KM = 50.0
DEFAULT_CORRELATION_WINDOW_DAYS = 7.0


@dataclass(frozen=True)
class AisPosition:
    mmsi: str
    lon: float
    lat: float
    timestamp: datetime


def match_sar_to_ais(
    sar: list[VesselDetection],
    ais: list[AisPosition],
    *,
    radius_km: float = DEFAULT_MATCH_RADIUS_KM,
    window_minutes: int = DEFAULT_MATCH_WINDOW_MINUTES,
) -> list[VesselDetection]:
    """Label each SAR detection with the AIS vessel it matches, if any (FR-5.2).

    Greedy nearest-first matching, one AIS track per SAR detection: without the
    consumed-set an AIS position sitting between two SAR returns would explain
    both, and two real vessels would be reported as one plus a dark contact.
    """
    window = timedelta(minutes=window_minutes)
    consumed: set[tuple[str, datetime]] = set()
    matched: list[VesselDetection] = []

    for detection in sar:
        best: tuple[float, AisPosition] | None = None
        for position in ais:
            key = (position.mmsi, position.timestamp)
            if key in consumed:
                continue
            if abs(position.timestamp - detection.detected_at) > window:
                continue
            distance = haversine_km(
                detection.lon, detection.lat, position.lon, position.lat
            )
            if distance <= radius_km and (best is None or distance < best[0]):
                best = (distance, position)
        if best is None:
            matched.append(detection.model_copy(update={"matched_ais_mmsi": None}))
        else:
            consumed.add((best[1].mmsi, best[1].timestamp))
            matched.append(
                detection.model_copy(update={"matched_ais_mmsi": best[1].mmsi})
            )
    return matched


def correlate(
    detection: Detection,
    vessels: list[VesselDetection],
    *,
    backward_trajectory: Trajectory | None = None,
    radius_km: float = DEFAULT_CORRELATION_RADIUS_KM,
    window_days: float = DEFAULT_CORRELATION_WINDOW_DAYS,
    source_ref: str = "gfw",
) -> VesselCorrelation:
    """Correlate dark-vessel presence with one debris detection (FR-5.3).

    Proximity is measured to the detection *and* to its backward trajectory when
    one is available: gear abandoned upstream of where the patch was imaged is
    the case the agent exists to catch, and scoring only against the detection
    point would miss exactly that.
    """
    window = timedelta(days=window_days)
    track = [(p.lon, p.lat) for p in backward_trajectory.points] if backward_trajectory else []

    dark: list[VesselDetection] = []
    matched_count = 0
    strengths: list[float] = []

    for vessel in vessels:
        if abs(vessel.detected_at - detection.acquired_at) > window:
            continue
        if not vessel.is_dark:
            matched_count += 1
            continue
        distance = haversine_km(detection.lon, detection.lat, vessel.lon, vessel.lat)
        for lon, lat in track:
            distance = min(distance, haversine_km(lon, lat, vessel.lon, vessel.lat))
        if distance > radius_km:
            continue
        dark.append(vessel)
        proximity = 1.0 - (distance / radius_km)
        gap_days = abs((vessel.detected_at - detection.acquired_at).total_seconds()) / 86400
        recency = 1.0 - min(gap_days / window_days, 1.0)
        strengths.append(0.6 * proximity + 0.4 * recency)

    # Strongest contact dominates; additional ones add with diminishing returns,
    # so three marginal contacts never outweigh one right on top of the patch.
    strength = 0.0
    for i, value in enumerate(sorted(strengths, reverse=True)):
        strength += value * (0.5**i)
    strength = round(min(1.0, strength), 4)

    evidence = [
        Evidence(
            kind="vessel_record",
            ref=f"{source_ref}:{vessel.id}",
            detail=(
                f"SAR detection at ({vessel.lon:.3f}, {vessel.lat:.3f}) "
                f"{vessel.detected_at.isoformat()}, no AIS match within tolerance"
            ),
        )
        for vessel in dark
    ]
    if backward_trajectory is not None:
        evidence.extend(backward_trajectory.evidence)

    return VesselCorrelation(
        detection_id=detection.id,
        dark_vessels=dark,
        matched_vessels=matched_count,
        correlation_strength=strength,
        evidence=evidence,
    )


def load_cached_detections(path: Path | None = None) -> list[VesselDetection]:
    """Load previously cached GFW SAR detections from ``data/gfw``.

    The cache is the normal path for a demo run: the free tier is rate-limited
    (PRD §13), and re-querying per pipeline run would also break the
    reproducibility requirement in PRD §8.

    Expected shape — a JSON list of objects with ``id``, ``lon``, ``lat``,
    ``detected_at`` (ISO 8601), and optionally ``length_m`` and
    ``matched_ais_mmsi``.
    """
    if path is None:
        directory = dataset_path(
            "gfw", required=True, purpose="Dark-vessel correlation (FR-5.1)."
        )
        files = sorted(directory.glob("*.json"))
        if not files:
            raise DataUnavailableError(
                "gfw", directory, "No cached JSON SAR-detection responses found."
            )
        path = files[0]

    with Path(path).open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return [VesselDetection.model_validate(record) for record in raw]


class GlobalFishingWatchClient:
    """Thin client for the GFW public API (FR-5.1).

    Free-tier and rate-limited (PRD §13), so callers are expected to cache
    responses under ``data/gfw`` rather than re-query per pipeline run.
    """

    def __init__(self, token: str | None = None, *, root: str = GFW_API_ROOT) -> None:
        self._token = token
        self.root = root

    @property
    def token(self) -> str:
        if self._token:
            return self._token
        self._token = require_env("GFW_API_TOKEN", "Global Fishing Watch API")
        return self._token

    @property
    def available(self) -> bool:
        try:
            _ = self.token
        except CredentialsMissingError:
            return False
        return True

    def sar_detections(
        self,
        bbox: tuple[float, float, float, float],
        start: datetime,
        end: datetime,
    ) -> list[VesselDetection]:
        """Query SAR vessel detections in a space-time window (FR-5.1)."""
        _ = self.token  # fail fast and clearly if the token is missing
        raise NotImplementedError(
            "The GFW SAR-detection query is not implemented yet. It needs a live "
            "token to develop against the v3 vessel-detections endpoint, and the "
            "free tier is rate-limited — cache responses under data/gfw and load "
            "them via load_cached_detections() rather than querying per run. "
            f"Requested bbox={bbox} window={start.isoformat()}..{end.isoformat()}"
        )
