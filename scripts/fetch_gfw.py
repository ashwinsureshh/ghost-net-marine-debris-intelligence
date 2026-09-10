"""Cache GFW hourly SAR observations for one region (no raw AIS-track claim).

    python scripts/fetch_gfw.py --region gulf_of_honduras

The default window includes the correlation agent's seven-day time buffer.
Reports are sequential, in bounded chunks; successful chunks are resumable.
Only a fully acquired window replaces the region cache. Credentials never enter it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ghostnet.agents.vessels import GlobalFishingWatchClient  # noqa: E402
from ghostnet.config import DATA_ROOT, GhostNetError, get_region  # noqa: E402
from ghostnet.gfw import DATASET, utc  # noqa: E402
from ghostnet.schemas import VesselDetection  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", required=True)
    parser.add_argument("--start", help="optional UTC date override (inclusive)")
    parser.add_argument("--end", help="optional UTC date override (exclusive)")
    parser.add_argument("--out-dir", type=Path, default=DATA_ROOT / "gfw")
    parser.add_argument("--chunk-days", type=int, default=7)
    parser.add_argument("--buffer-km", type=float, default=100)
    parser.add_argument("--overwrite", action="store_true",
                        help="replace an existing cache for a different query")
    args = parser.parse_args()
    if not 1 <= args.chunk_days <= 31 or not 0 <= args.buffer_km <= 500:
        parser.error("chunk-days must be 1..31 and buffer-km must be 0..500")
    region = get_region(args.region)
    window = region["time_window"]
    start = utc(datetime.fromisoformat(args.start or str(window["start"])))
    end = utc(datetime.fromisoformat(args.end or str(window["end"])))
    if not args.start:
        start -= timedelta(days=7)
    if not args.end:
        end += timedelta(days=7)
    if start >= end:
        parser.error("start must precede end")
    west, south, east, north = region["bbox"]
    dy = args.buffer_km / 111.32
    dx = dy / math.cos(math.radians((south + north) / 2))
    bbox = (max(-180, west-dx), max(-90, south-dy),
            min(180, east+dx), min(90, north+dy))
    query = {"region_id": args.region, "bbox": bbox, "start": start.isoformat(),
             "end": end.isoformat(), "dataset": DATASET, "buffer_km": args.buffer_km}
    dest = args.out_dir / f"{args.region}.json"
    if dest.exists() and not args.overwrite:
        previous = json.loads(dest.read_text(encoding="utf-8"))
        if json.dumps(previous.get("query"), sort_keys=True) != json.dumps(query, sort_keys=True):
            parser.error("existing cache has another query; use another out-dir or --overwrite")
    digest = hashlib.sha256(json.dumps(query, sort_keys=True).encode()).hexdigest()[:16]
    parts = args.out_dir / ".parts" / digest
    parts.mkdir(parents=True, exist_ok=True)
    records = {}
    cursor = start
    client = GlobalFishingWatchClient()
    while cursor < end:
        stop = min(cursor + timedelta(days=args.chunk_days), end)
        part = parts / f"{cursor:%Y%m%dT%H%M%S}-{stop:%Y%m%dT%H%M%S}.json"
        if part.exists():
            rows = [VesselDetection.model_validate(row) for row in
                    json.loads(part.read_text(encoding="utf-8"))]
        else:
            rows = client.sar_detections(bbox, cursor, stop)
            temporary = part.with_suffix(".tmp")
            temporary.write_text(json.dumps([r.model_dump(mode="json") for r in rows]),
                                 encoding="utf-8")
            temporary.replace(part)
        records.update({row.id: row for row in rows})
        print(f"{cursor.date()}..{stop.date()}: {len(rows)} grid observations", flush=True)
        cursor = stop
    cache = {"schema_version": 1, "complete": True, "query": query,
             "retrieved_at": datetime.now(UTC).isoformat(),
             "caveats": ["GFW provider AIS matching; no raw AIS tracks acquired.",
                          "0.01-degree cell centres and hourly bins; not exact positions/times.",
                          "No observations does not establish SAR coverage or vessel absence."],
             "records": [row.model_dump(mode="json") for row in records.values()]}
    temporary = dest.with_suffix(".tmp")
    temporary.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    temporary.replace(dest)
    print(f"Wrote {dest}: {len(records)} grid observations; "
          f"{sum(r.is_dark for r in records.values())} unmatched")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GhostNetError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from None
