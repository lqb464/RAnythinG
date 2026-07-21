# RAnythinG

Web RAG local kiểu **NotebookLM**: upload tài liệu → tự lập chỉ mục → hỏi đáp có trích dẫn nguồn — chạy trên máy bạn.

**Self-contained.** Không cần AgenThink, dOCRead, VirtuaLook hay bất kỳ service sibling nào. OCR dùng Docling in-process; vector index FAISS trên đĩa; LLM qua Gemini / Ollama / vLLM / local.

<p align="center">
  <img src="assets/landing-page.png" alt="Trang sản phẩm RAnythinG" width="900" />
</p>

**RAG · Local · Privacy-first** — PDF / DOCX / MD · trích dẫn nguồn · Docker ready

---

## Demo

| Trang sản phẩm | Workspace notebooks | Chat + Studio |
|:---:|:---:|:---:|
| ![Landing](assets/landing-page.png) | ![Workspace](assets/app-workspace.png) | ![Chat](assets/app-chat-studio.png) |

- **Landing** — giới thiệu sản phẩm, CTA mở app  
- **Workspace** — Assembly Canvas (sources · chat · Studio artifacts) + **Graph mode** (entity GraphRAG)  
- **Chat + Studio** — hỏi đáp có citation; Studio quiz / flashcard / mind map tương tác  

---

## Chạy nhanh

### Docker + PostgreSQL (khuyên dùng)

```powershell
copy .env.example .env
docker compose up --build
```

Mở **http://localhost:8000**

| Thành phần | Chi tiết |
|------------|----------|
| App + marketing | `http://localhost:8000` |
| Notebook UI | `http://localhost:8000/app` |
| Postgres | port `5432`, user/pass/db = `rananything` |
| Dữ liệu | notebook/file/chat → Postgres; FAISS → volume `app_data` |
| Auth | Đăng ký/đăng nhập JWT trên `/app` (`AUTH_REQUIRED=true`) |
| Service API (tuỳ chọn) | `/api/external/*` — set `EXTERNAL_API_TOKEN` nếu muốn khóa bằng Bearer |

Chỉ chạy DB (dev local):

```powershell
docker compose up db -d
$env:DATABASE_URL="postgresql://rananything:rananything@localhost:5432/rananything"
pip install sqlalchemy psycopg2-binary
python app.py
```

Migrate dữ liệu file cũ sang Postgres:

```powershell
$env:DATABASE_URL="postgresql://rananything:rananything@localhost:5432/rananything"
python scripts/migrate_to_postgres.py
```

Health check: `GET http://localhost:8000/api/health`

### Chạy local (không Docker)

Không bắt buộc Postgres — bỏ `DATABASE_URL` để dùng lưu trữ file dưới `DATA_DIR`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env   # chỉnh GEMINI_API_KEY hoặc Ollama
python app.py
```

- **http://localhost:8000** — website sản phẩm  
- **http://localhost:8000/app** — ứng dụng notebook  

---

## Luồng sử dụng

1. Mở **http://localhost:8000/app** — đăng ký / đăng nhập  
2. Tạo notebook → **Upload** nguồn (kéo-thả)  
3. Trên **Assembly Canvas**: bấm source để đưa vào context, nối cạnh vào Chat  
4. Hỏi đáp có citation; dùng **Studio** để gắn Quiz / Flashcards / Mind map / Report lên board  
5. **Export ZIP** để backup  

### Dev frontend (Assembly Canvas)

```powershell
cd web
npm install
npm run dev          # http://localhost:5173/app/ (proxy /api → :8000)
npm run build        # → src/rag_app/static/web
```

---

## Độc lập — không phụ thuộc project khác

| Cần để chạy solo | Không cần |
|------------------|-----------|
| Python deps (`requirements.txt`) | AgenThink |
| (Tuỳ chọn) Postgres qua `docker compose up db` | dOCRead |
| Gemini key **hoặc** Ollama/vLLM **hoặc** local Qwen | VirtuaLook / SketClothes |
| HF models (embedding + reranker, tải lần đầu) | Port/ecosystem của sibling |

`/api/external/*` chỉ là API tùy chọn để service khác gọi RAnythinG — **không** phải dependency runtime.

Repo GitHub riêng: https://github.com/lqb464/RAnythinG

---

## Trang marketing

| URL | Nội dung |
|-----|----------|
| `/` | Trang chủ |
| `/features` | Tính năng |
| `/use-cases` | Giải pháp theo ngành |
| `/guide` | Hướng dẫn cài đặt & dùng |
| `/pricing` | Bảng giá |
| `/compare` | So sánh NotebookLM / ChatGPT |
| `/changelog` | Lịch sử cập nhật |
| `/about` | Về dự án & roadmap |

---

## Kiến trúc RAG

| Thành phần | Vai trò |
|------------|---------|
| Embedding | `intfloat/multilingual-e5-small` |
| Retrieval | Hybrid dense (FAISS) + BM25 → RRF |
| Reranker | `BAAI/bge-reranker-v2-m3` |
| Generation | Gemini (nếu có API key) / `Qwen/Qwen2.5-1.5B-Instruct` + fallback extractive |
| Parsing | Docling (PDF/DOCX) + fallback PyPDF2 / python-docx |
| GraphRAG | UI Graph mode (build on-demand); auto-index tắt mặc định (`ENABLE_GRAPH_RAG=false`) |

### File chính

| File | Mô tả |
|------|-------|
| `app.py` | Entrypoint FastAPI |
| `src/rag_app/server.py` | API notebook, chat/stream, Studio, notes |
| `src/rag_app/core.py` | RAG engine + Studio tools |
| `src/rag_app/retrieval.py` | Hybrid retrieval, rewrite, rerank |
| `src/rag_app/synthesis.py` | Sinh câu trả lời / nội dung Studio |
| `src/rag_app/chunking.py` | Semantic chunking |
| `src/rag_app/graph_rag.py` | GraphRAG (entity / community) |
| `src/rag_app/parsers.py` | Đọc PDF/DOCX/PPTX/… |
| `src/rag_app/static/app.html` | Frontend notebook (legacy fallback) |
| `web/` | Assembly Canvas + Graph mode (Vite/React → `static/web/`) |

---

## CLI (tùy chọn)

```powershell
python -m src.rag_app.cli build --source-folder ./docs --output-dir ./data
python -m src.rag_app.cli query --index-path ./data/rag_index.faiss --metadata-path ./data/rag_index.faiss.json --query "Nội dung chính?"
```

> Lưu ý: thư mục `assets/` chứa ảnh demo README; đừng nhầm với `--source-folder ./docs` khi build index tài liệu.

---

## Test

```powershell
pip install -r requirements-dev.txt
python -m pytest
```
