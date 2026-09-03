"""PRD §12: every number the console serves traces to a committed artefact.

This is the repeatable version of a check that was first done by hand while
writing `docs/ablation-study.md`, and which found two real defects — a
mis-transcribed CNN candidate table, and three FR-2.2 arms quoted with no
committed artefact behind them. Doing it by hand is how those were caught;
doing it never again is how the next one ships.

The tests below assert both directions, because either alone leaves a hole:

* every *declared* field still agrees with its artefact (`reconcile`), and
* no *undeclared* number reached the wire (`undeclared_numbers`), which is how
  an unbacked figure would otherwise arrive.

Plus the check that matters most for a check: that it actually fails. A
reconciliation that cannot be made to fail proves nothing, so several tests
deliberately break something and assert the failure names the field, both
values and the source file.

Synthetic fixtures and committed `eval/*.json` only — no network, no
credentials, no downloaded data.
"""

from __future__ import annotations

import copy
import json

import pytest

from ghostnet.benchmark import cached_benchmark, load_generalisation
from ghostnet.provenance import (
    ARTEFACTS,
    CLAIMS,
    PUBLISHED,
    committed_artefacts,
    declared_fields,
    missing_artefacts,
    numeric_leaves,
    published_drift,
    reconcile,
    unaccounted_artefacts,
    undeclared_numbers,
)


@pytest.fixture
def payload():
    return cached_benchmark().model_dump()


# --------------------------------------------------- the check passes -----


def test_every_served_number_reconciles_with_its_artefact(payload):
    mismatches = reconcile(payload)
    assert mismatches == [], "\n".join(str(m) for m in mismatches)


def test_no_served_number_reached_the_wire_without_a_declaration(payload):
    undeclared = undeclared_numbers(payload)
    assert undeclared == [], (
        "these numbers are served but nothing says where they came from: "
        f"{undeclared}. Add a Claim in ghostnet.provenance naming the artefact "
        "and pointer, or stop serving them."
    )


def test_every_committed_artefact_is_accounted_for():
    stray = unaccounted_artefacts()
    assert stray == [], (
        f"eval artefacts nothing accounts for: {stray}. Register each in "
        "provenance.ARTEFACTS as surfaced, or as checked-not-surfaced with the "
        "reason it is not on screen."
    )


def test_every_registered_artefact_is_actually_on_disk():
    assert missing_artefacts() == []


def test_the_registry_covers_the_whole_eval_directory():
    assert {a.path for a in ARTEFACTS} == set(committed_artefacts())


def test_unsurfaced_artefacts_have_to_justify_themselves():
    for artefact in ARTEFACTS:
        if not artefact.surfaced:
            assert len(artefact.reason) > 40, (
                f"{artefact.path} is not surfaced but gives no real reason; "
                "an artefact nothing renders still has to say why."
            )


# ----------------------------------------------- the check actually bites --


def test_a_number_that_drifts_from_its_artefact_is_caught(payload):
    """The defect this whole module exists to prevent."""
    broken = copy.deepcopy(payload)
    broken["detectors"][1]["region_recall"] = 0.9999

    mismatches = reconcile(broken)

    assert mismatches, "a fabricated region recall reconciled — the check is inert"
    hit = [m for m in mismatches if m.field == "detectors[1].region_recall"]
    assert len(hit) == 1
    message = str(hit[0])
    assert "0.9999" in message, "the failure must name the value served"
    assert "0.7034" in message, "the failure must name the value recorded"
    assert "eval/detector_cnn_test.json" in message, "the failure must name the source file"


def test_a_derived_field_that_stops_matching_its_inputs_is_caught(payload):
    broken = copy.deepcopy(payload)
    broken["detectors"][0]["verification"]["precision_gain"] = 0.5

    mismatches = reconcile(broken)
    fields = [m.field for m in mismatches]
    assert "detectors[0].verification.precision_gain" in fields


def test_a_field_that_disappears_from_the_payload_is_caught(payload):
    broken = copy.deepcopy(payload)
    del broken["multi_temporal"]["true_debris_lost"]

    mismatches = reconcile(broken)
    hit = [m for m in mismatches if m.field == "multi_temporal.true_debris_lost"]
    assert hit and "serves no such field" in str(hit[0])


def test_an_artefact_that_stops_backing_its_claim_is_caught(payload, monkeypatch):
    """Drift on the *artefact* side, not the payload side."""
    import ghostnet.provenance as provenance

    real = provenance._load

    def doctored(source: str):
        raw = copy.deepcopy(real(source))
        if source == "eval/detector_fdi_test.json":
            raw["debris_regions_hit"] = 999
        return raw

    monkeypatch.setattr(provenance, "_load", doctored)
    mismatches = reconcile(payload)

    hit = [m for m in mismatches if m.field == "detectors[0].regions_hit"]
    assert hit, "an artefact rewritten under the console's feet went unnoticed"
    assert "999" in str(hit[0])


