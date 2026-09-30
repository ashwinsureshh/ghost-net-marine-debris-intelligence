"""Which verification checks reject candidates, per served real run.

    python scripts/eval_rejection_breakdown.py --json eval/rejection_breakdown.json

Reads the committed run artefacts in webapp_data/ (no recomputation) and
records, per region: verified share, how often each check disqualifies, how
often it is the sole reason, and for cloud_shadow whether cloud was present in
the sampling window. Explains *why* candidates were rejected; says nothing
about whether the rejections were correct, which needs local labels.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghostnet.evidence_hash import TEXT_HASH_METHOD, text_evidence_sha256  # noqa: E402

RUNS = ("gulf_of_honduras", "gulf_of_gonave", "puducherry_coast")


def breakdown(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    verifications = data["verifications"]
    n = len(verifications)
    disq, sole = Counter(), Counter()
    shadow_cf, shadow_br = [], []
    for v in verifications:
        failed = [c for c in v["checks"] if c.get("disqualified")]
        for c in failed:
            disq[c["name"]] += 1
            if c["name"] == "cloud_shadow":
                shadow_cf.append(c["detail"].get("cloud_fraction"))
                shadow_br.append(c["detail"].get("brightness"))
        if len(failed) == 1:
            sole[failed[0]["name"]] += 1
    names = sorted({c["name"] for v in verifications for c in v["checks"]})
    cf = [x for x in shadow_cf if x is not None]
    br = [x for x in shadow_br if x is not None]
    return {
        "input_sha256": text_evidence_sha256(path),
        "input_hash_method": TEXT_HASH_METHOD,
        "candidates": n,
        "verified": sum(v["verified"] for v in verifications),
        "verified_share": round(sum(v["verified"] for v in verifications) / n, 4) if n else None,
        "checks": {name: {"disqualifies": disq[name],
                          "disqualifies_share": round(disq[name] / n, 4) if n else None,
                          "sole_reason": sole[name]} for name in names},
        "cloud_shadow_rejections": {
            "count": disq["cloud_shadow"],
            "with_cloud_in_window": sum(x > 0 for x in cf),
            "median_cloud_fraction": round(statistics.median(cf), 4) if cf else None,
            "median_brightness": round(statistics.median(br), 5) if br else None,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", type=Path, required=True)
    args = ap.parse_args()
    runs = {r: breakdown(ROOT / "webapp_data" / f"{r}.run.json") for r in RUNS}
    out = {"runs": runs, "caveats": [
        "Counts from committed run artefacts; no recomputation.",
        "Explains why candidates were rejected, not whether rejections were correct; "
        "no local labels exist for these regions.",
        "Checks can co-occur; sole_reason counts candidates failing exactly one check.",
        "Candidates are not confirmed ghost nets.",
    ]}
    args.json.write_text(json.dumps(out, indent=2), encoding="utf-8")
    for r, b in runs.items():
        print(r, b["verified"], "/", b["candidates"], b["cloud_shadow_rejections"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
