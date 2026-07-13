# RAnythinG

Web RAG local giống **NotebookLM**: upload tài liệu → tự lập chỉ mục → hỏi đáp có trích dẫn nguồn.

## Chạy với Docker + PostgreSQL (khuyên dùng)

```powershell
docker compose up --build
```

Mở **http://localhost:8000** — trang sản phẩm + app + Postgres (pgvector) chạy trong container.

- **Postgres:** port `5432`, user/pass/db = `rananything`
- **Dữ liệu:** notebook, file, chat → PostgreSQL; FAISS index → volume `app_data`

Chỉ chạy database (dev local):

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

Kiểm tra storage backend: `GET http://localhost:8000/api/health`

## Chạy app (UI chính — HTML/CSS/JS)

```powershell
python app.py
```


- **http://localhost:8000** — website sản phẩm (8 trang marketing)
- **http://localhost:8000/app** — ứng dụng notebook (Sources | Chat | Studio)

### Trang marketing

| URL | Nội dung |
|-----|----------|
| `/` | Trang chủ |
| `/features` | Tính năng chi tiết |
| `/use-cases` | Giải pháp theo ngành |
| `/guide` | Hướng dẫn cài đặt & sử dụng |
| `/pricing` | Bảng giá |
| `/compare` | So sánh với NotebookLM, ChatGPT |
| `/changelog` | Lịch sử cập nhật |
| `/about` | Về dự án & roadmap |

Giao diện HTML/CSS/JS với **3 panel cố định**. Chat history và gợi ý cuộn **bên trong** khung, không đẩy layout. Chat trả lời theo kiểu **streaming** (hiện dần từng token) và nhớ vài lượt hội thoại gần nhất.

## Cài đặt

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

## Luồng sử dụng

1. Tạo notebook mới trên trang chủ
2. Upload tài liệu ở panel **Sources** (tự index, không cần nút riêng — thêm tài liệu vào notebook đã có sẽ index tăng dần thay vì lập lại chỉ mục từ đầu)
3. Chọn nguồn muốn dùng cho chat
4. Hỏi trong **Chat** hoặc dùng câu hỏi gợi ý
5. Dùng **Studio** để tạo Tóm tắt, Quiz, Flashcards, Mind Map, Report, Audio Overview, Video Overview, Infographic, Slide Deck, Data Table — tất cả sinh bằng LLM dựa trên nguồn đã chọn (có fallback rule-based nếu LLM lỗi)

## CLI (tùy chọn)

```powershell
python -m src.rag_app.cli build --source-folder ./docs --output-dir ./data
python -m src.rag_app.cli query --index-path ./data/rag_index.faiss --metadata-path ./data/rag_index.faiss.json --query "Nội dung chính?"
```

## Kiến trúc

| File | Mô tả |
|------|-------|
| `app.py` | Entrypoint (FastAPI + HTML) |
| `src/rag_app/server.py` | API backend (notebook, chat/stream, Studio, notes) |
| `src/rag_app/site_pages.py` | Renderer trang marketing (Jinja2) |
| `src/rag_app/templates/` | HTML templates (home, features, docs…) |
| `src/rag_app/static/app.html` | Frontend ứng dụng notebook |
| `src/rag_app/static/` | CSS/JS (landing + app) |
| `src/rag_app/notebook_store.py` / `postgres_store.py` | Lưu notebook, file, index (filesystem hoặc Postgres) |
| `src/rag_app/agent_cache.py` | Cache `RagAgent` theo notebook, điều phối add/remove tăng dần |
| `src/rag_app/core.py` | RAG engine (chunking, retrieval, generation, Studio tools) |
| `src/rag_app/retrieval.py` | Hybrid dense+BM25 retrieval, RRF fusion, cross-encoder rerank |
| `src/rag_app/synthesis.py` | Sinh câu trả lời + nội dung Studio bằng LLM (JSON có cấu trúc) |
| `src/rag_app/graph_rag.py` / `graph_index.py` | GraphRAG: entity graph, community detection, expand tăng dần |
| `src/rag_app/parsers.py` | Đọc PDF/DOCX/PPTX/... (Docling khi có thể) |

## Mô hình

- Embedding: `intfloat/multilingual-e5-small` (đa ngôn ngữ)
- Reranker: `BAAI/bge-reranker-v2-m3` (cross-encoder)
- Generation: `Qwen/Qwen2.5-1.5B-Instruct` (fallback trích xuất từ chunk khi cần)
- Vector store: FAISS (+ BM25 cho hybrid retrieval)

## Test

```powershell
pip install -r requirements-dev.txt
python -m pytest
```
