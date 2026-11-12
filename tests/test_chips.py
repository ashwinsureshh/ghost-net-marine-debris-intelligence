"""Satellite chips: the export helpers and the endpoint that serves them.

The chips themselves are cut from Planetary Computer on the workstation, so
these tests cover only what can be checked offline: the geometry and the shared
stretch of ``scripts/export_chips.py``, and that the API serves a chip that
exists, refuses ones that don't, and cannot be walked outside its folder.
"""

from __future__ import annotations

import importlib.util
import math

import numpy as np
import pytest

from ghostnet.config import REPO_ROOT

_spec = importlib.util.spec_from_file_location(
    "export_chips", REPO_ROOT / "scripts" / "export_chips.py"
)
chips = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chips)


# ----------------------------------------------------------- helpers ------


def test_chip_bbox_is_centred_and_the_right_size():
    lon, lat = -88.4681, 16.2225
    w, s, e, n = chips.chip_bbox(lon, lat, px=160, res_m=10)
    assert (w + e) / 2 == pytest.approx(lon)
    assert (s + n) / 2 == pytest.approx(lat)
    height_m = (n - s) * 111_320
    width_m = (e - w) * 111_320 * math.cos(math.radians(lat))
    assert height_m == pytest.approx(1600, rel=1e-6)
    assert width_m == pytest.approx(1600, rel=1e-6)


def test_stretch_is_fixed_not_per_chip():
    """The same reflectance must give the same brightness in every chip."""
    a = chips.to_rgb8(np.full((2, 2, 3), 0.05, dtype="float32"))
    b = chips.to_rgb8(np.array([[[0.05] * 3, [0.4] * 3]], dtype="float32"))
    assert a[0, 0, 0] == b[0, 0, 0]
    assert chips.to_rgb8(np.full((1, 1, 3), 1.0))[0, 0, 0] == 255   # clipped, not rescaled
    assert chips.to_rgb8(np.zeros((1, 1, 3)))[0, 0, 0] == 0


def test_centre_crop_crops_and_pads_to_exact_size():
    big = np.zeros((170, 165, 3), dtype=np.uint8)
    assert chips.centre_crop(big, 160).shape == (160, 160, 3)
    small = np.zeros((158, 159, 3), dtype=np.uint8)
    assert chips.centre_crop(small, 160).shape == (160, 160, 3)


def test_scene_id_comes_from_the_detections_own_evidence():
    class Ev:
        detail = (
            "acquired 2018-09-19 "
            "(sentinel-2-l2a/S2B_MSIL2A_20180919T160929_R140_T16PCC_20201009T025650)"
        )

    class Det:
        evidence = [Ev()]

    assert chips.scene_id(Det()) == "S2B_MSIL2A_20180919T160929_R140_T16PCC_20201009T025650"


# ----------------------------------------------------------- endpoint -----

pytest.importorskip("fastapi", reason="web deps are in requirements-web.txt")


@pytest.fixture
def served(artefact, tmp_path, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    from ghostnet.export import write_artefact
    from ghostnet.webapp import app as app_module
    from ghostnet.webapp.store import ArtefactStore

    write_artefact(artefact, tmp_path)
    monkeypatch.setattr(app_module, "store", ArtefactStore(tmp_path))
    client = TestClient(app_module.app)
    run_id = client.get("/api/runs").json()["runs"][0]["run_id"]
    det_id = artefact.detections[0].id
    chip_dir = tmp_path / "chips" / run_id
    chip_dir.mkdir(parents=True)
    from PIL import Image

    Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8)).save(chip_dir / f"{det_id}.jpg")
    return client, run_id, det_id, artefact


from tests.test_export import artefact  # noqa: E402,F401 — reused fixture


def test_serves_an_existing_chip_as_jpeg(served):
    client, run_id, det_id, _ = served
    r = client.get(f"/api/runs/{run_id}/chips/{det_id}.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content[:2] == b"\xff\xd8"


def test_a_detection_without_a_chip_is_404(served):
    client, run_id, _, run = served
    other = run.detections[1].id
    assert client.get(f"/api/runs/{run_id}/chips/{other}.jpg").status_code == 404


def test_unknown_detection_and_unknown_run_are_404(served):
    client, run_id, det_id, _ = served
    assert client.get(f"/api/runs/{run_id}/chips/not-a-detection.jpg").status_code == 404
    assert client.get(f"/api/runs/no_such_run/chips/{det_id}.jpg").status_code == 404


def test_cannot_walk_out_of_the_chip_folder(served):
    client, run_id, _, _ = served
    for bad in ("..%2F..%2Fsecret", "%2E%2E", ".hidden", "a%5Cb"):
        assert client.get(f"/api/runs/{run_id}/chips/{bad}.jpg").status_code == 404
