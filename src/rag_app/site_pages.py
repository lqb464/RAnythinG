"""Marketing site pages — product-first nav (landing + app; extras in footer)."""

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Keep nav minimal — product lives in /app (Assembly Canvas).
NAV_ITEMS = [
    {"href": "/#product", "label": "Sản phẩm", "key": "product"},
    {"href": "/guide", "label": "Cài đặt", "key": "guide"},
]

FOOTER_SECTIONS = [
    {
        "title": "Sản phẩm",
        "links": [
            {"href": "/app", "label": "Mở Workspace"},
            {"href": "/#product", "label": "Assembly Canvas"},
            {"href": "/guide", "label": "Cài đặt"},
        ],
    },
    {
        "title": "Tài nguyên",
        "links": [
            {"href": "/changelog", "label": "Changelog"},
            {"href": "/about", "label": "Về chúng tôi"},
            {"href": "/features", "label": "Tính năng (chi tiết)"},
            {"href": "https://github.com/lqb464/RAnythinG", "label": "GitHub"},
        ],
    },
]


def render_page(request: Request, template: str, page_key: str, **extra: Any):
    ctx = {
        "page_key": page_key,
        "nav_items": NAV_ITEMS,
        "footer_sections": FOOTER_SECTIONS,
        **extra,
    }
    return templates.TemplateResponse(request, template, ctx)
