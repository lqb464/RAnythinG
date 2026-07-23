"""Migrate dữ liệu từ data/notebooks/ (file) sang PostgreSQL."""

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

if not os.getenv("DATABASE_URL"):
    print("Set DATABASE_URL trước:")
    print("  $env:DATABASE_URL='postgresql://ranything:ranything@localhost:5432/ranything'")
    sys.exit(1)

from src.rag_app.database import NotebookRow, SessionLocal, init_db
from src.rag_app import notebook_store as files
from src.rag_app import postgres_store as pg


def migrate() -> None:
    init_db()
    notebooks = files.list_notebooks()
    if not notebooks:
        print("Không có notebook file nào trong data/notebooks/.")
        return

    for meta in notebooks:
        nb_id = meta["id"]
        print(f"→ {nb_id} ({meta['name']})")

        with SessionLocal() as db:
            if db.get(NotebookRow, nb_id):
                print("  đã có trong Postgres, bỏ qua")
                continue

        created = datetime.fromisoformat(meta.get("created_at", datetime.now().isoformat()))
        updated = datetime.fromisoformat(meta.get("updated_at", datetime.now().isoformat()))
        with SessionLocal() as db:
            db.add(
                NotebookRow(
                    id=nb_id,
                    name=meta["name"],
                    created_at=created,
                    updated_at=updated,
                )
            )
            db.commit()

        for fname in files.list_source_files(nb_id):
            raw_path = files._sources_dir(nb_id) / fname
            if raw_path.exists():
                pg.save_upload_bytes(nb_id, fname, raw_path.read_bytes())
                print(f"  + {fname}")

        notes = files.load_notes(nb_id)
        if notes:
            pg.save_notes(nb_id, notes)

        history = files.load_chat_history(nb_id)
        if history:
            pg.save_chat_history(nb_id, history)

        dst = pg._notebook_dir(nb_id)
        for src_fn, dst_name in [
            (files._index_path(nb_id), "index.faiss"),
            (files._metadata_path(nb_id), "index.json"),
        ]:
            if src_fn.exists():
                shutil.copy2(src_fn, dst / dst_name)

        print("  xong")

    print("Migration hoàn tất.")


if __name__ == "__main__":
    migrate()
