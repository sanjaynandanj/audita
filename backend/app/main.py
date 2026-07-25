"""Audita — GST ITC recon agent (Phase 1).

Upload GSTR-2B + purchase register -> matching engine -> report behind a
signed expiring link -> CA verifies exceptions -> headline counts only
verified rupees. Every step lands in the append-only event log.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict as _asdict
from decimal import Decimal
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import config
from .ap.register import build_register_csv
from .ap.store import PERIOD_RE, AlreadyConfirmed, InvoiceStore
from .books.coa import ChartOfAccounts
from .books.rules import RuleStore, apply_rules
from .books.store import (
    AlreadyConfirmed as TxnAlreadyConfirmed,
)
from .books.store import (
    LedgerStore,
    build_ledger_csv,
    new_txn,
    summarize,
)
from .close.workbook import CloseStore
from .engine.bank import match_bank
from .engine.matcher import match
from .events.log import EventLog
from .parsers import parse_gstr2b, parse_purchase_register
from .parsers.bank import parse_bank_ledger, parse_bank_statement
from .report.bank_builder import BankReport, BankReportStore, build_bank_report
from .report.builder import Report, ReportStore, build_report
from .report.excel import export_xlsx
from .review.compute import (
    ReviewWorkbook,
    compute_flags,
    compute_pnl,
    prior_period_of,
)
from .review.store import AlreadyVerified, ReviewStore
from .workqueue import build_workqueue

app = FastAPI(title="Audita", docs_url=None, redoc_url=None)
_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "AUDITA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Production: serve the built React app from AUDITA_STATIC_DIR (see Dockerfile).
_static_dir = Path(os.environ.get("AUDITA_STATIC_DIR", ""))
SPA_ENABLED = _static_dir.is_dir() and (_static_dir / "index.html").is_file()
if SPA_ENABLED:
    app.mount("/assets", StaticFiles(directory=_static_dir / "assets"), name="assets")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "report" / "templates"))

store = ReportStore(config.REPORTS_DIR)
events = EventLog(config.EVENTS_DB)
signer = URLSafeTimedSerializer(config.secret_key(), salt="audita-report-link")

AGENT = "itc-recon-agent/0.1"


def sign_report_id(report_id: str) -> str:
    return signer.dumps(report_id)


def resolve_token(token: str) -> str:
    try:
        return signer.loads(token, max_age=config.LINK_MAX_AGE_SECONDS)
    except SignatureExpired:
        raise HTTPException(status_code=410, detail="This report link has expired. Ask for a fresh link.") from None
    except BadSignature:
        raise HTTPException(status_code=404, detail="Invalid report link.") from None


async def _save_upload(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "upload").suffix.lower()
    if suffix not in (".json", ".csv", ".xlsx", ".xls"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=config.UPLOADS_DIR, suffix=suffix, delete=False) as tmp:
        tmp.write(await upload.read())
        return Path(tmp.name)


@app.get("/", response_class=HTMLResponse)
async def upload_form(request: Request):
    if SPA_ENABLED:
        return FileResponse(_static_dir / "index.html")
    return templates.TemplateResponse(request, "upload.html", {})


@app.post("/recon", response_class=HTMLResponse)
async def run_recon(
    request: Request,
    client_name: str = Form(...),
    period_note: str = Form(""),
    gstr2b_file: UploadFile = File(...),
    register_file: UploadFile = File(...),
):
    g2b_path = await _save_upload(gstr2b_file)
    reg_path = await _save_upload(register_file)
    input_ref = f"gstr2b={gstr2b_file.filename};register={register_file.filename}"

    try:
        gstr2b_records = parse_gstr2b(g2b_path)
        books_records = parse_purchase_register(reg_path)
    except ValueError as exc:
        events.append(AGENT, "parse_failed", input_doc_ref=input_ref, output_ref=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    events.append(
        AGENT, "parsed",
        input_doc_ref=input_ref,
        output_ref=f"books={len(books_records)};gstr2b={len(gstr2b_records)}",
    )

    result = match(books_records, gstr2b_records)
    report = build_report(client_name.strip(), result, period_note.strip())
    store.save(report)
    events.append(AGENT, "recon_completed", input_doc_ref=input_ref, output_ref=report.report_id)

    token = sign_report_id(report.report_id)
    link = str(request.url_for("view_report", token=token))
    return templates.TemplateResponse(
        request, "created.html",
        {"report": report, "link": link, "expiry_days": config.LINK_MAX_AGE_SECONDS // 86400},
    )


@app.get("/r/{token}", response_class=HTMLResponse, name="view_report")
async def view_report(request: Request, token: str):
    report_id = resolve_token(token)
    try:
        report = store.load(report_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Report not found.") from None
    return templates.TemplateResponse(
        request, "report.html",
        {"report": report, "token": token, "trail": events.for_output(report_id)},
    )


@app.post("/r/{token}/verify")
async def verify_exception(
    token: str,
    exception_id: str = Form(...),
    actor: str = Form(...),
    ca_signoff: str = Form(""),
):
    report_id = resolve_token(token)
    actor = actor.strip()
    if not actor:
        raise HTTPException(status_code=400, detail="Verifier name is required.")
    try:
        store.verify_exception(report_id, exception_id, actor=actor, ca_signoff=ca_signoff.strip())
    except KeyError:
        raise HTTPException(status_code=404, detail="Exception not found.") from None
    events.append(
        AGENT, "exception_verified",
        input_doc_ref=exception_id, output_ref=report_id,
        actor=actor, reviewed_by=ca_signoff.strip() or actor,
    )
    return RedirectResponse(url=f"/r/{token}", status_code=303)


@app.get("/r/{token}/export.xlsx")
async def export_report(token: str):
    report_id = resolve_token(token)
    report = store.load(report_id)
    events.append(AGENT, "report_exported", output_ref=report_id)
    return Response(
        content=export_xlsx(report),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="audita-{report_id}.xlsx"'},
    )


# ---------------------------------------------------------------------------
# JSON API (consumed by the React frontend)
# ---------------------------------------------------------------------------

def _report_json(report: Report, token: str) -> dict:
    from dataclasses import asdict

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


@app.post("/api/recon")
async def api_run_recon(
    client_name: str = Form(...),
    period_note: str = Form(""),
    gstr2b_file: UploadFile = File(...),
    register_file: UploadFile = File(...),
):
    g2b_path = await _save_upload(gstr2b_file)
    reg_path = await _save_upload(register_file)
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
    store.save(report)
    events.append(AGENT, "recon_completed", input_doc_ref=input_ref, output_ref=report.report_id)
    token = sign_report_id(report.report_id)
    return {"report_id": report.report_id, "token": token}


@app.get("/api/reports/{token}")
async def api_get_report(token: str):
    report_id = resolve_token(token)
    try:
        report = store.load(report_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Report not found.") from None
    return {"report": _report_json(report, token), "trail": events.for_output(report_id)}


@app.post("/api/reports/{token}/verify")
async def api_verify_exception(token: str, payload: dict = Body(...)):
    report_id = resolve_token(token)
    exception_id = str(payload.get("exception_id", "")).strip()
    actor = str(payload.get("actor", "")).strip()
    ca_signoff = str(payload.get("ca_signoff", "")).strip()
    if not actor or not exception_id:
        raise HTTPException(status_code=400, detail="exception_id and actor are required.")
    try:
        report = store.verify_exception(report_id, exception_id, actor=actor, ca_signoff=ca_signoff)
    except KeyError:
        raise HTTPException(status_code=404, detail="Exception not found.") from None
    events.append(AGENT, "exception_verified", input_doc_ref=exception_id,
                  output_ref=report_id, actor=actor, reviewed_by=ca_signoff or actor)
    return {"report": _report_json(report, token), "trail": events.for_output(report_id)}


# ---------------------------------------------------------------------------
# Bank reconciliation, close workbook, operations feed
# ---------------------------------------------------------------------------


bank_store = BankReportStore(config.BANKREC_DIR)
close_store = CloseStore(config.CLOSE_DIR)
bank_signer = URLSafeTimedSerializer(config.secret_key(), salt="audita-bankrec-link")

BANK_AGENT = "bank-recon-agent/0.1"
CLOSE_AGENT = "close-agent/0.1"


def _bank_report_json(report: BankReport, token: str) -> dict:
    data = _asdict(report)
    data.update(
        unrecorded_total=str(report.unrecorded_total),
        uncleared_total=str(report.uncleared_total),
        token=token,
    )
    return data


def _resolve_bank_token(token: str) -> str:
    try:
        return bank_signer.loads(token, max_age=config.LINK_MAX_AGE_SECONDS)
    except SignatureExpired:
        raise HTTPException(status_code=410, detail="This report link has expired.") from None
    except BadSignature:
        raise HTTPException(status_code=404, detail="Invalid report link.") from None


@app.post("/api/bankrec")
async def api_run_bankrec(
    client_name: str = Form(...),
    period_note: str = Form(""),
    statement_file: UploadFile = File(...),
    ledger_file: UploadFile = File(...),
):
    stmt_path = await _save_upload(statement_file)
    ledger_path = await _save_upload(ledger_file)
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
    bank_store.save(report)
    events.append(BANK_AGENT, "bankrec_completed", input_doc_ref=input_ref, output_ref=report.report_id)
    return {"report_id": report.report_id, "token": bank_signer.dumps(report.report_id)}


@app.get("/api/bankrec/{token}")
async def api_get_bankrec(token: str):
    report_id = _resolve_bank_token(token)
    try:
        report = bank_store.load(report_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Report not found.") from None
    return {"report": _bank_report_json(report, token)}


@app.get("/api/close/{period}")
async def api_get_close(period: str):
    try:
        wb = close_store.load_or_create(period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"workbook": _asdict(wb), "done_count": wb.done_count, "periods": close_store.list_periods()}


@app.post("/api/close/{period}/item")
async def api_set_close_item(period: str, payload: dict = Body(...)):
    key = str(payload.get("key", "")).strip()
    done = bool(payload.get("done", False))
    actor = str(payload.get("actor", "")).strip()
    note = str(payload.get("note", "")).strip()
    if done and not actor:
        raise HTTPException(status_code=400, detail="actor is required to mark an item done.")
    try:
        wb = close_store.set_item(period, key, done, actor, note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="Close item not found.") from None
    events.append(CLOSE_AGENT, "close_item_done" if done else "close_item_reopened",
                  input_doc_ref=f"{period}/{key}", output_ref=period, actor=actor)
    return {"workbook": _asdict(wb), "done_count": wb.done_count, "periods": close_store.list_periods()}


# ---------------------------------------------------------------------------
# Invoice Agent (AP capture pipeline) — PRD-2 Phase 1
# ---------------------------------------------------------------------------

invoice_store = InvoiceStore(config.INVOICES_DIR)

INVOICE_AGENT = "invoice-agent/0.1"

_INVOICE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


def _invoice_json(doc) -> dict:
    return _asdict(doc)


@app.post("/api/invoices")
async def api_upload_invoice(
    period: str = Form(...),
    invoice_file: UploadFile = File(...),
):
    from .vision.gemini import extract_invoice_fields, is_configured

    period = period.strip()
    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")
    suffix = Path(invoice_file.filename or "upload").suffix.lower()
    mime = _INVOICE_MIME.get(suffix)
    if mime is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported invoice file type: {suffix}. Use JPG, PNG, WEBP or PDF.",
        )
    data = await invoice_file.read()

    fields: dict = {}
    extraction = "manual"
    note = "Vision not configured — enter fields manually."
    if is_configured():
        try:
            fields = extract_invoice_fields(data, mime_type=mime)
            extraction = "vision"
            note = ""
        except Exception as exc:  # extraction must never block capture
            extraction = "failed"
            note = f"Extraction failed: {exc}"

    doc = invoice_store.create(
        period=period,
        source_file=invoice_file.filename or "upload",
        suffix=suffix,
        data=data,
        extraction=extraction,
        fields=fields,
        extraction_note=note,
    )

    events.append(INVOICE_AGENT, "invoice_uploaded",
                  input_doc_ref=doc.source_file, output_ref=doc.invoice_id)
    if extraction == "vision":
        events.append(INVOICE_AGENT, "invoice_extracted",
                      input_doc_ref=doc.source_file, output_ref=doc.invoice_id)
    return {"invoice": _invoice_json(doc)}


@app.get("/api/invoices")
async def api_list_invoices(period: str = "", status: str = ""):
    docs = invoice_store.list(period=period.strip(), status=status.strip())
    return {
        "invoices": [_invoice_json(d) for d in docs],
        "periods": invoice_store.periods(),
    }


@app.get("/api/invoices/{invoice_id}")
async def api_get_invoice(invoice_id: str):
    try:
        doc = invoice_store.load(invoice_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="Invoice not found.") from None
    return {"invoice": _invoice_json(doc), "trail": events.for_output(invoice_id)}


@app.post("/api/invoices/{invoice_id}/confirm")
async def api_confirm_invoice(invoice_id: str, payload: dict = Body(...)):
    actor = str(payload.get("actor", "")).strip()
    ca_signoff = str(payload.get("ca_signoff", "")).strip()
    fields = payload.get("fields") or {}
    if not actor:
        raise HTTPException(status_code=400, detail="actor is required to confirm an invoice.")
    if not isinstance(fields, dict):
        raise HTTPException(status_code=400, detail="fields must be an object.")
    try:
        doc = invoice_store.confirm(invoice_id, fields, actor=actor, ca_signoff=ca_signoff)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Invoice not found.") from None
    except AlreadyConfirmed:
        raise HTTPException(
            status_code=409,
            detail="Invoice already confirmed. Record a correction as a new invoice.",
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    events.append(INVOICE_AGENT, "invoice_confirmed",
                  input_doc_ref=doc.source_file, output_ref=doc.invoice_id,
                  actor=actor, reviewed_by=ca_signoff or actor)
    return {"invoice": _invoice_json(doc), "trail": events.for_output(invoice_id)}


@app.get("/api/registers/{period}.csv")
async def api_export_register(period: str):
    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")
    confirmed = invoice_store.list(period=period, status="confirmed")
    if not confirmed:
        raise HTTPException(status_code=404, detail=f"No confirmed invoices for {period}.")
    events.append(INVOICE_AGENT, "register_exported",
                  input_doc_ref=period, output_ref=f"invoices={len(confirmed)}")
    return Response(
        content=build_register_csv(confirmed),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audita-register-{period}.csv"'},
    )


# ---------------------------------------------------------------------------
# Bookkeeping Agent (transaction categorization) — PRD-2 Phase 2
# ---------------------------------------------------------------------------

coa = ChartOfAccounts(config.BOOKS_DIR / "coa.json")
rule_store = RuleStore(config.BOOKS_DIR / "rules.json")
ledger_store = LedgerStore(config.BOOKS_DIR / "ledgers")

BOOKS_AGENT = "bookkeeping-agent/0.1"


def _ledger_response(period: str) -> dict:
    ledger = ledger_store.load(period)
    names = {a.code: a.name for a in coa.list()}
    return {
        "ledger": {
            "period": ledger.period,
            "created_at": ledger.created_at,
            "txns": [_asdict(t) for t in ledger.txns],
        },
        "summary": summarize(ledger),
        "account_names": names,
        "periods": ledger_store.periods(),
    }


@app.post("/api/books/{period}/transactions")
async def api_import_transactions(period: str, statement_file: UploadFile = File(...)):
    from .books.suggest import is_configured, suggest_accounts

    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")
    path = await _save_upload(statement_file)
    try:
        bank_txns = parse_bank_statement(path)
    except ValueError as exc:
        events.append(BOOKS_AGENT, "parse_failed",
                      input_doc_ref=statement_file.filename or "", output_ref=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    txns = [
        new_txn(t.txn_date, t.description, t.ref, t.amount,
                f"{statement_file.filename}:{t.source_ref.split(':')[-1]}")
        for t in bank_txns
    ]

    rules = rule_store.list()
    rule_hits = 0
    for txn in txns:
        rule = apply_rules(rules, txn.description, txn.ref)
        if rule is not None:
            txn.status = "coded"
            txn.source = "rule"
            txn.account_code = rule.account_code
            txn.rule_id = rule.rule_id
            rule_hits += 1

    _, imported, skipped = ledger_store.import_txns(period, txns)
    events.append(BOOKS_AGENT, "txn_imported",
                  input_doc_ref=statement_file.filename or "",
                  output_ref=f"{period};imported={imported};skipped={skipped}")
    if rule_hits:
        events.append(BOOKS_AGENT, "txn_categorized_rule",
                      input_doc_ref=statement_file.filename or "",
                      output_ref=f"{period};coded={rule_hits}")

    if is_configured():
        ledger = ledger_store.load(period)
        pending = [_asdict(t) for t in ledger.txns
                   if t.status == "pending" and not t.suggested_account]
        if pending:
            try:
                suggestions = suggest_accounts(pending, [_asdict(a) for a in coa.list()])
            except Exception:  # suggestions must never block the import
                suggestions = {}
            applied = ledger_store.suggest(period, suggestions)
            if applied:
                events.append(BOOKS_AGENT, "txn_category_suggested",
                              input_doc_ref=statement_file.filename or "",
                              output_ref=f"{period};suggested={applied}")

    return _ledger_response(period)


@app.get("/api/books/coa")
async def api_get_coa():
    return {"accounts": [_asdict(a) for a in coa.list()]}


@app.post("/api/books/coa")
async def api_add_account(payload: dict = Body(...)):
    try:
        account = coa.add(
            str(payload.get("code", "")), str(payload.get("name", "")),
            str(payload.get("type", "")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    events.append(BOOKS_AGENT, "account_added", output_ref=f"{account.code} {account.name}")
    return {"accounts": [_asdict(a) for a in coa.list()]}


@app.get("/api/books/rules")
async def api_get_rules():
    return {"rules": [_asdict(r) for r in rule_store.list()]}


@app.post("/api/books/rules")
async def api_add_rule(payload: dict = Body(...)):
    actor = str(payload.get("actor", "")).strip()
    account_code = str(payload.get("account_code", "")).strip()
    if not actor:
        raise HTTPException(status_code=400, detail="actor is required to create a rule.")
    try:
        coa.get(account_code)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown account code: {account_code!r}") from None
    try:
        rule = rule_store.add(
            str(payload.get("field", "description")), str(payload.get("contains", "")),
            account_code, created_by=actor,
            priority=int(payload.get("priority", 100)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    events.append(BOOKS_AGENT, "rule_created",
                  input_doc_ref=f"{rule.field} contains {rule.contains!r}",
                  output_ref=f"rule={rule.rule_id};account={account_code}", actor=actor)
    return {"rules": [_asdict(r) for r in rule_store.list()]}


@app.delete("/api/books/rules/{rule_id}")
async def api_delete_rule(rule_id: str, actor: str = ""):
    if not actor.strip():
        raise HTTPException(status_code=400, detail="actor is required to delete a rule.")
    try:
        rule = rule_store.remove(rule_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Rule not found.") from None
    events.append(BOOKS_AGENT, "rule_deleted",
                  input_doc_ref=f"{rule.field} contains {rule.contains!r}",
                  output_ref=f"rule={rule.rule_id}", actor=actor.strip())
    return {"rules": [_asdict(r) for r in rule_store.list()]}


@app.get("/api/books/{period}")
async def api_get_ledger(period: str):
    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")
    return _ledger_response(period)


@app.post("/api/books/{period}/txn/{txn_id}/confirm")
async def api_confirm_txn(period: str, txn_id: str, payload: dict = Body(...)):
    actor = str(payload.get("actor", "")).strip()
    account_code = str(payload.get("account_code", "")).strip()
    rule_pattern = str(payload.get("rule_pattern", "")).strip()
    rule_field = str(payload.get("rule_field", "description")).strip() or "description"
    if not actor:
        raise HTTPException(status_code=400, detail="actor is required to confirm a categorization.")
    try:
        coa.get(account_code)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown account code: {account_code!r}") from None
    try:
        txn = ledger_store.confirm(period, txn_id, account_code, actor=actor)
    except KeyError:
        raise HTTPException(status_code=404, detail="Transaction not found.") from None
    except TxnAlreadyConfirmed:
        raise HTTPException(
            status_code=409,
            detail="Categorization already confirmed. Record a correction as a new event.",
        ) from None
    events.append(BOOKS_AGENT, "txn_category_confirmed",
                  input_doc_ref=txn.source_ref,
                  output_ref=f"{period}/{txn_id};account={account_code}", actor=actor)

    if rule_pattern:
        try:
            rule = rule_store.add(rule_field, rule_pattern, account_code, created_by=actor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        events.append(BOOKS_AGENT, "rule_created",
                      input_doc_ref=f"{rule.field} contains {rule.contains!r}",
                      output_ref=f"rule={rule.rule_id};account={account_code}", actor=actor)

    return _ledger_response(period)


@app.get("/api/books/{period}/ledger.csv")
async def api_export_ledger(period: str):
    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")
    ledger = ledger_store.load(period)
    names = {a.code: a.name for a in coa.list()}
    csv_text = build_ledger_csv(ledger, names)
    if csv_text.count("\n") <= 1:
        raise HTTPException(status_code=404, detail=f"No categorized transactions for {period}.")
    events.append(BOOKS_AGENT, "ledger_exported", input_doc_ref=period,
                  output_ref=f"rows={csv_text.count(chr(10)) - 1}")
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audita-ledger-{period}.csv"'},
    )


# ---------------------------------------------------------------------------
# Review Agent (monthly financial review) — PRD-2 Phase 3
# ---------------------------------------------------------------------------

review_store = ReviewStore(config.REVIEW_DIR)

REVIEW_AGENT = "review-agent/0.1"


def _workbook_json(wb: ReviewWorkbook) -> dict:
    data = _asdict(wb)
    data["verified_count"] = wb.verified_count
    data["pending_count"] = wb.pending_count
    return data


def _register_tax_total(period: str) -> Decimal | None:
    confirmed = invoice_store.list(period=period, status="confirmed")
    if not confirmed:
        return None
    total = Decimal("0")
    for doc in confirmed:
        for key in ("igst", "cgst", "sgst", "cess"):
            total += Decimal(doc.fields.get(key, "0") or "0")
    return total


@app.post("/api/review/{period}")
async def api_build_review(period: str):
    from .review.narrate import is_configured, narrate_review

    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")
    current = ledger_store.load(period)
    if not any(t.status in ("coded", "confirmed") for t in current.txns):
        raise HTTPException(
            status_code=400,
            detail=f"No categorized transactions for {period}. Code the books first.",
        )
    prior_period = prior_period_of(period)
    prior = ledger_store.load(prior_period)
    accounts = coa.list()

    pnl, summary = compute_pnl(current, prior, accounts)
    flags = compute_flags(current, prior, accounts,
                          gst_register_tax_total=_register_tax_total(period))
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
                  output_ref=f"{period};flags={len(wb.flags)}")

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


@app.get("/api/review/{period}")
async def api_get_review(period: str):
    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")
    if not review_store.exists(period):
        raise HTTPException(status_code=404, detail=f"No review workbook for {period} yet.")
    wb = review_store.load(period)
    return {"workbook": _workbook_json(wb), "periods": review_store.periods()}


@app.post("/api/review/{period}/flags/{flag_id}/verify")
async def api_verify_flag(period: str, flag_id: str, payload: dict = Body(...)):
    actor = str(payload.get("actor", "")).strip()
    ca_signoff = str(payload.get("ca_signoff", "")).strip()
    if not actor:
        raise HTTPException(status_code=400, detail="actor is required to verify a flag.")
    try:
        review_store.verify_flag(period, flag_id, actor=actor, ca_signoff=ca_signoff)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Review workbook not found.") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="Flag not found.") from None
    except AlreadyVerified:
        raise HTTPException(status_code=409, detail="Flag already verified.") from None
    events.append(REVIEW_AGENT, "review_flag_verified",
                  input_doc_ref=flag_id, output_ref=period,
                  actor=actor, reviewed_by=ca_signoff or actor)
    wb = review_store.load(period)
    return {"workbook": _workbook_json(wb), "periods": review_store.periods()}


# ---------------------------------------------------------------------------
# Agent Workspace (unified review queue) — PRD-2 Phase 4
# ---------------------------------------------------------------------------

@app.get("/api/workqueue")
async def api_workqueue():
    items = build_workqueue(
        reports_dir=Path(config.REPORTS_DIR),
        invoice_store=invoice_store,
        ledger_store=ledger_store,
        close_store=close_store,
        review_store=review_store,
        sign=sign_report_id,
    )
    by_agent: dict[str, int] = {}
    total_decisions = 0
    for item in items:
        by_agent[item.agent] = by_agent.get(item.agent, 0) + item.count
        total_decisions += item.count
    return {
        "items": [_asdict(i) for i in items],
        "total_decisions": total_decisions,
        "by_agent": by_agent,
    }


@app.get("/api/operations")
async def api_operations(limit: int = 25):
    return {"events": events.recent(limit)}


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "spa": SPA_ENABLED}


if SPA_ENABLED:
    @app.get("/app", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/app/{rest:path}", response_class=HTMLResponse, include_in_schema=False)
    async def spa_fallback(rest: str = ""):
        return FileResponse(_static_dir / "index.html")
