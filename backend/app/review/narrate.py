"""LLM narration of a computed review workbook.

Env-gated on GEMINI_API_KEY. The narrative is commentary attached to the
workbook — it cites only figures already computed by app.review.compute and
is never a source of numbers. Without the key the workbook stands on its
computed tables alone.
"""

from __future__ import annotations

import json
import os

PROMPT = (
    "You are drafting review notes for an Indian chartered accountant's month-end "
    "financial review workpaper. Below is the COMPUTED review data: a P&L movement "
    "table, group summary, and anomaly flags. Write concise CA-style review notes "
    "(3-6 short paragraphs). STRICT RULES: cite only numbers that appear verbatim in "
    "the data; do not compute, estimate, round differently, or introduce any figure "
    "not present; refer to flags by their titles; note that flagged items await named "
    "verification where status is pending. Amounts are INR, sign convention: positive "
    "is money in.\n\nDATA:\n{data}"
)


def is_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def narrate_review(workbook_data: dict) -> str:
    if not is_configured():
        raise RuntimeError("Set GEMINI_API_KEY to enable review narration.")
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=os.environ.get("AUDITA_REVIEW_MODEL", "gemini-2.5-flash"),
        contents=PROMPT.format(data=json.dumps(workbook_data, ensure_ascii=False)),
    )
    return (response.text or "").strip()
