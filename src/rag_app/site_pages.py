"""Marketing site pages — nav config and Jinja2 renderer."""

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

NAV_ITEMS = [
    {"href": "/features", "label": "Tính năng", "key": "features"},
    {"href": "/use-cases", "label": "Giải pháp", "key": "use-cases"},
    {"href": "/guide", "label": "Tài liệu", "key": "guide"},
    {"href": "/pricing", "label": "Giá", "key": "pricing"},
    {"href": "/compare", "label": "So sánh", "key": "compare"},
]

FOOTER_SECTIONS = [
    {
        "title": "Sản phẩm",
        "links": [
            {"href": "/app", "label": "Ứng dụng"},
            {"href": "/features", "label": "Tính năng"},
            {"href": "/use-cases", "label": "Giải pháp"},
            {"href": "/pricing", "label": "Giá"},
        ],
    },
    {
        "title": "Tài nguyên",
        "links": [
            {"href": "/guide", "label": "Hướng dẫn"},
            {"href": "/compare", "label": "So sánh"},
            {"href": "/changelog", "label": "Changelog"},
            {"href": "/about", "label": "Về chúng tôi"},
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
