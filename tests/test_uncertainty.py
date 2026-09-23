import pytest

from ghostnet.uncertainty import fit_radius_multiplier, split_buoys


def test_buoy_split_is_disjoint_and_order_independent():
    ids = [str(i) for i in range(19)]
    calibration, held_out = split_buoys(ids)
    assert len(calibration) == 6
    assert len(held_out) == 13
    assert not set(calibration) & set(held_out)
    assert split_buoys(ids[::-1]) == (calibration, held_out)


def test_scale_fitted_on_calibration_does_not_guarantee_test_coverage():
    factor = fit_radius_multiplier([1., 2., 3.], [1., 1., 1.])
    assert factor == 3.
    held_out_error, held_out_radius = 10., 1.
    assert held_out_error > factor * held_out_radius


def test_scale_never_shrinks_and_undefined_radii_fail():
    assert fit_radius_multiplier([.1, .2], [1., 1.]) == 1.
    with pytest.raises(ValueError):
        fit_radius_multiplier([1.], [0.])
