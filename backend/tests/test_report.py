from decimal import Decimal

from app.engine.matcher import match
from app.engine.models import InvoiceRecord, Source
from app.report.builder import ReportStore, build_report


def rec(source, gstin="29ABCDE1234F1Z5", inv="INV-001", igst="180", **kw):
    return InvoiceRecord(source=source, gstin=gstin, invoice_no=inv,
                         taxable_value=Decimal("1000"), igst=Decimal(igst), **kw)


def make_report():
    books = [rec(Source.BOOKS, inv="A1"), rec(Source.BOOKS, inv="B2", igst="500")]
    gstr2b = [rec(Source.GSTR2B, inv="A1")]  # B2 becomes books_only (at risk 500)
    return build_report("Test Client", match(books, gstr2b))


class TestHeadlineGating:
    def test_headline_zero_until_verified(self):
        report = make_report()
        assert report.verified_at_risk == Decimal("0")
        assert report.pending_at_risk == Decimal("500")

    def test_verification_moves_amount_to_headline(self, db_conn, org):
        store = ReportStore(db_conn, org)
        report = make_report()
        store.save(report)
        exc_id = report.exceptions[0].exception_id
        updated = store.verify_exception(report.report_id, exc_id, actor="Sanjay", ca_signoff="CA 123456")
        assert updated.verified_at_risk == Decimal("500")
        assert updated.pending_at_risk == Decimal("0")
        item = updated.find(exc_id)
        assert item.verified_by == "Sanjay"
        assert item.ca_signoff == "CA 123456"

    def test_unresolved_never_in_headline(self):
        books = [rec(Source.BOOKS, doc_type="CDN", igst="9999")]
        report = build_report("Client", match(books, []))
        assert report.exceptions == []
        assert report.unresolved_total == Decimal("9999")
        assert report.verified_at_risk == Decimal("0")


class TestStoreRoundTrip:
    def test_save_load(self, db_conn, org):
        store = ReportStore(db_conn, org)
        report = make_report()
        store.save(report)
        loaded = store.load(report.report_id)
        assert loaded.client_name == "Test Client"
        assert len(loaded.exceptions) == 1
        assert loaded.matched_count == 1

    def test_unknown_report_id_rejected(self, db_conn, org):
        import pytest

        with pytest.raises(FileNotFoundError):
            ReportStore(db_conn, org).load("no-such-report")

    def test_cross_org_isolation(self, db_conn, org):
        import pytest

        store = ReportStore(db_conn, org)
        report = make_report()
        store.save(report)
        other = str(
            db_conn.execute("INSERT INTO orgs (name) VALUES ('Other') RETURNING org_id").fetchone()["org_id"]
        )
        with pytest.raises(FileNotFoundError):
            ReportStore(db_conn, other).load(report.report_id)


class TestExcelExport:
    def test_export_bytes(self):
        from app.report.excel import export_xlsx

        data = export_xlsx(make_report())
        assert data[:2] == b"PK"  # xlsx is a zip
        assert len(data) > 1000
