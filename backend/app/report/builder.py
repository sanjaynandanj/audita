"""Report model and store.

The headline rupee figure counts ONLY human-verified exceptions (design doc
accuracy bar). Unverified exceptions are shown as pending; unresolved items
are listed separately and never enter the headline.
"""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from psycopg import Connection
from psycopg.types.json import Jsonb

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


def _report_from_row(row: dict) -> Report:
    return Report(
        report_id=row["report_id"],
        client_name=row["client_name"],
        created_at=row["created_at"],
        period_note=row["period_note"],
        matched_count=row["matched_count"],
        matched_tax_total=row["matched_tax_total"],
        exceptions=[ExceptionItem(**e) for e in row["exceptions"]],
        missed_itc=[ExceptionItem(**e) for e in row["missed_itc"]],
        unresolved=[ExceptionItem(**e) for e in row["unresolved"]],
    )


def report_org(conn: Connection, report_id: str) -> str:
    """Owning org of a report reached via a signed link (no org in the URL)."""
    row = conn.execute("SELECT org_id FROM reports WHERE report_id = %s", (report_id,)).fetchone()
    if row is None:
        raise FileNotFoundError(report_id)
    return str(row["org_id"])


class ReportStore:
    def __init__(self, conn: Connection, org_id: str):
        self.conn = conn
        self.org_id = org_id

    def save(self, report: Report) -> None:
        data = asdict(report)
        self.conn.execute(
            """
            INSERT INTO reports (report_id, org_id, client_name, created_at, period_note,
                                 matched_count, matched_tax_total, exceptions, missed_itc, unresolved)
            VALUES (%(report_id)s, %(org_id)s, %(client_name)s, %(created_at)s, %(period_note)s,
                    %(matched_count)s, %(matched_tax_total)s, %(exceptions)s, %(missed_itc)s, %(unresolved)s)
            ON CONFLICT (report_id) DO UPDATE SET
                exceptions = EXCLUDED.exceptions,
                missed_itc = EXCLUDED.missed_itc,
                unresolved = EXCLUDED.unresolved
            """,
            {
                "report_id": report.report_id,
                "org_id": self.org_id,
                "client_name": report.client_name,
                "created_at": report.created_at,
                "period_note": report.period_note,
                "matched_count": report.matched_count,
                "matched_tax_total": report.matched_tax_total,
                "exceptions": Jsonb(data["exceptions"]),
                "missed_itc": Jsonb(data["missed_itc"]),
                "unresolved": Jsonb(data["unresolved"]),
            },
        )

    def load(self, report_id: str) -> Report:
        row = self.conn.execute(
            "SELECT * FROM reports WHERE report_id = %s AND org_id = %s",
            (report_id, self.org_id),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(report_id)
        return _report_from_row(row)

    def list(self) -> list[Report]:
        rows = self.conn.execute(
            "SELECT * FROM reports WHERE org_id = %s ORDER BY created_at", (self.org_id,)
        ).fetchall()
        return [_report_from_row(r) for r in rows]

    def verify_exception(
        self, report_id: str, exception_id: str, actor: str, ca_signoff: str = ""
    ) -> Report:
        row = self.conn.execute(
            "SELECT * FROM reports WHERE report_id = %s AND org_id = %s FOR UPDATE",
            (report_id, self.org_id),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(report_id)
        report = _report_from_row(row)
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
