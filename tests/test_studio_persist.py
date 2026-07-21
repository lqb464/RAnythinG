"""Studio persist on filesystem store (no faiss required)."""

from __future__ import annotations


def test_studio_persist_filesystem(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    import src.rag_app.notebook_store as ns

    monkeypatch.setattr(ns, "NOTEBOOKS_ROOT", tmp_path / "notebooks")
    meta = ns.create_notebook("Studio NB", notebook_id="user_testhostid01")
    assert meta["id"] == "user_testhostid01"
    assert len(meta["id"]) > 8

    entry = ns.save_studio_output(
        "user_testhostid01",
        "summary",
        "Tóm tắt",
        ["a.pdf"],
        {"markdown": "hello"},
    )
    loaded = ns.load_studio_outputs("user_testhostid01")
    assert len(loaded) == 1
    assert loaded[0]["id"] == entry["id"]
    assert loaded[0]["result"]["markdown"] == "hello"
    assert ns.delete_studio_output("user_testhostid01", entry["id"]) is True
    assert ns.load_studio_outputs("user_testhostid01") == []
