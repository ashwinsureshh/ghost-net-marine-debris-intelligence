"""GFW v3 SAR report adapter. Reports are grid observations, not raw tracks.

Contract: https://globalfishingwatch.org/our-apis/documentation/docs/v3/4wings/report
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime

from ghostnet.config import GhostNetError
from ghostnet.schemas import VesselDetection

DATASET = "public-global-sar-presence:latest"
MAX_BYTES = 32 * 1024 * 1024
DEFAULT_QUERY_BUFFER_KM = 100.0


def buffered_bbox(bbox: tuple, buffer_km: float = DEFAULT_QUERY_BUFFER_KM) -> tuple:
    """Shared acquisition/validation extent; never trust a metadata buffer label."""
    west, south, east, north = bbox
    if not math.isfinite(buffer_km) or not 0 <= buffer_km <= 500:
        raise ValueError("buffer_km must be finite and between 0 and 500")
    dy = buffer_km / 111.32
    dx = dy / math.cos(math.radians((south + north) / 2))
    return (max(-180, west - dx), max(-90, south - dy),
            min(180, east + dx), min(90, north + dy))


class GFWError(GhostNetError):
    """Failed acquisition; never interpreted as an empty observation window."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the bearer token to a download/login host.


def request_report(root: str, token: str, params: dict, body: dict) -> dict:
    if not root.startswith("https://"):
        raise ValueError("GFW API root must use HTTPS")
    request = urllib.request.Request(
        root.rstrip("/") + "/4wings/report?" + urllib.parse.urlencode(params),
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "GhostNet/0.1 (research API client)"},
    )
    opener = urllib.request.build_opener(_NoRedirect())
    for attempt in range(3):
        try:
            with opener.open(request, timeout=110) as response:
                raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise GFWError("GFW report exceeds 32 MB; request a smaller window")
            return decode_report(raw)
        except urllib.error.HTTPError as exc:
            status = exc.code
            retry = exc.headers.get("Retry-After", "")
            exc.close()
            if status in (429, 502, 503) and attempt < 2:
                delay = float(retry) if retry.isdigit() else 2 ** attempt
                if delay <= 30:
                    time.sleep(delay)
                    continue
            raise GFWError(
                f"GFW HTTP {status}; no cache written. Check token/access for 401/403, "
                "wait for rate limits, or reduce the report window for timeouts."
            ) from None
        except (urllib.error.URLError, TimeoutError):
            raise GFWError("GFW network request failed; no cache written. Retry later.") from None
    raise GFWError("GFW retries exhausted")


def decode_report(raw: bytes) -> dict:
    try:
        if raw.startswith(b"PK"):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                candidates = []
                for entry in archive.infolist():
                    if entry.filename.lower().endswith(".json"):
                        if entry.file_size > MAX_BYTES:
                            raise GFWError("Oversized GFW JSON member")
                        value = json.loads(archive.read(entry))
                        if isinstance(value, dict) and "entries" in value:
                            candidates.append(value)
                if len(candidates) != 1:
                    raise GFWError("Expected exactly one report JSON in GFW archive")
                return candidates[0]
        value = json.loads(raw)
        if not isinstance(value, dict) or "entries" not in value:
            raise GFWError("GFW response is not a report; refusing an empty cache")
        return value
    except (ValueError, zipfile.BadZipFile, KeyError):
        raise GFWError("Invalid GFW report JSON/archive") from None


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def parse_report(report: dict, *, matched: bool, bbox: tuple,
                 start: datetime, end: datetime) -> list[VesselDetection]:
    if report.get("nextOffset") not in (None, 0):
        raise GFWError("GFW returned a paginated report; narrow the window before caching")
    entries = report.get("entries")
    if not isinstance(entries, list):
        raise GFWError("Invalid GFW entries")
    rows = []
    for group in entries:
        if not isinstance(group, dict):
            raise GFWError("Invalid GFW report group")
        if "detections" in group:
            rows.append((DATASET, group))
        else:
            for dataset, values in group.items():
                if (not dataset.startswith("public-global-sar-presence:")
                        or not isinstance(values, list)):
                    raise GFWError("Unexpected GFW dataset or report shape")
                rows.extend((dataset, row) for row in values)
    records = {}
    for dataset, row in rows:
        try:
            count = row["detections"]
            if isinstance(count, bool) or int(count) != float(count) or int(count) <= 0:
                raise ValueError("invalid count")
            lon, lat = float(row["lon"]), float(row["lat"])
            if not math.isfinite(lon) or not math.isfinite(lat):
                raise ValueError("nonfinite coordinate")
            # Report coordinates are 0.01-degree cell centres, not SAR positions.
            if not (bbox[0] - .01 <= lon <= bbox[2] + .01 and
                    bbox[1] - .01 <= lat <= bbox[3] + .01):
                raise ValueError("outside query")
            # entryTimestamp/exitTimestamp describe the report-wide vessel
            # interval, NOT this observation. Use the hourly bin date.
            timestamp = row["date"]
            acquired = utc(datetime.fromisoformat(timestamp.replace("Z", "+00:00")))
            if not utc(start) <= acquired < utc(end):
                continue  # Adjacent query windows may include the same endpoint.
            mmsi = str(row.get("mmsi") or "").strip() or None
            identity = json.dumps([dataset, matched, acquired.isoformat(), lon, lat,
                                   row.get("vesselId"), mmsi, int(count)], sort_keys=True)
            record = VesselDetection(
                id="gfw-grid-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
                lon=lon, lat=lat, detected_at=acquired,
                matched_ais_mmsi=mmsi if matched else None, ais_matched=matched,
                detection_count=int(count), position_resolution_deg=.01,
                source=f"GFW 4Wings {dataset}; hourly grid report; provider AIS matching",
            )
        except (KeyError, TypeError, ValueError):
            raise GFWError("Malformed GFW SAR row; refusing a partial cache") from None
        records[record.id] = record
    return list(records.values())


def fetch_sar(root: str, token: str, bbox: tuple, start: datetime,
              end: datetime) -> list[VesselDetection]:
    start, end = utc(start), utc(end)
    if start >= end:
        raise ValueError("start must precede end")
    if len(bbox) != 4 or not all(math.isfinite(x) for x in bbox):
        raise ValueError("bbox must contain four finite coordinates")
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox must be ordered and cannot cross the antimeridian")
    body = {"geojson": {"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {}, "geometry": {"type": "Polygon",
        "coordinates": [[[west, south], [east, south], [east, north],
                         [west, north], [west, south]]]}}]}}
    date_range = ",".join(t.strftime("%Y-%m-%dT%H:%M:%S.000Z") for t in (start, end))
    params = {"datasets[0]": DATASET, "format": "JSON", "spatial-resolution": "HIGH",
              "temporal-resolution": "HOURLY", "spatial-aggregation": "false",
              "group-by": "VESSEL_ID", "date-range": date_range}
    records = []
    # Explicit provider filters: an absent MMSI is NOT evidence of no AIS match.
    for matched in (False, True):
        params["filters[0]"] = f"matched='{str(matched).lower()}'"
        report = request_report(root, token, params, body)
        records.extend(parse_report(report, matched=matched, bbox=bbox, start=start, end=end))
    return records
