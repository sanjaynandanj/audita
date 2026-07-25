"""Invoice Agent — AP capture store.

A scanned/photographed purchase invoice becomes a draft with extracted
fields; a named human confirms (with optional CA sign-off) and the invoice
becomes an immutable row in the period's purchase register. Corrections
after confirmation are new events, never mutations (PRD-2 invariant #3).
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

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


class InvoiceStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.files_dir = self.root / "files"
        self.root.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, invoice_id: str) -> Path:
        if not invoice_id.isalnum():
            raise ValueError("invalid invoice id")
        return self.root / f"{invoice_id}.json"

    def create(
        self,
        period: str,
        source_file: str,
        suffix: str,
        data: bytes,
        extraction: str,
        fields: dict,
        extraction_note: str = "",
    ) -> InvoiceDoc:
        if not PERIOD_RE.match(period):
            raise ValueError("period must be YYYY-MM")
        invoice_id = secrets.token_hex(8)
        stored_file = f"{invoice_id}{suffix}"
        (self.files_dir / stored_file).write_bytes(data)
        doc = InvoiceDoc(
            invoice_id=invoice_id,
            period=period,
            created_at=datetime.now(UTC).isoformat(),
            status="draft",
            source_file=source_file,
            stored_file=stored_file,
            extraction=extraction,
            fields=normalize_fields(fields, strict=False),
            extraction_note=extraction_note,
        )
        self._save(doc)
        return doc

    def _save(self, doc: InvoiceDoc) -> None:
        self._path(doc.invoice_id).write_text(
            json.dumps(asdict(doc), indent=2), encoding="utf-8"
        )

    def load(self, invoice_id: str) -> InvoiceDoc:
        data = json.loads(self._path(invoice_id).read_text(encoding="utf-8"))
        return InvoiceDoc(**data)

    def list(self, period: str = "", status: str = "") -> list[InvoiceDoc]:
        docs = []
        for path in sorted(self.root.glob("*.json")):
            doc = InvoiceDoc(**json.loads(path.read_text(encoding="utf-8")))
            if period and doc.period != period:
                continue
            if status and doc.status != status:
                continue
            docs.append(doc)
        docs.sort(key=lambda d: d.created_at, reverse=True)
        return docs

    def confirm(
        self, invoice_id: str, fields: dict, actor: str, ca_signoff: str = ""
    ) -> InvoiceDoc:
        doc = self.load(invoice_id)
        if doc.status == "confirmed":
            raise AlreadyConfirmed(f"invoice {invoice_id} is already confirmed")
        fields = normalize_fields(fields)
        if not fields["supplier_gstin"] or not fields["invoice_no"]:
            raise ValueError("supplier_gstin and invoice_no are required to confirm")
        doc.fields = fields
        doc.status = "confirmed"
        doc.confirmed_by = actor
        doc.confirmed_at = datetime.now(UTC).isoformat()
        doc.ca_signoff = ca_signoff
        self._save(doc)
        return doc

    def periods(self) -> list[str]:
        return sorted({d.period for d in self.list()}, reverse=True)
