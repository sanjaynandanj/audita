"""Agent Workspace — the unified review queue (PRD-2 Phase 4).

One list of every pending human decision across all agents: unverified
recon exceptions, draft invoices, uncoded transactions, open close items,
unreviewed review flags. Aggregation only — nothing here mutates state,
and every figure is a sum over data the individual agents already gate.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from .ap.store import InvoiceStore
from .books.store import LedgerStore
from .close.workbook import CloseStore
from .report.builder import ReportStore
from .review.store import ReviewStore


@dataclass
class WorkItem:
    agent: str          # itc-recon | invoice | bookkeeping | close | review
    kind: str           # recon_exceptions | invoice_draft | txns_pending | close_open | review_flags
    title: str
    detail: str
    amount: str         # ₹ impact ("" when not meaningful)
    count: int          # pending decisions bundled in this item
    ref: str            # report id or period
    age_days: int
    link: str           # SPA deep link


def _age_days(created_at: str) -> int:
    if not created_at:
        return 0
    try:
        then = datetime.fromisoformat(created_at)
    except ValueError:
        return 0
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    return max(0, (datetime.now(UTC) - then).days)


def _recon_items(report_store: ReportStore, sign: Callable[[str], str]) -> list[WorkItem]:
    items: list[WorkItem] = []
    for report in report_store.list():
        pending = [e for e in report.exceptions if not e.verified]
        if not pending:
            continue
        total = sum((Decimal(e.itc_amount) for e in pending), Decimal("0"))
        items.append(WorkItem(
            agent="itc-recon",
            kind="recon_exceptions",
            title=f"{len(pending)} unverified ITC exception{'s' if len(pending) != 1 else ''} — "
                  f"{report.client_name}",
            detail=f"report {report.report_id}"
                   + (f" · {report.period_note}" if report.period_note else ""),
            amount=str(total),
            count=len(pending),
            ref=report.report_id,
            age_days=_age_days(report.created_at),
            link=f"/app/r/{sign(report.report_id)}",
        ))
    return items


def _invoice_items(invoice_store: InvoiceStore) -> list[WorkItem]:
    items: list[WorkItem] = []
    for doc in invoice_store.list(status="draft"):
        total = doc.fields.get("total", "0") or "0"
        supplier = doc.fields.get("supplier_name") or doc.source_file
        items.append(WorkItem(
            agent="invoice",
            kind="invoice_draft",
            title=f"Draft invoice: {supplier}",
            detail=f"{doc.period} · extraction {doc.extraction}",
            amount=total,
            count=1,
            ref=doc.invoice_id,
            age_days=_age_days(doc.created_at),
            link="/app/invoices",
        ))
    return items


def _books_items(ledger_store: LedgerStore) -> list[WorkItem]:
    items: list[WorkItem] = []
    for period in ledger_store.periods():
        ledger = ledger_store.load(period)
        pending = [t for t in ledger.txns if t.status == "pending"]
        if not pending:
            continue
        total = sum((Decimal(t.amount) for t in pending), Decimal("0"))
        items.append(WorkItem(
            agent="bookkeeping",
            kind="txns_pending",
            title=f"{len(pending)} transaction{'s await' if len(pending) != 1 else ' awaits'} coding — {period}",
            detail="rule misses queued for a named human",
            amount=str(total),
            count=len(pending),
            ref=period,
            age_days=_age_days(ledger.created_at),
            link="/app/books",
        ))
    return items


def _close_items(close_store: CloseStore) -> list[WorkItem]:
    items: list[WorkItem] = []
    for period in close_store.list_periods():
        wb = close_store.load_or_create(period)
        open_items = [i for i in wb.items if not i.done]
        # untouched workbooks are templates, fully ticked ones are done
        if not open_items or wb.done_count == 0:
            continue
        items.append(WorkItem(
            agent="close",
            kind="close_open",
            title=f"{len(open_items)} open close item{'s' if len(open_items) != 1 else ''} — {period}",
            detail="; ".join(i.title for i in open_items[:3])
                   + ("…" if len(open_items) > 3 else ""),
            amount="",
            count=len(open_items),
            ref=period,
            age_days=0,
            link="/app/close",
        ))
    return items


def _review_items(review_store: ReviewStore) -> list[WorkItem]:
    items: list[WorkItem] = []
    for period in review_store.periods():
        wb = review_store.load(period)
        pending = [f for f in wb.flags if f.status == "pending"]
        if not pending:
            continue
        total = sum((Decimal(f.amount) for f in pending), Decimal("0"))
        items.append(WorkItem(
            agent="review",
            kind="review_flags",
            title=f"{len(pending)} review flag{'s await' if len(pending) != 1 else ' awaits'} verification — {period}",
            detail="; ".join(f.title for f in pending[:2]) + ("…" if len(pending) > 2 else ""),
            amount=str(total),
            count=len(pending),
            ref=period,
            age_days=_age_days(wb.created_at),
            link="/app/review",
        ))
    return items


def build_workqueue(
    report_store: ReportStore,
    invoice_store: InvoiceStore,
    ledger_store: LedgerStore,
    close_store: CloseStore,
    review_store: ReviewStore,
    sign: Callable[[str], str],
) -> list[WorkItem]:
    items = (
        _recon_items(report_store, sign)
        + _invoice_items(invoice_store)
        + _books_items(ledger_store)
        + _close_items(close_store)
        + _review_items(review_store)
    )

    def sort_key(item: WorkItem):
        amount = abs(Decimal(item.amount)) if item.amount else Decimal("0")
        return (-amount, -item.age_days, item.agent, item.ref)

    items.sort(key=sort_key)
    return items
