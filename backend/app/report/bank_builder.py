"""Bank reconciliation report (BRS) model and store."""

from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

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
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, report_id: str) -> Path:
        if not report_id.isalnum():
            raise ValueError("invalid report id")
        return self.root / f"{report_id}.json"

    def save(self, report: BankReport) -> None:
        self._path(report.report_id).write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")

    def load(self, report_id: str) -> BankReport:
        data = json.loads(self._path(report_id).read_text(encoding="utf-8"))
        data["unrecorded"] = [BankItem(**i) for i in data.get("unrecorded", [])]
        data["uncleared"] = [BankItem(**i) for i in data.get("uncleared", [])]
        return BankReport(**data)
