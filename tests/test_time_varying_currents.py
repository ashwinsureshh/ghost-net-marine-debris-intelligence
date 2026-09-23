from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from ghostnet.agents.drift import (
    GriddedCurrentField,
    TimeVaryingCurrentField,
    _rk4_step,
    load_oscar_field,
)
from tests.test_oscar import oscar_dir, write_oscar  # noqa: F401

START = datetime(2014, 4, 1, tzinfo=UTC)


def field(values=(0.0, 2.0), days=2):
    return TimeVaryingCurrentField(
        np.array(["2014-04-01", f"2014-04-{1+days:02d}"], dtype="datetime64[ns]"),
        [GriddedCurrentField(np.array([0., 1.]), np.array([0., 1.]),
                             np.full((2, 2), value), np.zeros((2, 2))) for value in values],
    )


def test_time_interpolation_and_exact_endpoints():
    current = field()
    assert current.velocity(.5, .5, START) == (0., 0.)
    assert current.velocity(.5, .5, START + timedelta(days=1)) == (1., 0.)
    assert current.velocity(.5, .5, START + timedelta(days=2)) == (2., 0.)


def test_time_zone_represents_same_instant():
    moment = datetime.fromisoformat("2014-04-02T05:30:00+05:30")
    assert field().velocity(.5, .5, moment) == (1., 0.)


def test_no_time_extrapolation_or_season_bridging():
    with pytest.raises(ValueError, match="outside"):
        field().velocity(0, 0, START - timedelta(seconds=1))
    with pytest.raises(ValueError, match="temporal gap"):
        field(days=10).velocity(0, 0, START + timedelta(days=1))


def test_backward_rk4_samples_past_and_is_reversible_for_temporal_current():
    current = field()
    args = {"field": current, "lat": 0., "dt_s": 86400.,
            "velocity_scale": 1., "windage": (0., 0.)}
    lon, _ = _rk4_step(lon=0., when=START, sign=1, **args)
    recovered, _ = _rk4_step(lon=lon, when=START+timedelta(days=1), sign=-1, **args)
    assert lon > 0
    assert recovered == pytest.approx(0., abs=1e-10)


def test_loader_preserves_time_descending_latitude_and_longitude_wrap(oscar_dir):  # noqa: F811
    for day, value in ((1, 0.), (3, 2.)):
        write_oscar(oscar_dir, lats=[17., 16., 15.], lons=[270., 271., 272.],
                    times=[np.datetime64(f"2014-04-{day:02d}")], u_value=value,
                    filename=f"{day}.nc")
    current = load_oscar_field(START, START+timedelta(days=2), time_varying=True)
    baseline = load_oscar_field(START, START+timedelta(days=2))
    assert isinstance(current, TimeVaryingCurrentField)
    assert isinstance(baseline, GriddedCurrentField)
    assert current.velocity(-89, 16, START)[0] == 0
    assert current.velocity(-89, 16, START+timedelta(days=2))[0] == 2
    assert baseline.velocity(-89, 16, START)[0] == 1


def test_duplicate_current_times_rejected():
    current = field()
    with pytest.raises(ValueError, match="unique"):
        TimeVaryingCurrentField(np.array(["2014-04-01"] * 2), current.fields)


def test_coordinate_names_can_differ_from_dimension_names(oscar_dir):  # noqa: F811
    import xarray as xr

    path = write_oscar(oscar_dir, times=[np.datetime64("2014-04-01"),
                                        np.datetime64("2014-04-03")])
    with xr.open_dataset(path) as source:
        dataset = source.load().rename_dims({"lat": "latitude", "lon": "longitude"})
    dataset.to_netcdf(path, mode="w")
    current = load_oscar_field(START, START+timedelta(days=2),
                              bbox=(-90, 15, -88, 17), time_varying=True)
    assert current.velocity(-89, 16, START)[0] == pytest.approx(.1)
