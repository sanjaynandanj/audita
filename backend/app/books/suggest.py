"""LLM account suggestions for uncategorized transactions.

Env-gated on GEMINI_API_KEY, mirroring app.vision.gemini. Suggestions are
advice attached to pending transactions — they never categorize anything
and never enter a total. Without the key the queue simply shows uncoded
transactions for manual coding.
"""

from __future__ import annotations

import json
import os

PROMPT = (
    "You are helping an Indian SME bookkeeper code bank transactions to a chart "
    "of accounts. For each transaction, pick the single best account code from "
    "the chart and a confidence between 0 and 1. Amounts are signed: positive is "
    "money into the bank account, negative is money out. Return ONLY a JSON "
    "array of objects with keys: txn_id, account_code, confidence. If no account "
    "fits, omit that transaction.\n\nCHART OF ACCOUNTS:\n{coa}\n\nTRANSACTIONS:\n{txns}"
)


def is_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def suggest_accounts(
    txns: list[dict], accounts: list[dict]
) -> dict[str, tuple[str, str]]:
    """Return {txn_id: (account_code, confidence)} for the given transactions."""
    if not is_configured() or not txns:
        return {}
    from google import genai

    coa_text = "\n".join(f"{a['code']}  {a['name']}  ({a['type']})" for a in accounts)
    txn_text = "\n".join(
        json.dumps(
            {"txn_id": t["txn_id"], "date": t["txn_date"],
             "description": t["description"], "ref": t["ref"], "amount": t["amount"]}
        )
        for t in txns
    )
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=os.environ.get("AUDITA_BOOKS_MODEL", "gemini-2.5-flash"),
        contents=PROMPT.format(coa=coa_text, txns=txn_text),
    )
    text = (response.text or "").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    valid_codes = {a["code"] for a in accounts}
    valid_ids = {t["txn_id"] for t in txns}
    suggestions: dict[str, tuple[str, str]] = {}
    for item in json.loads(text):
        txn_id = str(item.get("txn_id", ""))
        code = str(item.get("account_code", ""))
        if txn_id in valid_ids and code in valid_codes:
            try:
                confidence = f"{float(item.get('confidence', 0)):.2f}"
            except (TypeError, ValueError):
                confidence = "0.00"
            suggestions[txn_id] = (code, confidence)
    return suggestions
