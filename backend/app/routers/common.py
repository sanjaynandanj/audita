"""Shared helpers for the API routers: signed links, uploads, agent names."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .. import config

AGENT = "itc-recon-agent/0.1"
BANK_AGENT = "bank-recon-agent/0.1"
CLOSE_AGENT = "close-agent/0.1"
INVOICE_AGENT = "invoice-agent/0.1"
BOOKS_AGENT = "bookkeeping-agent/0.1"
REVIEW_AGENT = "review-agent/0.1"

signer = URLSafeTimedSerializer(config.secret_key(), salt="audita-report-link")
bank_signer = URLSafeTimedSerializer(config.secret_key(), salt="audita-bankrec-link")


def sign_report_id(report_id: str) -> str:
    return signer.dumps(report_id)


def resolve_token(token: str) -> str:
    try:
        return signer.loads(token, max_age=config.LINK_MAX_AGE_SECONDS)
    except SignatureExpired:
        raise HTTPException(status_code=410, detail="This report link has expired. Ask for a fresh link.") from None
    except BadSignature:
        raise HTTPException(status_code=404, detail="Invalid report link.") from None


def resolve_bank_token(token: str) -> str:
    try:
        return bank_signer.loads(token, max_age=config.LINK_MAX_AGE_SECONDS)
    except SignatureExpired:
        raise HTTPException(status_code=410, detail="This report link has expired.") from None
    except BadSignature:
        raise HTTPException(status_code=404, detail="Invalid report link.") from None


def check_upload_size(data: bytes) -> bytes:
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.",
        )
    return data


async def save_upload(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "upload").suffix.lower()
    if suffix not in (".json", ".csv", ".xlsx", ".xls"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
    data = check_upload_size(await upload.read())
    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=config.UPLOADS_DIR, suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        return Path(tmp.name)
