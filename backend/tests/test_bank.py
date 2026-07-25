from decimal import Decimal
from pathlib import Path

from app.engine.bank import BankBucket, BankSource, BankTxn, match_bank, parse_date
from app.parsers.bank import parse_bank_ledger, parse_bank_statement
from app.report.bank_builder import build_bank_report

SAMPLES = Path(__file__).parent.parent / "sample_data"


def txn(source, amount, date="05-04-2026", ref="", desc=""):
    return BankTxn(source=source, txn_date=date, description=desc, ref=ref, amount=Decimal(amount))


class TestBankMatching:
    def test_exact_match(self):
        r = match_bank(
            [txn(BankSource.BANK, "-11800", ref="CHQ 4471")],
            [txn(BankSource.BOOKS, "-11800", ref="4471")],
        )
        assert [p.bucket for p in r.pairs] == [BankBucket.MATCHED]

    def test_date_window(self):
        r = match_bank(
            [txn(BankSource.BANK, "-5000", date="10-04-2026")],
            [txn(BankSource.BOOKS, "-5000", date="04-04-2026")],
        )
        assert r.pairs[0].bucket == BankBucket.MATCHED
        r2 = match_bank(
            [txn(BankSource.BANK, "-5000", date="20-04-2026")],
            [txn(BankSource.BOOKS, "-5000", date="04-04-2026")],
        )
        buckets = sorted(p.bucket.value for p in r2.pairs)
        assert buckets == ["bank_only", "books_only"]

    def test_direction_never_crosses(self):
        # a deposit cannot match a withdrawal of the same magnitude
        r = match_bank(
            [txn(BankSource.BANK, "9000")],
            [txn(BankSource.BOOKS, "-9000")],
        )
        buckets = sorted(p.bucket.value for p in r.pairs)
        assert buckets == ["bank_only", "books_only"]

    def test_unrecorded_bank_charge(self):
        r = match_bank([txn(BankSource.BANK, "-590", desc="BANK CHARGES GST")], [])
        assert r.pairs[0].bucket == BankBucket.BANK_ONLY
        assert "unrecorded payment" in r.pairs[0].reason

    def test_uncleared_cheque_and_transit(self):
        r = match_bank([], [txn(BankSource.BOOKS, "-15000"), txn(BankSource.BOOKS, "22000")])
        reasons = sorted(p.reason for p in r.pairs)
        assert any("uncleared cheque" in x for x in reasons)
        assert any("deposit in transit" in x for x in reasons)

    def test_ref_similarity_breaks_amount_tie(self):
        bank = [txn(BankSource.BANK, "-7500", ref="NEFT UTR7781", desc="NEFT ALPHA TRADERS")]
        books = [
            txn(BankSource.BOOKS, "-7500", ref="UTR9902", desc="Beta Suppliers"),
            txn(BankSource.BOOKS, "-7500", ref="UTR7781", desc="Alpha Traders"),
        ]
        r = match_bank(bank, books)
        matched = [p for p in r.pairs if p.bucket == BankBucket.MATCHED][0]
        assert matched.books.ref == "UTR7781"


class TestBankReport:
    def test_report_totals(self):
        result = match_bank(
            [txn(BankSource.BANK, "-590", desc="BANK CHARGES")],
            [txn(BankSource.BOOKS, "-15000", ref="CHQ 101")],
        )
        report = build_bank_report("Acme", result)
        assert report.unrecorded_total == Decimal("-590")
        assert report.uncleared_total == Decimal("-15000")
        assert len(report.unrecorded) == 1 and len(report.uncleared) == 1


class TestBankParsers:
    def test_statement_sample(self):
        txns = parse_bank_statement(SAMPLES / "bank_statement_sample.csv")
        assert len(txns) == 5
        # statement: credit = money in
        deposits = [t for t in txns if t.amount > 0]
        assert len(deposits) == 2

    def test_ledger_sample_mirrors_convention(self):
        txns = parse_bank_ledger(SAMPLES / "bank_ledger_sample.csv")
        assert len(txns) == 5
        # ledger: debit = money in
        money_in = [t for t in txns if t.amount > 0]
        assert len(money_in) == 2

    def test_date_formats(self):
        assert parse_date("05-04-2026") is not None
        assert parse_date("2026-04-05") is not None
        assert parse_date("garbage") is None
