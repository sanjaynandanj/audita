"""Invoice Agent (AP capture) tests: draft gating, confirm immutability,
register CSV round-trip into the ITC recon engine."""

from pathlib import Path

import pytest

from app.ap.register import build_register_csv
from app.ap.store import AlreadyConfirmed, InvoiceStore, normalize_fields
from app.parsers import parse_purchase_register

SAMPLES = Path(__file__).parent.parent / "sample_data"

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f030005fe02fea72d1e480000000049454e44ae426082"
)

FIELDS = {
    "supplier_gstin": "27AAPFU0939F1ZV",
    "supplier_name": "Bharat Traders",
    "invoice_no": "BT/2026/041",
    "invoice_date": "12-06-2026",
    "taxable_value": "10000",
    "igst": "0",
    "cgst": "900",
    "sgst": "900",
    "cess": "0",
    "total": "11800",
}


def _upload(client, org, period="2026-06") -> dict:
    res = client.post(
        f"/api/orgs/{org}/invoices",
        data={"period": period},
        files={"invoice_file": ("bill.png", PNG_1PX, "image/png")},
    )
    assert res.status_code == 200, res.text
    return res.json()["invoice"]


class TestUpload:
    def test_no_vision_key_yields_blank_manual_draft(self, owner_client):
        client, org = owner_client
        inv = _upload(client, org)
        assert inv["status"] == "draft"
        assert inv["extraction"] == "manual"
        assert inv["fields"]["supplier_gstin"] == ""
        assert inv["fields"]["taxable_value"] == "0"
        assert "Vision not configured" in inv["extraction_note"]

    def test_rejects_bad_period_and_bad_type(self, owner_client):
        client, org = owner_client
        res = client.post(
            f"/api/orgs/{org}/invoices",
            data={"period": "June 2026"},
            files={"invoice_file": ("bill.png", PNG_1PX, "image/png")},
        )
        assert res.status_code == 400
        res = client.post(
            f"/api/orgs/{org}/invoices",
            data={"period": "2026-06"},
            files={"invoice_file": ("bill.exe", b"x", "application/octet-stream")},
        )
        assert res.status_code == 400

    def test_upload_is_event_logged(self, owner_client):
        client, org = owner_client
        inv = _upload(client, org)
        trail = client.get(f"/api/orgs/{org}/invoices/{inv['invoice_id']}").json()["trail"]
        assert [e["action"] for e in trail] == ["invoice_uploaded"]

    def test_scan_served_back(self, owner_client):
        client, org = owner_client
        inv = _upload(client, org)
        res = client.get(f"/api/orgs/{org}/invoices/{inv['invoice_id']}/scan")
        assert res.status_code == 200
        assert res.content == PNG_1PX
        assert res.headers["content-type"] == "image/png"


class TestConfirm:
    def test_confirm_records_session_identity(self, owner_client):
        client, org = owner_client
        inv = _upload(client, org)
        res = client.post(
            f"/api/orgs/{org}/invoices/{inv['invoice_id']}/confirm",
            json={"fields": FIELDS},
        )
        assert res.status_code == 200, res.text
        doc = res.json()["invoice"]
        assert doc["status"] == "confirmed"
        assert doc["confirmed_by"] == "Owner"  # display name from session, not payload
        actions = [e["action"] for e in res.json()["trail"]]
        assert "invoice_confirmed" in actions

    def test_confirm_is_immutable(self, owner_client):
        client, org = owner_client
        inv = _upload(client, org)
        first = client.post(
            f"/api/orgs/{org}/invoices/{inv['invoice_id']}/confirm", json={"fields": FIELDS}
        )
        assert first.status_code == 200
        second = client.post(
            f"/api/orgs/{org}/invoices/{inv['invoice_id']}/confirm",
            json={"fields": {**FIELDS, "taxable_value": "99999"}},
        )
        assert second.status_code == 409

    def test_confirm_requires_key_fields(self, owner_client):
        client, org = owner_client
        inv = _upload(client, org)
        res = client.post(
            f"/api/orgs/{org}/invoices/{inv['invoice_id']}/confirm",
            json={"fields": {**FIELDS, "supplier_gstin": ""}},
        )
        assert res.status_code == 400

    def test_confirm_rejects_garbage_amounts(self, owner_client):
        client, org = owner_client
        inv = _upload(client, org)
        res = client.post(
            f"/api/orgs/{org}/invoices/{inv['invoice_id']}/confirm",
            json={"fields": {**FIELDS, "taxable_value": "ten thousand"}},
        )
        assert res.status_code == 400


