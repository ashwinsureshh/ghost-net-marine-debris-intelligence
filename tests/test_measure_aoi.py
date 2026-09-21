"""Coverage estimates must include nodata and exclude unrelated scenes."""
from types import SimpleNamespace

import numpy as np

import measure_aoi


def test_usable_water_counts_uncovered_pixels(monkeypatch):
    monkeypatch.setattr(measure_aoi, "build_grid", lambda *a, **k: SimpleNamespace(pixels=4))
    monkeypatch.setattr(
        measure_aoi, "_read_asset",
        lambda *a, **k: np.array([[6, 0], [0, 0]], dtype=np.uint8),
    )
    result = measure_aoi.score((0, 0, 1, 1), [SimpleNamespace(bbox=[0, 0, 1, 1])],
                               resolution_m=200)
    assert result["water_pct"] == 100
    assert result["usable_water_pct"] == 25
    assert result["nodata_pct"] == 75


def test_nonintersecting_scene_is_not_read(monkeypatch):
    monkeypatch.setattr(measure_aoi, "build_grid", lambda *a, **k: SimpleNamespace(pixels=4))
    def unexpected(*args, **kwargs):
        raise AssertionError("unrelated asset read")
    monkeypatch.setattr(measure_aoi, "_read_asset", unexpected)
    result = measure_aoi.score((0, 0, 1, 1), [SimpleNamespace(bbox=[2, 2, 3, 3])],
                               resolution_m=200)
    assert result["scenes_used"] == 0
    assert result["usable_water_pct"] is None
