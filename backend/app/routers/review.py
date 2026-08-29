"""Review Agent (monthly financial review)."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection

from ..ap.store import InvoiceStore
from ..auth.deps import AuthContext, require_role
from ..books.coa import ChartOfAccounts
from ..books.store import PERIOD_RE, LedgerStore
from ..db import get_conn
from ..events.log import EventLog
from ..review.compute import ReviewWorkbook, compute_flags, compute_pnl, prior_period_of
from ..review.store import AlreadyVerified, ReviewStore
from .common import REVIEW_AGENT

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["review"])


def _workbook_json(wb: ReviewWorkbook) -> dict:
    data = asdict(wb)
    data["verified_count"] = wb.verified_count
    data["pending_count"] = wb.pending_count
    return data


def _register_tax_total(conn: Connection, org_id: str, period: str) -> Decimal | None:
    confirmed = InvoiceStore(conn, org_id).list(period=period, status="confirmed")
    if not confirmed:
        return None
    total = Decimal("0")
    for doc in confirmed:
        for key in ("igst", "cgst", "sgst", "cess"):
            total += Decimal(doc.fields.get(key, "0") or "0")
    return total


@router.post("/review/{period}")
async def api_build_review(
    period: str,
    ctx: AuthContext = Depends(require_role("preparer")),
    conn: Connection = Depends(get_conn),
):
    from ..review.narrate import is_configured, narrate_review

    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")
    ledger_store = LedgerStore(conn, ctx.org_id)
    review_store = ReviewStore(conn, ctx.org_id)
    events = EventLog(conn, ctx.org_id)
    current = ledger_store.load(period)
    if not any(t.status in ("coded", "confirmed") for t in current.txns):
        raise HTTPException(
            status_code=400,
            detail=f"No categorized transactions for {period}. Code the books first.",
        )
    prior_period = prior_period_of(period)
    prior = ledger_store.load(prior_period)
    accounts = ChartOfAccounts(conn, ctx.org_id).list()

    pnl, summary = compute_pnl(current, prior, accounts)
    flags = compute_flags(current, prior, accounts,
                          gst_register_tax_total=_register_tax_total(conn, ctx.org_id, period))
    wb = ReviewWorkbook(
        period=period,
        prior_period=prior_period,
        created_at="",
        pnl=pnl,
        summary=summary,
        flags=flags,
        txn_counts={
            "current": sum(1 for t in current.txns if t.status in ("coded", "confirmed")),
            "prior": sum(1 for t in prior.txns if t.status in ("coded", "confirmed")),
        },
    )
    wb = review_store.save_new(wb)
    events.append(REVIEW_AGENT, "review_computed",
                  input_doc_ref=f"{prior_period}..{period}",
                  output_ref=f"{period};flags={len(wb.flags)}", actor=ctx.user.email)

    if is_configured():
        try:
            narrative = narrate_review(_workbook_json(wb))
            wb = review_store.set_narrative(period, narrative)
            events.append(REVIEW_AGENT, "review_narrated", output_ref=period)
        except Exception as exc:  # narration must never block the computed workbook
            wb = review_store.set_narrative(period, "", note=f"Narration failed: {exc}")
    else:
        wb = review_store.set_narrative(
            period, "", note="Narration not configured — computed tables stand alone."
        )

    return {"workbook": _workbook_json(wb), "periods": review_store.periods()}


@router.get("/review/{period}")
async def api_get_review(
    period: str,
    ctx: AuthContext = Depends(require_role("viewer")),
    conn: Connection = Depends(get_conn),
):
    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")
    review_store = ReviewStore(conn, ctx.org_id)
    if not review_store.exists(period):
        raise HTTPException(status_code=404, detail=f"No review workbook for {period} yet.")
    wb = review_store.load(period)
    return {"workbook": _workbook_json(wb), "periods": review_store.periods()}


@router.post("/review/{period}/flags/{flag_id}/verify")
async def api_verify_flag(
    period: str,
    flag_id: str,
    ctx: AuthContext = Depends(require_role("reviewer")),
    conn: Connection = Depends(get_conn),
):
    review_store = ReviewStore(conn, ctx.org_id)
    try:
        review_store.verify_flag(
            period, flag_id,
            actor=ctx.user.display_name,
            ca_signoff=ctx.user.ca_membership_no,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Review workbook not found.") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="Flag not found.") from None
    except AlreadyVerified:
        raise HTTPException(status_code=409, detail="Flag already verified.") from None
    EventLog(conn, ctx.org_id).append(
        REVIEW_AGENT, "review_flag_verified",
        input_doc_ref=flag_id, output_ref=period,
        actor=ctx.user.email,
        reviewed_by=ctx.user.ca_membership_no or ctx.user.email,
    )
    wb = review_store.load(period)
    return {"workbook": _workbook_json(wb), "periods": review_store.periods()}
