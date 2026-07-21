"""Minimal conftest — keep HF offline for CI."""

from __future__ import annotations

import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("AUTH_REQUIRED", "false")
os.environ.setdefault("EXTERNAL_API_TOKEN", "")
