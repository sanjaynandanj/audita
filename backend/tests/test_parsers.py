import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers import parse_gstr2b, parse_purchase_register

SAMPLES = Path(__file__).parent.parent / "sample_data"


class TestGstr2bPortalJson:
    def test_parses_sample(self):
        records = parse_gstr2b(SAMPLES / "gstr2b_sample.json")
        assert len(records) == 6  # 3 b2b + 1 b2ba + 1 cdnr + 1 isd
        b2b = [r for r in records if not (r.is_amendment or r.doc_type == "CDN" or r.is_isd)]
        assert len(b2b) == 3

    def test_amounts_summed_from_items(self):
        records = parse_gstr2b(SAMPLES / "gstr2b_sample.json")
        inv1 = next(r for r in records if r.invoice_no == "S1/001")
        assert inv1.taxable_value == Decimal("100000")
        assert inv1.total_tax == Decimal("18000")

    def test_amendment_and_cdn_and_isd_flags(self):
        records = parse_gstr2b(SAMPLES / "gstr2b_sample.json")
        assert any(r.is_amendment for r in records)
        assert any(r.doc_type == "CDN" for r in records)
        assert any(r.is_isd for r in records)

    def test_rcm_flag(self):
        records = parse_gstr2b(SAMPLES / "gstr2b_sample.json")
        rcm = next(r for r in records if r.invoice_no == "S3/777")
        assert rcm.reverse_charge is True


class TestPurchaseRegisterCsv:
    def test_parses_sample(self):
        records = parse_purchase_register(SAMPLES / "purchase_register_sample.csv")
        assert len(records) == 6
        assert all(r.source.value == "books" for r in records)

    def test_flexible_headers_and_amounts(self):
        records = parse_purchase_register(SAMPLES / "purchase_register_sample.csv")
        first = records[0]
        assert first.gstin == "29AAACA1111A1Z5"
        assert first.total_tax == Decimal("18000")

    def test_source_ref_traceability(self):
        records = parse_purchase_register(SAMPLES / "purchase_register_sample.csv")
        assert all("row" in r.source_ref for r in records)

    def test_missing_headers_is_a_clear_error(self, tmp_path):
        bad = tmp_path / "bad.csv"
        bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="GSTIN"):
            parse_purchase_register(bad)

    def test_empty_file(self, tmp_path):
        empty = tmp_path / "empty.csv"
        empty.write_text("", encoding="utf-8")
        assert parse_purchase_register(empty) == []


class TestGstr2bDocLevelTotals:
    def test_doc_level_amounts_when_no_items(self, tmp_path):
        payload = {
            "data": {"docdata": {"b2b": [{
                "ctin": "29AAACA1111A1Z5", "trdnm": "Doc Level Co",
                "inv": [{"inum": "DL/1", "dt": "01-04-2026", "txval": 5000,
                         "igst": 900, "cgst": 0, "sgst": 0, "cess": 0}],
            }]}}
        }
        path = tmp_path / "g2b.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        records = parse_gstr2b(path)
        assert records[0].taxable_value == Decimal("5000")
        assert records[0].total_tax == Decimal("900")
