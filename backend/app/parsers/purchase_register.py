"""Purchase register parser (Tally CSV/XLSX exports)."""

from __future__ import annotations

from pathlib import Path

from ..engine.models import InvoiceRecord, Source
from .tabular import parse_tabular


def parse_purchase_register(path: str | Path) -> list[InvoiceRecord]:
    return parse_tabular(Path(path), source=Source.BOOKS)
