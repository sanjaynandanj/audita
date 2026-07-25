"""Bank reconciliation engine (BRS).

Matches the bank statement against the books' bank ledger:
- amounts must agree within the standard tolerance (±₹1 or ±0.1%)
- dates within a ±7 day window (cheque clearing lag)
- among amount/date candidates, best reference/description similarity wins

Buckets:
- matched
- bank_only  : in the bank statement, not in books (unrecorded receipts/charges)
- books_only : in books, not yet in the bank (uncleared cheques / deposits in transit)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

try:
    from rapidfuzz import fuzz

    def _ratio(a: str, b: str) -> float:
        return float(fuzz.partial_ratio(a.upper(), b.upper())) if a and b else 0.0
except ImportError:  # pragma: no cover
    from difflib import SequenceMatcher

    def _ratio(a: str, b: str) -> float:
        return SequenceMatcher(None, a.upper(), b.upper()).ratio() * 100.0 if a and b else 0.0

from .matcher import amounts_match

DATE_WINDOW_DAYS = 7

_DATE_FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%d.%m.%Y")


def parse_date(text: str) -> date | None:
    text = (text or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


class BankBucket(StrEnum):
    MATCHED = "matched"
    BANK_ONLY = "bank_only"       # unrecorded in books
    BOOKS_ONLY = "books_only"     # uncleared / in transit


class BankSource(StrEnum):
    BANK = "bank"
    BOOKS = "books"


@dataclass
class BankTxn:
    source: BankSource
    txn_date: str                 # as given
    description: str
    ref: str                      # cheque no / UTR / voucher no
    amount: Decimal               # signed: +credit(deposit), -debit(withdrawal)
    source_ref: str = ""

    @property
    def parsed_date(self) -> date | None:
        return parse_date(self.txn_date)

    def to_dict(self) -> dict:
        return {
            "source": self.source.value,
            "txn_date": self.txn_date,
            "description": self.description,
            "ref": self.ref,
            "amount": str(self.amount),
            "source_ref": self.source_ref,
        }


@dataclass
class BankPair:
    bank: BankTxn | None
    books: BankTxn | None
    bucket: BankBucket
    reason: str = ""

    @property
    def amount(self) -> Decimal:
        rec = self.bank or self.books
        return rec.amount if rec else Decimal("0")


@dataclass
class BankMatchResult:
    pairs: list[BankPair] = field(default_factory=list)

    def bucket(self, bucket: BankBucket) -> list[BankPair]:
        return [p for p in self.pairs if p.bucket == bucket]


def _date_gap(a: BankTxn, b: BankTxn) -> int:
    da, db = a.parsed_date, b.parsed_date
    if da is None or db is None:
        return 0  # unparseable dates don't disqualify; amount is the anchor
    return abs((da - db).days)


def match_bank(bank: list[BankTxn], books: list[BankTxn]) -> BankMatchResult:
    result = BankMatchResult()
    consumed: set[int] = set()

    for b in bank:
        best: tuple[float, int, BankTxn] | None = None
        for k in books:
            if id(k) in consumed:
                continue
            if (b.amount >= 0) != (k.amount >= 0):
                continue
            if not amounts_match(abs(b.amount), abs(k.amount)):
                continue
            gap = _date_gap(b, k)
            if gap > DATE_WINDOW_DAYS:
                continue
            sim = max(_ratio(b.ref, k.ref), _ratio(b.description, k.description))
            score = (sim, -gap)
            if best is None or score > (best[0], -best[1]):
                best = (sim, gap, k)

        if best is None:
            direction = "receipt" if b.amount >= 0 else "payment"
            result.pairs.append(BankPair(
                bank=b, books=None, bucket=BankBucket.BANK_ONLY,
                reason=f"unrecorded {direction} — in bank statement, not in books",
            ))
        else:
            _, gap, k = best
            consumed.add(id(k))
            note = f"date gap {gap}d" if gap else ""
            result.pairs.append(BankPair(bank=b, books=k, bucket=BankBucket.MATCHED, reason=note))

    for k in books:
        if id(k) not in consumed:
            kind = "deposit in transit" if k.amount >= 0 else "uncleared cheque/payment"
            result.pairs.append(BankPair(
                bank=None, books=k, bucket=BankBucket.BOOKS_ONLY,
                reason=f"{kind} — in books, not yet in bank",
            ))

    return result
