"""Tool functions exposed to the ADK agent.

The deterministic engine does the matching — the agent orchestrates and
explains. Precision lives in code, not in the model.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from .. import config
from ..engine.matcher import match
from ..parsers import parse_gstr2b, parse_purchase_register
from ..report.builder import ReportStore, build_report


def run_reconciliation(gstr2b_path: str, register_path: str, client_name: str) -> dict:
    """Run a GST ITC reconciliation.

    Args:
        gstr2b_path: Path to the GSTR-2B file (portal JSON, CSV, or XLSX).
        register_path: Path to the purchase register export (CSV or XLSX).
        client_name: Name of the business being reconciled.

    Returns:
        Summary dict with report_id, bucket counts, and rupee totals.
    """
    gstr2b_records = parse_gstr2b(gstr2b_path)
    books_records = parse_purchase_register(register_path)
    result = match(books_records, gstr2b_records)
    report = build_report(client_name, result)
    ReportStore(config.REPORTS_DIR).save(report)
    return {
        "report_id": report.report_id,
        "matched": report.matched_count,
        "exceptions_at_risk": len(report.exceptions),
        "pending_at_risk_inr": str(report.pending_at_risk),
        "missed_itc_inr": str(report.missed_itc_total),
        "unresolved": len(report.unresolved),
        "note": "Headline counts only human-verified exceptions; all amounts start as pending.",
    }


def get_report_summary(report_id: str) -> dict:
    """Fetch the summary of an existing reconciliation report.

    Args:
        report_id: The report identifier returned by run_reconciliation.

    Returns:
        Summary dict with totals and per-exception one-liners.
    """
    report = ReportStore(config.REPORTS_DIR).load(report_id)
    return {
        "report_id": report.report_id,
        "client_name": report.client_name,
        "verified_at_risk_inr": str(report.verified_at_risk),
        "pending_at_risk_inr": str(report.pending_at_risk),
        "missed_itc_inr": str(report.missed_itc_total),
        "exceptions": [
            {
                "id": e.exception_id,
                "bucket": e.bucket,
                "amount_inr": e.itc_amount,
                "supplier": ((e.books or e.gstr2b or {}).get("supplier_name", "")
                             if isinstance(e.books or e.gstr2b, dict) else ""),
                "verified": e.verified,
            }
            for e in report.exceptions
        ],
    }


def list_reports() -> list[dict]:
    """List all reconciliation reports on this machine.

    Returns:
        List of dicts with report_id, client_name, and created_at.
    """
    out = []
    reports_dir = Path(config.REPORTS_DIR)
    if not reports_dir.exists():
        return out
    for path in sorted(reports_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pending = sum(
                (Decimal(e["itc_amount"]) for e in data.get("exceptions", []) if not e.get("verified")),
                Decimal("0"),
            )
            out.append({
                "report_id": data["report_id"],
                "client_name": data["client_name"],
                "created_at": data["created_at"],
                "pending_at_risk_inr": str(pending),
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return out


def run_bank_reconciliation(statement_path: str, ledger_path: str, client_name: str) -> dict:
    """Run a bank reconciliation (statement vs books bank ledger).

    Args:
        statement_path: Path to the bank statement (CSV or XLSX).
        ledger_path: Path to the books-side bank ledger export (CSV or XLSX).
        client_name: Name of the business being reconciled.

    Returns:
        Summary dict with report_id, matched count, and outstanding items.
    """
    from ..engine.bank import match_bank
    from ..parsers.bank import parse_bank_ledger, parse_bank_statement
    from ..report.bank_builder import BankReportStore, build_bank_report

    bank_txns = parse_bank_statement(statement_path)
    book_txns = parse_bank_ledger(ledger_path)
    result = match_bank(bank_txns, book_txns)
    report = build_bank_report(client_name, result)
    BankReportStore(config.BANKREC_DIR).save(report)
    return {
        "report_id": report.report_id,
        "matched": report.matched_count,
        "unrecorded_in_books": len(report.unrecorded),
        "unrecorded_total_inr": str(report.unrecorded_total),
        "uncleared_or_in_transit": len(report.uncleared),
        "uncleared_total_inr": str(report.uncleared_total),
    }


def get_workqueue() -> dict:
    """Get every pending human decision across all Audita agents.

    Returns:
        Dict with total pending decision count, per-agent counts, and the
        queue items (agent, title, amount in INR, age in days).
    """
    from ..ap.store import InvoiceStore
    from ..books.store import LedgerStore
    from ..close.workbook import CloseStore
    from ..review.store import ReviewStore
    from ..workqueue import build_workqueue

    items = build_workqueue(
        reports_dir=Path(config.REPORTS_DIR),
        invoice_store=InvoiceStore(config.INVOICES_DIR),
        ledger_store=LedgerStore(config.BOOKS_DIR / "ledgers"),
        close_store=CloseStore(config.CLOSE_DIR),
        review_store=ReviewStore(config.REVIEW_DIR),
        sign=lambda report_id: report_id,  # agent chat has no link surface
    )
    by_agent: dict[str, int] = {}
    for item in items:
        by_agent[item.agent] = by_agent.get(item.agent, 0) + item.count
    return {
        "total_pending_decisions": sum(i.count for i in items),
        "by_agent": by_agent,
        "items": [
            {"agent": i.agent, "title": i.title, "detail": i.detail,
             "amount_inr": i.amount, "count": i.count, "age_days": i.age_days}
            for i in items
        ],
        "note": "Every item needs a named human decision before it can enter a headline.",
    }


def get_invoice_status(period: str) -> dict:
    """Get Invoice Agent status for a period: drafts awaiting confirmation
    and confirmed register rows.

    Args:
        period: The period in YYYY-MM format, e.g. "2026-07".

    Returns:
        Dict with draft/confirmed counts and per-invoice one-liners.
    """
    from ..ap.store import InvoiceStore

    store = InvoiceStore(config.INVOICES_DIR)
    drafts = store.list(period=period, status="draft")
    confirmed = store.list(period=period, status="confirmed")
    return {
        "period": period,
        "drafts_awaiting_confirmation": len(drafts),
        "confirmed_in_register": len(confirmed),
        "drafts": [
            {"invoice_id": d.invoice_id,
             "supplier": d.fields.get("supplier_name") or d.source_file,
             "total_inr": d.fields.get("total", "0"), "extraction": d.extraction}
            for d in drafts
        ],
        "confirmed_total_inr": str(sum(
            (Decimal(d.fields.get("total", "0") or "0") for d in confirmed), Decimal("0")
        )),
    }


def get_ledger_status(period: str) -> dict:
    """Get Bookkeeping Agent status for a period: coding progress and
    per-account totals from the categorized ledger.

    Args:
        period: The period in YYYY-MM format, e.g. "2026-07".

    Returns:
        Dict with coded/confirmed/pending counts and account totals
        (coded + confirmed entries only; pending never enters a total).
    """
    from ..books.store import LedgerStore, summarize

    ledger = LedgerStore(config.BOOKS_DIR / "ledgers").load(period)
    summary = summarize(ledger)
    return {
        "period": period,
        "transactions": summary["txn_count"],
        "coded_by_rules": summary["coded_count"],
        "human_confirmed": summary["confirmed_count"],
        "awaiting_review": summary["pending_count"],
        "account_totals_inr": summary["accounts"],
        "note": "Account totals include only rule-coded and human-confirmed entries.",
    }


def get_close_status(period: str) -> dict:
    """Get the month-end close workbook status for a period.

    Args:
        period: The period in YYYY-MM format, e.g. "2026-04".

    Returns:
        Dict with done/total counts and the list of open items.
    """
    from ..close.workbook import CloseStore

    wb = CloseStore(config.CLOSE_DIR).load_or_create(period)
    return {
        "period": wb.period,
        "done": wb.done_count,
        "total": len(wb.items),
        "open_items": [i.title for i in wb.items if not i.done],
        "completed_items": [f"{i.title} ({i.done_by})" for i in wb.items if i.done],
    }
