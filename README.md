# RAnythinG

Local privacy-first RAG web app: upload documents, index them on your machine, and ask grounded questions with source citations.

Features an **Assembly Canvas** workspace (drag sources, chat, Studio artifacts) and optional **Graph mode** (entity GraphRAG). Runs fully local — FastAPI API, Next.js UI, FAISS (+ BM25) retrieval, Docling parsing, LLM via Gemini / Ollama / vLLM / local models.

<p align="center">
  <img src="assets/landing-page.png" alt="RAnythinG product page" width="900" />
</p>

**RAG · Local · Privacy-first** — PDF / DOCX / MD · citations · Docker ready

---

## Repository layout

| Path | What it is | When you touch it |
|------|------------|-------------------|
| `backend/` | Python API, RAG, auth, storage | **Edit here** to change server / RAG behavior |
| `frontend/` | Next.js App Router UI | **Edit here** to change the product site and `/app` workspace |

```text
frontend/   → Next.js :3000  (UI; proxies /api → FastAPI)
backend/    → FastAPI  :8000  (API only) — run: python -m backend
```

- **Docker:** `docker compose up --build` runs `web` + `api` + `db`. Open **http://localhost:3000**.
- **Change backend / RAG:** edit `backend/`.
- **Change UI:** edit `frontend/`, then `npm run dev` (or rebuild the `web` image).

---

## Demo

| Product page | Workspaces | Chat + Studio |
|:---:|:---:|:---:|
| ![Landing](assets/landing-page.png) | ![Workspace](assets/app-workspace.png) | ![Chat](assets/app-chat-studio.png) |

- **Landing** — product intro and CTA
- **Workspace** — Assembly Canvas + Graph mode
- **Chat + Studio** — grounded Q&A; quiz / flashcards / mind map on the board

---

## Quick start

### Docker + PostgreSQL (recommended)

```powershell
copy .env.example .env
docker compose up --build
```

Open **http://localhost:3000** (site) and **http://localhost:3000/app** (workspace).
API health: **http://localhost:8000/api/health**

| Component | Details |
|-----------|---------|
| UI (Next.js) | port `3000` |
| API (FastAPI) | port `8000` |
| Postgres | port `5432`, user/pass/db = `ranything` |
| Data | workspaces/chat → Postgres; FAISS → `app_data` volume |
| Auth | JWT sign-up / sign-in on `/app` (`AUTH_REQUIRED=true`) |
| Service API (optional) | `/api/external/*` — set `EXTERNAL_API_TOKEN` for Bearer auth |

DB only (run API + UI on the host):

```powershell
docker compose up db -d
$env:DATABASE_URL="postgresql://ranything:ranything@localhost:5432/ranything"
pip install -r backend/requirements.txt
copy .env.example .env
python -m backend
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

### Local run (no Docker)

Postgres is optional — omit `DATABASE_URL` to use files under `DATA_DIR`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r backend/requirements.txt
copy .env.example .env
python -m backend
```

```powershell
cd frontend
npm install
npm run dev          # http://localhost:3000 — proxies /api → :8000
```

Production UI (after `npm run build`):

```powershell
cd frontend
npm run build
npm start            # http://localhost:3000
```

---

## Usage

1. Open **/app** — sign up / sign in
2. Create a workspace → upload sources
3. On Assembly Canvas: add sources to context, connect to Chat
4. Ask grounded questions; pin Studio artifacts (quiz, flashcards, mind map, report)
5. Export ZIP for backup

---

## Self-contained

No sibling ML services required. OCR is in-process Docling; vectors are local FAISS; LLM is your Gemini key, Ollama/vLLM, or a local instruct model.

`/api/external/*` is an optional API for other apps to call RAnythinG — not a runtime dependency.

Repo: https://github.com/lqb464/RAnythinG

---

## Site routes

| URL | Content |
|-----|---------|
| `/` | Home |
| `/features` | Features |
| `/use-cases` | Use cases |
| `/guide` | Install & usage |
| `/pricing` | Pricing |
| `/compare` | Comparison |
| `/changelog` | Changelog |
| `/about` | About & roadmap |
| `/app` | Workspace list |
| `/app/[notebookId]` | Open workspace |

---

## RAG stack

| Component | Role |
|-----------|------|
| Embedding | `intfloat/multilingual-e5-small` |
| Retrieval | Hybrid dense (FAISS) + BM25 → RRF |
| Reranker | `BAAI/bge-reranker-v2-m3` |
| Generation | Gemini (if API key) / `Qwen/Qwen2.5-1.5B-Instruct` + extractive fallback |
| Parsing | Docling (PDF/DOCX) + PyPDF2 / python-docx fallback |
| GraphRAG | Graph mode UI (on demand); auto-index off by default (`ENABLE_GRAPH_RAG=false`) |

### Main backend modules

| File | Role |
|------|------|
| `backend/server.py` | HTTP API |
| `backend/core.py` | RAG agent + Studio tools |
| `backend/retrieval.py` | Hybrid retrieval, rewrite, rerank |
| `backend/synthesis.py` | Answer / Studio generation |
| `backend/chunking.py` | Chunking |
| `backend/graph_rag.py` | GraphRAG |
| `backend/parsers.py` | Document parsers |

---

## CLI (optional)

```powershell
python -m backend.cli build --source-folder ./docs --output-dir ./data
python -m backend.cli query --index-path ./data/rag_index.faiss --metadata-path ./data/rag_index.faiss.json --query "What is the main topic?"
```

`assets/` is for README screenshots only — not the same as `--source-folder ./docs`.
