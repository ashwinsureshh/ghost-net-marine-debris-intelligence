"""Geographic holdout for the CNN detector — the tile-splitting logic.

MARIDA's published splits are by patch, so most test patches sit on tiles the
model trained on. ``--holdout-tile`` withholds a whole MGRS tile instead. These
tests pin the id parsing and the filtering; they need neither MARIDA nor torch,
because what can silently go wrong here is *which patches end up in which arm*,
not the arithmetic downstream of it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from eval_marida import tile_of  # noqa: E402
from train_cnn import filter_by_tile  # noqa: E402

# Real ids, copied from the MARIDA split files.
IDS = [
    "1-12-19_48MYU_0",
    "12-1-17_16PCC_3",
    "12-1-17_16PCC_11",
    "18-9-18_18QYF_0",
    "18-9-18_18QYF_7",
    "11-1-19_19QDA_4",
]


class TestTileOf:
    def test_it_reads_the_mgrs_tile_out_of_a_split_id(self):
        assert tile_of("1-12-19_48MYU_0") == "48MYU"
        assert tile_of("12-1-17_16PCC_11") == "16PCC"

    def test_the_patch_index_is_not_mistaken_for_the_tile(self):
        # '_0' and '_11' are patch indices; a rsplit-based parse would return
        # them and every holdout would silently select nothing.
        assert tile_of("18-9-18_18QYF_7") == "18QYF"

    def test_an_unparseable_id_raises_rather_than_returning_a_wrong_tile(self):
        # Returning a junk tile here would silently produce an empty holdout,
        # which reads as "the model generalises perfectly" — a wrong answer,
        # not an error.
        with pytest.raises(ValueError, match="unparseable"):
            tile_of("nonsense")


class TestFilterByTile:
    def test_exclude_drops_only_the_named_tile(self):
        kept = filter_by_tile(IDS, exclude=frozenset({"18QYF"}))
        assert [tile_of(i) for i in kept] == ["48MYU", "16PCC", "16PCC", "19QDA"]

    def test_keep_only_is_the_complement_of_exclude(self):
        held = filter_by_tile(IDS, keep_only=frozenset({"18QYF"}))
        assert held == ["18-9-18_18QYF_0", "18-9-18_18QYF_7"]

    def test_the_two_arms_partition_the_input_with_no_overlap_and_nothing_lost(self):
        # This is the property that makes the experiment honest: a patch is
        # either trained on or evaluated as unseen, never both.
        holdout = frozenset({"18QYF"})
        trained = filter_by_tile(IDS, exclude=holdout)
        held = filter_by_tile(IDS, keep_only=holdout)
        assert set(trained) & set(held) == set()
        assert set(trained) | set(held) == set(IDS)

    def test_order_is_preserved_so_a_limit_truncation_stays_deterministic(self):
        assert filter_by_tile(IDS, exclude=frozenset({"18QYF"}))[:2] == [
            "1-12-19_48MYU_0",
            "12-1-17_16PCC_3",
        ]

    def test_no_filter_is_the_identity(self):
        assert filter_by_tile(IDS) == IDS

    def test_excluding_several_tiles_at_once(self):
        kept = filter_by_tile(IDS, exclude=frozenset({"18QYF", "16PCC"}))
        assert [tile_of(i) for i in kept] == ["48MYU", "19QDA"]


class TestCheckpointExposure:
    """What an exported artefact says about the ground its detector had seen.

    Training a held-out checkpoint is only half the experiment: the other half
    is that a run exported with it says so, and that a run exported with an
    ordinary checkpoint says the opposite. The failure this guards against is
    silent and total — a within-tile run read as geographic generalisation,
    with nothing on the artefact to tell the two apart.

    The partial case is the one that actually bit: the first held-out
    checkpoint withheld 18QYF alone, while the Gulf of Gonâve spans three
    tiles, so it is NOT a clean held-out run for that region.
    """

    @staticmethod
    def _checkpoint(tmp_path, holdout=None):
        weights = tmp_path / "detector_test.pt"
        weights.write_bytes(b"")
        meta = {"run_id": "detector_test"}
        if holdout is not None:
            meta["holdout_tiles"] = holdout
        weights.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
        return weights

    @pytest.fixture
    def region(self, monkeypatch):
        import export_run

        monkeypatch.setattr(
            export_run, "get_region", lambda _id: {"mgrs_tiles": ["18QYF", "18QYG", "18QWF"]}
        )
        return export_run

    def test_a_checkpoint_that_withheld_nothing_is_named_a_within_tile_run(
        self, region, tmp_path
    ):
        note = region.checkpoint_exposure(self._checkpoint(tmp_path), "r")
        assert "GEOGRAPHIC HOLDOUT NOT ESTABLISHED" in note
        assert "WITHIN-TILE" in note

    def test_withholding_every_tile_of_the_region_is_a_holdout_run(self, region, tmp_path):
        weights = self._checkpoint(tmp_path, ["18QYF", "18QYG", "18QWF"])
        note = region.checkpoint_exposure(weights, "r")
        assert note.startswith("GEOGRAPHIC HOLDOUT")
        assert "geographic exclusion" in note
        assert "does not measure detection accuracy" in note

    def test_withholding_some_tiles_is_reported_as_partial_and_not_as_a_holdout(
        self, region, tmp_path
    ):
        note = region.checkpoint_exposure(self._checkpoint(tmp_path, ["18QYF"]), "r")
        assert note.startswith("PARTIAL GEOGRAPHIC HOLDOUT")
        assert "NOT a clean held-out region run" in note
        # The seen tiles have to be named, or the reader cannot judge the run.
        assert "18QYG" in note and "18QWF" in note

    def test_a_tile_the_region_does_not_contain_does_not_count_as_withheld(
        self, region, tmp_path
    ):
        # Withholding 16PCC says nothing about a region made of 18Q* tiles.
        note = region.checkpoint_exposure(self._checkpoint(tmp_path, ["16PCC"]), "r")
        assert "GEOGRAPHIC HOLDOUT NOT ESTABLISHED" in note

    def test_a_checkpoint_with_no_sidecar_refuses_to_claim_anything(self, region, tmp_path):
        weights = tmp_path / "orphan.pt"
        weights.write_bytes(b"")
        note = region.checkpoint_exposure(weights, "r")
        assert "PROVENANCE UNKNOWN" in note
        assert "within-tile" in note

    def test_a_region_with_no_declared_tiles_is_unknown_rather_than_clean(
        self, monkeypatch, tmp_path
    ):
        import export_run

        monkeypatch.setattr(export_run, "get_region", lambda _id: {})
        note = export_run.checkpoint_exposure(self._checkpoint(tmp_path, ["18QYF"]), "r")
        assert "PROVENANCE UNKNOWN" in note
