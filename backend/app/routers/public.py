"""Signed-link routes: anyone with a valid link can VIEW a report.

Verifying an exception is identity-backed — it requires a logged-in
reviewer (or owner) of the org that owns the report.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from psycopg import Connection

from ..auth.deps import current_user, require_role_for_org
from ..auth.service import User
from ..db import get_conn
from ..events.log import EventLog
from ..report.bank_builder import BankReport, BankReportStore, bank_report_org
from ..report.builder import Report, ReportStore, report_org
from ..report.excel import export_xlsx
from .common import AGENT, resolve_bank_token, resolve_token

router = APIRouter(tags=["public"])

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "report" / "templates"))


def _load_by_token(conn: Connection, token: str) -> tuple[Report, str]:
    report_id = resolve_token(token)
    try:
        org_id = report_org(conn, report_id)
        return ReportStore(conn, org_id).load(report_id), org_id
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Report not found.") from None


def _report_json(report: Report, token: str) -> dict:
    data = asdict(report)
    data.update(
        verified_at_risk=str(report.verified_at_risk),
        pending_at_risk=str(report.pending_at_risk),
        missed_itc_total=str(report.missed_itc_total),
        unresolved_total=str(report.unresolved_total),
        token=token,
        export_url=f"/r/{token}/export.xlsx",
    )
    return data


@router.get("/r/{token}", response_class=HTMLResponse, name="view_report")
async def view_report(request: Request, token: str, conn: Connection = Depends(get_conn)):
    report, org_id = _load_by_token(conn, token)
    return templates.TemplateResponse(
        request, "report.html",
        {"report": report, "token": token,
         "trail": EventLog(conn, org_id).for_output(report.report_id)},
    )


@router.get("/r/{token}/export.xlsx")
async def export_report(token: str, conn: Connection = Depends(get_conn)):
    report, org_id = _load_by_token(conn, token)
    EventLog(conn, org_id).append(AGENT, "report_exported", output_ref=report.report_id)
    return Response(
        content=export_xlsx(report),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="audita-{report.report_id}.xlsx"'},
    )


@router.get("/api/reports/{token}")
async def api_get_report(token: str, conn: Connection = Depends(get_conn)):
    report, org_id = _load_by_token(conn, token)
    return {"report": _report_json(report, token),
            "trail": EventLog(conn, org_id).for_output(report.report_id)}


@router.post("/api/reports/{token}/verify")
async def api_verify_exception(
    token: str,
    payload: dict = Body(...),
    user: User = Depends(current_user),
    conn: Connection = Depends(get_conn),
):
    report_id = resolve_token(token)
    exception_id = str(payload.get("exception_id", "")).strip()
    if not exception_id:
        raise HTTPException(status_code=400, detail="exception_id is required.")
    try:
        org_id = report_org(conn, report_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Report not found.") from None
    ctx = require_role_for_org(conn, user, org_id, "reviewer")
    try:
        report = ReportStore(conn, org_id).verify_exception(
            report_id, exception_id,
            actor=user.display_name,
            ca_signoff=user.ca_membership_no,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Exception not found.") from None
    events = EventLog(conn, ctx.org_id)
    events.append(AGENT, "exception_verified", input_doc_ref=exception_id,
                  output_ref=report_id, actor=user.email,
                  reviewed_by=user.ca_membership_no or user.email)
    return {"report": _report_json(report, token), "trail": events.for_output(report_id)}


def _bank_report_json(report: BankReport, token: str) -> dict:
    data = asdict(report)
    data.update(
        unrecorded_total=str(report.unrecorded_total),
        uncleared_total=str(report.uncleared_total),
        token=token,
    )
    return data


@router.get("/api/bankrec/{token}")
async def api_get_bankrec(token: str, conn: Connection = Depends(get_conn)):
    report_id = resolve_bank_token(token)
    try:
        org_id = bank_report_org(conn, report_id)
        report = BankReportStore(conn, org_id).load(report_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Report not found.") from None
    return {"report": _bank_report_json(report, token)}
