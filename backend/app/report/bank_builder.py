"""Bank reconciliation report (BRS) model and store."""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from psycopg import Connection
from psycopg.types.json import Jsonb

from ..engine.bank import BankBucket, BankMatchResult


@dataclass
class BankItem:
    item_id: str
    bucket: str
    amount: str
    reason: str
    bank: dict | None
    books: dict | None


@dataclass
class BankReport:
    report_id: str
    client_name: str
    created_at: str
    period_note: str = ""
    matched_count: int = 0
    matched_total: str = "0"
    unrecorded: list[BankItem] = field(default_factory=list)     # bank_only
    uncleared: list[BankItem] = field(default_factory=list)      # books_only

    @property
    def unrecorded_total(self) -> Decimal:
        return sum((Decimal(i.amount) for i in self.unrecorded), Decimal("0"))

    @property
    def uncleared_total(self) -> Decimal:
        return sum((Decimal(i.amount) for i in self.uncleared), Decimal("0"))


def build_bank_report(client_name: str, result: BankMatchResult, period_note: str = "") -> BankReport:
    report = BankReport(
        report_id=secrets.token_hex(8),
        client_name=client_name,
        created_at=datetime.now(UTC).isoformat(),
        period_note=period_note,
    )
    matched = result.bucket(BankBucket.MATCHED)
    report.matched_count = len(matched)
    report.matched_total = str(sum((abs(p.amount) for p in matched), Decimal("0")))

    counter = 0
    for pair in result.pairs:
        if pair.bucket == BankBucket.MATCHED:
            continue
        counter += 1
        item = BankItem(
            item_id=f"B{counter:04d}",
            bucket=pair.bucket.value,
            amount=str(pair.amount),
            reason=pair.reason,
            bank=pair.bank.to_dict() if pair.bank else None,
            books=pair.books.to_dict() if pair.books else None,
        )
        if pair.bucket == BankBucket.BANK_ONLY:
            report.unrecorded.append(item)
        else:
            report.uncleared.append(item)
    return report


class BankReportStore:
    def __init__(self, conn: Connection, org_id: str):
        self.conn = conn
        self.org_id = org_id

    def save(self, report: BankReport) -> None:
        data = asdict(report)
        self.conn.execute(
            """
            INSERT INTO bank_reports (report_id, org_id, client_name, created_at, period_note,
                                      matched_count, matched_total, unrecorded, uncleared)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                report.report_id,
                self.org_id,
                report.client_name,
                report.created_at,
                report.period_note,
                report.matched_count,
                report.matched_total,
                Jsonb(data["unrecorded"]),
                Jsonb(data["uncleared"]),
            ),
        )

    def load(self, report_id: str) -> BankReport:
        row = self.conn.execute(
            "SELECT * FROM bank_reports WHERE report_id = %s AND org_id = %s",
            (report_id, self.org_id),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(report_id)
        return BankReport(
            report_id=row["report_id"],
            client_name=row["client_name"],
            created_at=row["created_at"],
            period_note=row["period_note"],
            matched_count=row["matched_count"],
            matched_total=row["matched_total"],
            unrecorded=[BankItem(**i) for i in row["unrecorded"]],
            uncleared=[BankItem(**i) for i in row["uncleared"]],
        )


def bank_report_org(conn: Connection, report_id: str) -> str:
    row = conn.execute("SELECT org_id FROM bank_reports WHERE report_id = %s", (report_id,)).fetchone()
    if row is None:
        raise FileNotFoundError(report_id)
    return str(row["org_id"])
