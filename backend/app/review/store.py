"""Review workbook store.

One row per (org, period). Rebuilding a workbook recomputes every figure
but preserves verification state for flags whose flag_id still exists
(flag_ids are content-derived, so an unchanged finding keeps its sign-off;
a changed finding returns to pending)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from psycopg import Connection
from psycopg.types.json import Jsonb

from ..books.store import PERIOD_RE
from .compute import PnlLine, ReviewFlag, ReviewWorkbook


class AlreadyVerified(RuntimeError):
    pass


class ReviewStore:
    def __init__(self, conn: Connection, org_id: str):
        self.conn = conn
        self.org_id = org_id

    @staticmethod
    def _check_period(period: str) -> str:
        if not PERIOD_RE.match(period):
            raise ValueError("period must be YYYY-MM")
        return period

    def _save(self, wb: ReviewWorkbook) -> None:
        data = asdict(wb)
        self.conn.execute(
            """
            INSERT INTO review_workbooks (org_id, period, prior_period, created_at, pnl, summary,
                                          flags, txn_counts, narrative, narrative_note)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (org_id, period) DO UPDATE SET
                prior_period = EXCLUDED.prior_period,
                created_at = EXCLUDED.created_at,
                pnl = EXCLUDED.pnl,
                summary = EXCLUDED.summary,
                flags = EXCLUDED.flags,
                txn_counts = EXCLUDED.txn_counts,
                narrative = EXCLUDED.narrative,
                narrative_note = EXCLUDED.narrative_note
            """,
            (self.org_id, wb.period, wb.prior_period, wb.created_at, Jsonb(data["pnl"]),
             Jsonb(data["summary"]), Jsonb(data["flags"]), Jsonb(data["txn_counts"]),
             wb.narrative, wb.narrative_note),
        )

    def exists(self, period: str) -> bool:
        self._check_period(period)
        return (
            self.conn.execute(
                "SELECT 1 FROM review_workbooks WHERE org_id = %s AND period = %s",
                (self.org_id, period),
            ).fetchone()
            is not None
        )

    def load(self, period: str) -> ReviewWorkbook:
        self._check_period(period)
        row = self.conn.execute(
            "SELECT * FROM review_workbooks WHERE org_id = %s AND period = %s",
            (self.org_id, period),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(period)
        return ReviewWorkbook(
            period=row["period"],
            prior_period=row["prior_period"],
            created_at=row["created_at"],
            pnl=[PnlLine(**line) for line in row["pnl"]],
            summary=row["summary"],
            flags=[ReviewFlag(**flag) for flag in row["flags"]],
            narrative=row["narrative"],
            narrative_note=row["narrative_note"],
            txn_counts=row["txn_counts"],
        )

    def save_new(self, wb: ReviewWorkbook) -> ReviewWorkbook:
        """Persist a freshly computed workbook, carrying over verification
        for flags whose flag_id matches the previous build."""
        if self.exists(wb.period):
            previous = {f.flag_id: f for f in self.load(wb.period).flags}
            for flag in wb.flags:
                old = previous.get(flag.flag_id)
                if old is not None and old.status == "verified":
                    flag.status = old.status
                    flag.verified_by = old.verified_by
                    flag.verified_at = old.verified_at
                    flag.ca_signoff = old.ca_signoff
        wb.created_at = datetime.now(UTC).isoformat()
        self._save(wb)
        return wb

    def verify_flag(
        self, period: str, flag_id: str, actor: str, ca_signoff: str = ""
    ) -> ReviewFlag:
        self._check_period(period)
        self.conn.execute(
            "SELECT 1 FROM review_workbooks WHERE org_id = %s AND period = %s FOR UPDATE",
            (self.org_id, period),
        )
        wb = self.load(period)
        for flag in wb.flags:
            if flag.flag_id != flag_id:
                continue
            if flag.status == "verified":
                raise AlreadyVerified(f"flag {flag_id} is already verified")
            flag.status = "verified"
            flag.verified_by = actor
            flag.verified_at = datetime.now(UTC).isoformat()
            flag.ca_signoff = ca_signoff
            self._save(wb)
            return flag
        raise KeyError(f"no flag {flag_id!r} in {period}")

    def set_narrative(self, period: str, narrative: str, note: str = "") -> ReviewWorkbook:
        wb = self.load(period)
        wb.narrative = narrative
        wb.narrative_note = note
        self._save(wb)
        return wb

    def periods(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT period FROM review_workbooks WHERE org_id = %s ORDER BY period DESC",
            (self.org_id,),
        ).fetchall()
        return [r["period"] for r in rows]
