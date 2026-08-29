"""Invoice Agent — AP capture store.

A scanned/photographed purchase invoice becomes a draft with extracted
fields; a named human confirms (with optional CA sign-off) and the invoice
becomes an immutable row in the period's purchase register. Corrections
after confirmation are new events, never mutations (PRD-2 invariant #3).
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from psycopg import Connection
from psycopg.types.json import Jsonb

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

FIELD_KEYS = (
    "supplier_gstin",
    "supplier_name",
    "invoice_no",
    "invoice_date",
    "taxable_value",
    "igst",
    "cgst",
    "sgst",
    "cess",
    "total",
)
AMOUNT_KEYS = ("taxable_value", "igst", "cgst", "sgst", "cess", "total")


class AlreadyConfirmed(RuntimeError):
    pass


def _dec(value) -> Decimal:
    if value is None:
        return Decimal("0")
    text = str(value).strip().replace(",", "").replace("₹", "")
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(f"not a valid amount: {value!r}") from None


def normalize_fields(raw: dict, strict: bool = True) -> dict:
    """Coerce a fields payload (Vision output or human edit) to canonical shape.

    Amounts are validated as Decimal and stored as strings; unknown keys
    dropped; missing keys become empty/zero. strict=False (draft creation
    from Vision output) zeroes unparseable amounts instead of raising.
    """
    fields: dict[str, str] = {}
    for key in FIELD_KEYS:
        value = raw.get(key)
        if key in AMOUNT_KEYS:
            try:
                fields[key] = str(_dec(value))
            except ValueError:
                if strict:
                    raise
                fields[key] = "0"
        else:
            fields[key] = str(value or "").strip()
    return fields


@dataclass
class InvoiceDoc:
    invoice_id: str
    period: str                     # YYYY-MM
    created_at: str
    status: str                     # draft | confirmed
    source_file: str                # original upload filename
    stored_file: str                # saved artifact filename under files/
    extraction: str                 # vision | manual | failed
    fields: dict = field(default_factory=dict)
    extraction_note: str = ""
    confirmed_by: str = ""
    confirmed_at: str = ""
    ca_signoff: str = ""


_DOC_COLS = """invoice_id, period, created_at, status, source_file, scan_mime,
               extraction, fields, extraction_note, confirmed_by, confirmed_at, ca_signoff"""


def _doc_from_row(row: dict) -> InvoiceDoc:
    suffix = "." + row["scan_mime"].rpartition("/")[2].replace("jpeg", "jpg")
    return InvoiceDoc(
        invoice_id=row["invoice_id"],
        period=row["period"],
        created_at=row["created_at"],
        status=row["status"],
        source_file=row["source_file"],
        stored_file=f"{row['invoice_id']}{suffix}",
        extraction=row["extraction"],
        fields=row["fields"],
        extraction_note=row["extraction_note"],
        confirmed_by=row["confirmed_by"],
        confirmed_at=row["confirmed_at"],
        ca_signoff=row["ca_signoff"],
    )


class InvoiceStore:
    def __init__(self, conn: Connection, org_id: str):
        self.conn = conn
        self.org_id = org_id

    def create(
        self,
        period: str,
        source_file: str,
        suffix: str,
        data: bytes,
        extraction: str,
        fields: dict,
        extraction_note: str = "",
        mime: str = "",
    ) -> InvoiceDoc:
        if not PERIOD_RE.match(period):
            raise ValueError("period must be YYYY-MM")
        invoice_id = secrets.token_hex(8)
        mime = mime or f"application/{suffix.lstrip('.')}"
        row = self.conn.execute(
            f"""
            INSERT INTO invoices (invoice_id, org_id, period, created_at, status, source_file,
                                  scan, scan_mime, extraction, fields, extraction_note)
            VALUES (%s, %s, %s, %s, 'draft', %s, %s, %s, %s, %s, %s)
            RETURNING {_DOC_COLS}
            """,
            (
                invoice_id,
                self.org_id,
                period,
                datetime.now(UTC).isoformat(),
                source_file,
                data,
                mime,
                extraction,
                Jsonb(normalize_fields(fields, strict=False)),
                extraction_note,
            ),
        ).fetchone()
        return _doc_from_row(row)

    def load(self, invoice_id: str) -> InvoiceDoc:
        row = self.conn.execute(
            f"SELECT {_DOC_COLS} FROM invoices WHERE invoice_id = %s AND org_id = %s",
            (invoice_id, self.org_id),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(invoice_id)
        return _doc_from_row(row)

    def scan(self, invoice_id: str) -> tuple[bytes, str]:
        row = self.conn.execute(
            "SELECT scan, scan_mime FROM invoices WHERE invoice_id = %s AND org_id = %s",
            (invoice_id, self.org_id),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(invoice_id)
        return bytes(row["scan"]), row["scan_mime"]

    def list(self, period: str = "", status: str = "") -> list[InvoiceDoc]:
        query = f"SELECT {_DOC_COLS} FROM invoices WHERE org_id = %s"
        params: list = [self.org_id]
        if period:
            query += " AND period = %s"
            params.append(period)
        if status:
            query += " AND status = %s"
            params.append(status)
        query += " ORDER BY created_at DESC"
        return [_doc_from_row(r) for r in self.conn.execute(query, params).fetchall()]

    def confirm(
        self, invoice_id: str, fields: dict, actor: str, ca_signoff: str = ""
    ) -> InvoiceDoc:
        row = self.conn.execute(
            "SELECT status FROM invoices WHERE invoice_id = %s AND org_id = %s FOR UPDATE",
            (invoice_id, self.org_id),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(invoice_id)
        if row["status"] == "confirmed":
            raise AlreadyConfirmed(f"invoice {invoice_id} is already confirmed")
        fields = normalize_fields(fields)
        if not fields["supplier_gstin"] or not fields["invoice_no"]:
            raise ValueError("supplier_gstin and invoice_no are required to confirm")
        updated = self.conn.execute(
            f"""
            UPDATE invoices
            SET status = 'confirmed', fields = %s, confirmed_by = %s, confirmed_at = %s, ca_signoff = %s
            WHERE invoice_id = %s AND org_id = %s
            RETURNING {_DOC_COLS}
            """,
            (
                Jsonb(fields),
                actor,
                datetime.now(UTC).isoformat(),
                ca_signoff,
                invoice_id,
                self.org_id,
            ),
        ).fetchone()
        return _doc_from_row(updated)

    def periods(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT period FROM invoices WHERE org_id = %s ORDER BY period DESC",
            (self.org_id,),
        ).fetchall()
        return [r["period"] for r in rows]
