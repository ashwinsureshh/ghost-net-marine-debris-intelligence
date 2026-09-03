"""PRD §12: the run artefact really does trace back to its evidence.

`docs/evidence-traceability.md` walks an evaluator from a dispatch line to the
imagery tile, current field and vessel record behind it. That walk-through is a
set of structural claims about the artefact, and claims rot — so they are
asserted here rather than left to be discovered broken during a viva.

The committed synthetic run is a fixture like any other: no network, no
credentials, no downloaded data.
"""

from __future__ import annotations

import json

import pytest

from ghostnet.config import REPO_ROOT

ARTEFACT = REPO_ROOT / "webapp_data" / "synthetic-coastal-demo.run.json"

#: The three the PRD names, plus the river table FR-4 needs.
REQUIRED_KINDS = {"sentinel2_tile", "current_field", "vessel_record", "river_table"}


@pytest.fixture(scope="module")
def run():
    if not ARTEFACT.exists():  # pragma: no cover
        pytest.skip(f"{ARTEFACT} is not present")
    return json.loads(ARTEFACT.read_text())


def _refs(node):
    """Every evidence ref anywhere under a node."""
    if isinstance(node, dict):
        if "kind" in node and "ref" in node:
            yield node
        for value in node.values():
            yield from _refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _refs(value)


def test_the_artefact_carries_every_evidence_kind_the_prd_names(run):
    kinds = {ref["kind"] for ref in _refs(run)}
    missing = REQUIRED_KINDS - kinds
    assert not missing, (
        f"the walk-through traces {sorted(REQUIRED_KINDS)}; the artefact carries "
        f"no {sorted(missing)}"
    )


def test_every_detection_names_the_tile_it_came_from(run):
    for detection in run["detections"]:
        kinds = {ref["kind"] for ref in _refs(detection)}
        assert "sentinel2_tile" in kinds, f"{detection['id']} traces to no imagery"
        assert detection["tile_id"], f"{detection['id']} has no tile_id"


def test_every_evidence_ref_says_what_it_is_and_gives_detail(run):
    for ref in _refs(run):
        assert ref["ref"], f"empty ref on a {ref['kind']} record"
        assert ref.get("detail"), (
            f"{ref['kind']} {ref['ref']} carries no detail — a bare identifier is "
            "not a trace"
        )


def test_a_verified_detection_traces_through_every_downstream_agent(run):
    """The chain the walk-through follows: imagery -> drift -> source -> vessels."""
    verified = [v["detection_id"] for v in run["verifications"] if v["verified"]]
    assert verified, "no verified detection to trace"

    traced = [
        did
        for did in verified
        if did in run["backward"] and did in run["attributions"] and did in run["correlations"]
    ]
    assert traced, "no verified detection reaches drift, attribution and vessels"

    did = traced[0]
    assert "current_field" in {r["kind"] for r in _refs(run["backward"][did])}
    assert "river_table" in {r["kind"] for r in _refs(run["attributions"][did])}
    assert "vessel_record" in {r["kind"] for r in _refs(run["correlations"][did])}


def test_the_drift_evidence_is_reproducible_not_merely_plausible(run):
    """An envelope without its seed cannot be re-derived, so it is not evidence."""
    track = next(iter(run["backward"].values()))
    assert track.get("seed") is not None
    assert track.get("ensemble_size")
    detail = " ".join(r["detail"] for r in _refs(track))
    assert "seed" in detail.lower()


def test_a_rejected_detection_keeps_its_evidence_and_its_reasons(run):
    """FR-2.3: rejected detections are retained with the reason, never dropped."""
    rejected = [v for v in run["verifications"] if not v["verified"]]
    assert rejected, "nothing was rejected, so the Rejected tab shows nothing"

    for verification in rejected:
        assert verification["checks"], f"{verification['detection_id']} lists no checks"
        disqualifying = [c for c in verification["checks"] if c["disqualified"]]
        assert disqualifying, "a rejected detection with no disqualifying check"
        for check in disqualifying:
            assert check.get("reason"), f"{check['name']} disqualified without a reason"


def test_the_provenance_answers_under_what_conditions(run):
    """Every field the walk-through reads off the provenance block."""
    provenance = run["provenance"]
    for field in (
        "git_commit",
        "tile_ids",
        "fdi_threshold",
        "verification_thresholds",
        "drift_seed",
        "drift_ensemble_size",
        "inputs_are_synthetic",
    ):
        assert field in provenance, f"provenance carries no {field}"


def test_the_synthetic_run_still_declares_itself_synthetic(run):
    """The console renders this on its face. It must stay true until a real run."""
    assert run["provenance"]["inputs_are_synthetic"] is True
    notes = " ".join(run["provenance"].get("notes", []))
    assert "synthetic" in notes.lower() or "generated" in notes.lower()


def test_the_walkthrough_document_is_present_and_names_the_check():
    doc = REPO_ROOT / "docs" / "evidence-traceability.md"
    assert doc.exists()
    text = doc.read_text()
    assert "python -m ghostnet.provenance" in text
    for kind in sorted(REQUIRED_KINDS):
        assert kind in text, f"the walk-through never mentions {kind}"
