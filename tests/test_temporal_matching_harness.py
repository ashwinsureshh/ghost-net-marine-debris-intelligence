"""Coverage conservatism and cached-input reproducibility for the experiment."""

import datetime as dt
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "temporal_harness", ROOT / "scripts/eval_temporal_matching.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tile(module):
    return module.Tile(
        "test", dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
        {band: np.ones((100, 100)) * .1 for band in ("B04", "B06", "B08", "B11")},
        module.GeoTransform(-.5, .5, .01, -.01),
        cloud_mask=np.zeros((100, 100), dtype=bool))


def test_coverage_requires_clear_valid_entire_search_area(harness):
    image = tile(harness)
    assert harness.fully_observed(image, 0, 0, 5)
    assert not harness.fully_observed(image, .49, 0, 5)
    image.cloud_mask[50, 50] = True
    assert not harness.fully_observed(image, 0, 0, 5)
    image.cloud_mask[:] = False
    image.bands["B04"][50, 50] = np.nan
    assert not harness.fully_observed(image, 0, 0, 5)
    image.bands["B04"][50, 50] = 0
    assert not harness.fully_observed(image, 0, 0, 5)
    image.cloud_mask = None
    assert not harness.fully_observed(image, 0, 0, 5)


def test_cached_tile_reuses_exact_input_without_network(harness, monkeypatch, tmp_path):
    original = tile(harness)
    calls = []

    def acquire(*args):
        calls.append(args)
        return original

    monkeypatch.setattr(harness.baseline, "tile_for_date", acquire)
    pair = {"bbox": [-.5, -.5, .5, .5], "tile": "test"}
    first, digest = harness.cached_tile(pair, dt.date(2020, 1, 1), None, tmp_path)
    second, second_digest = harness.cached_tile(pair, dt.date(2020, 1, 1), None, tmp_path)
    assert len(calls) == 1
    assert digest == second_digest
    assert first.acquired_at == second.acquired_at == original.acquired_at
    assert second.transform == original.transform
    np.testing.assert_array_equal(second.bands["B08"], original.bands["B08"])
    np.testing.assert_array_equal(second.cloud_mask, original.cloud_mask)


def test_cli_help_without_pythonpath():
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/eval_temporal_matching.py"), "--help"],
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "--json" in result.stdout