def test_an_unsurfaced_artefact_that_changes_is_caught(payload, monkeypatch):
    """The supporting FR-2.2 arms are not rendered, but they still cannot rot."""
    import ghostnet.provenance as provenance

    real = provenance._load

    def doctored(source: str):
        raw = copy.deepcopy(real(source))
        if source == "eval/multitemporal_sensitivity_010.json":
            raw["marginal_true_debris_lost"] = 7
        return raw

    monkeypatch.setattr(provenance, "_load", doctored)
    mismatches = reconcile(payload)

    hit = [m for m in mismatches if "multitemporal_sensitivity_010" in m.field]
    assert hit, (
        "the 0.10 m/s arm is the evidence that FR-2.2 is blocked on FR-3.1; "
        "it must not be able to change unnoticed just because nothing renders it"
    )


def test_the_artefacts_still_record_what_the_write_ups_published():
    drift = published_drift()
    assert drift == [], "\n".join(str(d) for d in drift)


def test_a_doctored_artefact_is_caught_even_though_the_console_reads_it(monkeypatch):
    """The gap `reconcile` alone cannot close.

    The console reads the same JSON, so editing an artefact moves both sides
    together and they still agree. That is correct — the artefact is the source
    of truth — but it leaves the published figures tamper-blind. The pins are
    what make an edited headline number fail.
    """
    import ghostnet.provenance as provenance

    real = provenance._load

    def doctored(source: str):
        raw = copy.deepcopy(real(source))
        if source == "eval/detector_cnn_test.json":
            raw["region_recall"] = 0.95
        return raw

    monkeypatch.setattr(provenance, "_load", doctored)
    drift = published_drift()

    assert drift, "a fabricated region recall passed as published"
    message = str(drift[0])
    assert "0.95" in message and "0.7034" in message
    assert "eval/results.md" in message, "the failure must name the authority"


def test_every_pin_points_at_something_that_exists():
    for source, pointer, _ in PUBLISHED:
        assert source.startswith("eval/")
        assert pointer


def test_an_unavailable_benchmark_is_a_mismatch_not_a_pass():
    """Zero claims checked must never look like zero disagreements."""
    mismatches = reconcile({"available": False, "unavailable_reason": "file missing"})
    assert len(mismatches) == 1
    assert "file missing" in str(mismatches[0])


# ------------------------------------------------------ the experiment -----


def test_the_generalisation_arms_are_paired_and_that_is_asserted(payload):
    """Same patches, same debris density — otherwise it measures difficulty."""
    gen = payload["generalisation"]
    assert gen["patches"] == 84
    assert gen["debris_px_per_patch"] == 13.24

    paired = [
        c
        for c in CLAIMS
        if c.field.startswith("generalisation.") and "paired" in (c.note or "")
    ]
    assert paired, "nothing asserts the two arms were scored on the same patches"


def test_an_unpaired_holdout_experiment_is_refused_not_reported(tmp_path):
    """A mismatched pair would read as a generalisation result. Refuse it."""
    trained = tmp_path / "trained.json"
    unseen = tmp_path / "unseen.json"
    block = {
        "patches": 84,
        "debris_precision": 0.9,
        "debris_recall": 0.9,
        "debris_f1": 0.9,
        "debris_px_per_patch": 13.24,
    }
    trained.write_text(json.dumps({"holdout_tiles": ["18QYF"], "holdout": block}))
    unseen.write_text(
        json.dumps({"holdout_tiles": ["18QYF"], "holdout": {**block, "patches": 61}})
    )

    assert load_generalisation(trained, unseen) is None


def test_the_generalisation_cost_is_mostly_recall(payload):
    """The finding, and the reason it is the tolerable failure direction."""
    gen = payload["generalisation"]
    assert gen["f1_cost"] == pytest.approx(-0.0723, abs=5e-5)
    assert gen["recall_cost"] < gen["precision_cost"] < 0
    assert abs(gen["recall_cost"]) > 4 * abs(gen["precision_cost"])


def test_the_wrong_sign_subtraction_is_warned_against(payload):
    """An evaluator computing the naive gap gets -0.194 and the wrong story."""
    caveats = " ".join(payload["generalisation_caveats"])
    assert "-0.194" in caveats
    assert "task difficulty" in caveats
    assert "upper" in caveats.lower(), "the 8.5%-less-data bound must survive"


def test_region_recall_never_travels_without_the_generalisation_qualifier(payload):
    """Region recall is within-tile; on its own it reads as generalisation."""
    assert payload["generalisation"] is not None, (
        "the strip serves region recall, which is a within-tile number. The "
        "unseen-region cost has to travel with it."
    )


# ------------------------------------------------------------- coverage ----


def test_the_declarations_cover_every_detector_arm(payload):
    declared = declared_fields()
    for i in range(len(payload["detectors"])):
        assert f"detectors[{i}].region_recall" in declared
        assert f"detectors[{i}].verification.verified_precision" in declared


def test_the_payload_is_not_trivially_small(payload):
    """Guards against the suite passing because almost nothing is served."""
    assert len(list(numeric_leaves(payload))) >= 60
    assert len(CLAIMS) >= 60
