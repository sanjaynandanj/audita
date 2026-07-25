"""Purchase-register CSV built from confirmed invoices.

Headers are chosen from parsers/tabular.py COLUMN_ALIASES so the export
round-trips through the existing purchase-register parser into ITC recon.
"""

from __future__ import annotations

import csv
import io

from .store import InvoiceDoc

HEADERS = [
    "Supplier GSTIN",
    "Invoice No",
    "Invoice Date",
    "Party Name",
    "Taxable Value",
    "IGST",
    "CGST",
    "SGST",
    "Cess",
    "Reverse Charge",
]


def build_register_csv(invoices: list[InvoiceDoc]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(HEADERS)
    for doc in invoices:
        if doc.status != "confirmed":
            continue
        f = doc.fields
        writer.writerow([
            f.get("supplier_gstin", ""),
            f.get("invoice_no", ""),
            f.get("invoice_date", ""),
            f.get("supplier_name", ""),
            f.get("taxable_value", "0"),
            f.get("igst", "0"),
            f.get("cgst", "0"),
            f.get("sgst", "0"),
            f.get("cess", "0"),
            "N",
        ])
    return buf.getvalue()
