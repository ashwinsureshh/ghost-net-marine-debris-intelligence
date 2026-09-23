# River attribution: published-prior consistency, not source accuracy

23 September 2026. Three existing real exports, no pipeline rerun, new imagery,
threshold tuning or production algorithm changes. All regions are reported.

## Reference and method

The Ocean Cleanup's [published map](https://theoceancleanup.com/sources/) identifies
its point file as modeled annual river plastic emissions and links to the
[Meijer 2021 dataset](https://doi.org/10.6084/m9.figshare.14515590).
We reuse the locally converted CSV (31,819 records), not a newly acquired dataset.
Source-table and export hashes use sha256-utf8-lf-v1. A workstation cross-check
against the existing downloaded shapefile matched all 31,819 coordinate/emission
records including multiplicities (coordinates at five decimals, emissions at
four). This validates conversion consistency, not independent source truth.

Match each exported candidate by coordinates rounded to five decimals AND its
emission value, never by the locally attached name. Refuse unmatched candidates
or regional rows that differ from the global conversion. Regional ranks use
all extract mouths eligible under the existing >=1 tonne/year filter, including
those never selected by a trajectory. Global ranks retain all published records,
including 130 duplicate-coordinate records; they are not silently deduplicated.
Equal emissions share a competition rank. Global rank <=1000 can include ties.

For each attributed detection, compare its first candidate with regional
emission ranks <=1, <=5 and <=10, and global rank <=1000. The regional top-five
boundary is an exploratory comparison, not a preregistered acceptance threshold.
Empty attributions are separate; a zero denominator yields null. The comparison
stores top-source frequencies, ranks and input hashes in
[river_rankings.json](../eval/river_rankings.json). Names are annotations.

## Results

| Run | Attributed | Regional top 1 | Regional top 5 | Regional top 10 | Global top 1000 |
|---|---:|---:|---:|---:|---:|
| Honduras | 443 | 0 | 17 (3.84%) | 18 (4.06%) | 18 (4.06%) |
| Gonave | 65 | 0 | 13 (20.00%) | 13 (20.00%) | 13 (20.00%) |
| Puducherry | 6 | 1 | 6 (100%) | 6 (100%) | 6 (100%) |

All recorded attributions have candidates. These denominators exclude detections
without attribution, principally rejected detections; they are not all detection
counts or confirmed source labels. Puducherry remains partial because GFW is
unavailable. Its six attributions are a very small sample.

Honduras's modal top source has regional emission rank 60 (164 attributions);
Gonave's has rank 20 (46); Puducherry's has rank 4 (5). Geography/trajectory
proximity can outweigh the emission prior. This describes model behavior,
not evidence that those river identities are correct.

## Why this cannot measure independent accuracy

Meijer emissions already multiply the proximity score in the attribution agent.
Choosing the highest regional emitter for every detection trivially scores 100%
regional top-1/top-5/top-10 agreement, without using any detection or trajectory.
Thus a high match rate cannot establish source accuracy, and disagreement with
an annual emissions ranking is not necessarily an incorrect source attribution.
The existing API's probability is a normalized model score, not calibrated source
confidence. The production algorithm and outputs are unchanged by this study.

External context also must not be conflated with the input prior. The Ocean
Cleanup's [June 2022 Motagua update](https://theoceancleanup.com/updates/the-ocean-cleanup-trials-new-interceptor-in-worlds-most-polluting-river/)
estimates approximately 20,000 tonnes/year. The local mouth annotated Motagua
uses 398.963 tonnes/year. The [Deltares December 2025 report, p.23](https://publications.deltares.nl/11209994_000_0001.pdf)
cites a 232-tonne/year model estimate and the separate 20,000 estimate. These
figures differ in provenance; we have not reconciled that mouth-level identity
or substituted any estimate. None labels the source of our historical detections.

## Acceptance and remaining evidence

The published-ranking comparison requested in PRD section 12 is now measured,
but independent source accuracy remains unvalidated. Preserve this exception.
To validate accuracy, obtain dated debris release/transport observations with
known source mouths, select matching satellite/current windows independently,
and compare predicted sources with those labels and emission-only and nearest-mouth
baselines. Later river collection totals alone do not label 2018 detections.

Reproduce from the existing local river extracts and committed exports:

```text
py -3.11 scripts/eval_river_rankings.py --json eval/river_rankings.json
```

Regression tests use synthetic tables and committed small summaries, never raw
local river data. No checkpoint, scientific measurement or live run was changed.
