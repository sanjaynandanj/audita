"""Invoice Agent (AP capture pipeline)."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from psycopg import Connection

from ..ap.register import build_register_csv
from ..ap.store import PERIOD_RE, AlreadyConfirmed, InvoiceStore
from ..auth.deps import AuthContext, require_role
from ..db import get_conn
from ..events.log import EventLog
from .common import INVOICE_AGENT, check_upload_size

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["invoices"])

_INVOICE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


@router.post("/invoices")
async def api_upload_invoice(
    period: str = Form(...),
    invoice_file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_role("preparer")),
    conn: Connection = Depends(get_conn),
):
    from ..vision.gemini import extract_invoice_fields, is_configured

    events = EventLog(conn, ctx.org_id)
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
    data = check_upload_size(await invoice_file.read())

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

    doc = InvoiceStore(conn, ctx.org_id).create(
        period=period,
        source_file=invoice_file.filename or "upload",
        suffix=suffix,
        data=data,
        extraction=extraction,
        fields=fields,
        extraction_note=note,
        mime=mime,
    )

    events.append(INVOICE_AGENT, "invoice_uploaded",
                  input_doc_ref=doc.source_file, output_ref=doc.invoice_id, actor=ctx.user.email)
    if extraction == "vision":
        events.append(INVOICE_AGENT, "invoice_extracted",
                      input_doc_ref=doc.source_file, output_ref=doc.invoice_id)
    return {"invoice": asdict(doc)}


@router.get("/invoices")
async def api_list_invoices(
    period: str = "",
    status: str = "",
    ctx: AuthContext = Depends(require_role("viewer")),
    conn: Connection = Depends(get_conn),
):
    store = InvoiceStore(conn, ctx.org_id)
    docs = store.list(period=period.strip(), status=status.strip())
    return {"invoices": [asdict(d) for d in docs], "periods": store.periods()}


@router.get("/invoices/{invoice_id}")
async def api_get_invoice(
    invoice_id: str,
    ctx: AuthContext = Depends(require_role("viewer")),
    conn: Connection = Depends(get_conn),
):
    try:
        doc = InvoiceStore(conn, ctx.org_id).load(invoice_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="Invoice not found.") from None
    return {"invoice": asdict(doc), "trail": EventLog(conn, ctx.org_id).for_output(invoice_id)}


@router.get("/invoices/{invoice_id}/scan")
async def api_get_invoice_scan(
    invoice_id: str,
    ctx: AuthContext = Depends(require_role("viewer")),
    conn: Connection = Depends(get_conn),
):
    try:
        data, mime = InvoiceStore(conn, ctx.org_id).scan(invoice_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="Invoice not found.") from None
    return Response(content=data, media_type=mime)


@router.post("/invoices/{invoice_id}/confirm")
async def api_confirm_invoice(
    invoice_id: str,
    payload: dict = Body(...),
    ctx: AuthContext = Depends(require_role("preparer")),
    conn: Connection = Depends(get_conn),
):
    fields = payload.get("fields") or {}
    if not isinstance(fields, dict):
        raise HTTPException(status_code=400, detail="fields must be an object.")
    try:
        doc = InvoiceStore(conn, ctx.org_id).confirm(
            invoice_id, fields,
            actor=ctx.user.display_name,
            ca_signoff=ctx.user.ca_membership_no,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Invoice not found.") from None
    except AlreadyConfirmed:
        raise HTTPException(
            status_code=409,
            detail="Invoice already confirmed. Record a correction as a new invoice.",
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    events = EventLog(conn, ctx.org_id)
    events.append(INVOICE_AGENT, "invoice_confirmed",
                  input_doc_ref=doc.source_file, output_ref=doc.invoice_id,
                  actor=ctx.user.email,
                  reviewed_by=ctx.user.ca_membership_no or ctx.user.email)
    return {"invoice": asdict(doc), "trail": events.for_output(invoice_id)}


@router.get("/registers/{period}.csv")
async def api_export_register(
    period: str,
    ctx: AuthContext = Depends(require_role("viewer")),
    conn: Connection = Depends(get_conn),
):
    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")
    confirmed = InvoiceStore(conn, ctx.org_id).list(period=period, status="confirmed")
    if not confirmed:
        raise HTTPException(status_code=404, detail=f"No confirmed invoices for {period}.")
    EventLog(conn, ctx.org_id).append(
        INVOICE_AGENT, "register_exported",
        input_doc_ref=period, output_ref=f"invoices={len(confirmed)}",
    )
    return Response(
        content=build_register_csv(confirmed),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audita-register-{period}.csv"'},
    )
