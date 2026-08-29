"""ITC recon: upload GSTR-2B + purchase register, run the matching engine."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from psycopg import Connection

from ..auth.deps import AuthContext, require_role
from ..db import get_conn
from ..engine.matcher import match
from ..events.log import EventLog
from ..parsers import parse_gstr2b, parse_purchase_register
from ..report.builder import ReportStore, build_report
from .common import AGENT, save_upload, sign_report_id

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["recon"])


@router.post("/recon")
async def api_run_recon(
    client_name: str = Form(...),
    period_note: str = Form(""),
    gstr2b_file: UploadFile = File(...),
    register_file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_role("preparer")),
    conn: Connection = Depends(get_conn),
):
    events = EventLog(conn, ctx.org_id)
    g2b_path = await save_upload(gstr2b_file)
    reg_path = await save_upload(register_file)
    input_ref = f"gstr2b={gstr2b_file.filename};register={register_file.filename}"
    try:
        gstr2b_records = parse_gstr2b(g2b_path)
        books_records = parse_purchase_register(reg_path)
    except ValueError as exc:
        events.append(AGENT, "parse_failed", input_doc_ref=input_ref, output_ref=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    events.append(AGENT, "parsed", input_doc_ref=input_ref,
                  output_ref=f"books={len(books_records)};gstr2b={len(gstr2b_records)}")
    result = match(books_records, gstr2b_records)
    report = build_report(client_name.strip(), result, period_note.strip())
    ReportStore(conn, ctx.org_id).save(report)
    events.append(AGENT, "recon_completed", input_doc_ref=input_ref,
                  output_ref=report.report_id, actor=ctx.user.email)
    return {"report_id": report.report_id, "token": sign_report_id(report.report_id)}
