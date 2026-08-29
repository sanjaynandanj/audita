from __future__ import annotations

import os
import secrets
from pathlib import Path

# Domain data lives in Postgres (AUDITA_DATABASE_URL, see app.db). The data
# dir only holds the upload tempdir and the dev-fallback signing key.
DATA_DIR = Path(os.environ.get("AUDITA_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
UPLOADS_DIR = DATA_DIR / "uploads"

# Signed report links expire after 7 days by default
LINK_MAX_AGE_SECONDS = int(os.environ.get("AUDITA_LINK_MAX_AGE", 7 * 24 * 3600))

# App-level upload ceiling (statements, registers, invoice scans).
MAX_UPLOAD_BYTES = int(os.environ.get("AUDITA_MAX_UPLOAD_MB", "15")) * 1024 * 1024

# Session cookies are Secure by default (browsers exempt localhost).
# Set AUDITA_COOKIE_SECURE=0 only for plain-HTTP LAN testing.
COOKIE_SECURE = os.environ.get("AUDITA_COOKIE_SECURE", "1") != "0"


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
