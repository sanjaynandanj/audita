"""Bookkeeping Agent (transaction categorization)."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from psycopg import Connection

from ..auth.deps import AuthContext, require_role
from ..books.coa import ChartOfAccounts
from ..books.rules import RuleStore, apply_rules
from ..books.store import (
    PERIOD_RE,
    LedgerStore,
    build_ledger_csv,
    new_txn,
    summarize,
)
from ..books.store import (
    AlreadyConfirmed as TxnAlreadyConfirmed,
)
from ..db import get_conn
from ..events.log import EventLog
from ..parsers.bank import parse_bank_statement
from .common import BOOKS_AGENT, save_upload

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["books"])


def _ledger_response(conn: Connection, org_id: str, period: str) -> dict:
    ledger = LedgerStore(conn, org_id).load(period)
    names = {a.code: a.name for a in ChartOfAccounts(conn, org_id).list()}
    return {
        "ledger": {
            "period": ledger.period,
            "created_at": ledger.created_at,
            "txns": [asdict(t) for t in ledger.txns],
        },
        "summary": summarize(ledger),
        "account_names": names,
        "periods": LedgerStore(conn, org_id).periods(),
    }


@router.post("/books/{period}/transactions")
async def api_import_transactions(
    period: str,
    statement_file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_role("preparer")),
    conn: Connection = Depends(get_conn),
):
    from ..books.suggest import is_configured, suggest_accounts

    events = EventLog(conn, ctx.org_id)
    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")
    path = await save_upload(statement_file)
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

    rule_store = RuleStore(conn, ctx.org_id)
    ledger_store = LedgerStore(conn, ctx.org_id)
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
                  output_ref=f"{period};imported={imported};skipped={skipped}",
                  actor=ctx.user.email)
    if rule_hits:
        events.append(BOOKS_AGENT, "txn_categorized_rule",
                      input_doc_ref=statement_file.filename or "",
                      output_ref=f"{period};coded={rule_hits}")

    if is_configured():
        ledger = ledger_store.load(period)
        pending = [asdict(t) for t in ledger.txns
                   if t.status == "pending" and not t.suggested_account]
        if pending:
            coa = ChartOfAccounts(conn, ctx.org_id)
            try:
                suggestions = suggest_accounts(pending, [asdict(a) for a in coa.list()])
            except Exception:  # suggestions must never block the import
                suggestions = {}
            applied = ledger_store.suggest(period, suggestions)
            if applied:
                events.append(BOOKS_AGENT, "txn_category_suggested",
                              input_doc_ref=statement_file.filename or "",
                              output_ref=f"{period};suggested={applied}")

    return _ledger_response(conn, ctx.org_id, period)


@router.get("/books/coa")
async def api_get_coa(
    ctx: AuthContext = Depends(require_role("viewer")),
    conn: Connection = Depends(get_conn),
):
    return {"accounts": [asdict(a) for a in ChartOfAccounts(conn, ctx.org_id).list()]}


@router.post("/books/coa")
async def api_add_account(
    payload: dict = Body(...),
    ctx: AuthContext = Depends(require_role("preparer")),
    conn: Connection = Depends(get_conn),
):
    coa = ChartOfAccounts(conn, ctx.org_id)
    try:
        account = coa.add(
            str(payload.get("code", "")), str(payload.get("name", "")),
            str(payload.get("type", "")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    EventLog(conn, ctx.org_id).append(
        BOOKS_AGENT, "account_added", output_ref=f"{account.code} {account.name}",
        actor=ctx.user.email,
    )
    return {"accounts": [asdict(a) for a in coa.list()]}


@router.get("/books/rules")
async def api_get_rules(
    ctx: AuthContext = Depends(require_role("viewer")),
    conn: Connection = Depends(get_conn),
):
    return {"rules": [asdict(r) for r in RuleStore(conn, ctx.org_id).list()]}


@router.post("/books/rules")
async def api_add_rule(
    payload: dict = Body(...),
    ctx: AuthContext = Depends(require_role("preparer")),
    conn: Connection = Depends(get_conn),
):
    account_code = str(payload.get("account_code", "")).strip()
    try:
        ChartOfAccounts(conn, ctx.org_id).get(account_code)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown account code: {account_code!r}") from None
    rule_store = RuleStore(conn, ctx.org_id)
    try:
        rule = rule_store.add(
            str(payload.get("field", "description")), str(payload.get("contains", "")),
            account_code, created_by=ctx.user.display_name,
            priority=int(payload.get("priority", 100)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    EventLog(conn, ctx.org_id).append(
        BOOKS_AGENT, "rule_created",
        input_doc_ref=f"{rule.field} contains {rule.contains!r}",
        output_ref=f"rule={rule.rule_id};account={account_code}", actor=ctx.user.email,
    )
    return {"rules": [asdict(r) for r in rule_store.list()]}


@router.delete("/books/rules/{rule_id}")
async def api_delete_rule(
    rule_id: str,
    ctx: AuthContext = Depends(require_role("preparer")),
    conn: Connection = Depends(get_conn),
):
    rule_store = RuleStore(conn, ctx.org_id)
    try:
        rule = rule_store.remove(rule_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Rule not found.") from None
    EventLog(conn, ctx.org_id).append(
        BOOKS_AGENT, "rule_deleted",
        input_doc_ref=f"{rule.field} contains {rule.contains!r}",
        output_ref=f"rule={rule.rule_id}", actor=ctx.user.email,
    )
    return {"rules": [asdict(r) for r in rule_store.list()]}


@router.get("/books/{period}")
async def api_get_ledger(
    period: str,
    ctx: AuthContext = Depends(require_role("viewer")),
    conn: Connection = Depends(get_conn),
):
    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")
    return _ledger_response(conn, ctx.org_id, period)


@router.post("/books/{period}/txn/{txn_id}/confirm")
async def api_confirm_txn(
    period: str,
    txn_id: str,
    payload: dict = Body(...),
    ctx: AuthContext = Depends(require_role("preparer")),
    conn: Connection = Depends(get_conn),
):
    account_code = str(payload.get("account_code", "")).strip()
    rule_pattern = str(payload.get("rule_pattern", "")).strip()
    rule_field = str(payload.get("rule_field", "description")).strip() or "description"
    try:
        ChartOfAccounts(conn, ctx.org_id).get(account_code)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown account code: {account_code!r}") from None
    try:
        txn = LedgerStore(conn, ctx.org_id).confirm(
            period, txn_id, account_code, actor=ctx.user.display_name
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Transaction not found.") from None
    except TxnAlreadyConfirmed:
        raise HTTPException(
            status_code=409,
            detail="Categorization already confirmed. Record a correction as a new event.",
        ) from None
    events = EventLog(conn, ctx.org_id)
    events.append(BOOKS_AGENT, "txn_category_confirmed",
                  input_doc_ref=txn.source_ref,
                  output_ref=f"{period}/{txn_id};account={account_code}", actor=ctx.user.email)

    if rule_pattern:
        try:
            rule = RuleStore(conn, ctx.org_id).add(
                rule_field, rule_pattern, account_code, created_by=ctx.user.display_name
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        events.append(BOOKS_AGENT, "rule_created",
                      input_doc_ref=f"{rule.field} contains {rule.contains!r}",
                      output_ref=f"rule={rule.rule_id};account={account_code}",
                      actor=ctx.user.email)

    return _ledger_response(conn, ctx.org_id, period)


@router.get("/books/{period}/ledger.csv")
async def api_export_ledger(
    period: str,
    ctx: AuthContext = Depends(require_role("viewer")),
    conn: Connection = Depends(get_conn),
):
    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")
    ledger = LedgerStore(conn, ctx.org_id).load(period)
    names = {a.code: a.name for a in ChartOfAccounts(conn, ctx.org_id).list()}
    csv_text = build_ledger_csv(ledger, names)
    if csv_text.count("\n") <= 1:
        raise HTTPException(status_code=404, detail=f"No categorized transactions for {period}.")
    EventLog(conn, ctx.org_id).append(
        BOOKS_AGENT, "ledger_exported", input_doc_ref=period,
        output_ref=f"rows={csv_text.count(chr(10)) - 1}",
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audita-ledger-{period}.csv"'},
    )
