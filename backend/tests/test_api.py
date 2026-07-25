"""API tests against the FastAPI app with an isolated data directory."""

import os
import tempfile
from pathlib import Path

# Isolate ALL storage before app.main is imported (stores bind at import time).
_TMP = tempfile.mkdtemp(prefix="audita-test-")
os.environ["AUDITA_DATA_DIR"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
SAMPLES = Path(__file__).parent.parent / "sample_data"


def _run_recon() -> dict:
    with open(SAMPLES / "gstr2b_sample.json", "rb") as g2b, \
         open(SAMPLES / "purchase_register_sample.csv", "rb") as reg:
        res = client.post(
            "/api/recon",
            data={"client_name": "API Test Client", "period_note": "April 2026"},
            files={
                "gstr2b_file": ("gstr2b.json", g2b, "application/json"),
                "register_file": ("register.csv", reg, "text/csv"),
            },
        )
    assert res.status_code == 200, res.text
    return res.json()


class TestReconApi:
    def test_recon_and_fetch(self):
        token = _run_recon()["token"]
        res = client.get(f"/api/reports/{token}")
        assert res.status_code == 200
        report = res.json()["report"]
        assert report["client_name"] == "API Test Client"
        assert report["verified_at_risk"] == "0"
        assert float(report["pending_at_risk"]) > 0
        # "parsed" logs before a report_id exists, so a fresh report's trail
        # carries recon_completed only
        assert len(res.json()["trail"]) >= 1

    def test_verify_moves_headline(self):
        token = _run_recon()["token"]
        report = client.get(f"/api/reports/{token}").json()["report"]
        exc_id = report["exceptions"][0]["exception_id"]
        amount = report["exceptions"][0]["itc_amount"]
        res = client.post(
            f"/api/reports/{token}/verify",
            json={"exception_id": exc_id, "actor": "Tester", "ca_signoff": "CA 000001"},
        )
        assert res.status_code == 200
        updated = res.json()["report"]
        assert updated["verified_at_risk"] == amount

    def test_verify_requires_actor(self):
        token = _run_recon()["token"]
        res = client.post(f"/api/reports/{token}/verify", json={"exception_id": "E0001", "actor": ""})
        assert res.status_code == 400

    def test_tampered_token_rejected(self):
        token = _run_recon()["token"]
        res = client.get(f"/api/reports/{token}tampered")
        assert res.status_code == 404

    def test_bad_file_type_rejected(self):
        res = client.post(
            "/api/recon",
            data={"client_name": "X"},
            files={
                "gstr2b_file": ("evil.exe", b"MZ", "application/octet-stream"),
                "register_file": ("register.csv", b"a,b", "text/csv"),
            },
        )
        assert res.status_code == 400

    def test_excel_export(self):
        token = _run_recon()["token"]
        res = client.get(f"/r/{token}/export.xlsx")
        assert res.status_code == 200
        assert res.content[:2] == b"PK"


class TestBankRecApi:
    def test_bankrec_end_to_end(self):
        with open(SAMPLES / "bank_statement_sample.csv", "rb") as stmt, \
             open(SAMPLES / "bank_ledger_sample.csv", "rb") as ledger:
            res = client.post(
                "/api/bankrec",
                data={"client_name": "API Bank Client", "period_note": "April 2026"},
                files={
                    "statement_file": ("statement.csv", stmt, "text/csv"),
                    "ledger_file": ("ledger.csv", ledger, "text/csv"),
                },
            )
        assert res.status_code == 200, res.text
        token = res.json()["token"]
        report = client.get(f"/api/bankrec/{token}").json()["report"]
        assert report["matched_count"] == 3
        assert len(report["unrecorded"]) == 2
        assert len(report["uncleared"]) == 2


class TestCloseApi:
    def test_close_lifecycle(self):
        wb = client.get("/api/close/2030-01").json()
        assert wb["done_count"] == 0
        res = client.post(
            "/api/close/2030-01/item",
            json={"key": "tds", "done": True, "actor": "Tester"},
        )
        assert res.json()["done_count"] == 1
        res = client.post("/api/close/2030-01/item", json={"key": "tds", "done": False, "actor": ""})
        assert res.json()["done_count"] == 0

    def test_done_requires_actor(self):
        res = client.post("/api/close/2030-02/item", json={"key": "tds", "done": True, "actor": ""})
        assert res.status_code == 400

    def test_invalid_period(self):
        assert client.get("/api/close/January").status_code == 400


class TestOperations:
    def test_feed(self):
        _run_recon()
        res = client.get("/api/operations?limit=10")
        assert res.status_code == 200
        events = res.json()["events"]
        assert events and events[0]["event_id"] >= events[-1]["event_id"]


class TestHealth:
    def test_healthz(self):
        res = client.get("/healthz")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
