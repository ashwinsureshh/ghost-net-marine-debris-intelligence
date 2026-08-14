"""FR-2 — False-Positive Verification Agent.

The agent's job is adversarial: for each candidate it *tries to disqualify* the
detection against the documented failure modes of spectral debris detection
(PRD §13 — "spectral detection has a real, literature-acknowledged
false-positive problem"), and reports the specific check that killed it.

Design decisions worth knowing before changing anything here:

* A check that cannot be evaluated — no acquisition geometry, no repeat pass —
  returns ``disqualified=False`` **and** says so in its reason. Inconclusive is
  not the same as passed, and it costs the detection confidence rather than
  being silently treated as evidence of innocence.
* Nothing is deleted. A rejected candidate becomes a ``VerificationResult`` with
  ``verified=False``; ``ghostnet.pipeline`` keeps those in state so the
  auditability requirement (PRD §8) holds and FR-2.4's before/after comparison
  has both populations to work from.

Thresholds are literature-informed starting points, not fitted constants. They
must be re-fitted against MARIDA on the workstation before any precision/recall
figure from this agent goes in the report.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from ghostnet.agents.detection import BandWindow
from ghostnet.geo import haversine_km
from ghostnet.schemas import CheckResult, Detection, Evidence, VerificationResult


@dataclass(frozen=True)
class VerificationThresholds:
    """Tunable cut-offs for the four spectral failure modes.

    FITTED against MARIDA on the workstation 2026-08-14 — train split only, by
    coordinate descent with the detector held fixed. Full before/after table,
    method and caveats in eval/results.md. Held-out test result: precision
    0.238 -> 0.623, F1 0.385 -> 0.753, false rejection of true debris 5.0%.

    The previous literature-derived defaults were not merely uncalibrated, they
    were net-harmful: ``shadow_brightness_max=0.015`` sat in the middle of the
    true-debris brightness distribution and rejected 78.6% of real debris, and
    on the val split the agent as a whole *lowered* F1 (0.697 -> 0.648).

    KNOWN ISSUE with these fitted values: the checks now fire outside their
    named failure modes — ``foam_whitecap`` rejects turbid water, ``sun_glint``
    rejects clouds and ships. The decisions are right (those are all genuine
    false positives) but the reason strings are therefore sometimes inaccurate,
    which FR-2.3 and PRD §8 care about. The fix is to split out dedicated
    turbid-water and bright-target checks, not to revert these numbers.
    """

    # Sun glint: bright *and* spectrally flat, including in SWIR where clean
    # water absorbs almost everything.
    glint_swir_min: float = 0.02          # was 0.05
    glint_flatness_max: float = 0.20      # was 0.18
    glint_specular_angle_deg: float = 20.0
    # Foam / whitecaps: bright in the visible with no vegetation-like red edge.
    foam_red_min: float = 0.045           # was 0.12 — foam's red is only ~0.048
    foam_ndvi_max: float = -0.10          # was 0.05
    # Kelp / Sargassum: vegetation-like NDVI dominating the FDI response.
    kelp_ndvi_min: float = 0.10           # was 0.20 — catches Sparse Sargassum
    kelp_ndvi_fdi_ratio: float = 1.0      # was 12.0
    # Cloud shadow: anomalously dark across all bands.
    shadow_brightness_max: float = 0.008  # was 0.015
    shadow_cloud_fraction_min: float = 0.10
    # Multi-temporal: how far beyond the current-implied displacement a repeat
    # observation may sit and still count as the same patch.
    persistence_tolerance_km: float = 5.0
    # Confidence multiplier applied when a check could not be evaluated.
    inconclusive_penalty: float = 0.85


DEFAULT_THRESHOLDS = VerificationThresholds()


@dataclass(frozen=True)
class RepeatObservation:
    """A later or earlier pass over the same water (FR-2.2)."""

    tile_id: str
    acquired_at: datetime
    lon: float | None
    lat: float | None
    detected: bool


def _specular_angle_deg(geometry: dict[str, float]) -> float | None:
    """Angle between the view direction and the sun's specular reflection.

    Small angles mean the sensor is looking straight at the sun glint spot.
    """
    needed = ("sun_zenith_deg", "sun_azimuth_deg", "view_zenith_deg", "view_azimuth_deg")
    if not all(k in geometry for k in needed):
        return None
    sz = math.radians(geometry["sun_zenith_deg"])
    vz = math.radians(geometry["view_zenith_deg"])
    daz = math.radians(geometry["sun_azimuth_deg"] - geometry["view_azimuth_deg"])
    # Specular direction has the sun's zenith mirrored about the nadir plane.
    cos_gamma = math.cos(sz) * math.cos(vz) - math.sin(sz) * math.sin(vz) * math.cos(daz)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_gamma))))


def check_sun_glint(window: BandWindow, t: VerificationThresholds) -> CheckResult:
    swir = window.band_means.get("B11", 0.0)
    flatness = window.flatness
    angle = _specular_angle_deg(window.geometry)

    spectrally_glinty = swir > t.glint_swir_min and flatness < t.glint_flatness_max
    geometrically_glinty = angle is not None and angle < t.glint_specular_angle_deg

    detail = {"swir_b11": round(swir, 5), "flatness": round(flatness, 4)}
    if angle is not None:
        detail["specular_angle_deg"] = round(angle, 2)

    if spectrally_glinty and (geometrically_glinty or angle is None):
        return CheckResult(
            name="sun_glint",
            disqualified=True,
            reason=(
                f"Sun glint: SWIR1 reflectance {swir:.3f} exceeds {t.glint_swir_min} "
                f"and the spectrum is flat (CV {flatness:.2f}) — clean water absorbs "
                "SWIR, so a bright flat SWIR signal is specular reflection, not debris."
            ),
            detail=detail,
        )
    if angle is None:
        return CheckResult(
            name="sun_glint",
            disqualified=False,
            reason=(
                "Sun-glint geometry unavailable for this tile; judged on spectral "
                "shape alone (inconclusive)."
            ),
            detail=detail,
        )
    return CheckResult(
        name="sun_glint",
        disqualified=False,
        reason=f"No glint signature (SWIR1 {swir:.3f}, specular angle {angle:.0f}°).",
        detail=detail,
    )


def check_foam(window: BandWindow, t: VerificationThresholds) -> CheckResult:
    red = window.band_means.get("B04", 0.0)
    detail = {"red_b04": round(red, 5), "ndvi": round(window.ndvi, 4)}
    if red > t.foam_red_min and window.ndvi < t.foam_ndvi_max:
        return CheckResult(
            name="foam_whitecap",
            disqualified=True,
            reason=(
                f"Sea foam / whitecap: red reflectance {red:.3f} is high while NDVI "
                f"is {window.ndvi:.3f} — bright and spectrally neutral, unlike "
                "floating plastic which lifts the NIR shoulder."
            ),
            detail=detail,
        )
    return CheckResult(
        name="foam_whitecap",
        disqualified=False,
        reason=f"Not foam-like (red {red:.3f}, NDVI {window.ndvi:.3f}).",
        detail=detail,
    )


def check_vegetation(window: BandWindow, t: VerificationThresholds) -> CheckResult:
    ratio = window.ndvi / window.fdi if window.fdi > 1e-9 else float("inf")
    detail = {"ndvi": round(window.ndvi, 4), "fdi": round(window.fdi, 6)}
    if window.ndvi > t.kelp_ndvi_min and ratio > t.kelp_ndvi_fdi_ratio:
        return CheckResult(
            name="kelp_sargassum",
            disqualified=True,
            reason=(
                f"Floating vegetation: NDVI {window.ndvi:.2f} dominates the FDI "
                f"response (ratio {ratio:.0f}) — the red-edge slope of kelp or "
                "Sargassum, not of plastic."
            ),
            detail=detail | {"ndvi_fdi_ratio": round(min(ratio, 1e6), 2)},
        )
    return CheckResult(
        name="kelp_sargassum",
        disqualified=False,
        reason=f"Vegetation signature absent (NDVI {window.ndvi:.2f}).",
        detail=detail,
    )


def check_cloud_shadow(window: BandWindow, t: VerificationThresholds) -> CheckResult:
    brightness = window.brightness
    detail = {
        "brightness": round(brightness, 5),
        "cloud_fraction": round(window.cloud_fraction, 3),
    }
    if brightness < t.shadow_brightness_max:
        return CheckResult(
            name="cloud_shadow",
            disqualified=True,
            reason=(
                f"Cloud shadow: mean reflectance {brightness:.4f} is below "
                f"{t.shadow_brightness_max} across all bands — a shadow depresses "
                "the baseline and fakes a positive FDI."
            ),
            detail=detail,
        )
    if window.cloud_fraction > t.shadow_cloud_fraction_min:
        return CheckResult(
            name="cloud_shadow",
            disqualified=True,
            reason=(
                f"Cloud contamination: {window.cloud_fraction:.0%} of the sampling "
                "window is flagged cloud."
            ),
            detail=detail,
        )
    return CheckResult(
        name="cloud_shadow",
        disqualified=False,
        reason=f"Clear window (brightness {brightness:.3f}).",
        detail=detail,
    )


def check_persistence(
    detection: Detection,
    repeats: list[RepeatObservation],
    *,
    current_speed_ms: float | None,
    t: VerificationThresholds,
) -> CheckResult:
    """FR-2.2 — does it persist and move coherently with local currents?"""
    if not repeats:
        return CheckResult(
            name="multi_temporal",
            disqualified=False,
            reason=(
                "No repeat pass available for this window — persistence could not "
                "be tested (inconclusive)."
            ),
            detail={"repeats": 0.0},
        )

    positives = [r for r in repeats if r.detected and r.lon is not None]
    if not positives:
        return CheckResult(
            name="multi_temporal",
            disqualified=True,
            reason=(
                f"Transient: the patch appears once and is absent from all "
                f"{len(repeats)} repeat pass(es) — foam and glint vanish between "
                "acquisitions, a debris raft does not."
            ),
            detail={"repeats": float(len(repeats)), "reobserved": 0.0},
        )

    best_ratio = float("inf")
    best: dict[str, float] = {}
    for repeat in positives:
        dt_s = abs((repeat.acquired_at - detection.acquired_at).total_seconds())
        moved_km = haversine_km(detection.lon, detection.lat, repeat.lon, repeat.lat)
        drift_km = (current_speed_ms or 0.0) * dt_s / 1000.0
        allowed_km = drift_km + t.persistence_tolerance_km
        ratio = moved_km / allowed_km if allowed_km > 0 else float("inf")
        if ratio < best_ratio:
            best_ratio = ratio
            best = {
                "moved_km": round(moved_km, 2),
                "current_implied_km": round(drift_km, 2),
                "allowed_km": round(allowed_km, 2),
                "gap_hours": round(dt_s / 3600.0, 1),
            }

    if best_ratio > 1.0:
        return CheckResult(
            name="multi_temporal",
            disqualified=True,
            reason=(
                f"Incoherent motion: re-observed {best['moved_km']} km away, beyond "
                f"the {best['allowed_km']} km the local current allows over "
                f"{best['gap_hours']} h — not the same drifting patch."
            ),
            detail=best | {"repeats": float(len(repeats))},
        )
    return CheckResult(
        name="multi_temporal",
        disqualified=False,
        reason=(
            f"Persists across {len(positives)} repeat pass(es) and moved "
            f"{best['moved_km']} km, consistent with the local current."
        ),
        detail=best | {"repeats": float(len(repeats))},
    )


def verify(
    detection: Detection,
    window: BandWindow,
    *,
    repeats: list[RepeatObservation] | None = None,
    current_speed_ms: float | None = None,
    thresholds: VerificationThresholds = DEFAULT_THRESHOLDS,
) -> VerificationResult:
    """Run every disqualification check against one candidate (FR-2.1 – FR-2.3)."""
    checks = [
        check_sun_glint(window, thresholds),
        check_foam(window, thresholds),
        check_vegetation(window, thresholds),
        check_cloud_shadow(window, thresholds),
        check_persistence(
            detection,
            repeats or [],
            current_speed_ms=current_speed_ms,
            t=thresholds,
        ),
    ]

    disqualified = any(c.disqualified for c in checks)
    inconclusive = sum(1 for c in checks if "inconclusive" in c.reason)
    confidence = 0.0
    if not disqualified:
        confidence = detection.confidence * (
            thresholds.inconclusive_penalty**inconclusive
        )

    evidence = [
        Evidence(
            kind="sentinel2_tile",
            ref=window.tile_id,
            detail=f"{window.window_px}px spectral window at {window.acquired_at.isoformat()}",
        )
    ]
    for repeat in repeats or []:
        evidence.append(
            Evidence(
                kind="sentinel2_tile",
                ref=repeat.tile_id,
                detail=(
                    f"repeat pass {repeat.acquired_at.isoformat()}: "
                    f"{'re-observed' if repeat.detected else 'absent'}"
                ),
            )
        )

    return VerificationResult(
        detection_id=detection.id,
        verified=not disqualified,
        checks=checks,
        confidence=round(min(1.0, max(0.0, confidence)), 4),
        evidence=evidence,
    )


def precision_recall_delta(
    detections: list[Detection],
    results: list[VerificationResult],
    labels: dict[str, bool],
) -> dict[str, float]:
    """FR-2.4 — the headline ablation number: PR with and without this agent.

    ``labels`` maps detection ID to ground truth (True = real debris), as it
    comes out of a labelled benchmark such as MARIDA. Detections with no label
    are ignored rather than assumed negative.
    """
    verified = {r.detection_id for r in results if r.verified}
    labelled = [d for d in detections if d.id in labels]

    def pr(selected: set[str]) -> tuple[float, float]:
        tp = sum(1 for d in labelled if d.id in selected and labels[d.id])
        fp = sum(1 for d in labelled if d.id in selected and not labels[d.id])
        fn = sum(1 for d in labelled if d.id not in selected and labels[d.id])
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        return precision, recall

    baseline_p, baseline_r = pr({d.id for d in labelled})
    verified_p, verified_r = pr(verified)

    def f1(p: float, r: float) -> float:
        return 2 * p * r / (p + r) if p + r else 0.0

    return {
        "n_labelled": float(len(labelled)),
        "baseline_precision": round(baseline_p, 4),
        "baseline_recall": round(baseline_r, 4),
        "baseline_f1": round(f1(baseline_p, baseline_r), 4),
        "verified_precision": round(verified_p, 4),
        "verified_recall": round(verified_r, 4),
        "verified_f1": round(f1(verified_p, verified_r), 4),
        "precision_delta": round(verified_p - baseline_p, 4),
        "recall_delta": round(verified_r - baseline_r, 4),
        "false_positive_rate_drop": round(
            (1 - verified_p) - (1 - baseline_p) if labelled else 0.0, 4
        ),
    }
