"""The report and viva materials quote only what a committed artefact backs.

`docs/viva-pack.md` exists to enforce one rule — no number reaches the report
that the person quoting it cannot derive and defend. That rule is worth nothing
if the pack itself drifts from the artefacts, so the headline figures are
asserted here against `eval/*.json` rather than trusted.

The negative assertions matter as much as the positive ones. Several claims are
*forbidden* (drift validation, anything from the synthetic demo, end-to-end
latency), and a document that quietly acquires one of them later is exactly the
failure this guards.

Committed artefacts only — no network, no credentials, no downloaded data.
"""

from __future__ import annotations

import json

import pytest

from ghostnet.config import REPO_ROOT

DOCS = REPO_ROOT / "docs"
VIVA = DOCS / "viva-pack.md"
OUTLINE = DOCS / "report-outline.md"


def _load(name: str) -> dict:
    return json.loads((REPO_ROOT / "eval" / name).read_text())


@pytest.fixture(scope="module")
def viva() -> str:
    if not VIVA.exists():  # pragma: no cover
        pytest.skip("viva pack not present")
    return VIVA.read_text()


# ------------------------------------------------------- the numbers ------


def test_the_headline_figures_match_the_artefacts(viva):
    """Every number the pack leads with, checked against its source."""
    fdi = _load("detector_fdi_test.json")
    cnn = _load("detector_cnn_test.json")
    fitted = _load("marida_ablation.json")["held_out_fitted"]

    expected = {
        "FR-2.4 baseline precision": f"{fitted['metrics']['baseline_precision']:.3f}",
        "FR-2.4 verified precision": f"{fitted['metrics']['verified_precision']:.3f}",
        "test patches": str(fdi["patches"]),
        "candidates emitted": str(fdi["detections_total"]),
        "candidates scored": str(int(fdi["metrics"]["n_labelled"])),
        "annotated regions": str(fdi["debris_regions"]),
        "FDI regions hit": str(fdi["debris_regions_hit"]),
        "CNN regions hit": str(cnn["debris_regions_hit"]),
        "CNN candidates": str(cnn["detections_total"]),
        "FDI region recall": f"{fdi['region_recall']:.3f}",
        "CNN region recall": f"{cnn['region_recall']:.3f}",
    }
    missing = {k: v for k, v in expected.items() if v not in viva}
    assert not missing, f"the pack quotes figures that no longer match: {missing}"


def test_the_generalisation_arms_are_quoted_as_the_artefacts_record_them(viva):
    trained = _load("holdout_18QYF_leaky.json")["holdout"]
    unseen = _load("holdout_18QYF.json")["holdout"]

    assert f"{trained['debris_f1']:.4f}" in viva
    assert f"{unseen['debris_f1']:.4f}" in viva
    assert str(trained["patches"]) in viva
    assert f"{trained['debris_px_per_patch']:.2f}" in viva


def test_both_verification_gains_are_quoted_never_one_alone(viva):
    """+0.385 alone overstates the agent once the CNN is the detector."""
    fdi_gain = f"{_load('detector_fdi_test.json')['metrics']['precision_delta']:.3f}"
    cnn_gain = f"{_load('detector_cnn_test.json')['metrics']['precision_delta']:.3f}"
    assert fdi_gain in viva and cnn_gain in viva
    assert "never" in viva.lower() and "alone" in viva.lower()


def test_region_recall_is_never_quoted_without_the_within_tile_qualifier(viva):
    assert "within-tile" in viva
    assert "91%" in viva, "the share of test patches on trained-on tiles"


# ------------------------------------------------- the forbidden claims ----


@pytest.mark.parametrize(
    "prohibition",
    [
        "zero drifters",          # drift was not validated
        "run_pipeline_demo.py",   # synthetic, illustrative, not results
        "latency",                # not measured
        "detector_v1.pt",         # the shipped checkpoint, not the holdout one
    ],
)
def test_the_do_not_claim_list_names_each_prohibition(viva, prohibition):
    section = viva.split("## 4. What must not be claimed")[1].split("## 5.")[0]
    assert prohibition.lower() in section.lower(), (
        f"the do-not-claim list no longer mentions {prohibition!r}"
    )


def test_the_pack_never_claims_drift_was_validated(viva):
    """The single most tempting overstatement in the project."""
    lowered = viva.lower()
    for phrase in (
        "drift model validated",
        "validated the drift",
        "drift validation against",
        "validated against the drifter",
    ):
        assert phrase not in lowered, f"the pack claims {phrase!r}"
    assert "**no.**" in lowered or "not validated" in lowered


def test_fr_2_2_is_framed_as_a_dependency_not_a_contribution(viva):
    assert "dependency" in viva.lower()
    section = viva.split("FR-2.2")[1]
    assert "contributes **nothing**" in section or "contributes nothing" in section


# ------------------------------------------------------- the materials ----


def test_the_pack_admits_what_it_could_not_verify(viva):
    """Gaps found while assembling it are recorded, not quietly carried."""
    gaps = viva.split("## 6.")[1]
    assert "prose-only" in gaps.lower()
    assert "train" in gaps.lower(), "the fdi_sweep split trap"


def test_the_report_outline_marks_what_still_needs_a_person():
    assert OUTLINE.exists()
    text = OUTLINE.read_text()
    assert "**[W]**" in text and "**[E]**" in text and "**[B]**" in text
    assert "Related work" in text
    assert "does not draft" in text, (
        "the outline has to say which sections it deliberately leaves to a person"
    )
