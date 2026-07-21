"""Auth + ownership + external token — uses TestClient when fastapi installed."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("jwt")
pytest.importorskip("bcrypt")

from fastapi.testclient import TestClient


def test_register_login_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("EXTERNAL_API_TOKEN", "")
    monkeypatch.setenv("JWT_SECRET", "test-secret-not-for-production-32chars")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    import importlib

    import src.rag_app.auth as auth_mod
    import src.rag_app.notebook_store as ns
    import src.rag_app.store as store_mod
    import src.rag_app.user_store as us

    monkeypatch.setattr(ns, "NOTEBOOKS_ROOT", tmp_path / "notebooks")
    monkeypatch.setattr(us, "USERS_PATH", tmp_path / "users.json")
    importlib.reload(store_mod)
    importlib.reload(auth_mod)

    # Avoid loading ML synthesizer at import if possible — server imports it
    pytest.importorskip("faiss")
    from src.rag_app.server import app

    with TestClient(app) as client:
        r1 = client.post("/api/auth/register", json={"email": "a@test.com", "password": "secret1"})
        assert r1.status_code == 200, r1.text
        token_a = r1.json()["access_token"]

        r2 = client.post("/api/auth/register", json={"email": "b@test.com", "password": "secret2"})
        assert r2.status_code == 200
        token_b = r2.json()["access_token"]

        ha = {"Authorization": f"Bearer {token_a}"}
        hb = {"Authorization": f"Bearer {token_b}"}

        ca = client.post("/api/notebooks", json={"name": "Alice NB"}, headers=ha)
        assert ca.status_code == 200
        nb_a = ca.json()["id"]

        listed_b = client.get("/api/notebooks", headers=hb)
        assert listed_b.status_code == 200
        assert all(n["id"] != nb_a for n in listed_b.json())

        forbidden = client.get(f"/api/notebooks/{nb_a}", headers=hb)
        assert forbidden.status_code == 403


def test_external_token_required(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setenv("EXTERNAL_API_TOKEN", "secret-external")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    import importlib

    import src.rag_app.notebook_store as ns
    import src.rag_app.store as store_mod

    monkeypatch.setattr(ns, "NOTEBOOKS_ROOT", tmp_path / "notebooks")
    importlib.reload(store_mod)

    pytest.importorskip("faiss")
    from src.rag_app.server import app

    with TestClient(app) as client:
        bad = client.post(
            "/api/external/projects",
            json={"project_id": "user_abc123456789", "name": "Long id ok"},
        )
        assert bad.status_code == 401

        ok = client.post(
            "/api/external/projects",
            json={"project_id": "user_abc123456789", "name": "Long id ok"},
            headers={"Authorization": "Bearer secret-external"},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["project_id"] == "user_abc123456789"
