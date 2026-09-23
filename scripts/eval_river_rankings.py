"""Compare exported attribution with its published emission prior, not truth labels."""

import argparse
import bisect
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghostnet.evidence_hash import TEXT_HASH_METHOD, text_evidence_sha256  # noqa: E402

REGIONS = ("gulf_of_honduras", "gulf_of_gonave", "puducherry_coast")


def key(row):
    return (round(float(row["lon"]), 5), round(float(row["lat"]), 5))


def index_rows(rows):
    indexed = {}
    for row in rows:
        point = key(row)
        emission = float(row["emission_tonnes_yr"])
        if (not all(map(math.isfinite, (*point, emission))) or emission < 0
                or not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90):
            raise ValueError("Invalid river coordinates/emission")
        if point in indexed:
            raise ValueError("Ambiguous duplicate river coordinates")
        indexed[point] = {**row, "emission_tonnes_yr": emission}
    if not indexed:
        raise ValueError("Empty river reference")
    return indexed


def compare(run, regional_rows, global_rows):
    regional = index_rows(regional_rows)
    worldwide = defaultdict(list)
    for row in global_rows:
        checked = index_rows([row])
        point, parsed = next(iter(checked.items()))
        worldwide[point].append(parsed)
    for point, row in regional.items():
        if (point not in worldwide or not any(math.isclose(row["emission_tonnes_yr"],
                item["emission_tonnes_yr"], rel_tol=1e-9, abs_tol=1e-8)
                for item in worldwide[point])):
            raise ValueError("Regional extract differs from global published-table conversion")
    eligible = {k: r for k, r in regional.items() if r["emission_tonnes_yr"] >= 1.0}
    local_emissions = sorted(r["emission_tonnes_yr"] for r in eligible.values())
    global_emissions = sorted(
        r["emission_tonnes_yr"] for group in worldwide.values() for r in group)

    def rank(emissions, value):
        # Competition ranks: tied emissions share the same rank; never break by name.
        return 1 + len(emissions) - bisect.bisect_right(emissions, value)

    tops, empty = Counter(), 0
    for attribution in run["attributions"].values():
        candidates = attribution["candidates"]
        if not candidates:
            empty += 1
            continue
        for candidate in candidates:
            point = key(candidate)
            if (point not in eligible or not math.isclose(
                    float(candidate["emission_tonnes_yr"]),
                    eligible[point]["emission_tonnes_yr"], rel_tol=1e-9, abs_tol=1e-8)):
                raise ValueError("Export candidate cannot be matched to reference")
        tops[key(candidates[0])] += 1
    rows = []
    for point, count in sorted(tops.items(), key=lambda item: (-item[1], item[0])):
        river = eligible[point]
        emission = river["emission_tonnes_yr"]
        rows.append({"name": river["name"], "lon": point[0], "lat": point[1],
                     "top_attributions": count, "emission_tonnes_yr": emission,
                     "regional_emission_rank": rank(local_emissions, emission),
                     "global_emission_rank": rank(global_emissions, emission)})
    n = sum(tops.values())
    counts = {str(k): sum(r["top_attributions"] for r in rows
                         if r["regional_emission_rank"] <= k) for k in (1, 5, 10)}
    global_hits = sum(r["top_attributions"] for r in rows if r["global_emission_rank"] <= 1000)
    return {
        "detections": len(run["detections"]), "attribution_records": len(run["attributions"]),
        "attributed": n, "empty_attributions": empty,
        "regional_mouths": len(regional), "eligible_regional_mouths": len(eligible),
        "global_records": len(global_rows),
        "global_duplicate_coordinate_records": len(global_rows) - len(worldwide),
        "regional_top_k_counts": counts,
        "regional_top_k_fractions": {k: round(v / n, 4) if n else None
                                     for k, v in counts.items()},
        "global_top_1000_count": global_hits,
        "global_top_1000_fraction": round(global_hits / n, 4) if n else None,
        "emission_only_regional_top_k_fraction": 1.0 if eligible and n else None,
        "top_mouths": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", required=True, type=Path)
    args = parser.parse_args()
    global_path = ROOT / "data/rivers/meijer2021_global.csv"
    with global_path.open(encoding="utf-8", newline="") as handle:
        global_rows = list(csv.DictReader(handle))
    regions = {}
    for region in REGIONS:
        run_path = ROOT / "webapp_data" / f"{region}.run.json"
        table_path = ROOT / "data/rivers" / f"{region}.csv"
        run = json.loads(run_path.read_text("utf-8"))
        with table_path.open(encoding="utf-8", newline="") as handle:
            table = list(csv.DictReader(handle))
        regions[region] = {**compare(run, table, global_rows),
                           "run_sha256": text_evidence_sha256(run_path),
                           "table_sha256": text_evidence_sha256(table_path)}
    output = {
        "protocol": "river-emission-prior-consistency-v1",
        "hash_method": TEXT_HASH_METHOD,
        "global_table_sha256": text_evidence_sha256(global_path),
        "published_source": "https://theoceancleanup.com/sources/",
        "dataset": "https://doi.org/10.6084/m9.figshare.14515590",
        "independent_accuracy_measured": False,
        "regions": regions,
        "caveats": [
            "Emission ranking is already an attribution input: agreement is circular consistency.",
            "Always selecting the highest emitter trivially achieves 100% regional agreement.",
            "Annual emission ranks are not source labels for individual detections/dates.",
            "Coordinate identity at five decimals; river names are local annotations, not truth.",
            "Ranks include ties; regional eligible prior uses the existing >=1 tonne/year filter.",
            "Unattributed records are counted separately; an empty denominator is null, not zero.",
            "No drift, export, threshold or production algorithm changes; no new accuracy claim.",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(output, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
