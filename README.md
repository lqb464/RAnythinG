# RAnythinG

Web RAG local kiểu **NotebookLM**: upload tài liệu → tự lập chỉ mục → hỏi đáp có trích dẫn nguồn — chạy trên máy bạn.

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
- **Workspace** — tạo / mở notebook  
- **Chat + Studio** — hỏi đáp có citation, Sources · Chat · Studio 3 panel  

---

## Chạy nhanh

### Docker + PostgreSQL (khuyên dùng)

```powershell
docker compose up --build
```

Mở **http://localhost:8000**

| Thành phần | Chi tiết |
|------------|----------|
| App + marketing | `http://localhost:8000` |
| Notebook UI | `http://localhost:8000/app` |
| Postgres | port `5432`, user/pass/db = `rananything` |
| Dữ liệu | notebook/file/chat → Postgres; FAISS → volume `app_data` |

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

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

- **http://localhost:8000** — website sản phẩm  
- **http://localhost:8000/app** — ứng dụng notebook  

---

## Luồng sử dụng

1. Tạo notebook trên workspace  
2. Upload tài liệu ở **Sources** (tự index; thêm file vào notebook đã có = index tăng dần)  
3. Chọn nguồn cho chat  
4. Hỏi trong **Chat** (streaming, nhớ vài lượt gần nhất)  
5. Dùng **Studio**: Tóm tắt, Quiz, Flashcards, Mind Map, Report, Audio, Video, Infographic, Slides, Data Table  

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
| GraphRAG | Có trong code; tắt mặc định (`ENABLE_GRAPH_RAG=False`) để index nhanh |

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
| `src/rag_app/static/app.html` | Frontend notebook |

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
