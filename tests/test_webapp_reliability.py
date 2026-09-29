"""Backend reliability: approval-log safety, request IDs, errors, readiness.

The approval tests pin the property that matters most: an approval log the
server cannot read is never overwritten. Before this, a single corrupt byte
made the next approval replace the whole FR-6.4 audit trail with one record.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi", reason="web deps are in requirements-web.txt")

from ghostnet.webapp.approvals import (  # noqa: E402
    ApprovalStoreError,
    JsonFileBackend,
    SqliteBackend,
)
from ghostnet.webapp.store import ArtefactStore  # noqa: E402
from tests.test_export import artefact  # noqa: F401,E402
from tests.test_webapp import client  # noqa: F401,E402

APPROVE = {"reviewer": "A. Coordinator", "vessel_capacity": 3}


# ------------------------------------------------------------ approvals ---


def test_a_corrupt_log_is_never_overwritten(client, tmp_path):  # noqa: F811
    log = tmp_path / "approvals.json"
    log.write_text('[{"run_id": "test-run", "reviewer": "Earlier"', encoding="utf-8")
    before = log.read_bytes()

    response = client.post("/api/runs/test-run/approve", json=APPROVE)

    assert response.status_code == 503
    assert "left untouched" in response.json()["detail"]
    assert log.read_bytes() == before


def test_a_corrupt_log_is_reported_not_read_as_empty(client, tmp_path):  # noqa: F811
    (tmp_path / "approvals.json").write_text("not json", encoding="utf-8")
    response = client.get("/api/runs/test-run/approvals")
    assert response.status_code == 503


def test_one_malformed_record_does_not_hide_the_valid_ones(client, tmp_path):  # noqa: F811
    client.post("/api/runs/test-run/approve", json=APPROVE)
    log = tmp_path / "approvals.json"
    records = json.loads(log.read_text(encoding="utf-8"))
    records.append({"run_id": "test-run"})  # missing required fields
    log.write_text(json.dumps(records), encoding="utf-8")

    approvals = client.get("/api/runs/test-run/approvals").json()["approvals"]
    assert [a["reviewer"] for a in approvals] == ["A. Coordinator"]


def test_file_writes_are_atomic(tmp_path, monkeypatch):
    backend = JsonFileBackend(tmp_path / "approvals.json")
    backend.append({"n": 1})

    def crash(*_args, **_kwargs):
        raise OSError("disk vanished mid-write")

    monkeypatch.setattr("ghostnet.webapp.approvals.os.replace", crash)
    with pytest.raises(OSError):
        backend.append({"n": 2})

    assert backend.load() == [{"n": 1}]
    assert not list(tmp_path.glob("*.tmp"))


def test_approvals_survive_a_restart_on_both_backends(tmp_path):
    for backend_cls, name in ((JsonFileBackend, "a.json"), (SqliteBackend, "a.sqlite3")):
        backend_cls(tmp_path / name).append({"reviewer": "R"})
        assert backend_cls(tmp_path / name).load() == [{"reviewer": "R"}]


def test_sqlite_backend_serves_the_same_api(client, tmp_path, monkeypatch):  # noqa: F811
    from ghostnet.webapp import app as app_module

    monkeypatch.setenv("GHOSTNET_APPROVAL_BACKEND", "sqlite")
    monkeypatch.setattr(app_module, "store", ArtefactStore(tmp_path))
    assert client.post("/api/runs/test-run/approve", json=APPROVE).status_code == 201
    assert (tmp_path / "approvals.sqlite3").exists()
    assert len(client.get("/api/runs/test-run/approvals").json()["approvals"]) == 1


def test_an_unknown_backend_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOSTNET_APPROVAL_BACKEND", "postgres")
    with pytest.raises(ApprovalStoreError, match="Unknown"):
        _ = ArtefactStore(tmp_path).approval_backend


def test_an_unknown_backend_is_a_503_not_a_500(client, monkeypatch):  # noqa: F811
    monkeypatch.setenv("GHOSTNET_APPROVAL_BACKEND", "postgres")
    ready = client.get("/api/ready")
    assert ready.status_code == 503
    assert "Unknown" in ready.json()["checks"]["approvals"]["message"]
    assert client.post("/api/runs/test-run/approve", json=APPROVE).status_code == 503


def test_a_non_json_sqlite_row_is_refused_not_a_500(tmp_path):
    import sqlite3

    backend = SqliteBackend(tmp_path / "approvals.sqlite3")
    backend.append({"run_id": "test-run"})
    with sqlite3.connect(backend.path) as conn:
        conn.execute("INSERT INTO approvals (record) VALUES ('not json')")
    with pytest.raises(ApprovalStoreError, match="not JSON"):
        backend.load()
    assert backend.check()[0] is False


def test_non_list_log_is_refused(tmp_path):
    (tmp_path / "approvals.json").write_text('{"a": 1}', encoding="utf-8")
    with pytest.raises(ApprovalStoreError):
        JsonFileBackend(tmp_path / "approvals.json").load()


# ------------------------------------------------------- request hygiene ---


def test_every_response_carries_a_request_id_and_security_headers(client):  # noqa: F811
    response = client.get("/api/health")
    assert len(response.headers["x-request-id"]) >= 16
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_a_safe_supplied_request_id_is_echoed_and_an_unsafe_one_replaced(client):  # noqa: F811
    assert client.get("/api/health", headers={"X-Request-ID": "abc-123"}) \
        .headers["x-request-id"] == "abc-123"
    replaced = client.get("/api/health", headers={"X-Request-ID": "bad id\r\nx"})
    assert replaced.headers["x-request-id"] != "bad id\r\nx"


def test_errors_keep_detail_and_add_the_request_id(client):  # noqa: F811
    body = client.get("/api/runs/nope", headers={"X-Request-ID": "trace-1"}).json()
    assert "nope" in body["detail"]
    assert body["request_id"] == "trace-1"
    invalid = client.post("/api/runs/test-run/approve", json={}).json()
    assert isinstance(invalid["detail"], list) and invalid["request_id"]


def test_oversized_bodies_are_rejected_before_parsing(client):  # noqa: F811
    response = client.post(
        "/api/runs/test-run/approve",
        content=b"x" * 70_000,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413


# ------------------------------------------------------------ readiness ---


def test_ready_when_artefacts_and_approvals_are_usable(client):  # noqa: F811
    body = client.get("/api/ready").json()
    assert body["ready"] is True
    assert body["checks"]["approvals"]["backend"] == "file"


def test_not_ready_when_the_approval_log_is_corrupt(client, tmp_path):  # noqa: F811
    (tmp_path / "approvals.json").write_text("{{", encoding="utf-8")
    response = client.get("/api/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["approvals"]["ok"] is False


def test_not_ready_without_any_artefact(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from ghostnet.webapp import app as app_module

    monkeypatch.setattr(app_module, "store", ArtefactStore(tmp_path / "empty"))
    response = TestClient(app_module.app).get("/api/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["artefacts"]["readable"] == 0
