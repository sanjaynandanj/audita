from __future__ import annotations

import os
import secrets
from pathlib import Path

DATA_DIR = Path(os.environ.get("AUDITA_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
REPORTS_DIR = DATA_DIR / "reports"
BANKREC_DIR = DATA_DIR / "bankrecs"
CLOSE_DIR = DATA_DIR / "close"
UPLOADS_DIR = DATA_DIR / "uploads"
INVOICES_DIR = DATA_DIR / "invoices"
BOOKS_DIR = DATA_DIR / "books"
EVENTS_DB = DATA_DIR / "events.db"

# Signed report links expire after 7 days by default
LINK_MAX_AGE_SECONDS = int(os.environ.get("AUDITA_LINK_MAX_AGE", 7 * 24 * 3600))


def secret_key() -> str:
    env = os.environ.get("AUDITA_SECRET_KEY")
    if env:
        return env
    key_file = DATA_DIR / "secret_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(32)
    key_file.write_text(key, encoding="utf-8")
    return key
