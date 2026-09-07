"""FR-4 — Source Attribution Agent.

Cross-references the Drift Agent's backward trajectory against The Ocean
Cleanup's published river-emission rankings and returns a ranked probability
distribution (FR-4.2) — never a single confident claim, because PRD §13 lists
long-distance attribution as inherently probabilistic and requires the output
to say so.

Scoring, in one line: a river's weight is *how much plastic it emits* times
*how plausibly the backtrack passed its mouth*, where plausibility is a Gaussian
whose width is the drift model's own uncertainty at the closest approach. That
last part matters — a river 30 km from the backtrack is a strong candidate when
the envelope there is 50 km wide and a weak one when it is 5 km wide, and using
the envelope keeps the two agents' error models consistent instead of inventing
a second, unrelated distance cut-off.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from ghostnet.config import region_dataset_file
from ghostnet.geo import haversine_km
from ghostnet.schemas import Evidence, RiverCandidate, SourceAttribution, Trajectory

# Below this the emission ranking stops being informative for a coastal demo.
DEFAULT_MIN_EMISSION_TONNES = 1.0
# Floor on the Gaussian width so a near-zero envelope early in the backtrack
# cannot make one river win by numerical accident.
MIN_SIGMA_KM = 10.0
DEFAULT_TOP_K = 5


@dataclass(frozen=True)
class River:
    name: str
    lon: float
    lat: float
    emission_tonnes_yr: float
    country: str = ""


@dataclass
class RiverTable:
    """Ranked river-emission table (The Ocean Cleanup / Meijer et al. 2021)."""

    rivers: list[River]
    source: str = "data/rivers"

    def __len__(self) -> int:
        return len(self.rivers)

    @classmethod
    def from_csv(cls, path: Path, *, source: str | None = None) -> RiverTable:
        """Read a CSV with columns: name, lon, lat, emission_tonnes_yr[, country]."""
        rivers: list[River] = []
        with Path(path).open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            required = {"name", "lon", "lat", "emission_tonnes_yr"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    f"{path} is missing required column(s) {sorted(missing)}; "
                    f"found {reader.fieldnames}."
                )
            for row in reader:
                rivers.append(
                    River(
                        name=row["name"].strip(),
                        lon=float(row["lon"]),
                        lat=float(row["lat"]),
                        emission_tonnes_yr=float(row["emission_tonnes_yr"]),
                        country=(row.get("country") or "").strip(),
                    )
                )
        if not rivers:
            raise ValueError(f"{path} contained no river rows.")
        return cls(rivers=rivers, source=source or str(path))


def load_river_table(region_id: str | None = None) -> RiverTable:
    """Load the river-emission table for ``region_id`` from ``data/rivers``.

    Pass the region whenever one is known. Omitting it is only safe while a
    single extract exists; with two present this raises rather than guessing,
    because attributing debris to another region's rivers would produce a
    confident, plausible, wrong answer (see :func:`region_dataset_file`).
    """
    path = region_dataset_file(
        "rivers",
        region_id=region_id,
        suffix=".csv",
        purpose="Source attribution over candidate rivers (FR-4).",
        rebuild_hint=(
            "Build it with `python scripts/build_region_extracts.py rivers "
            "--region <id> --source <global.csv>`."
        ),
    )
    return RiverTable.from_csv(path, source=str(path))


def _closest_approach(
    trajectory: Trajectory, river: River
) -> tuple[float, float, int]:
    """Return (distance_km, envelope_km, point_index) at closest approach."""
    best = (float("inf"), 0.0, 0)
    for i, point in enumerate(trajectory.points):
        distance = haversine_km(point.lon, point.lat, river.lon, river.lat)
        if distance < best[0]:
            best = (distance, point.uncertainty_km, i)
    return best


def attribute(
    trajectory: Trajectory,
    table: RiverTable,
    *,
    top_k: int = DEFAULT_TOP_K,
    min_emission_tonnes: float = DEFAULT_MIN_EMISSION_TONNES,
    min_sigma_km: float = MIN_SIGMA_KM,
) -> SourceAttribution:
    """Rank candidate source rivers for one backward trajectory (FR-4.1, FR-4.2)."""
    if trajectory.direction != "backward":
        raise ValueError(
            "Source attribution needs the backward trajectory (FR-4.1); got "
            f"direction={trajectory.direction!r}."
        )

    scored: list[tuple[float, RiverCandidate]] = []
    for river in table.rivers:
        if river.emission_tonnes_yr < min_emission_tonnes:
            continue
        distance_km, envelope_km, _ = _closest_approach(trajectory, river)
        sigma = max(envelope_km, min_sigma_km)
        proximity = math.exp(-(distance_km**2) / (2 * sigma**2))
        if proximity < 1e-6:
            continue
        weight = river.emission_tonnes_yr * proximity
        scored.append(
            (
                weight,
                RiverCandidate(
                    name=river.name,
                    lon=river.lon,
                    lat=river.lat,
                    emission_tonnes_yr=river.emission_tonnes_yr,
                    distance_km=round(distance_km, 2),
                    probability=0.0,
                ),
            )
        )

    if not scored:
        return SourceAttribution(
            detection_id=trajectory.detection_id,
            candidates=[],
            note=(
                "No river in the table lies within the backward trajectory's "
                "uncertainty envelope. Either the source is outside the table's "
                "coverage or the backtrack horizon is too short — do not read "
                "this as 'no river source'."
            ),
            evidence=list(trajectory.evidence),
        )

    total = sum(weight for weight, _ in scored)
    scored.sort(key=lambda pair: pair[0], reverse=True)
    candidates = [
        candidate.model_copy(update={"probability": round(weight / total, 4)})
        for weight, candidate in scored[:top_k]
    ]

    covered = sum(c.probability for c in candidates)
    note = (
        f"Ranked over {len(scored)} candidate river(s); the listed {len(candidates)} "
        f"carry {covered:.0%} of the probability mass. Probabilistic by "
        "construction (PRD §13) — attribution over multi-day drift is not a "
        "single confident claim."
    )

    return SourceAttribution(
        detection_id=trajectory.detection_id,
        candidates=candidates,
        note=note,
        evidence=[
            *trajectory.evidence,
            Evidence(
                kind="river_table",
                ref=table.source,
                detail=f"{len(table)} rivers in the emission ranking",
            ),
        ],
    )


def matches_published_ranking(
    attributions: list[SourceAttribution], published_top_rivers: set[str]
) -> dict[str, float]:
    """PRD §3 metric: fraction of top attributions in the published rankings."""
    tops = [a.top.name for a in attributions if a.top is not None]
    if not tops:
        return {"n_attributed": 0.0, "match_fraction": 0.0}
    hits = sum(1 for name in tops if name in published_top_rivers)
    return {
        "n_attributed": float(len(tops)),
        "match_fraction": round(hits / len(tops), 4),
    }
