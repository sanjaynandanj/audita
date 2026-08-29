"""Per-period categorized ledger.

Statuses:
  pending   — no rule matched; may carry an LLM-suggested account, which is
              advice only and never enters a total (PRD-2 invariant #3/#4)
  coded     — a user-authored deterministic rule categorized it (source=rule)
  confirmed — a named human set/ratified the account (source=human); immutable

Account totals include coded + confirmed only. Confirmed entries reject
further edits — corrections are new events, never mutations.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from psycopg import Connection

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class AlreadyConfirmed(RuntimeError):
    pass


@dataclass
class LedgerTxn:
    txn_id: str
    txn_date: str
    description: str
    ref: str
    amount: str            # signed Decimal string; + money in, - money out
    source_ref: str        # originating file:row
    status: str = "pending"        # pending | coded | confirmed
    source: str = ""               # rule | llm | human ("" while uncoded)
    account_code: str = ""
    rule_id: str = ""
    suggested_account: str = ""    # LLM advice — display only
    confidence: str = ""           # LLM confidence 0..1 as string
    confirmed_by: str = ""
    confirmed_at: str = ""


@dataclass
class Ledger:
    period: str
    created_at: str
    txns: list = field(default_factory=list)


_TXN_COLS = """txn_id, txn_date, description, ref, amount, source_ref, status, source,
               account_code, rule_id, suggested_account, confidence, confirmed_by, confirmed_at"""


class LedgerStore:
    def __init__(self, conn: Connection, org_id: str):
        self.conn = conn
        self.org_id = org_id

    @staticmethod
    def _check_period(period: str) -> str:
        if not PERIOD_RE.match(period):
            raise ValueError("period must be YYYY-MM")
        return period

    def load(self, period: str) -> Ledger:
        self._check_period(period)
        head = self.conn.execute(
            "SELECT created_at FROM ledgers WHERE org_id = %s AND period = %s",
            (self.org_id, period),
        ).fetchone()
        if head is None:
            return Ledger(period=period, created_at="", txns=[])
        rows = self.conn.execute(
            f"SELECT {_TXN_COLS} FROM ledger_txns WHERE org_id = %s AND period = %s "
            "ORDER BY txn_date, txn_id",
            (self.org_id, period),
        ).fetchall()
        return Ledger(period=period, created_at=head["created_at"], txns=[LedgerTxn(**r) for r in rows])

    def periods(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT period FROM ledgers WHERE org_id = %s ORDER BY period DESC", (self.org_id,)
        ).fetchall()
        return [r["period"] for r in rows]

    def import_txns(self, period: str, txns: list[LedgerTxn]) -> tuple[Ledger, int, int]:
        """Append transactions, skipping duplicates already in the period.

        Returns (ledger, imported_count, skipped_count). Dedupe is the unique
        index on (org, period, date, lower(description), ref, amount).
        """
        self._check_period(period)
        self.conn.execute(
            """
            INSERT INTO ledgers (org_id, period, created_at) VALUES (%s, %s, %s)
            ON CONFLICT (org_id, period) DO NOTHING
            """,
            (self.org_id, period, datetime.now(UTC).isoformat()),
        )
        imported = skipped = 0
        for txn in txns:
            row = self.conn.execute(
                """
                INSERT INTO ledger_txns (org_id, period, txn_id, txn_date, description, ref,
                                         amount, source_ref, status, source, account_code, rule_id,
                                         suggested_account, confidence, confirmed_by, confirmed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (org_id, period, txn_date, (lower(btrim(description))), ref, amount)
                DO NOTHING
                RETURNING txn_id
                """,
                (self.org_id, period, txn.txn_id, txn.txn_date, txn.description, txn.ref,
                 txn.amount, txn.source_ref, txn.status, txn.source, txn.account_code, txn.rule_id,
                 txn.suggested_account, txn.confidence, txn.confirmed_by, txn.confirmed_at),
            ).fetchone()
            if row is None:
                skipped += 1
            else:
                imported += 1
        return self.load(period), imported, skipped

    def get_txn(self, period: str, txn_id: str) -> LedgerTxn:
        self._check_period(period)
        row = self.conn.execute(
            f"SELECT {_TXN_COLS} FROM ledger_txns WHERE org_id = %s AND period = %s AND txn_id = %s",
            (self.org_id, period, txn_id),
        ).fetchone()
        if row is None:
            raise KeyError(f"no transaction {txn_id!r} in {period}")
        return LedgerTxn(**row)

    def confirm(
        self, period: str, txn_id: str, account_code: str, actor: str
    ) -> LedgerTxn:
        self._check_period(period)
        row = self.conn.execute(
            "SELECT status FROM ledger_txns WHERE org_id = %s AND period = %s AND txn_id = %s FOR UPDATE",
            (self.org_id, period, txn_id),
        ).fetchone()
        if row is None:
            raise KeyError(f"no transaction {txn_id!r} in {period}")
        if row["status"] == "confirmed":
            raise AlreadyConfirmed(f"transaction {txn_id} is already confirmed")
        updated = self.conn.execute(
            f"""
            UPDATE ledger_txns
            SET status = 'confirmed', source = 'human', account_code = %s,
                confirmed_by = %s, confirmed_at = %s
            WHERE org_id = %s AND period = %s AND txn_id = %s
            RETURNING {_TXN_COLS}
            """,
            (account_code, actor, datetime.now(UTC).isoformat(), self.org_id, period, txn_id),
        ).fetchone()
        return LedgerTxn(**updated)

    def suggest(self, period: str, suggestions: dict[str, tuple[str, str]]) -> int:
        """Attach LLM suggestions {txn_id: (account_code, confidence)} to pending txns."""
        self._check_period(period)
        applied = 0
        for txn_id, (code, confidence) in suggestions.items():
            row = self.conn.execute(
                """
                UPDATE ledger_txns
                SET suggested_account = %s, confidence = %s, source = 'llm'
                WHERE org_id = %s AND period = %s AND txn_id = %s AND status = 'pending'
                RETURNING txn_id
                """,
                (code, confidence, self.org_id, period, txn_id),
            ).fetchone()
            if row is not None:
                applied += 1
        return applied


def new_txn(
    txn_date: str, description: str, ref: str, amount: Decimal, source_ref: str
) -> LedgerTxn:
    return LedgerTxn(
        txn_id=secrets.token_hex(8),
        txn_date=txn_date,
        description=description,
        ref=ref,
        amount=str(amount),
        source_ref=source_ref,
    )


def summarize(ledger: Ledger) -> dict:
    """Per-account totals over coded+confirmed only; pending stays outside."""
    accounts: dict[str, dict] = {}
    pending_count = 0
    pending_total = Decimal("0")
    coded_count = confirmed_count = 0
    for txn in ledger.txns:
        amount = Decimal(txn.amount)
        if txn.status in ("coded", "confirmed"):
            bucket = accounts.setdefault(
                txn.account_code, {"count": 0, "total": Decimal("0")}
            )
            bucket["count"] += 1
            bucket["total"] += amount
            if txn.status == "coded":
                coded_count += 1
            else:
                confirmed_count += 1
        else:
            pending_count += 1
            pending_total += amount
    return {
        "accounts": {
            code: {"count": b["count"], "total": str(b["total"])}
            for code, b in sorted(accounts.items())
        },
        "txn_count": len(ledger.txns),
        "coded_count": coded_count,
        "confirmed_count": confirmed_count,
        "pending_count": pending_count,
        "pending_total": str(pending_total),
    }


def build_ledger_csv(ledger: Ledger, coa_names: dict[str, str]) -> str:
    """Categorized ledger export — coded + confirmed rows only (Phase 3 input)."""
    import csv
    import io

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(
        ["date", "description", "ref", "amount", "account_code", "account_name",
         "source", "confirmed_by"]
    )
    for txn in ledger.txns:
        if txn.status not in ("coded", "confirmed"):
            continue
        writer.writerow([
            txn.txn_date, txn.description, txn.ref, txn.amount,
            txn.account_code, coa_names.get(txn.account_code, ""),
            txn.source, txn.confirmed_by,
        ])
    return out.getvalue()
