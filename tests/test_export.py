"""Run artefacts — the contract the workstation writes and the server reads."""

from __future__ import annotations

import json

import pytest

from ghostnet.agents.attribution import RiverTable
from ghostnet.agents.drift import UniformCurrentField
from ghostnet.agents.prioritisation import ProtectedArea
from ghostnet.export import (
    SCHEMA_VERSION,
    RunArtefact,
    RunRegion,
    discover_artefacts,
    export_run,
    load_artefact,
    write_artefact,
)
from ghostnet.llm import RationaleWriter
from ghostnet.pipeline import PipelineConfig, run_pipeline
from ghostnet.schemas import VesselDetection
from tests.conftest import BASE_TIME

REGION = RunRegion(
    id="test-region",
    name="Test region",
    bbox=(79.8, 12.0, 80.2, 12.2),
    window_start=BASE_TIME,
    window_end=BASE_TIME,
)


def test_duplicate_detection_ids_refuse_export(mixed_tile):
    run = run_pipeline(PipelineConfig(region_id="test", tiles=[mixed_tile]))
    run.detections.append(run.detections[0])
    with pytest.raises(ValueError, match="Duplicate detection IDs"):
        export_run(run, run_id="duplicate", region=REGION,
                   generated_on="laptop", inputs_are_synthetic=True)


@pytest.fixture
def artefact(mixed_tile, river_csv) -> RunArtefact:
    areas = [ProtectedArea("Test Reserve", 79.9, 11.99, radius_km=5.0)]
    run = run_pipeline(
        PipelineConfig(
            region_id="test-region",
            tiles=[mixed_tile],
            current_field=UniformCurrentField(u_ms=-0.25, v_ms=0.0, name="test"),
            river_table=RiverTable.from_csv(river_csv),
            vessel_detections=[
                VesselDetection(id="s1", lon=80.01, lat=11.99, detected_at=BASE_TIME)
            ],
            protected_areas=areas,
            rationale_writer=RationaleWriter(enabled=False),
            ensemble_size=8,
        )
    )
    return export_run(
        run,
        run_id="test-run",
        region=REGION,
        generated_on="laptop",
        inputs_are_synthetic=True,
        protected_areas=areas,
        dataset_sources={"all": "synthetic"},
        git_commit="abc1234",
    )


def test_artefact_carries_the_whole_reasoning_trail(artefact):
    assert artefact.detections
    assert artefact.verifications
    assert artefact.forward and artefact.backward
    assert artefact.attributions
    assert artefact.correlations
    assert artefact.protected_areas


def test_rejections_travel_with_the_artefact(artefact):
    """PRD §8 — the app must be able to show what was thrown away, and why."""
    assert artefact.rejected
    for rejection in artefact.rejected:
        assert rejection.rejection_reasons


def test_artefact_does_not_carry_a_plan(artefact):
    """The plan depends on operator input, so it is recomputed live (PRD §9.1)."""
    assert not hasattr(artefact, "plan")
    assert "plan" not in artefact.model_dump()


def test_provenance_records_how_the_run_was_made(artefact):
    provenance = artefact.provenance
    assert provenance.inputs_are_synthetic is True
    assert provenance.generated_on == "laptop"
    assert provenance.git_commit == "abc1234"
    assert provenance.tile_count == 1
    assert provenance.drift_ensemble_size == 8
    # Thresholds travel with the run so a plan can be traced to its settings.
    assert provenance.verification_thresholds["kelp_ndvi_min"] > 0
    assert provenance.fdi_threshold > 0


def test_round_trip_through_disk_is_lossless(artefact, tmp_path):
    path = write_artefact(artefact, tmp_path)
    assert path.name == "test-run.run.json"
    reloaded = load_artefact(path)
    assert reloaded.model_dump() == artefact.model_dump()


def test_a_future_schema_version_is_refused_rather_than_misread(artefact, tmp_path):
    path = write_artefact(artefact, tmp_path)
    raw = json.loads(path.read_text())
    raw["schema_version"] = "99.0"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="schema 99.0"):
        load_artefact(path)


def test_a_patch_version_bump_is_still_readable(artefact, tmp_path):
    path = write_artefact(artefact, tmp_path)
    raw = json.loads(path.read_text())
    raw["schema_version"] = f"{SCHEMA_VERSION.split('.')[0]}.99"
    path.write_text(json.dumps(raw))
    assert load_artefact(path).run_id == "test-run"


