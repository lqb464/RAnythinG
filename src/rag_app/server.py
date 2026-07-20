import asyncio
import json
import re
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent_cache, store
from .core import get_embedding_model
from .parsers import parse_upload_bytes
from .site_pages import render_page
from .synthesis import load_synthesizer_eager


def _load_models_eagerly() -> None:
    """Warm-up: load all ML models at startup so the first upload/query is instant."""
    get_embedding_model()
    load_synthesizer_eager()

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="RAnythinG", version="1.0")


@app.on_event("startup")
async def startup() -> None:
    if store.backend_name == "postgresql":
        from .database import init_db

        init_db()

    # Pre-load embedding model in a thread so it's ready before the first upload.
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _load_models_eagerly)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "storage": store.backend_name,
    }


class NotebookCreate(BaseModel):
    name: str = "Notebook mới"


class NotebookRename(BaseModel):
    name: str


class ChatRequest(BaseModel):
    query: str
    sources: List[str]


class NoteCreate(BaseModel):
    title: str
    content: str


class StudioRequest(BaseModel):
    sources: List[str] = []


def _studio_summary(agent, sources):
    return {"markdown": agent.summarize_documents(allowed_sources=sources)}


def _studio_quiz(agent, sources):
    return {"items": agent.generate_quiz(allowed_sources=sources)}


def _studio_flashcards(agent, sources):
    return {"items": agent.generate_flashcards(allowed_sources=sources)}


def _studio_mindmap(agent, sources):
    return agent.generate_mind_map(allowed_sources=sources)


def _studio_report(agent, sources):
    return {"markdown": agent.generate_reports(allowed_sources=sources)}


def _studio_audio(agent, sources):
    return {"dialogue": agent.generate_audio_overview(allowed_sources=sources)}


def _studio_video(agent, sources):
    return {"markdown": agent.generate_video_overview(allowed_sources=sources)}


def _studio_infographic(agent, sources):
    return {"markdown": agent.generate_infographic(allowed_sources=sources)}


def _studio_slides(agent, sources):
    return {"slides": agent.generate_slide_deck(allowed_sources=sources)}


def _studio_datatable(agent, sources):
    return {"rows": agent.generate_data_table(allowed_sources=sources)}


STUDIO_TOOLS = {
    "summary": _studio_summary,
    "quiz": _studio_quiz,
    "flashcards": _studio_flashcards,
    "mindmap": _studio_mindmap,
    "report": _studio_report,
    "audio": _studio_audio,
    "video": _studio_video,
    "infographic": _studio_infographic,
    "slides": _studio_slides,
    "datatable": _studio_datatable,
}

STUDIO_LABELS = {
    "summary": "Tóm tắt",
    "quiz": "Quiz",
    "flashcards": "Flashcards",
    "mindmap": "Mind Map",
    "report": "Báo cáo",
    "audio": "Audio Overview",
    "video": "Video Overview",
    "infographic": "Infographic",
    "slides": "Slide Deck",
    "datatable": "Data Table",
}


def _all_sources(notebook_id: str) -> List[str]:
    """Return only uploaded document sources (notes are indexed but not shown in the Sources panel)."""
    return store.list_source_files(notebook_id)


def _format_answer_html(text: str) -> str:
    return re.sub(
        r"\[(\d+)\]",
        r'<sup class="cite" title="Nguồn \1">\1</sup>',
        text,
    )


@app.get("/")
async def home(request: Request):
    return render_page(request, "home.html", "home")


@app.get("/features")
async def features_page(request: Request):
    return render_page(request, "features.html", "features")


@app.get("/use-cases")
async def use_cases_page(request: Request):
    return render_page(request, "use_cases.html", "use-cases")


@app.get("/guide")
async def guide_page(request: Request):
    return render_page(request, "docs.html", "guide")


@app.get("/pricing")
async def pricing_page(request: Request):
    return render_page(request, "pricing.html", "pricing")


@app.get("/compare")
async def compare_page(request: Request):
    return render_page(request, "compare.html", "compare")


@app.get("/changelog")
async def changelog_page(request: Request):
    return render_page(request, "changelog.html", "changelog")


@app.get("/about")
async def about_page(request: Request):
    return render_page(request, "about.html", "about")


