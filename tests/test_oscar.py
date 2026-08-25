"""The OSCAR NetCDF reader (FR-3.1), against synthetic files.

No real OSCAR is downloaded — EARTHDATA_TOKEN does not exist yet on either
machine — so every test writes a small NetCDF into `tmp_path` shaped the way
the real product is shaped, including the parts that are shaped awkwardly.

Each of the four traps in `load_oscar_field`'s docstring has a test here, and
they matter more than the happy path because every one of them fails *quietly*:
a descending latitude axis, a 0-360 longitude grid, a NaN land mask and a
geostrophic-only file all produce a field that loads fine, interpolates fine,
and moves debris to the wrong place.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from ghostnet.agents.detection import detect
from ghostnet.agents.drift import GriddedCurrentField, load_oscar_field, run_trajectory
from ghostnet.config import DataUnavailableError

xr = pytest.importorskip("xarray", reason="netCDF stack lives in requirements-base")

START = datetime(2018, 2, 1, tzinfo=UTC)
END = datetime(2018, 10, 1, tzinfo=UTC)
# The demo region sits at negative longitude — the 0-360 trap's whole point.
REGION_LON, REGION_LAT = -88.2, 15.9


def write_oscar(
    tmp_path,
    *,
    lats=None,
    lons=None,
    u_value=0.10,
    v_value=0.02,
    times=None,
    geostrophic=False,
    land_mask=None,
    filename="oscar.nc",
):
    """Write a NetCDF shaped like OSCAR_L4_OC_NRT_V2.0."""
    lats = np.arange(10.0, 25.1, 1.0) if lats is None else np.asarray(lats, dtype=float)
    lons = np.arange(-95.0, -79.9, 1.0) if lons is None else np.asarray(lons, dtype=float)
    if times is None:
        times = [np.datetime64("2018-03-01"), np.datetime64("2018-06-01")]

    shape = (len(times), len(lats), len(lons))
    u = np.full(shape, u_value, dtype=float)
    v = np.full(shape, v_value, dtype=float)
    if land_mask is not None:
        u[:, land_mask] = np.nan
        v[:, land_mask] = np.nan

    u_name, v_name = ("ug", "vg") if geostrophic else ("u", "v")
    dataset = xr.Dataset(
        {
            u_name: (("time", "lat", "lon"), u),
            v_name: (("time", "lat", "lon"), v),
        },
        coords={"time": times, "lat": lats, "lon": lons},
    )
    path = tmp_path / filename
    dataset.to_netcdf(path)
    return path


@pytest.fixture
def detection(debris_tile):
    """A real detection off the shared synthetic tile, same as test_drift."""
    return detect(debris_tile)[0]


@pytest.fixture
def oscar_dir(tmp_path, monkeypatch):
    """Point `dataset_path` at a temp directory holding synthetic OSCAR.

    Patched on `ghostnet.agents.drift`, not on `ghostnet.config`: drift.py does
    `from ghostnet.config import dataset_path`, so it holds its own reference
    and patching the config module would leave the real loader in place.
    """
    directory = tmp_path / "oscar"
    directory.mkdir()
    import ghostnet.agents.drift as drift_module

    monkeypatch.setattr(drift_module, "dataset_path", lambda key, **kw: directory)
    return directory


# ------------------------------------------------------- happy path -------


def test_it_produces_the_contract_the_integrator_expects(oscar_dir):
    write_oscar(oscar_dir)
    field = load_oscar_field(START, END)

    assert isinstance(field, GriddedCurrentField)
    assert field.u.shape == (len(field.lats), len(field.lons))
    u, v = field.velocity(REGION_LON, REGION_LAT, START)
    assert u == pytest.approx(0.10, abs=1e-6)
    assert v == pytest.approx(0.02, abs=1e-6)


def test_the_field_drives_a_real_trajectory(oscar_dir, detection):
    """End to end: the reader's output has to actually integrate. A field that
    loads but produces NaN positions passes every shape assertion above —
    NaN velocities only show up once something advects through them."""
    write_oscar(oscar_dir)
    field = load_oscar_field(START, END)

    track = run_trajectory(detection, field, direction="forward", horizon_days=2.0)
    assert track.points, "trajectory produced no points"
    assert all(np.isfinite(p.lon) and np.isfinite(p.lat) for p in track.points)
    # 0.10 m/s eastward for 2 days is ~17 km, so longitude must have increased.
    assert track.points[-1].lon > track.points[0].lon


def test_the_name_records_what_was_averaged(oscar_dir):
    """The field is a time mean and the artefact should say so rather than
    implying an instantaneous current."""
    write_oscar(oscar_dir)
    name = load_oscar_field(START, END).name
    assert "mean" in name and "2018-02-01" in name and "2018-10-01" in name
    assert "step(s)" in name


# ------------------------------------------- trap 1: descending latitude ---


def test_descending_latitude_is_flipped_not_trusted(oscar_dir):
    """The headline trap. np.interp on a descending axis returns the last
    index rather than the interpolated one — no error, just a velocity from
    the wrong place. Verified by giving north and south opposite currents."""
    lats = np.arange(25.0, 9.9, -1.0)  # 25 -> 10, the way OSCAR ships it
    lons = np.arange(-95.0, -79.9, 1.0)
    u = np.zeros((1, len(lats), len(lons)))
    # Northern half flows east, southern half flows west.
    u[:, lats > 17.5, :] = 1.0
    u[:, lats <= 17.5, :] = -1.0

    dataset = xr.Dataset(
        {"u": (("time", "lat", "lon"), u), "v": (("time", "lat", "lon"), np.zeros_like(u))},
        coords={"time": [np.datetime64("2018-03-01")], "lat": lats, "lon": lons},
    )
    dataset.to_netcdf(oscar_dir / "oscar.nc")

    field = load_oscar_field(START, END)
    assert field.lats[0] < field.lats[-1], "latitude must come back ascending"

    north, _ = field.velocity(-88.0, 22.0, START)
    south, _ = field.velocity(-88.0, 12.0, START)
    assert north == pytest.approx(1.0, abs=1e-6), "north should flow east"
    assert south == pytest.approx(-1.0, abs=1e-6), "south should flow west"


# ------------------------------------------ trap 2: longitude convention ---


def test_a_0_360_grid_is_wrapped_so_the_region_exists_in_it(oscar_dir):
    """The Gulf of Honduras is at -88, which is simply absent from a 0-360
    grid: every lookup would clamp to an edge value from the wrong ocean."""
    lons_0_360 = np.arange(250.0, 285.1, 1.0)  # 250..285E == -110..-75
    write_oscar(oscar_dir, lons=lons_0_360, u_value=0.33)

    field = load_oscar_field(START, END)
    assert field.lons.min() < 0, "longitudes should be wrapped to -180..180"
    assert field.lons.min() <= REGION_LON <= field.lons.max()
    assert np.all(np.diff(field.lons) > 0), "longitudes must stay sorted after wrapping"

    u, _ = field.velocity(REGION_LON, REGION_LAT, START)
    assert u == pytest.approx(0.33, abs=1e-6)


# --------------------------------------------------- trap 3: land NaN ------


def test_land_nan_does_not_poison_the_interpolation(oscar_dir):
    """One NaN corner makes the whole bilinear result NaN, and the trajectory
    integrates to NaN from that step onward — silently, forever."""
    lats = np.arange(10.0, 25.1, 1.0)
    lons = np.arange(-95.0, -79.9, 1.0)
    land = np.zeros((len(lats), len(lons)), dtype=bool)
    land[0:2, 0:2] = True  # a corner of "land"
    write_oscar(oscar_dir, lats=lats, lons=lons, land_mask=land)

    field = load_oscar_field(START, END)
    assert np.isfinite(field.u).all() and np.isfinite(field.v).all()

    u, v = field.velocity(lons[0], lats[0], START)
    assert np.isfinite(u) and np.isfinite(v)


def test_the_land_fraction_is_reported(oscar_dir):
    lats = np.arange(10.0, 25.1, 1.0)
    lons = np.arange(-95.0, -79.9, 1.0)
    land = np.zeros((len(lats), len(lons)), dtype=bool)
    land[:, :] = True
    land[5:, 5:] = False
    write_oscar(oscar_dir, lats=lats, lons=lons, land_mask=land)

    assert "land" in load_oscar_field(START, END).name


# ------------------------------------------ trap 4: geostrophic only -------


def test_a_geostrophic_only_file_is_accepted_but_renamed(oscar_dir):
    """ug/vg omit the wind-driven Ekman component, which is much of what
    actually moves floating debris. Usable, but the field must not claim to be
    the total current."""
    write_oscar(oscar_dir, geostrophic=True, u_value=0.07)
    field = load_oscar_field(START, END)
    assert "geostrophic" in field.name
    assert field.velocity(REGION_LON, REGION_LAT, START)[0] == pytest.approx(0.07, abs=1e-6)


def test_total_current_is_preferred_when_both_are_present(oscar_dir):
    lats = np.arange(10.0, 25.1, 1.0)
    lons = np.arange(-95.0, -79.9, 1.0)
    shape = (1, len(lats), len(lons))
    dataset = xr.Dataset(
        {
            "u": (("time", "lat", "lon"), np.full(shape, 0.50)),
            "v": (("time", "lat", "lon"), np.zeros(shape)),
            "ug": (("time", "lat", "lon"), np.full(shape, 0.05)),
            "vg": (("time", "lat", "lon"), np.zeros(shape)),
        },
        coords={"time": [np.datetime64("2018-03-01")], "lat": lats, "lon": lons},
    )
    dataset.to_netcdf(oscar_dir / "oscar.nc")

    field = load_oscar_field(START, END)
    assert "geostrophic" not in field.name
    assert field.velocity(REGION_LON, REGION_LAT, START)[0] == pytest.approx(0.50, abs=1e-6)


# ----------------------------------------------------- time window --------


def test_only_the_requested_window_is_averaged(oscar_dir):
    """A window covering one step must not average in the other, or the
    seasonal signal the mean is already losing gets worse."""
    write_oscar(
        oscar_dir,
        times=[np.datetime64("2018-03-01"), np.datetime64("2019-03-01")],
        u_value=0.10,
    )
    field = load_oscar_field(START, END)
    assert "1 step(s)" in field.name


def test_a_window_with_no_coverage_says_what_the_files_do_cover(oscar_dir):
    write_oscar(oscar_dir, times=[np.datetime64("2021-03-01")])
    with pytest.raises(ValueError) as exc:
        load_oscar_field(START, END)
    message = str(exc.value)
    assert "2021-03-01" in message
    assert "2018-02-01" in message


# --------------------------------------------- absence stays honest -------


def test_a_missing_dataset_still_raises_the_documented_error(tmp_path, monkeypatch):
    """MACHINE-WORKFLOW rule 4: absent data fails with the fetch command, and
    never silently produces a field."""
    empty = tmp_path / "oscar"
    empty.mkdir()
    import ghostnet.agents.drift as drift_module

    monkeypatch.setattr(drift_module, "dataset_path", lambda key, **kw: empty)
    with pytest.raises(DataUnavailableError) as exc:
        load_oscar_field(START, END)
    assert "NetCDF" in str(exc.value)


def test_a_file_without_velocity_variables_names_what_it_found(oscar_dir):
    lats = np.arange(10.0, 15.1, 1.0)
    lons = np.arange(-95.0, -89.9, 1.0)
    xr.Dataset(
        {"sst": (("lat", "lon"), np.zeros((len(lats), len(lons))))},
        coords={"lat": lats, "lon": lons},
    ).to_netcdf(oscar_dir / "oscar.nc")

    with pytest.raises(ValueError) as exc:
        load_oscar_field(START, END)
    assert "sst" in str(exc.value)


def test_multiple_files_are_combined(oscar_dir):
    write_oscar(oscar_dir, times=[np.datetime64("2018-03-01")], filename="a.nc")
    write_oscar(oscar_dir, times=[np.datetime64("2018-04-01")], filename="b.nc")
    field = load_oscar_field(START, END)
    assert "2 file(s)" in field.name
    assert "2 step(s)" in field.name


def test_a_bbox_subset_keeps_padding_so_trajectories_do_not_clamp(oscar_dir):
    """`_interp` clamps outside the grid, so too tight a subset turns into a
    constant boundary current without any error."""
    write_oscar(oscar_dir)
    bbox = (-88.9, 15.7, -86.1, 16.5)
    field = load_oscar_field(START, END, bbox=bbox)
    assert field.lats.min() <= bbox[1] - 1.0
    assert field.lons.max() >= bbox[2] + 1.0
