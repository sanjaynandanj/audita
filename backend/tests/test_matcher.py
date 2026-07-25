from decimal import Decimal

from app.engine.matcher import amount_tolerance, amounts_match, match
from app.engine.models import Bucket, InvoiceRecord, Source


def rec(source, gstin="29ABCDE1234F1Z5", inv="INV-001", taxable="1000", igst="180",
        cgst="0", sgst="0", cess="0", **kw):
    return InvoiceRecord(
        source=source, gstin=gstin, invoice_no=inv,
        taxable_value=Decimal(taxable), igst=Decimal(igst),
        cgst=Decimal(cgst), sgst=Decimal(sgst), cess=Decimal(cess), **kw
    )


class TestTolerance:
    def test_rupee_one_floor(self):
        assert amount_tolerance(Decimal("100")) == Decimal("1")

    def test_point_one_percent_above_1000(self):
        assert amount_tolerance(Decimal("50000")) == Decimal("50")

    def test_amounts_within_tolerance(self):
        assert amounts_match(Decimal("1000.00"), Decimal("1000.99"))
        assert not amounts_match(Decimal("1000.00"), Decimal("1002.00"))
        assert amounts_match(Decimal("100000"), Decimal("100099"))
        assert not amounts_match(Decimal("100000"), Decimal("100101"))


class TestBuckets:
    def test_exact_match(self):
        result = match([rec(Source.BOOKS)], [rec(Source.GSTR2B)])
        assert [p.bucket for p in result.pairs] == [Bucket.MATCHED]

    def test_fuzzy_match_above_threshold(self):
        # separators stripped by normalization -> identical
        result = match([rec(Source.BOOKS, inv="INV-001")], [rec(Source.GSTR2B, inv="INV/001")])
        assert result.pairs[0].bucket == Bucket.MATCHED

    def test_books_only_is_at_risk(self):
        result = match([rec(Source.BOOKS)], [])
        pair = result.pairs[0]
        assert pair.bucket == Bucket.BOOKS_ONLY
        assert pair.itc_at_risk == Decimal("180")

    def test_gstr2b_only_is_missed_itc(self):
        result = match([], [rec(Source.GSTR2B)])
        assert result.pairs[0].bucket == Bucket.GSTR2B_ONLY

    def test_amount_mismatch(self):
        result = match(
            [rec(Source.BOOKS, taxable="1000", igst="180")],
            [rec(Source.GSTR2B, taxable="1000", igst="90")],
        )
        pair = result.pairs[0]
        assert pair.bucket == Bucket.MISMATCHED
        assert pair.itc_at_risk == Decimal("90")

    def test_different_gstin_never_matches(self):
        result = match(
            [rec(Source.BOOKS, gstin="29ABCDE1234F1Z5")],
            [rec(Source.GSTR2B, gstin="27ABCDE1234F1Z3")],
        )
        buckets = sorted(p.bucket for p in result.pairs)
        assert buckets == sorted([Bucket.BOOKS_ONLY, Bucket.GSTR2B_ONLY])

    def test_ambiguous_near_match_goes_unresolved(self):
        # ratio between 75 and 90 -> unresolved, never silently matched or at-risk
        # "INV12345" vs "INV12395": 7 of 8 chars align -> ratio 87.5
        result = match(
            [rec(Source.BOOKS, inv="INV12345")],
            [rec(Source.GSTR2B, inv="INV12395")],
        )
        assert result.pairs[0].bucket == Bucket.UNRESOLVED
        assert "ambiguous" in result.pairs[0].reason


class TestSpecialCategories:
    def test_credit_note_unresolved(self):
        result = match([rec(Source.BOOKS, doc_type="CDN")], [])
        pair = result.pairs[0]
        assert pair.bucket == Bucket.UNRESOLVED
        assert "credit/debit note" in pair.reason

    def test_rcm_unresolved(self):
        result = match([], [rec(Source.GSTR2B, reverse_charge=True)])
        assert result.pairs[0].bucket == Bucket.UNRESOLVED
        assert "reverse charge" in result.pairs[0].reason

    def test_amendment_unresolved(self):
        result = match([], [rec(Source.GSTR2B, is_amendment=True)])
        assert "amendment" in result.pairs[0].reason

    def test_isd_unresolved(self):
        result = match([], [rec(Source.GSTR2B, is_isd=True)])
        assert "ISD" in result.pairs[0].reason

    def test_special_never_pairs_with_plain(self):
        # A CDN in books must not consume the plain 2B invoice with same number
        result = match(
            [rec(Source.BOOKS, doc_type="CDN"), rec(Source.BOOKS)],
            [rec(Source.GSTR2B)],
        )
        buckets = sorted(p.bucket.value for p in result.pairs)
        assert buckets == sorted([Bucket.UNRESOLVED.value, Bucket.MATCHED.value])


class TestDeterminism:
    def test_best_candidate_by_amount_on_ratio_tie(self):
        b = rec(Source.BOOKS, inv="INV1", igst="180")
        g_close = rec(Source.GSTR2B, inv="INV1", igst="180")
        g_far = rec(Source.GSTR2B, inv="INV1", igst="500", taxable="3000")
        result = match([b], [g_far, g_close])
        matched = [p for p in result.pairs if p.bucket == Bucket.MATCHED]
        assert len(matched) == 1
        assert matched[0].gstr2b.igst == Decimal("180")