@app.get("/app")
async def app_page():
    return FileResponse(STATIC_DIR / "app.html")


@app.get("/api/notebooks")
async def list_notebooks():
    return store.list_notebooks()


@app.post("/api/notebooks")
async def create_notebook(body: NotebookCreate):
    return store.create_notebook(body.name)


@app.get("/api/notebooks/{notebook_id}")
async def get_notebook(notebook_id: str):
    meta = store.get_notebook(notebook_id)
    if not meta:
        raise HTTPException(404, "Notebook không tồn tại")
    agent = await agent_cache.async_get_agent(notebook_id)
    stats = agent.get_stats() if len(agent.chunks) > 0 else {"documents": 0, "chunks": 0, "avg_chunk_length": 0}
    return {
        **meta,
        "sources": _all_sources(notebook_id),
        "stats": stats,
        "indexed": len(agent.chunks) > 0,
    }


@app.patch("/api/notebooks/{notebook_id}")
async def rename_notebook(notebook_id: str, body: NotebookRename):
    if not store.get_notebook(notebook_id):
        raise HTTPException(404, "Notebook không tồn tại")
    store.update_notebook_name(notebook_id, body.name)
    return store.get_notebook(notebook_id)


@app.delete("/api/notebooks/{notebook_id}")
async def delete_notebook(notebook_id: str):
    agent_cache.invalidate_agent(notebook_id)
    store.delete_notebook(notebook_id)
    return {"ok": True}


@app.post("/api/notebooks/{notebook_id}/upload")
async def upload_files(notebook_id: str, files: List[UploadFile] = File(...)):
    if not store.get_notebook(notebook_id):
        raise HTTPException(404, "Notebook không tồn tại")
    added: List[str] = []
    existing = set(store.list_source_files(notebook_id))
    agent = await agent_cache.async_get_agent(notebook_id)
    has_existing_index = len(agent.chunks) > 0

    for f in files:
        if f.filename in existing:
            continue
        data = await f.read()
        filename = store.save_upload_bytes(notebook_id, f.filename, data)
        if not filename:
            continue
        added.append(filename)
        if has_existing_index:
            # Notebook already indexed: add incrementally instead of a full rebuild.
            parsed = parse_upload_bytes(filename, data)
            if parsed.text.strip():
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, agent_cache.add_document, notebook_id, filename, parsed.text
                )

    if added and not has_existing_index:
        # First source(s) in an empty notebook: build the baseline index once.
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, agent_cache.rebuild_agent, notebook_id)

    agent = await agent_cache.async_get_agent(notebook_id)
    return {
        "added": added,
        "sources": _all_sources(notebook_id),
        "stats": agent.get_stats(),
        "indexed": len(agent.chunks) > 0,
    }


@app.delete("/api/notebooks/{notebook_id}/sources/{filename:path}")
async def delete_source(notebook_id: str, filename: str):
    store.remove_source(notebook_id, filename)
    agent_cache.remove_document(notebook_id, filename)
    return {"sources": _all_sources(notebook_id)}


@app.get("/api/notebooks/{notebook_id}/chat")
async def get_chat_history(notebook_id: str):
    return store.load_chat_history(notebook_id)


@app.get("/api/notebooks/{notebook_id}/suggestions")
async def get_suggestions(notebook_id: str, sources: str = ""):
    agent = await agent_cache.async_get_agent(notebook_id)
    allowed = [s for s in sources.split("|") if s] if sources else None
    return {"suggestions": agent.generate_suggested_questions(allowed_sources=allowed, limit=4)}


def _recent_history(notebook_id: str, limit: int = 3) -> List[dict]:
    history = store.load_chat_history(notebook_id)
    return history[-limit:] if history else []


def _persist_chat_turn(notebook_id: str, query: str, answer: str, source_names: List[str]) -> None:
    if store.append_chat_message:
        store.append_chat_message(notebook_id, query, answer, source_names)
    else:
        history = store.load_chat_history(notebook_id)
        history.append({"query": query, "answer": answer, "sources": source_names})
        store.save_chat_history(notebook_id, history)


