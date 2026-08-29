"""Agent Workspace tests: the unified queue aggregates pending decisions
from every agent, links recon items behind signed tokens, and drops items
once the underlying decision is made."""

from decimal import Decimal
from pathlib import Path

from app.books.store import LedgerStore, new_txn
from app.close.workbook import CloseStore

SAMPLES = Path(__file__).parent.parent / "sample_data"

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f030005fe02fea72d1e480000000049454e44ae426082"
)

FIELDS = {
    "supplier_gstin": "27AAPFU0939F1ZV", "invoice_no": "WQ/1",
    "supplier_name": "WQ", "invoice_date": "01-01-2035",
    "taxable_value": "100", "igst": "0", "cgst": "9", "sgst": "9",
    "cess": "0", "total": "118",
}


def _items(client, org, kind=""):
    body = client.get(f"/api/orgs/{org}/workqueue").json()
    if kind:
        return [i for i in body["items"] if i["kind"] == kind]
    return body


class TestWorkqueue:
    def test_invoice_draft_appears_then_clears_on_confirm(self, owner_client):
        client, org = owner_client
        res = client.post(
            f"/api/orgs/{org}/invoices",
            data={"period": "2035-01"},
            files={"invoice_file": ("wq-bill.png", PNG_1PX, "image/png")},
        )
        invoice_id = res.json()["invoice"]["invoice_id"]
        drafts = [i for i in _items(client, org, "invoice_draft") if i["ref"] == invoice_id]
        assert len(drafts) == 1
        assert drafts[0]["agent"] == "invoice"
        assert drafts[0]["link"] == "/app/invoices"

        client.post(f"/api/orgs/{org}/invoices/{invoice_id}/confirm", json={"fields": FIELDS})
        assert not [i for i in _items(client, org, "invoice_draft") if i["ref"] == invoice_id]

    def test_pending_txns_appear_with_period_ref(self, db_conn, owner_client):
        client, org = owner_client
        txn = new_txn("01-01-2035", "WQ MYSTERY NARRATION", "W1", Decimal("-4321"), "wq:1")
        LedgerStore(db_conn, org).import_txns("2035-02", [txn])
        db_conn.commit()
        pending = [i for i in _items(client, org, "txns_pending") if i["ref"] == "2035-02"]
        assert len(pending) == 1
        assert pending[0]["agent"] == "bookkeeping"
        assert pending[0]["count"] == 1
        assert pending[0]["amount"] == "-4321"

    def test_touched_close_workbook_lists_open_items(self, db_conn, owner_client):
        client, org = owner_client
        client.post(f"/api/orgs/{org}/close/2035-03/item", json={"key": "bank-recon", "done": True})
        wq = [i for i in _items(client, org, "close_open") if i["ref"] == "2035-03"]
        assert len(wq) == 1
        total_items = len(CloseStore(db_conn, org).load_or_create("2035-03").items)
        assert wq[0]["count"] == total_items - 1

    def test_untouched_close_workbook_is_not_queued(self, owner_client):
        client, org = owner_client
        client.get(f"/api/orgs/{org}/close/2035-04")
        assert not [i for i in _items(client, org, "close_open") if i["ref"] == "2035-04"]

    def test_review_flags_and_recon_exceptions_queued(self, db_conn, owner_client):
        client, org = owner_client
        # review flags: seed a ledger month with a round sum, build workbook
        txn = new_txn("01-05-2035", "WQ ROUND PAYMENT PARTY", "W2",
                      Decimal("-20000"), "wq:2")
        txn.status = "confirmed"
        txn.source = "human"
        txn.account_code = "6100"
        LedgerStore(db_conn, org).import_txns("2035-05", [txn])
        db_conn.commit()
        client.post(f"/api/orgs/{org}/review/2035-05")
        flags = [i for i in _items(client, org, "review_flags") if i["ref"] == "2035-05"]
        assert len(flags) == 1
        assert flags[0]["agent"] == "review"

        # recon exceptions via the sample files
        with open(SAMPLES / "gstr2b_sample.json", "rb") as g2b, \
             open(SAMPLES / "purchase_register_sample.csv", "rb") as reg:
            res = client.post(
                f"/api/orgs/{org}/recon",
                data={"client_name": "WQ Traders", "period_note": "2035-05"},
                files={"gstr2b_file": ("g.json", g2b, "application/json"),
                       "register_file": ("r.csv", reg, "text/csv")},
            )
        report_id = res.json()["report_id"]
        recon = [i for i in _items(client, org, "recon_exceptions") if i["ref"] == report_id]
        assert len(recon) == 1
        assert recon[0]["link"].startswith("/app/r/")
        # the signed token in the link resolves through the report endpoint
        token = recon[0]["link"].removeprefix("/app/r/")
        assert client.get(f"/api/reports/{token}").status_code == 200

    def test_totals_and_sort_order(self, db_conn, owner_client):
        client, org = owner_client
        client.post(
            f"/api/orgs/{org}/invoices",
            data={"period": "2035-01"},
            files={"invoice_file": ("wq-bill.png", PNG_1PX, "image/png")},
        )
        txn = new_txn("01-01-2035", "WQ MYSTERY NARRATION", "W1", Decimal("-4321"), "wq:1")
        LedgerStore(db_conn, org).import_txns("2035-02", [txn])
        db_conn.commit()
        body = _items(client, org)
        assert body["total_decisions"] == sum(i["count"] for i in body["items"])
        assert set(body["by_agent"]) <= {"itc-recon", "invoice", "bookkeeping", "close", "review"}
        amounts = [abs(Decimal(i["amount"])) for i in body["items"] if i["amount"]]
        assert amounts == sorted(amounts, reverse=True)