class TestRbac:
    def test_viewer_cannot_upload_or_confirm(self, db_conn, owner_client):
        from tests.conftest import make_client

        client, org = owner_client
        inv = _upload(client, org)
        viewer, _ = make_client(db_conn, "viewer@test.local", role="viewer", org_id=org)
        res = viewer.post(
            f"/api/orgs/{org}/invoices",
            data={"period": "2026-06"},
            files={"invoice_file": ("b.png", PNG_1PX, "image/png")},
        )
        assert res.status_code == 403
        res = viewer.post(
            f"/api/orgs/{org}/invoices/{inv['invoice_id']}/confirm", json={"fields": FIELDS}
        )
        assert res.status_code == 403
        # but a viewer can read
        assert viewer.get(f"/api/orgs/{org}/invoices").status_code == 200

    def test_stranger_gets_404(self, db_conn, owner_client):
        from tests.conftest import make_client

        client, org = owner_client
        stranger, _ = make_client(db_conn, "stranger@test.local")
        assert stranger.get(f"/api/orgs/{org}/invoices").status_code == 404

    def test_anonymous_gets_401(self, owner_client):
        from fastapi.testclient import TestClient

        from app.main import app

        client, org = owner_client
        anon = TestClient(app, base_url="https://testserver")
        assert anon.get(f"/api/orgs/{org}/invoices").status_code == 401


class TestRegisterExport:
    def test_csv_round_trips_through_purchase_register_parser(self, db_conn, org, tmp_path):
        store = InvoiceStore(db_conn, org)
        doc = store.create(
            period="2026-06", source_file="bill.png", suffix=".png",
            data=PNG_1PX, extraction="manual", fields={},
        )
        store.confirm(doc.invoice_id, FIELDS, actor="Asha")
        csv_text = build_register_csv(store.list(period="2026-06"))
        out = tmp_path / "register.csv"
        out.write_text(csv_text, encoding="utf-8")
        records = parse_purchase_register(out)
        assert len(records) == 1
        rec = records[0]
        assert rec.gstin == FIELDS["supplier_gstin"]
        assert rec.invoice_no == FIELDS["invoice_no"]
        assert str(rec.taxable_value) == "10000"
        assert str(rec.cgst) == "900"

    def test_drafts_excluded_from_register(self, db_conn, org):
        store = InvoiceStore(db_conn, org)
        store.create(period="2026-06", source_file="a.png", suffix=".png",
                     data=PNG_1PX, extraction="manual", fields={})
        csv_text = build_register_csv(store.list(period="2026-06"))
        assert csv_text.count("\n") == 1  # header only

    def test_export_endpoint_404_when_no_confirmed(self, owner_client):
        client, org = owner_client
        res = client.get(f"/api/orgs/{org}/registers/1999-01.csv")
        assert res.status_code == 404

    def test_export_endpoint_serves_confirmed_period(self, owner_client):
        client, org = owner_client
        inv = _upload(client, org, period="2026-05")
        client.post(
            f"/api/orgs/{org}/invoices/{inv['invoice_id']}/confirm", json={"fields": FIELDS}
        )
        res = client.get(f"/api/orgs/{org}/registers/2026-05.csv")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/csv")
        assert FIELDS["invoice_no"] in res.text


class TestRegisterFeedsRecon:
    def test_confirmed_invoices_run_through_recon(self, owner_client):
        client, org = owner_client
        inv = _upload(client, org, period="2026-04")
        client.post(
            f"/api/orgs/{org}/invoices/{inv['invoice_id']}/confirm", json={"fields": FIELDS}
        )
        register_csv = client.get(f"/api/orgs/{org}/registers/2026-04.csv").text
        with open(SAMPLES / "gstr2b_sample.json", "rb") as g2b:
            res = client.post(
                f"/api/orgs/{org}/recon",
                data={"client_name": "AP Interop", "period_note": "2026-04"},
                files={
                    "gstr2b_file": ("gstr2b.json", g2b, "application/json"),
                    "register_file": ("register.csv", register_csv.encode(), "text/csv"),
                },
            )
        assert res.status_code == 200, res.text
        token = res.json()["token"]
        report = client.get(f"/api/reports/{token}").json()["report"]
        # our invoice isn't in the sample 2B, so it must surface as an exception
        assert any(
            (e.get("books") or {}).get("invoice_no") == FIELDS["invoice_no"]
            for e in report["exceptions"]
        )


class TestNormalizeFields:
    def test_strict_raises_lenient_zeroes(self):
        with pytest.raises(ValueError):
            normalize_fields({"taxable_value": "abc"})
        assert normalize_fields({"taxable_value": "abc"}, strict=False)["taxable_value"] == "0"

    def test_store_rejects_double_confirm(self, db_conn, org):
        store = InvoiceStore(db_conn, org)
        doc = store.create(period="2026-06", source_file="a.png", suffix=".png",
                           data=PNG_1PX, extraction="manual", fields={})
        store.confirm(doc.invoice_id, FIELDS, actor="Asha")
        with pytest.raises(AlreadyConfirmed):
            store.confirm(doc.invoice_id, FIELDS, actor="Asha")