def test_summary_counts_what_the_run_picker_shows(artefact):
    summary = artefact.summary()
    assert summary["run_id"] == "test-run"
    assert summary["inputs_are_synthetic"] is True
    assert summary["detections"] == len(artefact.detections)
    assert summary["verified"] + summary["rejected"] == len(artefact.verifications)
    assert summary["has_mpa_data"] is True


def test_summary_carries_region_context_without_the_full_artefact(artefact):
    summary = artefact.summary()
    assert summary["degradation_notes"] == list(artefact.degradations)
    assert sum(d["candidates"] for d in summary["candidate_dates"]) == len(artefact.detections)
    assert [d["date"] for d in summary["candidate_dates"]] == sorted(
        {d.acquired_at.date().isoformat() for d in artefact.detections})
    disqualified = sum(c.disqualified for v in artefact.rejected for c in v.checks)
    assert sum(summary["failed_checks"].values()) == disqualified
    counts = list(summary["failed_checks"].values())
    assert counts == sorted(counts, reverse=True)
    # Synthetic fixtures carry no holdout note, so the flag must stay False.
    assert summary["geographic_holdout"] is False


def test_holdout_flag_requires_an_affirmative_note(artefact):
    negative = artefact.model_copy(deep=True)
    negative.provenance.notes = ["GEOGRAPHIC HOLDOUT NOT ESTABLISHED. withheld no tile"]
    assert negative.summary()["geographic_holdout"] is False
    positive = artefact.model_copy(deep=True)
    positive.provenance.notes = ["GEOGRAPHIC HOLDOUT. withheld every tile"]
    assert positive.summary()["geographic_holdout"] is True


def test_discover_finds_artefacts_and_ignores_other_files(artefact, tmp_path):
    write_artefact(artefact, tmp_path)
    (tmp_path / "notes.txt").write_text("not an artefact")
    (tmp_path / "approvals.json").write_text("[]")
    found = discover_artefacts(tmp_path)
    assert [p.name for p in found] == ["test-run.run.json"]


def test_discover_on_a_missing_directory_is_empty(tmp_path):
    assert discover_artefacts(tmp_path / "nope") == []


def test_artefact_stays_small_enough_to_serve(artefact, tmp_path):
    """PRD §9.1 sizes artefacts for a free-tier connection, not a CDN."""
    path = write_artefact(artefact, tmp_path)
    assert path.stat().st_size < 2_000_000


def test_no_imagery_is_embedded(artefact, tmp_path):
    """Only derived detections travel — never band arrays."""
    raw = write_artefact(artefact, tmp_path).read_text()
    assert '"bands"' not in raw
    assert '"B08"' not in raw


def test_an_artefact_is_utf8_on_every_platform(artefact, tmp_path):
    """The workstation writes these; the Air and a Linux container read them.

    ``write_text`` defaults to the PLATFORM encoding — cp1252 on Windows, UTF-8
    elsewhere — and the demo region's name contains an em dash. So the first
    real Gulf of Honduras export was written as cp1252, round-tripped perfectly
    on the machine that produced it, and was undecodable anywhere else: the
    deployed console would have failed on its first real run.

    Asserting on the BYTES rather than on a read-back is the point. A read-back
    uses the same platform default that wrote the file, so it passes on the
    broken machine and proves nothing.
    """
    artefact.region.name = "Gulf of Honduras \u2014 Motagua outflow (Guatemala)"
    artefact.provenance.notes.append("Gulf of Gon\u00e2ve \u2014 \u00b13 km, 90\u00b0")

    raw = write_artefact(artefact, tmp_path).read_bytes()

    decoded = raw.decode("utf-8")  # raises UnicodeDecodeError if not UTF-8
    assert "\u2014" in decoded
    assert "Gon\u00e2ve" in decoded


def test_an_artefact_written_here_loads_back_with_its_accents_intact(artefact, tmp_path):
    """The other half: encoding is pinned on read as well as on write."""
    artefact.region.name = "Gulf of Gon\u00e2ve \u2014 Port-au-Prince (Haiti)"
    path = write_artefact(artefact, tmp_path)
    assert load_artefact(path).region.name == artefact.region.name
