import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .core import RagAgent
from .database import (
    ChatRow,
    NotebookRow,
    NoteRow,
    SessionLocal,
    SourceRow,
)
from .parsers import parse_upload_file

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))


def _now() -> datetime:
    return datetime.now()


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _notebook_dir(notebook_id: str) -> Path:
    path = DATA_DIR / "indexes" / notebook_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_path(notebook_id: str) -> Path:
    return _notebook_dir(notebook_id) / "index.faiss"


def _metadata_path(notebook_id: str) -> Path:
    return _notebook_dir(notebook_id) / "index.json"


def _row_to_meta(row: NotebookRow, source_count: int = 0) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "created_at": row.created_at.isoformat(timespec="seconds"),
        "updated_at": row.updated_at.isoformat(timespec="seconds"),
        "source_count": source_count,
    }


def list_notebooks() -> List[dict]:
    with SessionLocal() as db:
        rows = db.query(NotebookRow).order_by(NotebookRow.updated_at.desc()).all()
        result = []
        for row in rows:
            count = db.query(SourceRow).filter(SourceRow.notebook_id == row.id).count()
            result.append(_row_to_meta(row, count))
        return result


def create_notebook(name: str = "Notebook mới", notebook_id: Optional[str] = None) -> dict:
    nb_id = notebook_id or str(uuid.uuid4())[:8]
    now = _now()
    row = NotebookRow(
        id=nb_id,
        name=name.strip() or "Notebook mới",
        created_at=now,
        updated_at=now,
    )
    with SessionLocal() as db:
        if db.get(NotebookRow, nb_id):
            return _row_to_meta(row, 0)
        db.add(row)
        db.commit()
        return _row_to_meta(row, 0)


def get_notebook(notebook_id: str) -> Optional[dict]:
    with SessionLocal() as db:
        row = db.get(NotebookRow, notebook_id)
        if not row:
            return None
        count = db.query(SourceRow).filter(SourceRow.notebook_id == notebook_id).count()
        return _row_to_meta(row, count)


def update_notebook_name(notebook_id: str, name: str) -> None:
    with SessionLocal() as db:
        row = db.get(NotebookRow, notebook_id)
        if not row:
            return
        row.name = name.strip() or row.name
        row.updated_at = _now()
        db.commit()


def delete_notebook(notebook_id: str) -> None:
    import shutil

    with SessionLocal() as db:
        row = db.get(NotebookRow, notebook_id)
        if row:
            db.delete(row)
            db.commit()
    idx_dir = DATA_DIR / "indexes" / notebook_id
    if idx_dir.exists():
        shutil.rmtree(idx_dir)


def load_notes(notebook_id: str) -> List[dict]:
    with SessionLocal() as db:
        rows = (
            db.query(NoteRow)
            .filter(NoteRow.notebook_id == notebook_id)
            .order_by(NoteRow.created_at.desc())
            .all()
        )
        return [
            {
                "id": r.id,
                "title": r.title,
                "content": r.content,
                "date": r.created_at.strftime("%d/%m/%Y"),
            }
            for r in rows
        ]


def save_notes(notebook_id: str, notes: List[dict]) -> None:
    with SessionLocal() as db:
        db.query(NoteRow).filter(NoteRow.notebook_id == notebook_id).delete()
        for note in notes:
            db.add(
                NoteRow(
                    id=note["id"],
                    notebook_id=notebook_id,
                    title=note["title"],
                    content=note["content"],
                    created_at=_now(),
                )
            )
        row = db.get(NotebookRow, notebook_id)
        if row:
            row.updated_at = _now()
        db.commit()


def load_chat_history(notebook_id: str) -> List[dict]:
    with SessionLocal() as db:
        rows = (
            db.query(ChatRow)
            .filter(ChatRow.notebook_id == notebook_id)
            .order_by(ChatRow.created_at.asc())
            .all()
        )
        return [
            {
                "query": r.query,
                "answer": r.answer,
                "sources": json.loads(r.sources_json or "[]"),
            }
            for r in rows
        ]


def save_chat_history(notebook_id: str, history: List[dict]) -> None:
    with SessionLocal() as db:
        db.query(ChatRow).filter(ChatRow.notebook_id == notebook_id).delete()
        for item in history:
            sources = item.get("sources", [])
            if sources and isinstance(sources[0], dict):
                sources = [s.get("source", s) for s in sources]
            db.add(
                ChatRow(
                    id=str(uuid.uuid4()),
                    notebook_id=notebook_id,
                    query=item["query"],
                    answer=item["answer"],
                    sources_json=json.dumps(sources, ensure_ascii=False),
                    created_at=_now(),
                )
            )
        row = db.get(NotebookRow, notebook_id)
        if row:
            row.updated_at = _now()
        db.commit()


