"""Filesystem user store when DATABASE_URL is not set."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

USERS_PATH = Path("./data/users.json")


def _load() -> list[dict]:
    if not USERS_PATH.exists():
        return []
    try:
        with open(USERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(users: list[dict]) -> None:
    USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def create_user(email: str, password_hash: str) -> dict:
    users = _load()
    if any(u.get("email") == email for u in users):
        raise ValueError("Email already registered")
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": password_hash,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    users.append(user)
    _save(users)
    return {"id": user["id"], "email": email}


def get_user_by_email(email: str) -> Optional[dict]:
    for u in _load():
        if u.get("email") == email:
            return u
    return None


def get_user_by_id(user_id: str) -> Optional[dict]:
    for u in _load():
        if u.get("id") == user_id:
            return u
    return None
