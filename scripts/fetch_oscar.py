"""FR-3.1 — download NOAA OSCAR surface currents from PO.DAAC into data/oscar.

    python scripts/fetch_oscar.py --start 2020-09-16 --end 2020-09-25
    python scripts/fetch_oscar.py --pairs          # every FR-2.2 repeat pair
    python scripts/fetch_oscar.py --start ... --end ... --dry-run

Needs ``EARTHDATA_TOKEN`` in ``.env`` (a NASA Earthdata bearer token, free from
https://urs.earthdata.nasa.gov/users/new). ``load_oscar_field()`` globs
``data/oscar/*.nc``; this writes the files it reads, and nothing else in the
pipeline changes.

Three things worth knowing before changing this
-----------------------------------------------
1. **The collection is FINAL, not NRT.** ``OSCAR_L4_OC_NRT_V2.0`` begins in
   2021, so it does not cover the 2018 demo window or the 2018 FR-2.2 repeat
   pair at all — a query against it returns zero granules for those dates,
   which reads as "no data exists" rather than "wrong collection".
   ``OSCAR_L4_OC_FINAL_V2.0`` spans 1993 onward and is what this uses.
2. **Granules are global and ~32 MB per day.** The whole Feb–Oct demo window is
   243 files and about 7.7 GB, which is a lot of disk to compute one time-mean
   field over a small bbox. Fetch the windows you actually need; ``--pairs``
   fetches only the days the FR-2.2 repeat pairs span, which is far less.
3. **The token expires.** Earthdata bearer tokens are short-lived (~60 days).
   When one lapses PO.DAAC answers with a 302 to a login page rather than an
   error, so an expired token looks like a redirect loop or an HTML file on
   disk, not an auth failure. This script checks the magic bytes of everything
   it writes and deletes anything that is not NetCDF/HDF, so a lapsed token
   fails loudly here instead of silently poisoning the current field.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghostnet.config import DATA_ROOT  # noqa: E402

CMR = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
COLLECTION = "OSCAR_L4_OC_FINAL_V2.0"
OSCAR_DIR = DATA_ROOT / "oscar"

# NetCDF-3 starts "CDF", NetCDF-4/HDF5 starts \x89HDF. Anything else PO.DAAC
# hands back — an HTML login page, most likely — is not data.
MAGIC = (b"CDF", b"\x89HDF")

# The FR-2.2 repeat pairs, from eval/results.md. A day of padding each side so
# the reader's window has something to average even at the ends.
FR22_PAIRS = [
    ("16PCC", "2020-09-18", "2020-09-23"),
    ("18QYF", "2020-03-14", "2020-03-19"),
    ("18QYF", "2020-11-29", "2020-12-04"),
    ("16PCC", "2018-09-14", "2018-09-19"),
]


def _token() -> str:
    """EARTHDATA_TOKEN from the environment or .env, without printing it."""
    tok = os.environ.get("EARTHDATA_TOKEN", "").strip()
    if not tok:
        env = REPO_ROOT / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("EARTHDATA_TOKEN=") and not line.startswith("#"):
                    tok = line.partition("=")[2].strip()
                    break
    if not tok:
        print(
            "ERROR: EARTHDATA_TOKEN is not set.\n"
            "  Register free at https://urs.earthdata.nasa.gov/users/new, generate a\n"
            "  token from your profile, and put it in .env as:\n"
            "      EARTHDATA_TOKEN=<token>\n"
            "  .env is gitignored. Never commit the token.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return tok


def granules(start: dt.date, end: dt.date) -> list[tuple[str, str]]:
    """(granule name, data URL) for the window, paging through CMR."""
    out: list[tuple[str, str]] = []
    page = 1
    while True:
        q = (
            f"{CMR}?short_name={COLLECTION}"
            f"&temporal={start:%Y-%m-%d}T00:00:00Z,{end:%Y-%m-%d}T23:59:59Z"
            f"&page_size=200&page_num={page}"
        )
        with urllib.request.urlopen(q, timeout=90) as r:
            doc = json.load(r)
        items = doc.get("items", [])
        if not items:
            break
        for it in items:
            umm = it["umm"]
            urls = [
                u["URL"]
                for u in umm.get("RelatedUrls", [])
                if u.get("Type") == "GET DATA" and u["URL"].startswith("http")
                and u["URL"].endswith(".nc")
            ]
            if urls:
                out.append((umm["GranuleUR"], urls[0]))
        if len(items) < 200:
            break
        page += 1
    return out


def download(url: str, dest: Path, token: str) -> tuple[bool, str]:
    """Fetch one granule. Returns (ok, note). Never writes a non-NetCDF file."""
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "ghostnet-fetch-oscar",
        },
    )
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(req, timeout=300) as r, tmp.open("wb") as fh:
            head = r.read(8)
            if not head.startswith(MAGIC):
                tmp.unlink(missing_ok=True)
                return False, (
                    "not NetCDF — PO.DAAC returned something else, which almost "
                    "always means the token is expired or lacks access"
                )
            fh.write(head)
            while chunk := r.read(1 << 20):
                fh.write(chunk)
    except urllib.error.HTTPError as e:
        tmp.unlink(missing_ok=True)
        extra = " (token expired or not authorised)" if e.code in (401, 403) else ""
        return False, f"HTTP {e.code} {e.reason}{extra}"
    except Exception as e:  # noqa: BLE001 - report and continue to the next granule
        tmp.unlink(missing_ok=True)
        return False, f"{type(e).__name__}: {e}"
    tmp.replace(dest)
    return True, f"{dest.stat().st_size / 1e6:.1f} MB"


def windows(args) -> list[tuple[dt.date, dt.date]]:
    if args.pairs:
        pad = dt.timedelta(days=1)
        return [
            (
                dt.date.fromisoformat(a) - pad,
                dt.date.fromisoformat(b) + pad,
            )
            for _tile, a, b in FR22_PAIRS
        ]
    return [(dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", help="YYYY-MM-DD")
    ap.add_argument("--end", help="YYYY-MM-DD")
    ap.add_argument("--pairs", action="store_true",
                    help="fetch the days the FR-2.2 repeat pairs span")
    ap.add_argument(
        "--stride",
        type=int,
        default=1,
        help=(
            "Keep every Nth granule in the window. The reader takes a TIME-MEAN "
            "over whatever it finds, so a regular sample across a long window "
            "characterises the mean circulation far better per gigabyte than "
            "every consecutive day of a short one. The demo window is 243 daily "
            "files (~7.7 GB) at stride 1; --stride 10 is 25 files (~800 MB) and "
            "still spans February to October."
        ),
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be downloaded, and the total size")
    args = ap.parse_args()

    if not args.pairs and not (args.start and args.end):
        ap.error("give --start and --end, or --pairs")

    token = None if args.dry_run else _token()
    OSCAR_DIR.mkdir(parents=True, exist_ok=True)

    wanted: dict[str, str] = {}
    for start, end in windows(args):
        found = granules(start, end)
        print(f"{start} .. {end}: {len(found)} granules")
        wanted.update({name: url for name, url in found})

    ordered = sorted(wanted.items())
    if args.stride > 1:
        kept = ordered[:: args.stride]
        print(f"stride {args.stride}: keeping {len(kept)} of {len(ordered)} granules")
        ordered = kept
    todo = [(n, u) for n, u in ordered if not (OSCAR_DIR / f"{n}.nc").exists()]
    have = len(ordered) - len(todo)
    print(f"\n{len(wanted)} unique granules; {have} already on disk, "
          f"{len(todo)} to fetch (~{len(todo) * 32 / 1000:.1f} GB)")

    if args.dry_run:
        for n, _ in todo[:10]:
            print(f"   would fetch {n}")
        if len(todo) > 10:
            print(f"   ... and {len(todo) - 10} more")
        return 0

    ok = fail = 0
    for i, (name, url) in enumerate(todo, 1):
        good, note = download(url, OSCAR_DIR / f"{name}.nc", token)
        ok, fail = ok + good, fail + (not good)
        print(f"  [{i:3d}/{len(todo)}] {name:35s} {'OK' if good else 'FAIL'}  {note}",
              flush=True)
        if fail and not ok:
            print("\nFirst download failed and none has succeeded — stopping rather "
                  "than hammering the server. Check the token.", file=sys.stderr)
            return 2

    total = sum(f.stat().st_size for f in OSCAR_DIR.glob("*.nc"))
    print(f"\n{ok} downloaded, {fail} failed. "
          f"data/oscar now holds {len(list(OSCAR_DIR.glob('*.nc')))} files, "
          f"{total / 1e9:.2f} GB")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