def append_chat_message(notebook_id: str, query: str, answer: str, sources: List[str]) -> None:
    with SessionLocal() as db:
        db.add(
            ChatRow(
                id=str(uuid.uuid4()),
                notebook_id=notebook_id,
                query=query,
                answer=answer,
                sources_json=json.dumps(sources, ensure_ascii=False),
                created_at=_now(),
            )
        )
        row = db.get(NotebookRow, notebook_id)
        if row:
            row.updated_at = _now()
        db.commit()


def list_source_files(notebook_id: str) -> List[str]:
    with SessionLocal() as db:
        rows = (
            db.query(SourceRow.filename)
            .filter(SourceRow.notebook_id == notebook_id)
            .order_by(SourceRow.filename)
            .all()
        )
        return [r[0] for r in rows]


def save_upload_bytes(notebook_id: str, filename: str, data: bytes) -> Optional[str]:
    class _Upload:
        pass

    upload = _Upload()
    upload.name = filename
    upload.getvalue = lambda: data
    return save_uploaded_file(notebook_id, upload)


def save_uploaded_file(notebook_id: str, uploaded) -> Optional[str]:
    text = parse_upload_file(uploaded)
    if not text.strip():
        return None
    with SessionLocal() as db:
        existing = (
            db.query(SourceRow)
            .filter(SourceRow.notebook_id == notebook_id, SourceRow.filename == uploaded.name)
            .first()
        )
        if existing:
            existing.raw_bytes = uploaded.getvalue()
            existing.parsed_text = text
        else:
            db.add(
                SourceRow(
                    id=str(uuid.uuid4()),
                    notebook_id=notebook_id,
                    filename=uploaded.name,
                    raw_bytes=uploaded.getvalue(),
                    parsed_text=text,
                )
            )
        row = db.get(NotebookRow, notebook_id)
        if row:
            row.updated_at = _now()
        db.commit()
    return uploaded.name


def remove_source(notebook_id: str, filename: str) -> None:
    with SessionLocal() as db:
        db.query(SourceRow).filter(
            SourceRow.notebook_id == notebook_id,
            SourceRow.filename == filename,
        ).delete()
        row = db.get(NotebookRow, notebook_id)
        if row:
            row.updated_at = _now()
        db.commit()


def collect_documents(notebook_id: str) -> List[Tuple[str, str]]:
    docs: List[Tuple[str, str]] = []
    with SessionLocal() as db:
        sources = db.query(SourceRow).filter(SourceRow.notebook_id == notebook_id).all()
        for src in sources:
            if src.parsed_text.strip():
                docs.append((src.filename, src.parsed_text))
    for note in load_notes(notebook_id):
        docs.append((f"[Ghi chú] {note['title']}", note["content"]))
    return docs


def persist_index(notebook_id: str, agent: RagAgent) -> None:
    """Save an already-updated agent's index/metadata (used after incremental add/remove)."""
    index_path = _index_path(notebook_id)
    meta_path = _metadata_path(notebook_id)
    if not agent.chunks:
        index_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
    else:
        agent.save_index(str(index_path))
        agent.save_metadata(str(meta_path))
    with SessionLocal() as db:
        row = db.get(NotebookRow, notebook_id)
        if row:
            row.updated_at = _now()
            db.commit()


def build_and_save_index(notebook_id: str, agent: RagAgent) -> bool:
    docs = collect_documents(notebook_id)
    if not docs:
        agent.chunks = []
        agent.index = None
        agent.embeddings = None
        agent.bm25 = None
        return False
    agent.add_documents(docs)
    agent.save_index(str(_index_path(notebook_id)))
    agent.save_metadata(str(_metadata_path(notebook_id)))
    with SessionLocal() as db:
        row = db.get(NotebookRow, notebook_id)
        if row:
            row.updated_at = _now()
            db.commit()
    return True


def load_index(notebook_id: str, agent: RagAgent) -> bool:
    index_path = _index_path(notebook_id)
    meta_path = _metadata_path(notebook_id)
    if not index_path.exists() or not meta_path.exists():
        return build_and_save_index(notebook_id, agent)
    try:
        agent.load_index(str(index_path))
        agent.load_metadata(str(meta_path))
        return len(agent.chunks) > 0 and agent.bm25 is not None
    except Exception:
        return build_and_save_index(notebook_id, agent)
        return build_and_save_index(notebook_id, agent)
