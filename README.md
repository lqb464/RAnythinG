# RAnythinG

Local **NotebookLM-style** web RAG: upload documents → auto-index → grounded Q&A with citations — runs on your machine.

**Self-contained.** No AgenThink, dOCRead, VirtuaLook, or any sibling service required. OCR runs via in-process Docling; FAISS vector index on disk; LLM via Gemini / Ollama / vLLM / local models.

<p align="center">
  <img src="assets/landing-page.png" alt="RAnythinG product page" width="900" />
</p>

**RAG · Local · Privacy-first** — PDF / DOCX / MD · source citations · Docker ready

---

## Demo

| Product page | Workspaces | Chat + Studio |
|:---:|:---:|:---:|
| ![Landing](assets/landing-page.png) | ![Workspace](assets/app-workspace.png) | ![Chat](assets/app-chat-studio.png) |

- **Landing** — product intro and CTA to open the app  
- **Workspace** — Assembly Canvas (sources · chat · Studio artifacts) + **Graph mode** (entity GraphRAG)  
- **Chat + Studio** — grounded Q&A with citations; interactive Studio quiz / flashcards / mind map  

---

## Quick start

### Docker + PostgreSQL (recommended)

```powershell
copy .env.example .env
docker compose up --build
```

Open **http://localhost:8000**

| Component | Details |
|-----------|---------|
| App + marketing | `http://localhost:8000` |
| Workspace UI | `http://localhost:8000/app` |
| Postgres | port `5432`, user/pass/db = `ranything` |
| Data | workspace/file/chat → Postgres; FAISS → `app_data` volume |
| Auth | Sign up / sign in with JWT on `/app` (`AUTH_REQUIRED=true`) |
| Service API (optional) | `/api/external/*` — set `EXTERNAL_API_TOKEN` to require Bearer auth |

DB only (local app process):

```powershell
docker compose up db -d
$env:DATABASE_URL="postgresql://ranything:ranything@localhost:5432/ranything"
pip install sqlalchemy psycopg2-binary
python app.py
```

Migrate legacy file data to Postgres:

```powershell
$env:DATABASE_URL="postgresql://ranything:ranything@localhost:5432/ranything"
python scripts/migrate_to_postgres.py
```

Health check: `GET http://localhost:8000/api/health`

### Local run (no Docker)

Postgres is optional — omit `DATABASE_URL` to use file storage under `DATA_DIR`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env   # set GEMINI_API_KEY or Ollama
python app.py
```

- **http://localhost:8000** — product site  
- **http://localhost:8000/app** — workspace app  

---

## Usage flow

1. Open **http://localhost:8000/app** — sign up / sign in  
2. Create a workspace → **Upload** sources (drag and drop)  
3. On **Assembly Canvas**: click a source to add context, connect edges into Chat  
4. Ask grounded questions; use **Studio** to pin Quiz / Flashcards / Mind map / Report on the board  
5. **Export ZIP** for backup  

### Frontend dev (Assembly Canvas)

```powershell
cd web
npm install
npm run dev          # http://localhost:5173/app/ (proxies /api → :8000)
npm run build        # → src/rag_app/static/web
```

---

## Standalone — no other project deps

| Required to run solo | Not required |
|----------------------|--------------|
| Python deps (`requirements.txt`) | AgenThink |
| (Optional) Postgres via `docker compose up db` | dOCRead |
| Gemini key **or** Ollama/vLLM **or** local Qwen | VirtuaLook / SketClothes |
| HF models (embedding + reranker, downloaded on first run) | Sibling ecosystem ports |

`/api/external/*` is an optional API for other services to call RAnythinG — **not** a runtime dependency.

GitHub repo: https://github.com/lqb464/RAnythinG

---

## Marketing pages

| URL | Content |
|-----|---------|
| `/` | Home |
| `/features` | Features |
| `/use-cases` | Industry use cases |
| `/guide` | Install & usage guide |
| `/pricing` | Pricing |
| `/compare` | Compare vs NotebookLM / ChatGPT |
| `/changelog` | Changelog |
| `/about` | About & roadmap |

---

## RAG architecture

| Component | Role |
|-----------|------|
| Embedding | `intfloat/multilingual-e5-small` |
| Retrieval | Hybrid dense (FAISS) + BM25 → RRF |
| Reranker | `BAAI/bge-reranker-v2-m3` |
| Generation | Gemini (if API key) / `Qwen/Qwen2.5-1.5B-Instruct` + extractive fallback |
| Parsing | Docling (PDF/DOCX) + PyPDF2 / python-docx fallback |
| GraphRAG | Graph mode UI (build on demand); auto-index off by default (`ENABLE_GRAPH_RAG=false`) |

### Key files

| File | Description |
|------|-------------|
| `app.py` | FastAPI entrypoint |
| `src/rag_app/server.py` | Workspace API, chat/stream, Studio, notes |
| `src/rag_app/core.py` | RAG engine + Studio tools |
| `src/rag_app/retrieval.py` | Hybrid retrieval, rewrite, rerank |
| `src/rag_app/synthesis.py` | Answer / Studio content generation |
| `src/rag_app/chunking.py` | Semantic chunking |
| `src/rag_app/graph_rag.py` | GraphRAG (entity / community) |
| `src/rag_app/parsers.py` | PDF/DOCX/PPTX/… parsing |
| `src/rag_app/static/app.html` | Legacy notebook UI fallback |
| `web/` | Assembly Canvas + Graph mode (Vite/React → `static/web/`) |

---

## CLI (optional)

```powershell
python -m src.rag_app.cli build --source-folder ./docs --output-dir ./data
python -m src.rag_app.cli query --index-path ./data/rag_index.faiss --metadata-path ./data/rag_index.faiss.json --query "What is the main topic?"
```

> Note: `assets/` holds README demo images; do not confuse it with `--source-folder ./docs` when building a document index.

---

## Tests

```powershell
pip install -r requirements-dev.txt
python -m pytest
```
