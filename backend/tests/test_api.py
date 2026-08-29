"""API tests: org-scoped endpoints with session auth + public signed links."""

from pathlib import Path

from tests.conftest import make_client

SAMPLES = Path(__file__).parent.parent / "sample_data"


def _run_recon(client, org) -> dict:
    with open(SAMPLES / "gstr2b_sample.json", "rb") as g2b, \
         open(SAMPLES / "purchase_register_sample.csv", "rb") as reg:
        res = client.post(
            f"/api/orgs/{org}/recon",
            data={"client_name": "API Test Client", "period_note": "April 2026"},
            files={
                "gstr2b_file": ("gstr2b.json", g2b, "application/json"),
                "register_file": ("register.csv", reg, "text/csv"),
            },
        )
    assert res.status_code == 200, res.text
    return res.json()


class TestReconApi:
    def test_recon_and_fetch(self, owner_client):
        client, org = owner_client
        token = _run_recon(client, org)["token"]
        res = client.get(f"/api/reports/{token}")
        assert res.status_code == 200
        report = res.json()["report"]
        assert report["client_name"] == "API Test Client"
        assert report["verified_at_risk"] == "0"
        assert float(report["pending_at_risk"]) > 0
        assert len(res.json()["trail"]) >= 1

    def test_report_link_viewable_logged_out(self, owner_client):
        from fastapi.testclient import TestClient

        from app.main import app

        client, org = owner_client
        token = _run_recon(client, org)["token"]
        anon = TestClient(app, base_url="https://testserver")
        assert anon.get(f"/api/reports/{token}").status_code == 200
        assert anon.get(f"/r/{token}").status_code == 200

    def test_verify_moves_headline_with_reviewer_identity(self, owner_client):
        client, org = owner_client
        token = _run_recon(client, org)["token"]
        report = client.get(f"/api/reports/{token}").json()["report"]
        exc_id = report["exceptions"][0]["exception_id"]
        amount = report["exceptions"][0]["itc_amount"]
        res = client.post(f"/api/reports/{token}/verify", json={"exception_id": exc_id})
        assert res.status_code == 200
        updated = res.json()["report"]
        assert updated["verified_at_risk"] == amount
        item = next(e for e in updated["exceptions"] if e["exception_id"] == exc_id)
        assert item["verified_by"] == "Owner"  # session identity, not typed name

    def test_verify_requires_session(self, owner_client):
        from fastapi.testclient import TestClient

        from app.main import app

        client, org = owner_client
        token = _run_recon(client, org)["token"]
        anon = TestClient(app, base_url="https://testserver")
        res = anon.post(f"/api/reports/{token}/verify", json={"exception_id": "E0001"})
        assert res.status_code == 401

    def test_verify_requires_reviewer_role(self, db_conn, owner_client):
        client, org = owner_client
        token = _run_recon(client, org)["token"]
        preparer, _ = make_client(db_conn, "preparer@test.local", role="preparer", org_id=org)
        res = preparer.post(f"/api/reports/{token}/verify", json={"exception_id": "E0001"})
        assert res.status_code == 403
        reviewer, _ = make_client(db_conn, "reviewer@test.local", role="reviewer", org_id=org)
        exc_id = client.get(f"/api/reports/{token}").json()["report"]["exceptions"][0]["exception_id"]
        res = reviewer.post(f"/api/reports/{token}/verify", json={"exception_id": exc_id})
        assert res.status_code == 200
        item = next(
            e for e in res.json()["report"]["exceptions"] if e["exception_id"] == exc_id
        )
        assert item["ca_signoff"] == "ICAI-000111"  # from the reviewer's profile

    def test_outside_reviewer_cannot_verify(self, db_conn, owner_client):
        client, org = owner_client
        token = _run_recon(client, org)["token"]
        outsider, _ = make_client(db_conn, "outsider@test.local")
        res = outsider.post(f"/api/reports/{token}/verify", json={"exception_id": "E0001"})
        assert res.status_code == 404  # org hidden from non-members

    def test_tampered_token_rejected(self, owner_client):
        client, org = owner_client
        token = _run_recon(client, org)["token"]
        assert client.get(f"/api/reports/{token}tampered").status_code == 404

    def test_bad_file_type_rejected(self, owner_client):
        client, org = owner_client
        res = client.post(
            f"/api/orgs/{org}/recon",
            data={"client_name": "X"},
            files={
                "gstr2b_file": ("evil.exe", b"MZ", "application/octet-stream"),
                "register_file": ("register.csv", b"a,b", "text/csv"),
            },
        )
        assert res.status_code == 400

    def test_excel_export(self, owner_client):
        client, org = owner_client
        token = _run_recon(client, org)["token"]
        res = client.get(f"/r/{token}/export.xlsx")
        assert res.status_code == 200
        assert res.content[:2] == b"PK"

    def test_cross_org_isolation(self, db_conn, owner_client):
        client, org = owner_client
        _run_recon(client, org)
        other, other_org = make_client(db_conn, "other@test.local")
        wq = other.get(f"/api/orgs/{other_org}/workqueue").json()
        assert wq["total_decisions"] == 0


class TestBankRecApi:
    def test_bankrec_end_to_end(self, owner_client):
        client, org = owner_client
        with open(SAMPLES / "bank_statement_sample.csv", "rb") as stmt, \
             open(SAMPLES / "bank_ledger_sample.csv", "rb") as ledger:
            res = client.post(
                f"/api/orgs/{org}/bankrec",
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
    def test_close_lifecycle(self, owner_client):
        client, org = owner_client
        wb = client.get(f"/api/orgs/{org}/close/2030-01").json()
        assert wb["done_count"] == 0
        res = client.post(
            f"/api/orgs/{org}/close/2030-01/item", json={"key": "tds", "done": True}
        )
        assert res.json()["done_count"] == 1
        assert res.json()["workbook"]["items"][3]["done_by"] == "Owner"
        res = client.post(
            f"/api/orgs/{org}/close/2030-01/item", json={"key": "tds", "done": False}
        )
        assert res.json()["done_count"] == 0

    def test_invalid_period(self, owner_client):
        client, org = owner_client
        assert client.get(f"/api/orgs/{org}/close/January").status_code == 400

    def test_viewer_cannot_tick(self, db_conn, owner_client):
        client, org = owner_client
        viewer, _ = make_client(db_conn, "viewer2@test.local", role="viewer", org_id=org)
        assert viewer.get(f"/api/orgs/{org}/close/2030-01").status_code == 200
        res = viewer.post(
            f"/api/orgs/{org}/close/2030-01/item", json={"key": "tds", "done": True}
        )
        assert res.status_code == 403


class TestOperations:
    def test_feed(self, owner_client):
        client, org = owner_client
        _run_recon(client, org)
        res = client.get(f"/api/orgs/{org}/operations?limit=10")
        assert res.status_code == 200
        events = res.json()["events"]
        assert events and events[0]["event_id"] >= events[-1]["event_id"]
        assert any(e["actor"] == "owner@test.local" for e in events)


class TestHealth:
    def test_healthz(self, owner_client):
        client, _ = owner_client
        res = client.get("/healthz")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
