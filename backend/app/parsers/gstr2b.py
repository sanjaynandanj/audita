"""GSTR-2B parser.

Accepts the GST portal JSON download (b2b / b2ba / cdnr / cdnra / isd
sections under data.docdata) and a simplified CSV/XLSX fallback with the
same columns as the purchase register format.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..engine.models import InvoiceRecord, Source
from .tabular import parse_tabular


def _dec(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def parse_gstr2b(path: str | Path) -> list[InvoiceRecord]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _parse_portal_json(path)
    if suffix in (".csv", ".xlsx", ".xls"):
        return parse_tabular(path, source=Source.GSTR2B)
    raise ValueError(f"Unsupported GSTR-2B file type: {suffix}")


def _parse_portal_json(path: Path) -> list[InvoiceRecord]:
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)

    docdata = payload.get("data", {}).get("docdata", payload.get("docdata", {}))
    records: list[InvoiceRecord] = []

    for section, is_amendment, doc_type in (
        ("b2b", False, "INV"),
        ("b2ba", True, "INV"),
        ("cdnr", False, "CDN"),
        ("cdnra", True, "CDN"),
    ):
        for supplier in docdata.get(section, []) or []:
            ctin = supplier.get("ctin", "")
            trdnm = supplier.get("trdnm", "")
            docs = supplier.get("inv") or supplier.get("nt") or []
            for i, doc in enumerate(docs):
                inum = doc.get("inum") or doc.get("ntnum") or ""
                igst = cgst = sgst = cess = txval = Decimal("0")
                for item in doc.get("items", doc.get("itms", [])) or []:
                    det = item.get("itm_det", item)
                    txval += _dec(det.get("txval"))
                    igst += _dec(det.get("igst") or det.get("iamt"))
                    cgst += _dec(det.get("cgst") or det.get("camt"))
                    sgst += _dec(det.get("sgst") or det.get("samt"))
                    cess += _dec(det.get("cess") or det.get("csamt"))
                # Doc-level totals when no item breakup present
                if txval == 0:
                    txval = _dec(doc.get("txval") or doc.get("val"))
                if igst + cgst + sgst + cess == 0:
                    igst = _dec(doc.get("igst"))
                    cgst = _dec(doc.get("cgst"))
                    sgst = _dec(doc.get("sgst"))
                    cess = _dec(doc.get("cess"))
                records.append(
                    InvoiceRecord(
                        source=Source.GSTR2B,
                        gstin=ctin,
                        supplier_name=trdnm,
                        invoice_no=inum,
                        invoice_date=doc.get("dt", ""),
                        taxable_value=txval,
                        igst=igst,
                        cgst=cgst,
                        sgst=sgst,
                        cess=cess,
                        doc_type=doc_type,
                        reverse_charge=str(doc.get("rev", "N")).upper() == "Y",
                        is_amendment=is_amendment,
                        source_ref=f"{section}[{ctin}][{i}]",
                    )
                )

    for i, supplier in enumerate(docdata.get("isd", []) or []):
        ctin = supplier.get("ctin", "")
        for j, doc in enumerate(supplier.get("doclist", supplier.get("inv", [])) or []):
            records.append(
                InvoiceRecord(
                    source=Source.GSTR2B,
                    gstin=ctin,
                    supplier_name=supplier.get("trdnm", ""),
                    invoice_no=doc.get("docnum", doc.get("inum", "")),
                    invoice_date=doc.get("docdt", doc.get("dt", "")),
                    igst=_dec(doc.get("igst")),
                    cgst=_dec(doc.get("cgst")),
                    sgst=_dec(doc.get("sgst")),
                    cess=_dec(doc.get("cess")),
                    is_isd=True,
                    source_ref=f"isd[{i}][{j}]",
                )
            )

    return records
