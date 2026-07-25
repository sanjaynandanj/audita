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

import json
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

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


def _dedupe_key(txn_date: str, description: str, ref: str, amount: str) -> str:
    return "|".join((txn_date.strip(), description.strip().lower(), ref.strip(), amount))


class LedgerStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, period: str) -> Path:
        if not PERIOD_RE.match(period):
            raise ValueError("period must be YYYY-MM")
        return self.root / f"{period}.json"

    def _save(self, ledger: Ledger) -> None:
        self._path(ledger.period).write_text(
            json.dumps(asdict(ledger), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def load(self, period: str) -> Ledger:
        path = self._path(period)
        if not path.exists():
            return Ledger(period=period, created_at="", txns=[])
        data = json.loads(path.read_text(encoding="utf-8"))
        data["txns"] = [LedgerTxn(**t) for t in data["txns"]]
        return Ledger(**data)

    def periods(self) -> list[str]:
        return sorted((p.stem for p in self.root.glob("*.json") if PERIOD_RE.match(p.stem)), reverse=True)

    def import_txns(self, period: str, txns: list[LedgerTxn]) -> tuple[Ledger, int, int]:
        """Append transactions, skipping duplicates already in the period.

        Returns (ledger, imported_count, skipped_count).
        """
        ledger = self.load(period)
        if not ledger.created_at:
            ledger.created_at = datetime.now(UTC).isoformat()
        existing = {
            _dedupe_key(t.txn_date, t.description, t.ref, t.amount) for t in ledger.txns
        }
        imported = skipped = 0
        for txn in txns:
            key = _dedupe_key(txn.txn_date, txn.description, txn.ref, txn.amount)
            if key in existing:
                skipped += 1
                continue
            existing.add(key)
            ledger.txns.append(txn)
            imported += 1
        self._save(ledger)
        return ledger, imported, skipped

    def get_txn(self, period: str, txn_id: str) -> LedgerTxn:
        for txn in self.load(period).txns:
            if txn.txn_id == txn_id:
                return txn
        raise KeyError(f"no transaction {txn_id!r} in {period}")

    def confirm(
        self, period: str, txn_id: str, account_code: str, actor: str
    ) -> LedgerTxn:
        ledger = self.load(period)
        for txn in ledger.txns:
            if txn.txn_id != txn_id:
                continue
            if txn.status == "confirmed":
                raise AlreadyConfirmed(f"transaction {txn_id} is already confirmed")
            txn.status = "confirmed"
            txn.source = "human"
            txn.account_code = account_code
            txn.confirmed_by = actor
            txn.confirmed_at = datetime.now(UTC).isoformat()
            self._save(ledger)
            return txn
        raise KeyError(f"no transaction {txn_id!r} in {period}")

    def suggest(self, period: str, suggestions: dict[str, tuple[str, str]]) -> int:
        """Attach LLM suggestions {txn_id: (account_code, confidence)} to pending txns."""
        ledger = self.load(period)
        applied = 0
        for txn in ledger.txns:
            if txn.status != "pending" or txn.txn_id not in suggestions:
                continue
            code, confidence = suggestions[txn.txn_id]
            txn.suggested_account = code
            txn.confidence = confidence
            txn.source = "llm"
            applied += 1
        if applied:
            self._save(ledger)
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
