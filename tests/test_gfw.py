"""Synthetic API fixtures: no credentials or network required."""
import io
import json
import urllib.error
import zipfile
from datetime import UTC, datetime

import pytest

from ghostnet import gfw
from ghostnet.agents.detection import detect
from ghostnet.agents.vessels import correlate, load_cached_detections
from ghostnet.config import DataUnavailableError

START = datetime(2018, 2, 1, tzinfo=UTC)
END = datetime(2018, 3, 1, tzinfo=UTC)
BBOX = (-89, 15, -86, 17)


def report(**overrides):
    row = {"detections": 1, "lat": 16.1, "lon": -88.0,
           "date": "2018-02-19 11:00", "entryTimestamp": "2018-02-02T11:37:21Z",
           "mmsi": "", "vesselId": ""}
    row.update(overrides)
    return {"entries": [{"public-global-sar-presence:v4.0": [row]}], "nextOffset": None}


def parse(value, matched=False):
    return gfw.parse_report(value, matched=matched, bbox=BBOX, start=START, end=END)


def test_hourly_date_not_report_entry_timestamp():
    record = parse(report())[0]
    assert record.detected_at == datetime(2018, 2, 19, 11, tzinfo=UTC)
    assert record.position_resolution_deg == .01
    assert record.is_dark


def test_matched_without_published_mmsi_is_not_dark():
    record = parse(report(), matched=True)[0]
    assert record.matched_ais_mmsi is None
    assert record.is_dark is False


def test_real_api_utc_offsets_accept_legacy_naive_satellite_times(debris_tile):
    detection = detect(debris_tile)[0]
    detection = detection.model_copy(update={"acquired_at": datetime(2018, 2, 19, 11)})
    record = parse(report())[0].model_copy(update={"lon": detection.lon, "lat": detection.lat})
    result = correlate(detection, [record])
    assert result.correlation_strength == 1
    assert "cell centre" in result.evidence[0].detail


def test_multiple_detections_stay_one_explicit_grid_observation():
    records = parse(report(detections=3))
    assert len(records) == 1 and records[0].detection_count == 3


@pytest.mark.parametrize("change", [{"detections": -1}, {"detections": 1.5},
                                   {"lon": float("nan")}, {"lon": 80}, {"date": "bad"}])
def test_malformed_rows_cannot_be_silently_skipped(change):
    with pytest.raises(gfw.GFWError):
        parse(report(**change))


def test_half_open_window_and_stable_identity():
    assert parse(report(date=END.isoformat())) == []
    assert parse(report())[0].id == parse(report(entryTimestamp="changed"))[0].id


def test_truncation_is_not_success():
    value = report()
    value["nextOffset"] = 100
    with pytest.raises(gfw.GFWError, match="paginated"):
        parse(value)


def test_two_provider_filters_and_z_date_format(monkeypatch):
    calls = []
    def request(root, token, params, body):
        calls.append(dict(params))
        assert body["geojson"]["features"][0]["geometry"]["coordinates"][0][0] == [-89, 15]
        return report()
    monkeypatch.setattr(gfw, "request_report", request)
    records = gfw.fetch_sar("https://example.test", "secret", BBOX, START, END)
    assert [r.is_dark for r in records] == [True, False]
    assert [c["filters[0]"] for c in calls] == ["matched='false'", "matched='true'"]
    assert calls[0]["date-range"] == "2018-02-01T00:00:00.000Z,2018-03-01T00:00:00.000Z"


def test_json_and_zip_supported_without_extraction():
    raw = json.dumps(report()).encode()
    assert gfw.decode_report(raw) == report()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("report.json", raw)
        archive.writestr("README.txt", "caveats")
    assert gfw.decode_report(buffer.getvalue()) == report()
    with pytest.raises(gfw.GFWError):
        gfw.decode_report(b'{"error":"unauthorized"}')


def test_auth_error_does_not_leak_token(monkeypatch):
    class Opener:
        def open(self, *args, **kwargs):
            raise urllib.error.HTTPError("https://example.test", 401, "secret", {}, None)
    monkeypatch.setattr(gfw.urllib.request, "build_opener", lambda *a: Opener())
    with pytest.raises(gfw.GFWError) as error:
        gfw.request_report("https://example.test", "secret", {}, {})
    assert "401" in str(error.value) and "secret" not in str(error.value)


