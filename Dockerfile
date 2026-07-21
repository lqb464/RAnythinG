FROM node:20-alpine AS web
WORKDIR /repo
COPY web ./web
RUN mkdir -p src/rag_app/static
WORKDIR /repo/web
RUN npm install && npm run build

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=web /repo/src/rag_app/static/web ./src/rag_app/static/web

ENV HOST=0.0.0.0
ENV PORT=8000
ENV DATA_DIR=/data
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "app.py"]