@app.post("/api/notebooks/{notebook_id}/chat")
async def chat(notebook_id: str, body: ChatRequest):
    if not body.query.strip():
        raise HTTPException(400, "Câu hỏi trống")
    if not body.sources:
        raise HTTPException(400, "Chọn ít nhất 1 nguồn")
    agent = await agent_cache.async_get_agent(notebook_id)
    if len(agent.chunks) == 0:
        raise HTTPException(400, "Chưa có chỉ mục RAG — hãy upload tài liệu")
    query = body.query.strip()
    history = _recent_history(notebook_id)
    answer, chunks = agent.answer(query, top_k=4, allowed_sources=body.sources, history=history)
    source_names = [c.source for c in chunks]
    entry = {
        "query": query,
        "answer": answer,
        "sources": [{"source": c.source, "text": c.text[:300]} for c in chunks],
    }
    _persist_chat_turn(notebook_id, query, answer, source_names)
    return {
        **entry,
        "answer_html": _format_answer_html(answer),
    }


@app.post("/api/notebooks/{notebook_id}/chat/stream")
async def chat_stream(notebook_id: str, body: ChatRequest):
    if not body.query.strip():
        raise HTTPException(400, "Câu hỏi trống")
    if not body.sources:
        raise HTTPException(400, "Chọn ít nhất 1 nguồn")
    agent = await agent_cache.async_get_agent(notebook_id)
    if len(agent.chunks) == 0:
        raise HTTPException(400, "Chưa có chỉ mục RAG — hãy upload tài liệu")

    query = body.query.strip()
    sources = body.sources
    history = _recent_history(notebook_id)

    def event_stream():
        final_answer = ""
        final_sources: List[dict] = []
        for event in agent.answer_stream(query, top_k=4, allowed_sources=sources, history=history):
            if event["type"] == "sources":
                final_sources = event["sources"]
            elif event["type"] in ("done", "replace"):
                final_answer = event["answer"]
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        source_names = [s["source"] for s in final_sources]
        _persist_chat_turn(notebook_id, query, final_answer, source_names)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/notebooks/{notebook_id}/notes")
async def get_notes(notebook_id: str):
    return store.load_notes(notebook_id)


@app.post("/api/notebooks/{notebook_id}/notes")
async def add_note(notebook_id: str, body: NoteCreate):
    if not store.get_notebook(notebook_id):
        raise HTTPException(status_code=404, detail="Notebook không tồn tại")
    title = body.title.strip()
    content = body.content.strip()
    if not title or not content:
        raise HTTPException(status_code=400, detail="Tiêu đề và nội dung không được để trống")

    notes = store.load_notes(notebook_id)
    from datetime import datetime

    notes.append({
        "id": f"note_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "title": title,
        "content": content,
        "date": "Vừa xong",
    })
    store.save_notes(notebook_id, notes)

    agent = await agent_cache.async_get_agent(notebook_id)
    loop = asyncio.get_event_loop()
    if len(agent.chunks) > 0:
        await loop.run_in_executor(
            None, agent_cache.add_document, notebook_id, f"[Ghi chú] {title}", content
        )
    else:
        await loop.run_in_executor(None, agent_cache.rebuild_agent, notebook_id)
    return notes


@app.put("/api/notebooks/{notebook_id}/notes/{note_id}")
async def update_note(notebook_id: str, note_id: str, body: NoteCreate):
    if not store.get_notebook(notebook_id):
        raise HTTPException(status_code=404, detail="Notebook không tồn tại")
    title = body.title.strip()
    content = body.content.strip()
    if not title or not content:
        raise HTTPException(status_code=400, detail="Tiêu đề và nội dung không được để trống")

    notes = store.load_notes(notebook_id)
    found = False
    old_title = ""
    for n in notes:
        if n["id"] == note_id:
            old_title = n.get("title", "")
            n["title"] = title
            n["content"] = content
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Ghi chú không tồn tại")
    store.save_notes(notebook_id, notes)

    if old_title:
        agent_cache.remove_document(notebook_id, f"[Ghi chú] {old_title}")
    agent = await agent_cache.async_get_agent(notebook_id)
    loop = asyncio.get_event_loop()
    if len(agent.chunks) > 0:
        await loop.run_in_executor(
            None, agent_cache.add_document, notebook_id, f"[Ghi chú] {title}", content
        )
    return notes


