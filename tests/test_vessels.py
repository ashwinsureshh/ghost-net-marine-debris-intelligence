"""FR-5 — SAR/AIS matching and dark-vessel correlation."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from ghostnet.agents.detection import detect
from ghostnet.agents.vessels import (
    AisPosition,
    GlobalFishingWatchClient,
    correlate,
    load_cached_detections,
    match_sar_to_ais,
)
from ghostnet.config import CredentialsMissingError
from ghostnet.schemas import VesselDetection
from tests.conftest import BASE_TIME


def _sar(vid: str, lon: float, lat: float, offset_hours: float = 0.0) -> VesselDetection:
    return VesselDetection(
        id=vid,
        lon=lon,
        lat=lat,
        detected_at=BASE_TIME + timedelta(hours=offset_hours),
        length_m=24.0,
    )


@pytest.fixture
def detection(debris_tile):
    return detect(debris_tile)[0]


def test_a_vessel_broadcasting_ais_is_matched():
    sar = [_sar("s1", 80.010, 12.010)]
    # ~0.5 km away, inside the 1 km matching tolerance.
    ais = [AisPosition(mmsi="419000001", lon=80.0145, lat=12.010, timestamp=BASE_TIME)]
    matched = match_sar_to_ais(sar, ais)
    assert matched[0].matched_ais_mmsi == "419000001"
    assert matched[0].is_dark is False


def test_a_vessel_with_no_ais_record_is_dark():
    sar = [_sar("s1", 80.010, 12.010)]
    matched = match_sar_to_ais(sar, ais=[])
    assert matched[0].is_dark is True


def test_ais_outside_the_time_window_does_not_match():
    sar = [_sar("s1", 80.010, 12.010)]
    ais = [
        AisPosition(
            mmsi="419000001",
            lon=80.010,
            lat=12.010,
            timestamp=BASE_TIME + timedelta(hours=6),
        )
    ]
    assert match_sar_to_ais(sar, ais)[0].is_dark is True


def test_one_ais_track_cannot_explain_two_sar_returns():
    """Without the consumed-set, two vessels would look like one plus nothing."""
    sar = [_sar("s1", 80.0100, 12.010), _sar("s2", 80.0105, 12.010)]
    ais = [AisPosition(mmsi="419000001", lon=80.0100, lat=12.010, timestamp=BASE_TIME)]
    matched = match_sar_to_ais(sar, ais)
    assert matched[0].matched_ais_mmsi == "419000001"
    assert matched[1].is_dark is True


def test_correlation_flags_a_nearby_dark_vessel(detection):
    dark = _sar("s-dark", detection.lon + 0.05, detection.lat)  # ~5 km
    result = correlate(detection, [dark])
    assert [v.id for v in result.dark_vessels] == ["s-dark"]
    assert result.correlation_strength > 0.5


def test_a_distant_dark_vessel_is_excluded(detection):
    far = _sar("s-far", detection.lon + 5.0, detection.lat)  # ~540 km
    result = correlate(detection, [far])
    assert result.dark_vessels == []
    assert result.correlation_strength == 0.0


def test_a_vessel_outside_the_time_window_is_excluded(detection):
    stale = _sar("s-old", detection.lon + 0.05, detection.lat, offset_hours=24 * 30)
    result = correlate(detection, [stale])
    assert result.dark_vessels == []


def test_ais_broadcasting_vessels_are_counted_but_not_flagged(detection):
    lit = _sar("s-lit", detection.lon + 0.05, detection.lat).model_copy(
        update={"matched_ais_mmsi": "419000009"}
    )
    result = correlate(detection, [lit])
    assert result.dark_vessels == []
    assert result.matched_vessels == 1


def test_far_matched_ais_is_excluded_before_counting(detection):
    far = _sar("far-lit", detection.lon + 5, detection.lat).model_copy(
        update={"matched_ais_mmsi": "419000009"})
    near = _sar("near-lit", detection.lon, detection.lat).model_copy(
        update={"ais_matched": True})
    result = correlate(detection, [far, near])
    assert result.matched_vessels == 1
    assert result.dark_vessels == []


def test_matched_contact_near_backtrack_is_counted(detection):
    from types import SimpleNamespace

    contact = _sar("upstream", detection.lon + 5, detection.lat).model_copy(
        update={"ais_matched": True})
    track = SimpleNamespace(points=[SimpleNamespace(lon=contact.lon, lat=contact.lat)], evidence=[])
    assert correlate(detection, [contact]).matched_vessels == 0
    assert correlate(detection, [contact], backward_trajectory=track).matched_vessels == 1


def test_extra_contacts_add_with_diminishing_returns(detection):
    one = correlate(detection, [_sar("a", detection.lon + 0.05, detection.lat)])
    three = correlate(
        detection,
        [
            _sar("a", detection.lon + 0.05, detection.lat),
            _sar("b", detection.lon + 0.06, detection.lat),
            _sar("c", detection.lon + 0.07, detection.lat),
        ],
    )
    assert three.correlation_strength > one.correlation_strength
    assert three.correlation_strength <= 1.0


def test_the_disclaimer_travels_with_the_data(detection):
    """FR-5.3 / PRD §5.2 — a research signal, never an accusation."""
    result = correlate(detection, [_sar("s", detection.lon, detection.lat)])
    assert "not an accusation" in result.disclaimer


def test_evidence_names_each_dark_contact(detection):
    result = correlate(detection, [_sar("s-dark", detection.lon + 0.02, detection.lat)])
    assert result.evidence[0].kind == "vessel_record"
    assert "s-dark" in result.evidence[0].ref
    assert "no AIS match" in result.evidence[0].detail


def test_cached_detections_round_trip(tmp_path):
    path = tmp_path / "gfw.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "s1",
                    "lon": 80.0,
                    "lat": 12.0,
                    "detected_at": BASE_TIME.isoformat(),
                    "length_m": 30.0,
                    "matched_ais_mmsi": None,
                }
            ]
        )
    )
    vessels = load_cached_detections(path)
    assert len(vessels) == 1 and vessels[0].is_dark


def test_client_reports_missing_credentials_rather_than_failing_late(monkeypatch):
    monkeypatch.delenv("GFW_API_TOKEN", raising=False)
    monkeypatch.setattr("ghostnet.config.load_dotenv_if_present", lambda: None)
    client = GlobalFishingWatchClient()
    assert client.available is False
    with pytest.raises(CredentialsMissingError, match="GFW_API_TOKEN"):
        client.sar_detections((0, 0, 1, 1), BASE_TIME, BASE_TIME)