def test_rate_limit_retry_is_bounded(monkeypatch):
    attempts, sleeps = [], []
    class Opener:
        def open(self, *args, **kwargs):
            attempts.append(1)
            raise urllib.error.HTTPError("https://example.test", 429, "limit",
                                         {"Retry-After": "1"}, None)
    monkeypatch.setattr(gfw.urllib.request, "build_opener", lambda *a: Opener())
    monkeypatch.setattr(gfw.time, "sleep", sleeps.append)
    with pytest.raises(gfw.GFWError):
        gfw.request_report("https://example.test", "secret", {}, {})
    assert len(attempts) == 3 and sleeps == [1, 1]


def test_cache_rejects_wrong_region_and_short_window(tmp_path):
    path = tmp_path / "region.json"
    cache = {"schema_version": 1, "complete": True,
             "query": {"region_id": "r", "start": START.isoformat(), "end": END.isoformat()},
             "records": [r.model_dump(mode="json") for r in parse(report())]}
    path.write_text(json.dumps(cache), encoding="utf-8")
    assert len(load_cached_detections(path, region_id="r", start=START, end=END)) == 1
    with pytest.raises(DataUnavailableError):
        load_cached_detections(path, region_id="other")
    with pytest.raises(DataUnavailableError):
        load_cached_detections(path, region_id="r", bbox=BBOX)
    with pytest.raises(DataUnavailableError):
        load_cached_detections(path, region_id="r", end=datetime(2019, 1, 1, tzinfo=UTC))


def test_bad_request_does_not_make_api_call(monkeypatch):
    monkeypatch.setattr(gfw, "request_report", lambda *a: pytest.fail("network requested"))
    with pytest.raises(ValueError):
        gfw.fetch_sar("https://example.test", "x", BBOX, END, START)


@pytest.mark.parametrize("adequate", [False, True])
def test_loader_checks_buffer_geometry_not_buffer_label(tmp_path, adequate):
    path = tmp_path / "r.json"
    coverage = gfw.buffered_bbox(BBOX) if adequate else BBOX
    path.write_text(json.dumps({"schema_version": 1, "complete": True,
        "query": {"region_id": "r", "bbox": coverage, "buffer_km": 100,
                  "start": START.isoformat(), "end": END.isoformat()},
        "records": []}), encoding="utf-8")
    if adequate:
        assert load_cached_detections(path, region_id="r", bbox=BBOX) == []
    else:
        with pytest.raises(DataUnavailableError, match="100 km buffered"):
            load_cached_detections(path, region_id="r", bbox=BBOX)


def test_export_rejects_unbuffered_cache(monkeypatch, tmp_path):
    from pathlib import Path

    from ghostnet import config
    from ghostnet.agents import attribution, detection, drift, prioritisation

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import export_run

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    directory = tmp_path / "gfw"
    directory.mkdir()
    (directory / "r.json").write_text(json.dumps({
        "schema_version": 1, "complete": True,
        "query": {"region_id": "r", "bbox": BBOX, "buffer_km": 100,
                  "start": "2017-01-01", "end": "2020-01-01"},
        "records": [],
    }), encoding="utf-8")
    monkeypatch.setattr(export_run, "get_region", lambda _: {
        "bbox": BBOX, "time_window": {"start": "2018-02-01", "end": "2018-02-03"}})
    monkeypatch.setattr(detection, "load_tiles", lambda *a, **k: [])
    monkeypatch.setattr(prioritisation, "load_protected_areas", lambda **k: [])
    monkeypatch.setattr(drift, "load_oscar_field", lambda *a, **k: None)
    monkeypatch.setattr(attribution, "load_river_table", lambda *a, **k: None)
    with pytest.raises(DataUnavailableError, match="100 km buffered"):
        export_run.real_config("r")


def test_failed_chunk_preserves_previous_cache_and_completed_parts(monkeypatch, tmp_path):
    import sys
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import fetch_gfw

    monkeypatch.setattr(fetch_gfw, "get_region", lambda _: {
        "bbox": BBOX, "time_window": {"start": "2018-02-01", "end": "2018-02-03"}})
    calls = []
    def fetch(*args):
        calls.append(1)
        if len(calls) == 2:
            raise gfw.GFWError("upstream failed")
        return []
    monkeypatch.setattr(fetch_gfw.GlobalFishingWatchClient, "sar_detections", fetch)
    previous = tmp_path / "r.json"
    previous.write_text('{"old":"cache"}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["fetch_gfw.py", "--region", "r", "--start",
        "2018-02-01", "--end", "2018-02-03", "--chunk-days", "1", "--out-dir",
        str(tmp_path), "--overwrite"])
    with pytest.raises(gfw.GFWError):
        fetch_gfw.main()
    assert previous.read_text(encoding="utf-8") == '{"old":"cache"}'
    assert len(list((tmp_path / ".parts").rglob("*.json"))) == 1
