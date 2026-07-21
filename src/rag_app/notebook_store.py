import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from .core import RagAgent

NOTEBOOKS_ROOT = Path("./data/notebooks")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _meta_path(notebook_id: str) -> Path:
    return NOTEBOOKS_ROOT / notebook_id / "meta.json"


def _notes_path(notebook_id: str) -> Path:
    return NOTEBOOKS_ROOT / notebook_id / "notes.json"


def _studio_path(notebook_id: str) -> Path:
    return NOTEBOOKS_ROOT / notebook_id / "studio_outputs.json"


def _chat_path(notebook_id: str) -> Path:
    return NOTEBOOKS_ROOT / notebook_id / "chat_history.json"


def _sources_dir(notebook_id: str) -> Path:
    return NOTEBOOKS_ROOT / notebook_id / "sources"


def _index_path(notebook_id: str) -> Path:
    return NOTEBOOKS_ROOT / notebook_id / "index.faiss"


def _metadata_path(notebook_id: str) -> Path:
    return NOTEBOOKS_ROOT / notebook_id / "index.json"


def list_notebooks(owner_id: Optional[str] = None) -> List[dict]:
    if not NOTEBOOKS_ROOT.exists():
        return []
    notebooks = []
    for folder in sorted(NOTEBOOKS_ROOT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not folder.is_dir():
            continue
        meta_file = folder / "meta.json"
        if not meta_file.exists():
            continue
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            meta.setdefault("id", folder.name)
            if owner_id is not None and meta.get("owner_id") != owner_id:
                continue
            meta["source_count"] = len(list_source_files(meta["id"]))
            notebooks.append(meta)
        except Exception:
            continue
    return notebooks


def create_notebook(
    name: str = "Notebook mới",
    notebook_id: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> dict:
    notebook_id = notebook_id or str(uuid.uuid4())[:8]
    folder = NOTEBOOKS_ROOT / notebook_id
    folder.mkdir(parents=True, exist_ok=True)
    _sources_dir(notebook_id).mkdir(exist_ok=True)

    meta = {
        "id": notebook_id,
        "name": name.strip() or "Notebook mới",
        "owner_id": owner_id,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    with open(_meta_path(notebook_id), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    _save_json(_notes_path(notebook_id), [])
    _save_json(_chat_path(notebook_id), [])
    return meta


def get_notebook(notebook_id: str) -> Optional[dict]:
    path = _meta_path(notebook_id)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    meta.setdefault("id", notebook_id)
    return meta


def update_notebook_name(notebook_id: str, name: str) -> None:
    meta = get_notebook(notebook_id)
    if not meta:
        return
    meta["name"] = name.strip() or meta["name"]
    meta["updated_at"] = _now_iso()
    with open(_meta_path(notebook_id), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def delete_notebook(notebook_id: str) -> None:
    folder = NOTEBOOKS_ROOT / notebook_id
    if folder.exists():
        shutil.rmtree(folder)


def load_notes(notebook_id: str) -> List[dict]:
    return _load_json(_notes_path(notebook_id), [])


def save_notes(notebook_id: str, notes: List[dict]) -> None:
    _save_json(_notes_path(notebook_id), notes)
    _touch(notebook_id)


def load_chat_history(notebook_id: str) -> List[dict]:
    return _load_json(_chat_path(notebook_id), [])


def save_chat_history(notebook_id: str, history: List[dict]) -> None:
    _save_json(_chat_path(notebook_id), history)
    _touch(notebook_id)


def _parsed_dir(notebook_id: str) -> Path:
    return _sources_dir(notebook_id) / "_parsed"


def list_source_files(notebook_id: str) -> List[str]:
    src_dir = _sources_dir(notebook_id)
    if not src_dir.exists():
        return []
    return sorted(
        p.name
        for p in src_dir.iterdir()
        if p.is_file() and not p.name.endswith(".parsed.txt")
    )


def read_source_text(notebook_id: str, filename: str) -> str:
    path = _sources_dir(notebook_id) / filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def save_upload_bytes(notebook_id: str, filename: str, data: bytes) -> Optional[str]:
    class _Upload:
        pass

    upload = _Upload()
    upload.name = filename

    def getvalue() -> bytes:
        return data

    upload.getvalue = getvalue
    return save_uploaded_file(notebook_id, upload)


def save_uploaded_file(notebook_id: str, uploaded) -> Optional[str]:
    from .parsers import parse_upload_file

    text = parse_upload_file(uploaded)
    if not text.strip():
        return None
    src_dir = _sources_dir(notebook_id)
    src_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir = _parsed_dir(notebook_id)
    parsed_dir.mkdir(parents=True, exist_ok=True)
    dest = src_dir / uploaded.name
    dest.write_bytes(uploaded.getvalue())
    parsed_path = parsed_dir / f"{uploaded.name}.txt"
    parsed_path.write_text(text, encoding="utf-8")
    _touch(notebook_id)
    return uploaded.name


def remove_source(notebook_id: str, filename: str) -> None:
    src_dir = _sources_dir(notebook_id)
    parsed_dir = _parsed_dir(notebook_id)
    for path in [
        src_dir / filename,
        src_dir / f"{filename}.parsed.txt",
        parsed_dir / f"{filename}.txt",
    ]:
        if path.exists():
            path.unlink()
    _touch(notebook_id)


def _read_parsed_text(notebook_id: str, original_name: str) -> str:
    parsed_dir = _parsed_dir(notebook_id)
    new_path = parsed_dir / f"{original_name}.txt"
    if new_path.exists():
        return new_path.read_text(encoding="utf-8", errors="ignore")
    legacy = _sources_dir(notebook_id) / f"{original_name}.parsed.txt"
    if legacy.exists():
        return legacy.read_text(encoding="utf-8", errors="ignore")
    return ""


def collect_documents(notebook_id: str) -> List[Tuple[str, str]]:
    docs: List[Tuple[str, str]] = []
    for name in list_source_files(notebook_id):
        text = _read_parsed_text(notebook_id, name)
        if text.strip():
            docs.append((name, text))
    for note in load_notes(notebook_id):
        docs.append((f"[Ghi chú] {note['title']}", note["content"]))
    return docs


def persist_index(notebook_id: str, agent: RagAgent) -> None:
    """Save an already-updated agent's index/metadata (used after incremental add/remove)."""
    index_path = _index_path(notebook_id)
    meta_path = _metadata_path(notebook_id)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if not agent.chunks:
        index_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        _touch(notebook_id)
        return
    agent.save_index(str(index_path))
    agent.save_metadata(str(meta_path))
    _touch(notebook_id)


def build_and_save_index(notebook_id: str, agent: RagAgent) -> bool:
    docs = collect_documents(notebook_id)
    if not docs:
        agent.chunks = []
        agent.index = None
        agent.embeddings = None
        agent.bm25 = None
        return False

    agent.add_documents(docs)
    index_path = _index_path(notebook_id)
    meta_path = _metadata_path(notebook_id)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    agent.save_index(str(index_path))
    agent.save_metadata(str(meta_path))
    _touch(notebook_id)
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


def _touch(notebook_id: str) -> None:
    meta = get_notebook(notebook_id)
    if meta:
        meta["updated_at"] = _now_iso()
        with open(_meta_path(notebook_id), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)


def _load_json(path: Path, default):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Studio outputs
# ---------------------------------------------------------------------------

def load_studio_outputs(notebook_id: str) -> List[dict]:
    return _load_json(_studio_path(notebook_id), [])


def save_studio_output(notebook_id: str, tool: str, label: str, sources: List[str], result: dict) -> dict:
    outputs = load_studio_outputs(notebook_id)
    entry = {
        "id": str(uuid.uuid4()),
        "tool": tool,
        "label": label,
        "sources": sources,
        "source_count": len(sources),
        "created_at": _now_iso(),
        "result": result,
    }
    outputs.insert(0, entry)
    _save_json(_studio_path(notebook_id), outputs)
    return entry


def delete_studio_output(notebook_id: str, output_id: str) -> bool:
    outputs = load_studio_outputs(notebook_id)
    new_outputs = [o for o in outputs if o.get("id") != output_id]
    if len(new_outputs) == len(outputs):
        return False
    _save_json(_studio_path(notebook_id), new_outputs)
    return True