@app.delete("/api/notebooks/{notebook_id}/notes/{note_id}")
async def delete_note(notebook_id: str, note_id: str):
    if not store.get_notebook(notebook_id):
        raise HTTPException(status_code=404, detail="Notebook không tồn tại")
    notes = store.load_notes(notebook_id)
    note_to_remove = next((n for n in notes if n["id"] == note_id), None)
    if not note_to_remove:
        raise HTTPException(status_code=404, detail="Ghi chú không tồn tại")

    notes = [n for n in notes if n["id"] != note_id]
    store.save_notes(notebook_id, notes)

    agent_cache.remove_document(notebook_id, f"[Ghi chú] {note_to_remove['title']}")
    return notes


@app.post("/api/notebooks/{notebook_id}/notes/{note_id}/to_source")
async def note_to_source(notebook_id: str, note_id: str):
    if not store.get_notebook(notebook_id):
        raise HTTPException(status_code=404, detail="Notebook không tồn tại")
    notes = store.load_notes(notebook_id)
    note = next((n for n in notes if n["id"] == note_id), None)
    if not note:
        raise HTTPException(status_code=404, detail="Ghi chú không tồn tại")

    clean_title = re.sub(r'[^a-zA-Z0-9_\-À-ỹ ]', '', note['title']).strip() or "Ghi chu"
    filename = f"Ghi chú - {clean_title[:40]}.txt"
    data = f"# {note['title']}\n\n{note['content']}".encode("utf-8")
    saved_name = store.save_upload_bytes(notebook_id, filename, data)
    if not saved_name:
        raise HTTPException(status_code=500, detail="Không thể lưu file nguồn")

    agent = await agent_cache.async_get_agent(notebook_id)
    loop = asyncio.get_event_loop()
    if len(agent.chunks) > 0:
        await loop.run_in_executor(
            None, agent_cache.add_document, notebook_id, saved_name, note["content"]
        )
    else:
        await loop.run_in_executor(None, agent_cache.rebuild_agent, notebook_id)

    return {"ok": True, "filename": saved_name, "sources": store.list_source_files(notebook_id)}


@app.post("/api/notebooks/{notebook_id}/studio/{tool}")
async def studio_generate(notebook_id: str, tool: str, body: StudioRequest):
    if not store.get_notebook(notebook_id):
        raise HTTPException(404, "Notebook không tồn tại")
    handler = STUDIO_TOOLS.get(tool)
    if handler is None:
        raise HTTPException(404, f"Studio tool '{tool}' không tồn tại")
    agent = await agent_cache.async_get_agent(notebook_id)
    if len(agent.chunks) == 0:
        raise HTTPException(400, "Chưa có chỉ mục RAG — hãy upload tài liệu")
    allowed = body.sources or None
    try:
        result = handler(agent, allowed)
    except Exception as exc:
        raise HTTPException(500, f"Không thể tạo nội dung Studio: {exc}") from exc
    label = STUDIO_LABELS.get(tool, tool)
    sources = body.sources or store.list_source_files(notebook_id)
    entry = store.save_studio_output(notebook_id, tool, label, sources, result)
    return {"tool": tool, "output_id": entry["id"], **result}


@app.get("/api/notebooks/{notebook_id}/studio")
async def list_studio_outputs(notebook_id: str):
    if not store.get_notebook(notebook_id):
        raise HTTPException(404, "Notebook không tồn tại")
    outputs = store.load_studio_outputs(notebook_id)
    # Strip heavy result payload for list view — frontend fetches full on click
    return [
        {k: v for k, v in o.items() if k != "result"}
        for o in outputs
    ]


@app.get("/api/notebooks/{notebook_id}/studio/{output_id}")
async def get_studio_output(notebook_id: str, output_id: str):
    outputs = store.load_studio_outputs(notebook_id)
    for o in outputs:
        if o.get("id") == output_id:
            return o
    raise HTTPException(404, "Output không tồn tại")


@app.delete("/api/notebooks/{notebook_id}/studio/{output_id}")
async def delete_studio_output(notebook_id: str, output_id: str):
    if not store.delete_studio_output(notebook_id, output_id):
        raise HTTPException(404, "Output không tồn tại")
    return {"ok": True}


