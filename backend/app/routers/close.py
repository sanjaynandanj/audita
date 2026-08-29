"""Month-end close workbook."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Body, Depends, HTTPException
from psycopg import Connection

from ..auth.deps import AuthContext, require_role
from ..close.workbook import CloseStore
from ..db import get_conn
from ..events.log import EventLog
from .common import CLOSE_AGENT

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["close"])


def _payload(store: CloseStore, wb) -> dict:
    return {"workbook": asdict(wb), "done_count": wb.done_count, "periods": store.list_periods()}


@router.get("/close/{period}")
async def api_get_close(
    period: str,
    ctx: AuthContext = Depends(require_role("viewer")),
    conn: Connection = Depends(get_conn),
):
    store = CloseStore(conn, ctx.org_id)
    try:
        wb = store.load_or_create(period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _payload(store, wb)


@router.post("/close/{period}/item")
async def api_set_close_item(
    period: str,
    payload: dict = Body(...),
    ctx: AuthContext = Depends(require_role("preparer")),
    conn: Connection = Depends(get_conn),
):
    key = str(payload.get("key", "")).strip()
    done = bool(payload.get("done", False))
    note = str(payload.get("note", "")).strip()
    store = CloseStore(conn, ctx.org_id)
    try:
        wb = store.set_item(period, key, done, ctx.user.display_name, note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="Close item not found.") from None
    EventLog(conn, ctx.org_id).append(
        CLOSE_AGENT, "close_item_done" if done else "close_item_reopened",
        input_doc_ref=f"{period}/{key}", output_ref=period, actor=ctx.user.email,
    )
    return _payload(store, wb)
