"""Report model and store.

The headline rupee figure counts ONLY human-verified exceptions (design doc
accuracy bar). Unverified exceptions are shown as pending; unresolved items
are listed separately and never enter the headline.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from ..engine.models import Bucket, MatchResult

# Buckets that count as "exceptions" a CA can verify into the headline
EXCEPTION_BUCKETS = (Bucket.BOOKS_ONLY, Bucket.MISMATCHED)


@dataclass
class ExceptionItem:
    exception_id: str
    bucket: str
    itc_amount: str                 # Decimal serialized as str
    reason: str
    books: dict | None
    gstr2b: dict | None
    match_ratio: float | None = None
    verified: bool = False
    verified_by: str = ""
    verified_at: str = ""
    ca_signoff: str = ""            # sign-off column — name/membership no. of signing CA


@dataclass
class Report:
    report_id: str
    client_name: str
    created_at: str
    period_note: str = ""
    matched_count: int = 0
    matched_tax_total: str = "0"
    exceptions: list[ExceptionItem] = field(default_factory=list)      # books_only + mismatched
    missed_itc: list[ExceptionItem] = field(default_factory=list)      # gstr2b_only (unbooked credit)
    unresolved: list[ExceptionItem] = field(default_factory=list)

    # --- headline math -----------------------------------------------------
    @property
    def verified_at_risk(self) -> Decimal:
        return sum((Decimal(e.itc_amount) for e in self.exceptions if e.verified), Decimal("0"))

    @property
    def pending_at_risk(self) -> Decimal:
        return sum((Decimal(e.itc_amount) for e in self.exceptions if not e.verified), Decimal("0"))

    @property
    def missed_itc_total(self) -> Decimal:
        return sum((Decimal(e.itc_amount) for e in self.missed_itc), Decimal("0"))

    @property
    def unresolved_total(self) -> Decimal:
        return sum((Decimal(e.itc_amount) for e in self.unresolved), Decimal("0"))

    @property
    def all_items(self) -> list[ExceptionItem]:
        return self.exceptions + self.missed_itc + self.unresolved

    def find(self, exception_id: str) -> ExceptionItem | None:
        for item in self.all_items:
            if item.exception_id == exception_id:
                return item
        return None


def build_report(client_name: str, result: MatchResult, period_note: str = "") -> Report:
    report = Report(
        report_id=secrets.token_hex(8),
        client_name=client_name,
        created_at=datetime.now(UTC).isoformat(),
        period_note=period_note,
    )
    matched = result.bucket(Bucket.MATCHED)
    report.matched_count = len(matched)
    report.matched_tax_total = str(
        sum((p.books.total_tax for p in matched if p.books), Decimal("0"))
    )

    counter = 0
    for pair in result.pairs:
        if pair.bucket == Bucket.MATCHED:
            continue
        counter += 1
        item = ExceptionItem(
            exception_id=f"E{counter:04d}",
            bucket=pair.bucket.value,
            itc_amount=str(pair.itc_at_risk),
            reason=pair.reason,
            books=pair.books.to_dict() if pair.books else None,
            gstr2b=pair.gstr2b.to_dict() if pair.gstr2b else None,
            match_ratio=pair.match_ratio,
        )
        if pair.bucket in EXCEPTION_BUCKETS:
            report.exceptions.append(item)
        elif pair.bucket == Bucket.GSTR2B_ONLY:
            report.missed_itc.append(item)
        else:
            report.unresolved.append(item)
    return report


class ReportStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, report_id: str) -> Path:
        if not report_id.isalnum():
            raise ValueError("invalid report id")
        return self.root / f"{report_id}.json"

    def save(self, report: Report) -> None:
        self._path(report.report_id).write_text(
            json.dumps(asdict(report), indent=2), encoding="utf-8"
        )

    def load(self, report_id: str) -> Report:
        data = json.loads(self._path(report_id).read_text(encoding="utf-8"))
        data["exceptions"] = [ExceptionItem(**e) for e in data.get("exceptions", [])]
        data["missed_itc"] = [ExceptionItem(**e) for e in data.get("missed_itc", [])]
        data["unresolved"] = [ExceptionItem(**e) for e in data.get("unresolved", [])]
        return Report(**data)

    def verify_exception(
        self, report_id: str, exception_id: str, actor: str, ca_signoff: str = ""
    ) -> Report:
        report = self.load(report_id)
        item = report.find(exception_id)
        if item is None:
            raise KeyError(f"exception {exception_id} not found")
        item.verified = True
        item.verified_by = actor
        item.verified_at = datetime.now(UTC).isoformat()
        if ca_signoff:
            item.ca_signoff = ca_signoff
        self.save(report)
        return report
