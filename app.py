"""Entrypoint chính — giao diện HTML/CSS/JS (FastAPI)."""

from dotenv import load_dotenv

load_dotenv()

from src.rag_app.server import run

if __name__ == "__main__":
    run()