# --- External API for integration (e.g. with AgenThink) ---

class ExternalRetrieveRequest(BaseModel):
    project_id: str
    query: str
    top_k: Optional[int] = 4
    allowed_sources: Optional[List[str]] = None


class ExternalQueryRequest(BaseModel):
    project_id: str
    query: str
    top_k: Optional[int] = 4
    brief: Optional[bool] = False
    history: Optional[List[dict]] = None
    sources: Optional[List[str]] = None


class ExternalProjectCreate(BaseModel):
    project_id: str
    name: Optional[str] = None


class ExternalStudioRequest(BaseModel):
    project_id: str
    sources: Optional[List[str]] = None


@app.post("/api/external/projects")
async def external_create_project(body: ExternalProjectCreate):
    project_id = (body.project_id or "").strip()
    if not project_id:
        raise HTTPException(400, "project_id không được trống")
    name = (body.name or f"Project {project_id}").strip()
    existing = store.get_notebook(project_id)
    if existing:
        agent = await agent_cache.async_get_agent(project_id)
        return {
            "ok": True,
            "created": False,
            "project_id": project_id,
            "name": existing.get("name", name),
            "sources": store.list_source_files(project_id),
            "stats": agent.get_stats() if len(agent.chunks) > 0 else {"documents": 0, "chunks": 0},
        }
    meta = store.create_notebook(name, notebook_id=project_id)
    return {
        "ok": True,
        "created": True,
        "project_id": project_id,
        "name": meta.get("name", name),
        "sources": [],
        "stats": {"documents": 0, "chunks": 0},
    }


@app.get("/api/external/projects/{project_id}")
async def external_get_project(project_id: str):
    project_id = project_id.strip()
    if not project_id:
        raise HTTPException(400, "project_id không được trống")
    meta = store.get_notebook(project_id)
    if not meta:
        raise HTTPException(404, "Project không tồn tại")
    agent = await agent_cache.async_get_agent(project_id)
    sources = store.list_source_files(project_id)
    return {
        "ok": True,
        "project_id": project_id,
        "name": meta.get("name", project_id),
        "sources": sources,
        "stats": agent.get_stats() if len(agent.chunks) > 0 else {"documents": 0, "chunks": 0},
        "indexed": len(agent.chunks) > 0,
    }


@app.get("/api/external/projects/{project_id}/sources")
async def external_list_sources(project_id: str):
    project_id = project_id.strip()
    if not project_id:
        raise HTTPException(400, "project_id không được trống")
    if not store.get_notebook(project_id):
        raise HTTPException(404, "Project không tồn tại")
    return {"ok": True, "project_id": project_id, "sources": store.list_source_files(project_id)}


@app.post("/api/external/upload")
async def external_upload(project_id: str, files: List[UploadFile] = File(...)):
    project_id = project_id.strip()
    if not project_id:
        raise HTTPException(400, "project_id không được trống")
    
    # Auto-create project if it doesn't exist
    if not store.get_notebook(project_id):
        store.create_notebook(f"Project {project_id}", notebook_id=project_id)
        
    added: List[str] = []
    existing = set(store.list_source_files(project_id))
    agent = await agent_cache.async_get_agent(project_id)
    has_existing_index = len(agent.chunks) > 0

    for f in files:
        if f.filename in existing:
            continue
        data = await f.read()
        filename = store.save_upload_bytes(project_id, f.filename, data)
        if not filename:
            continue
        added.append(filename)
        if has_existing_index:
            parsed = parse_upload_bytes(filename, data)
            if parsed.text.strip():
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, agent_cache.add_document, project_id, filename, parsed.text
                )

    if added and not has_existing_index:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, agent_cache.rebuild_agent, project_id)

    agent = await agent_cache.async_get_agent(project_id)
    return {
        "ok": True,
        "added": added,
        "sources": store.list_source_files(project_id),
        "stats": agent.get_stats() if len(agent.chunks) > 0 else {"documents": 0, "chunks": 0},
    }


