"""Month-end close workbook — the Close Agent's checklist per period."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_ITEMS: list[tuple[str, str]] = [
    ("gst-itc-recon", "GST ITC reconciliation (GSTR-2B vs purchase register)"),
    ("bank-recon", "Bank reconciliation (statement vs bank ledger)"),
    ("gstr1-books", "GSTR-1 vs sales register tie-out"),
    ("tds", "TDS deducted, deposited, and returns reconciled"),
    ("accruals", "Accruals and provisions posted"),
    ("prepaid", "Prepaid expenses amortised"),
    ("depreciation", "Depreciation run posted"),
    ("intercompany", "Related-party / inter-company balances confirmed"),
    ("payables-review", "Creditors ageing reviewed, debit balances explained"),
    ("receivables-review", "Debtors ageing reviewed, credit balances explained"),
    ("suspense", "Suspense account emptied"),
    ("workpapers", "Workpapers filed with source references"),
]

_PERIOD_RE = re.compile(r"^[0-9]{4}-[0-9]{2}$")


@dataclass
class CloseItem:
    key: str
    title: str
    done: bool = False
    done_by: str = ""
    done_at: str = ""
    note: str = ""


@dataclass
class CloseWorkbook:
    period: str                    # YYYY-MM
    items: list[CloseItem] = field(default_factory=list)

    @property
    def done_count(self) -> int:
        return sum(1 for i in self.items if i.done)


class CloseStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, period: str) -> Path:
        if not _PERIOD_RE.match(period):
            raise ValueError("period must be YYYY-MM")
        return self.root / f"{period}.json"

    def load_or_create(self, period: str) -> CloseWorkbook:
        path = self._path(period)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return CloseWorkbook(period=data["period"], items=[CloseItem(**i) for i in data["items"]])
        wb = CloseWorkbook(period=period, items=[CloseItem(key=k, title=t) for k, t in DEFAULT_ITEMS])
        self.save(wb)
        return wb

    def save(self, wb: CloseWorkbook) -> None:
        self._path(wb.period).write_text(json.dumps(asdict(wb), indent=2), encoding="utf-8")

    def set_item(self, period: str, key: str, done: bool, actor: str, note: str = "") -> CloseWorkbook:
        wb = self.load_or_create(period)
        for item in wb.items:
            if item.key == key:
                item.done = done
                item.done_by = actor if done else ""
                item.done_at = datetime.now(UTC).isoformat() if done else ""
                if note:
                    item.note = note
                self.save(wb)
                return wb
        raise KeyError(f"close item {key} not found")

    def list_periods(self) -> list[str]:
        return sorted((p.stem for p in self.root.glob("*.json")), reverse=True)
