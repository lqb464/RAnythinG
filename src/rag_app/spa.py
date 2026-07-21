"""
Serve Assembly Canvas SPA (Vite build in static/web) with legacy fallback.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"
WEB_DIR = STATIC_DIR / "web"


def mount_app_spa(app: FastAPI) -> None:
    """Mount /app SPA if built; otherwise legacy app.html."""
    if WEB_DIR.exists() and (WEB_DIR / "index.html").exists():
        app.mount("/app", StaticFiles(directory=str(WEB_DIR), html=True), name="assembly_spa")
    else:

        @app.get("/app")
        @app.get("/app/")
        async def legacy_app_page():
            return FileResponse(STATIC_DIR / "app.html")
