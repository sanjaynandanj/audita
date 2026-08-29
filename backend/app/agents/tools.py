"""Tool functions exposed to the ADK agent.

The deterministic engine does the matching — the agent orchestrates and
explains. Precision lives in code, not in the model.

The conversational agent runs outside a web session, so it works inside
one org set via AUDITA_AGENT_ORG_ID (the org UUID).
"""

from __future__ import annotations

import os
from decimal import Decimal

from ..db import open_pool
from ..engine.matcher import match
from ..parsers import parse_gstr2b, parse_purchase_register
from ..report.builder import ReportStore, build_report


def _org() -> str:
    org = os.environ.get("AUDITA_AGENT_ORG_ID", "").strip()
    if not org:
        raise RuntimeError(
            "Set AUDITA_AGENT_ORG_ID to the org UUID this agent session works in."
        )
    return org


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
    with open_pool().connection() as conn:
        ReportStore(conn, _org()).save(report)
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
    with open_pool().connection() as conn:
        report = ReportStore(conn, _org()).load(report_id)
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
    """List all reconciliation reports in this workspace.

    Returns:
        List of dicts with report_id, client_name, and created_at.
    """
    with open_pool().connection() as conn:
        reports = ReportStore(conn, _org()).list()
    return [
        {
            "report_id": r.report_id,
            "client_name": r.client_name,
            "created_at": r.created_at,
            "pending_at_risk_inr": str(r.pending_at_risk),
        }
        for r in reports
    ]


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
    with open_pool().connection() as conn:
        BankReportStore(conn, _org()).save(report)
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

    org = _org()
    with open_pool().connection() as conn:
        items = build_workqueue(
            report_store=ReportStore(conn, org),
            invoice_store=InvoiceStore(conn, org),
            ledger_store=LedgerStore(conn, org),
            close_store=CloseStore(conn, org),
            review_store=ReviewStore(conn, org),
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

    with open_pool().connection() as conn:
        store = InvoiceStore(conn, _org())
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

    with open_pool().connection() as conn:
        ledger = LedgerStore(conn, _org()).load(period)
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

    with open_pool().connection() as conn:
        wb = CloseStore(conn, _org()).load_or_create(period)
    return {
        "period": wb.period,
        "done": wb.done_count,
        "total": len(wb.items),
        "open_items": [i.title for i in wb.items if not i.done],
        "completed_items": [f"{i.title} ({i.done_by})" for i in wb.items if i.done],
    }
