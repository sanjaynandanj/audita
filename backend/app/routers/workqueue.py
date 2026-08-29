"""Agent Workspace (unified review queue) and operations feed."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends
from psycopg import Connection

from ..ap.store import InvoiceStore
from ..auth.deps import AuthContext, require_role
from ..books.store import LedgerStore
from ..close.workbook import CloseStore
from ..db import get_conn
from ..events.log import EventLog
from ..report.builder import ReportStore
from ..review.store import ReviewStore
from ..workqueue import build_workqueue
from .common import sign_report_id

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["workqueue"])


@router.get("/workqueue")
async def api_workqueue(
    ctx: AuthContext = Depends(require_role("viewer")),
    conn: Connection = Depends(get_conn),
):
    items = build_workqueue(
        report_store=ReportStore(conn, ctx.org_id),
        invoice_store=InvoiceStore(conn, ctx.org_id),
        ledger_store=LedgerStore(conn, ctx.org_id),
        close_store=CloseStore(conn, ctx.org_id),
        review_store=ReviewStore(conn, ctx.org_id),
        sign=sign_report_id,
    )
    by_agent: dict[str, int] = {}
    total_decisions = 0
    for item in items:
        by_agent[item.agent] = by_agent.get(item.agent, 0) + item.count
        total_decisions += item.count
    return {
        "items": [asdict(i) for i in items],
        "total_decisions": total_decisions,
        "by_agent": by_agent,
    }


@router.get("/operations")
async def api_operations(
    limit: int = 25,
    ctx: AuthContext = Depends(require_role("viewer")),
    conn: Connection = Depends(get_conn),
):
    return {"events": EventLog(conn, ctx.org_id).recent(limit)}
