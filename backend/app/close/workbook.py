"""Month-end close workbook — the Close Agent's checklist per period."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from psycopg import Connection
from psycopg.types.json import Jsonb

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
    def __init__(self, conn: Connection, org_id: str):
        self.conn = conn
        self.org_id = org_id

    @staticmethod
    def _check_period(period: str) -> str:
        if not _PERIOD_RE.match(period):
            raise ValueError("period must be YYYY-MM")
        return period

    def load_or_create(self, period: str) -> CloseWorkbook:
        self._check_period(period)
        row = self.conn.execute(
            "SELECT items FROM close_workbooks WHERE org_id = %s AND period = %s",
            (self.org_id, period),
        ).fetchone()
        if row is not None:
            return CloseWorkbook(period=period, items=[CloseItem(**i) for i in row["items"]])
        wb = CloseWorkbook(period=period, items=[CloseItem(key=k, title=t) for k, t in DEFAULT_ITEMS])
        self.save(wb)
        return wb

    def save(self, wb: CloseWorkbook) -> None:
        self._check_period(wb.period)
        self.conn.execute(
            """
            INSERT INTO close_workbooks (org_id, period, created_at, items)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (org_id, period) DO UPDATE SET items = EXCLUDED.items
            """,
            (self.org_id, wb.period, datetime.now(UTC).isoformat(), Jsonb([asdict(i) for i in wb.items])),
        )

    def set_item(self, period: str, key: str, done: bool, actor: str, note: str = "") -> CloseWorkbook:
        self._check_period(period)
        self.conn.execute(
            "SELECT 1 FROM close_workbooks WHERE org_id = %s AND period = %s FOR UPDATE",
            (self.org_id, period),
        )
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
        rows = self.conn.execute(
            "SELECT period FROM close_workbooks WHERE org_id = %s ORDER BY period DESC",
            (self.org_id,),
        ).fetchall()
        return [r["period"] for r in rows]
