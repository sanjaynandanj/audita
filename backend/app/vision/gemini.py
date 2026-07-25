"""Scanned-invoice field extraction via Gemini vision.

Phase 1 scope: best-effort extraction on common invoice formats, used to
resolve exceptions (a mismatch explained by reading the actual bill).
Env-gated: without GEMINI_API_KEY the module reports not-configured and the
recon runs fine without it.
"""

from __future__ import annotations

import json
import os

PROMPT = (
    "Extract from this Indian GST invoice image and return ONLY JSON with keys: "
    "supplier_gstin, invoice_no, invoice_date (DD-MM-YYYY), taxable_value, "
    "igst, cgst, sgst, cess, total. Use null for unreadable fields. "
    "Amounts as plain numbers without currency symbols or commas."
)


class VisionNotConfigured(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def extract_invoice_fields(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    if not is_configured():
        raise VisionNotConfigured(
            "Set GEMINI_API_KEY to enable scanned-invoice extraction."
        )
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=os.environ.get("AUDITA_VISION_MODEL", "gemini-2.5-flash"),
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            PROMPT,
        ],
    )
    text = (response.text or "").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return json.loads(text)
