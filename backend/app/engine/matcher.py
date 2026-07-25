"""Matching engine.

Accuracy bar (from the approved design doc):
- exact GSTIN + fuzzy invoice number (ratio >= 90) + amount tolerance of
  +/- Rs.1 or +/- 0.1%, whichever is greater
- near-matches (ratio 75-89) are AMBIGUOUS and go to unresolved -- never
  silently into matched or at-risk
- credit/debit notes, GSTR-2B amendments, RCM entries, and ISD credits
  route to unresolved in Phase 1
- precision beats recall everywhere
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

try:
    from rapidfuzz import fuzz

    def _ratio(a: str, b: str) -> float:
        return float(fuzz.ratio(a, b))
except ImportError:  # pragma: no cover - rapidfuzz is a declared dependency
    from difflib import SequenceMatcher

    def _ratio(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio() * 100.0

from .models import Bucket, InvoiceRecord, MatchPair, MatchResult, Source

MATCH_THRESHOLD = 90.0
AMBIGUOUS_THRESHOLD = 75.0


def amount_tolerance(value: Decimal) -> Decimal:
    """+/- Rs.1 or +/- 0.1% of the value, whichever is greater."""
    return max(Decimal("1"), abs(value) * Decimal("0.001"))


def amounts_match(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= amount_tolerance(max(abs(a), abs(b)))


def match(books: list[InvoiceRecord], gstr2b: list[InvoiceRecord]) -> MatchResult:
    result = MatchResult()

    plain_books: list[InvoiceRecord] = []
    plain_2b: list[InvoiceRecord] = []
    for rec in books:
        reason = rec.special_reason
        if reason:
            result.pairs.append(_special(rec, reason))
        else:
            plain_books.append(rec)
    for rec in gstr2b:
        reason = rec.special_reason
        if reason:
            result.pairs.append(_special(rec, reason))
        else:
            plain_2b.append(rec)

    by_gstin_2b: dict[str, list[InvoiceRecord]] = defaultdict(list)
    for rec in plain_2b:
        by_gstin_2b[rec.gstin_norm].append(rec)

    consumed_2b: set[int] = set()

    # Deterministic order: process books rows in input order; among candidate
    # 2B rows pick highest invoice-number ratio, tie-broken by amount closeness.
    for book in plain_books:
        candidates = [
            (idx, rec)
            for idx, rec in enumerate(by_gstin_2b.get(book.gstin_norm, []))
            if id(rec) not in consumed_2b
        ]
        best: tuple[float, Decimal, int, InvoiceRecord] | None = None
        for _, rec in candidates:
            ratio = _ratio(book.invoice_no_norm, rec.invoice_no_norm)
            if ratio < AMBIGUOUS_THRESHOLD:
                continue
            amount_gap = abs(book.total_tax - rec.total_tax)
            key = (ratio, -amount_gap)
            if best is None or (key[0], key[1]) > (best[0], -best[1]):
                best = (ratio, amount_gap, 0, rec)

        if best is None:
            result.pairs.append(
                MatchPair(books=book, gstr2b=None, bucket=Bucket.BOOKS_ONLY,
                          reason="no GSTR-2B counterpart (ITC at risk)")
            )
            continue

        ratio, _, _, rec2b = best
        if ratio < MATCH_THRESHOLD:
            consumed_2b.add(id(rec2b))
            result.pairs.append(
                MatchPair(books=book, gstr2b=rec2b, bucket=Bucket.UNRESOLVED,
                          match_ratio=ratio,
                          reason=f"ambiguous invoice-number match (ratio {ratio:.0f} < {MATCH_THRESHOLD:.0f})")
            )
            continue

        consumed_2b.add(id(rec2b))
        taxable_ok = amounts_match(book.taxable_value, rec2b.taxable_value)
        tax_ok = amounts_match(book.total_tax, rec2b.total_tax)
        if taxable_ok and tax_ok:
            result.pairs.append(
                MatchPair(books=book, gstr2b=rec2b, bucket=Bucket.MATCHED, match_ratio=ratio)
            )
        else:
            deltas = []
            if not taxable_ok:
                deltas.append(f"taxable {book.taxable_value} vs {rec2b.taxable_value}")
            if not tax_ok:
                deltas.append(f"tax {book.total_tax} vs {rec2b.total_tax}")
            result.pairs.append(
                MatchPair(books=book, gstr2b=rec2b, bucket=Bucket.MISMATCHED,
                          match_ratio=ratio, reason="; ".join(deltas))
            )

    for rec in plain_2b:
        if id(rec) not in consumed_2b:
            result.pairs.append(
                MatchPair(books=None, gstr2b=rec, bucket=Bucket.GSTR2B_ONLY,
                          reason="in GSTR-2B but not in books (missed ITC)")
            )

    return result


def _special(rec: InvoiceRecord, reason: str) -> MatchPair:
    books = rec if rec.source == Source.BOOKS else None
    gstr2b = rec if rec.source == Source.GSTR2B else None
    return MatchPair(books=books, gstr2b=gstr2b, bucket=Bucket.UNRESOLVED,
                     reason=f"routed to unresolved in Phase 1: {reason}")
