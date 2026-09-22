import pytest

from ghostnet.sensitivity import compare_rankings, weight_variants


def test_relative_changes_normalise_and_preserve_zero():
    variants = weight_variants({"a": 0.75, "b": 0.25, "missing": 0})
    assert len(variants) == 18
    changed = variants["a:+50%"]
    assert changed["a"] / changed["b"] == pytest.approx(4.5)
    for weights in variants.values():
        assert sum(weights.values()) == pytest.approx(1)
        assert weights["missing"] == 0


@pytest.mark.parametrize("weights", [{}, {"a": 0}, {"a": -1}, {"a": float("nan")}])
def test_invalid_weights_rejected(weights):
    with pytest.raises(ValueError):
        weight_variants(weights)


def test_plan_membership_and_order_are_distinct():
    result = compare_rankings(["a", "b", "c", "d"], ["b", "a", "c", "d"], 3)
    assert result["dispatch_set_unchanged"]
    assert not result["dispatch_order_unchanged"]
    assert not result["top1_unchanged"]
    assert result["spearman_ordinal"] == pytest.approx(0.8)


def test_new_top_candidate_changes_dispatch():
    result = compare_rankings(["a", "b", "c", "d"], ["d", "b", "c", "a"], 3)
    assert result["top3_overlap_fraction"] == pytest.approx(2/3)
    assert not result["dispatch_set_unchanged"]


def test_empty_and_singleton_are_not_perfect_correlations():
    assert compare_rankings([], [], 3)["spearman_ordinal"] is None
    assert compare_rankings(["a"], ["a"], 3)["spearman_ordinal"] is None


def test_changed_universe_is_rejected():
    with pytest.raises(ValueError):
        compare_rankings(["a"], ["b"], 3)