@app.post("/api/external/retrieve")
async def external_retrieve(body: ExternalRetrieveRequest):
    project_id = body.project_id.strip()
    if not project_id:
        raise HTTPException(400, "project_id không được trống")
    if not store.get_notebook(project_id):
        raise HTTPException(404, "Project không tồn tại")
        
    agent = await agent_cache.async_get_agent(project_id)
    if len(agent.chunks) == 0:
        return {"chunks": []}
        
    query = body.query.strip()
    if not query:
        raise HTTPException(400, "query không được trống")
        
    top_k = body.top_k or 4
    allowed = body.allowed_sources or None
    chunks = agent.retrieve(query, top_k=top_k, allowed_sources=allowed)
    return {
        "chunks": [
            {
                "source": c.source,
                "text": c.text,
            }
            for c in chunks
        ]
    }


@app.post("/api/external/query")
async def external_query(body: ExternalQueryRequest):
    project_id = body.project_id.strip()
    if not project_id:
        raise HTTPException(400, "project_id không được trống")
    if not store.get_notebook(project_id):
        raise HTTPException(404, "Project không tồn tại")
        
    agent = await agent_cache.async_get_agent(project_id)
    if len(agent.chunks) == 0:
        raise HTTPException(400, "Chưa có tài liệu nào trong project này")
        
    query = body.query.strip()
    if not query:
        raise HTTPException(400, "query không được trống")
        
    top_k = body.top_k or 4
    brief = body.brief or False
    history = body.history or []
    allowed = body.sources or None
    
    answer, chunks = agent.answer(
        query, top_k=top_k, brief=brief, history=history, allowed_sources=allowed
    )
    return {
        "answer": answer,
        "answer_html": _format_answer_html(answer),
        "chunks": [
            {
                "source": c.source,
                "text": c.text,
            }
            for c in chunks
        ]
    }


@app.post("/api/external/summarize")
async def external_summarize(body: ExternalStudioRequest):
    project_id = body.project_id.strip()
    if not project_id:
        raise HTTPException(400, "project_id không được trống")
    if not store.get_notebook(project_id):
        raise HTTPException(404, "Project không tồn tại")
    agent = await agent_cache.async_get_agent(project_id)
    if len(agent.chunks) == 0:
        raise HTTPException(400, "Chưa có tài liệu nào trong project này")
    allowed = body.sources or None
    markdown = agent.summarize_documents(allowed_sources=allowed)
    return {
        "ok": True,
        "markdown": markdown,
        "sources": allowed or store.list_source_files(project_id),
    }


@app.post("/api/external/report")
async def external_report(body: ExternalStudioRequest):
    project_id = body.project_id.strip()
    if not project_id:
        raise HTTPException(400, "project_id không được trống")
    if not store.get_notebook(project_id):
        raise HTTPException(404, "Project không tồn tại")
    agent = await agent_cache.async_get_agent(project_id)
    if len(agent.chunks) == 0:
        raise HTTPException(400, "Chưa có tài liệu nào trong project này")
    allowed = body.sources or None
    markdown = agent.generate_reports(allowed_sources=allowed)
    return {
        "ok": True,
        "markdown": markdown,
        "sources": allowed or store.list_source_files(project_id),
    }


@app.delete("/api/external/projects/{project_id}")
async def external_delete_project(project_id: str):
    project_id = project_id.strip()
    if not store.get_notebook(project_id):
        raise HTTPException(404, "Project không tồn tại")
    agent_cache.invalidate_agent(project_id)
    store.delete_notebook(project_id)
    return {"ok": True}


@app.delete("/api/external/projects/{project_id}/sources/{filename:path}")
async def external_delete_source(project_id: str, filename: str):
    project_id = project_id.strip()
    if not store.get_notebook(project_id):
        raise HTTPException(404, "Project không tồn tại")
    
    existing = store.list_source_files(project_id)
    if filename not in existing:
        raise HTTPException(404, "Tập tin không tồn tại trong project")
        
    store.remove_source(project_id, filename)
    agent_cache.remove_document(project_id, filename)
    return {"ok": True, "sources": store.list_source_files(project_id)}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def run(host: str | None = None, port: int | None = None) -> None:
    import os
    import uvicorn

    host = host or os.getenv("HOST", "127.0.0.1")
    port = int(port or os.getenv("PORT", "8001"))
    uvicorn.run("src.rag_app.server:app", host=host, port=port, reload=True)
