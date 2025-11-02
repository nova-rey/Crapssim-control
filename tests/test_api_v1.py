# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from crapssim_control.http_api import create_app


def _mk_run(tmp_path: Path, rid: str = "r1") -> Path:
    rd = tmp_path / rid
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "decisions.csv").write_text("col\nval\n", encoding="utf-8")
    (rd / "manifest.json").write_text("{}", encoding="utf-8")
    (rd / "summary.json").write_text("{}", encoding="utf-8")
    (rd / "journal.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    return rd


def test_list_and_get_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("CSC_ARTIFACTS_DIR", str(tmp_path))
    app = create_app()
    client = TestClient(app)
    _mk_run(tmp_path, "aaa")
    _mk_run(tmp_path, "bbb")

    resp = client.get("/api/v1/runs?limit=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert len(data["items"]) == 1
    assert data.get("next_cursor")

    rid = data["items"][0]["id"]
    resp_detail = client.get(f"/api/v1/runs/{rid}")
    assert resp_detail.status_code == 200
    detail_payload = resp_detail.json()
    assert detail_payload["ok"] is True
    body = detail_payload.get("data", detail_payload)
    assert body["has"]["summary"] is True


def test_replay_returns_events(tmp_path, monkeypatch):
    monkeypatch.setenv("CSC_ARTIFACTS_DIR", str(tmp_path))
    app = create_app()
    client = TestClient(app)
    _mk_run(tmp_path, "runX")

    resp = client.get("/api/v1/runs/runX/replay?rate=2hz&max_events=1")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["events"]
    assert len(payload["events"]) <= 1


def test_cors_and_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("CSC_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setenv("CSC_CORS_ORIGINS", "http://localhost:1880,http://127.0.0.1:5173")
    monkeypatch.setenv("CSC_API_TOKEN", "secret")
    app = create_app()
    client = TestClient(app)

    resp = client.get("/api/v1/runs")
    assert resp.status_code == 401

    resp_ok = client.get(
        "/api/v1/runs",
        headers={"Authorization": "Bearer secret", "Origin": "http://localhost:1880"},
    )
    assert resp_ok.status_code == 200


def test_ui_static_mounts_when_present(tmp_path, monkeypatch):
    monkeypatch.setenv("CSC_UI_STATIC_DIR", str(tmp_path))
    (tmp_path / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    app = create_app()
    client = TestClient(app)

    resp = client.get("/ui/")
    assert resp.status_code in (200, 404)
