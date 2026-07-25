from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class Bucket(StrEnum):
    MATCHED = "matched"
    BOOKS_ONLY = "books_only"          # in purchase register, not in GSTR-2B -> ITC at risk
    GSTR2B_ONLY = "gstr2b_only"        # in GSTR-2B, not in books -> missed ITC
    MISMATCHED = "mismatched"          # paired but amounts differ beyond tolerance
    UNRESOLVED = "unresolved"          # ambiguous / CDN / amendment / RCM / ISD


class Source(StrEnum):
    BOOKS = "books"
    GSTR2B = "gstr2b"


_INVNO_CLEAN = re.compile(r"[^A-Z0-9]")


def normalize_gstin(gstin: str) -> str:
    return (gstin or "").strip().upper()


def normalize_invoice_no(inv: str) -> str:
    cleaned = _INVNO_CLEAN.sub("", (inv or "").strip().upper())
    return cleaned.lstrip("0") or cleaned


@dataclass
class InvoiceRecord:
    source: Source
    gstin: str
    invoice_no: str
    supplier_name: str = ""
    invoice_date: str = ""            # ISO or as-given; informational in Phase 1
    taxable_value: Decimal = Decimal("0")
    igst: Decimal = Decimal("0")
    cgst: Decimal = Decimal("0")
    sgst: Decimal = Decimal("0")
    cess: Decimal = Decimal("0")
    doc_type: str = "INV"             # INV | CDN
    reverse_charge: bool = False
    is_amendment: bool = False
    is_isd: bool = False
    source_ref: str = ""              # row number / json path for traceability

    @property
    def total_tax(self) -> Decimal:
        return self.igst + self.cgst + self.sgst + self.cess

    @property
    def gstin_norm(self) -> str:
        return normalize_gstin(self.gstin)

    @property
    def invoice_no_norm(self) -> str:
        return normalize_invoice_no(self.invoice_no)

    @property
    def special_reason(self) -> str | None:
        """Categories the design doc routes to unresolved in Phase 1."""
        if self.doc_type == "CDN":
            return "credit/debit note"
        if self.is_amendment:
            return "GSTR-2B amendment"
        if self.reverse_charge:
            return "reverse charge (RCM)"
        if self.is_isd:
            return "ISD credit"
        return None

    def to_dict(self) -> dict:
        return {
            "source": self.source.value,
            "gstin": self.gstin,
            "invoice_no": self.invoice_no,
            "supplier_name": self.supplier_name,
            "invoice_date": self.invoice_date,
            "taxable_value": str(self.taxable_value),
            "igst": str(self.igst),
            "cgst": str(self.cgst),
            "sgst": str(self.sgst),
            "cess": str(self.cess),
            "total_tax": str(self.total_tax),
            "doc_type": self.doc_type,
            "reverse_charge": self.reverse_charge,
            "is_amendment": self.is_amendment,
            "is_isd": self.is_isd,
            "source_ref": self.source_ref,
        }


@dataclass
class MatchPair:
    books: InvoiceRecord | None
    gstr2b: InvoiceRecord | None
    bucket: Bucket
    match_ratio: float | None = None
    reason: str = ""

    @property
    def itc_at_risk(self) -> Decimal:
        """Rupee amount at stake for this exception (0 for clean matches)."""
        if self.bucket == Bucket.BOOKS_ONLY and self.books:
            return self.books.total_tax
        if self.bucket == Bucket.GSTR2B_ONLY and self.gstr2b:
            return self.gstr2b.total_tax
        if self.bucket == Bucket.MISMATCHED and self.books and self.gstr2b:
            return abs(self.books.total_tax - self.gstr2b.total_tax)
        if self.bucket == Bucket.UNRESOLVED:
            rec = self.books or self.gstr2b
            return rec.total_tax if rec else Decimal("0")
        return Decimal("0")


@dataclass
class MatchResult:
    pairs: list[MatchPair] = field(default_factory=list)

    def bucket(self, bucket: Bucket) -> list[MatchPair]:
        return [p for p in self.pairs if p.bucket == bucket]
