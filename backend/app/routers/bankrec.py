"""Bank reconciliation: statement vs books bank ledger."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from psycopg import Connection

from ..auth.deps import AuthContext, require_role
from ..db import get_conn
from ..engine.bank import match_bank
from ..events.log import EventLog
from ..parsers.bank import parse_bank_ledger, parse_bank_statement
from ..report.bank_builder import BankReportStore, build_bank_report
from .common import BANK_AGENT, bank_signer, save_upload

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["bankrec"])


@router.post("/bankrec")
async def api_run_bankrec(
    client_name: str = Form(...),
    period_note: str = Form(""),
    statement_file: UploadFile = File(...),
    ledger_file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_role("preparer")),
    conn: Connection = Depends(get_conn),
):
    events = EventLog(conn, ctx.org_id)
    stmt_path = await save_upload(statement_file)
    ledger_path = await save_upload(ledger_file)
    input_ref = f"statement={statement_file.filename};ledger={ledger_file.filename}"
    try:
        bank_txns = parse_bank_statement(stmt_path)
        book_txns = parse_bank_ledger(ledger_path)
    except ValueError as exc:
        events.append(BANK_AGENT, "parse_failed", input_doc_ref=input_ref, output_ref=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    events.append(BANK_AGENT, "parsed", input_doc_ref=input_ref,
                  output_ref=f"bank={len(bank_txns)};books={len(book_txns)}")
    result = match_bank(bank_txns, book_txns)
    report = build_bank_report(client_name.strip(), result, period_note.strip())
    BankReportStore(conn, ctx.org_id).save(report)
    events.append(BANK_AGENT, "bankrec_completed", input_doc_ref=input_ref,
                  output_ref=report.report_id, actor=ctx.user.email)
    return {"report_id": report.report_id, "token": bank_signer.dumps(report.report_id)}
