"""Bookkeeping Agent tests: rules engine determinism, no-key gating (pending
suggestions never categorize), confirm immutability, the rule learning loop
(confirm once -> next import auto-codes), and ledger export gating."""

from decimal import Decimal

import pytest

from app.books.coa import ChartOfAccounts
from app.books.rules import RuleStore, apply_rules
from app.books.store import (
    AlreadyConfirmed,
    LedgerStore,
    build_ledger_csv,
    new_txn,
    summarize,
)

STATEMENT = (
    "date,narration,ref,withdrawal,deposit\n"
    "01-01-2026,NEFT ACME SUPPLIES PVT LTD,UTR001,11800,\n"
    "02-01-2026,SALARY JANUARY STAFF,NEFT002,50000,\n"
    "03-01-2026,CUSTOMER PAYMENT RELIANCE RETAIL,UTR003,,25000\n"
    "04-01-2026,SB A/C QUARTERLY CHARGES,CHG004,590,\n"
)


def _import(client, org, period: str, csv_text: str = STATEMENT) -> dict:
    res = client.post(
        f"/api/orgs/{org}/books/{period}/transactions",
        files={"statement_file": ("stmt.csv", csv_text.encode(), "text/csv")},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _first_pending(body: dict) -> dict:
    return next(t for t in body["ledger"]["txns"] if t["status"] == "pending")


class TestRulesEngine:
    def test_priority_order_and_field_match(self, db_conn, org):
        store = RuleStore(db_conn, org)
        store.add("description", "salary", "6000", created_by="Asha", priority=50)
        store.add("description", "sal", "6900", created_by="Asha", priority=90)
        store.add("ref", "CHG", "6400", created_by="Asha")
        rules = store.list()
        assert apply_rules(rules, "SALARY JANUARY STAFF", "").account_code == "6000"
        assert apply_rules(rules, "quarterly fees", "CHG004").account_code == "6400"
        assert apply_rules(rules, "no match here", "UTR9") is None

    def test_rejects_short_patterns_and_duplicates(self, db_conn, org):
        store = RuleStore(db_conn, org)
        with pytest.raises(ValueError):
            store.add("description", "ab", "6000", created_by="Asha")
        store.add("description", "salary", "6000", created_by="Asha")
        with pytest.raises(ValueError):
            store.add("description", "SALARY", "6900", created_by="Asha")


class TestImportGating:
    def test_no_llm_key_leaves_unmatched_pending_without_suggestion(self, owner_client):
        client, org = owner_client
        body = _import(client, org, "2031-01")
        txns = body["ledger"]["txns"]
        assert len(txns) == 4
        for txn in txns:
            if txn["status"] == "pending":
                assert txn["suggested_account"] == ""
                assert txn["source"] == ""
        assert body["summary"]["pending_count"] == len(
            [t for t in txns if t["status"] == "pending"]
        )

    def test_reimport_of_same_statement_is_deduped(self, owner_client):
        client, org = owner_client
        _import(client, org, "2031-02")
        body = _import(client, org, "2031-02")
        assert body["summary"]["txn_count"] == 4

    def test_pending_never_enters_account_totals(self, owner_client):
        # runs before any rule exists, so every row is pending
        client, org = owner_client
        body = _import(client, org, "2031-03")
        assert body["summary"]["accounts"] == {}
        assert body["summary"]["pending_count"] == 4
        assert body["summary"]["pending_total"] == "-37390"


class TestConfirmAndLearningLoop:
    def test_confirm_requires_known_account(self, owner_client):
        client, org = owner_client
        body = _import(client, org, "2031-04")
        txn = _first_pending(body)
        res = client.post(
            f"/api/orgs/{org}/books/2031-04/txn/{txn['txn_id']}/confirm",
            json={"account_code": "9999"},
        )
        assert res.status_code == 400

    def test_confirm_is_immutable(self, owner_client):
        client, org = owner_client
        body = _import(client, org, "2031-05")
        txn = _first_pending(body)
        first = client.post(
            f"/api/orgs/{org}/books/2031-05/txn/{txn['txn_id']}/confirm",
            json={"account_code": "6000"},
        )
        assert first.status_code == 200
        second = client.post(
            f"/api/orgs/{org}/books/2031-05/txn/{txn['txn_id']}/confirm",
            json={"account_code": "6900"},
        )
        assert second.status_code == 409

    def test_confirm_with_rule_then_next_import_auto_codes(self, owner_client):
        client, org = owner_client
        body = _import(client, org, "2031-06")
        salary = next(
            t for t in body["ledger"]["txns"] if "SALARY" in t["description"]
        )
        res = client.post(
            f"/api/orgs/{org}/books/2031-06/txn/{salary['txn_id']}/confirm",
            json={"account_code": "6000", "rule_pattern": "SALARY"},
        )
        assert res.status_code == 200, res.text
        # second month: same counterparty, new period -> rule fires, source=rule
        second_month = STATEMENT.replace("-01-2026", "-02-2026").replace(
            "JANUARY", "FEBRUARY"
        )
        body2 = _import(client, org, "2031-07", second_month)
        salary2 = next(
            t for t in body2["ledger"]["txns"] if "SALARY" in t["description"]
        )
        assert salary2["status"] == "coded"
        assert salary2["source"] == "rule"
        assert salary2["account_code"] == "6000"
        assert body2["summary"]["accounts"]["6000"]["total"] == "-50000"

    def test_events_logged_for_confirm_and_rule(self, owner_client):
        client, org = owner_client
        body = _import(client, org, "2031-06")
        salary = next(t for t in body["ledger"]["txns"] if "SALARY" in t["description"])
        client.post(
            f"/api/orgs/{org}/books/2031-06/txn/{salary['txn_id']}/confirm",
            json={"account_code": "6000", "rule_pattern": "SALARY"},
        )
        actions = [
            e["action"]
            for e in client.get(f"/api/orgs/{org}/operations?limit=100").json()["events"]
        ]
        assert "txn_imported" in actions
        assert "txn_category_confirmed" in actions
        assert "rule_created" in actions


class TestLedgerStoreUnit:
    def test_double_confirm_raises(self, db_conn, org):
        store = LedgerStore(db_conn, org)
        txn = new_txn("01-01-2026", "RENT OFFICE", "R1", Decimal("-30000"), "s:1")
        store.import_txns("2026-01", [txn])
        store.confirm("2026-01", txn.txn_id, "6100", actor="Asha")
        with pytest.raises(AlreadyConfirmed):
            store.confirm("2026-01", txn.txn_id, "6100", actor="Asha")

    def test_summary_excludes_pending_and_llm_suggested(self, db_conn, org):
        store = LedgerStore(db_conn, org)
        a = new_txn("01-01-2026", "RENT OFFICE", "R1", Decimal("-30000"), "s:1")
        b = new_txn("02-01-2026", "MYSTERY UPI", "U1", Decimal("-999"), "s:2")
        store.import_txns("2026-01", [a, b])
        store.confirm("2026-01", a.txn_id, "6100", actor="Asha")
        store.suggest("2026-01", {b.txn_id: ("6900", "0.55")})
        summary = summarize(store.load("2026-01"))
        assert summary["accounts"] == {"6100": {"count": 1, "total": "-30000"}}
        assert summary["pending_count"] == 1
        suggested = store.get_txn("2026-01", b.txn_id)
        assert suggested.status == "pending"
        assert suggested.suggested_account == "6900"

    def test_ledger_csv_exports_only_categorized_rows(self, db_conn, org):
        store = LedgerStore(db_conn, org)
        a = new_txn("01-01-2026", "RENT OFFICE", "R1", Decimal("-30000"), "s:1")
        b = new_txn("02-01-2026", "MYSTERY UPI", "U1", Decimal("-999"), "s:2")
        store.import_txns("2026-01", [a, b])
        store.confirm("2026-01", a.txn_id, "6100", actor="Asha")
        csv_text = build_ledger_csv(store.load("2026-01"), {"6100": "Rent"})
        lines = csv_text.strip().split("\n")
        assert len(lines) == 2
        assert "RENT OFFICE" in lines[1] and "Rent" in lines[1]


class TestCoaAndExportEndpoints:
    def test_default_coa_seeded_with_gst_accounts(self, owner_client):
        client, org = owner_client
        accounts = client.get(f"/api/orgs/{org}/books/coa").json()["accounts"]
        codes = {a["code"] for a in accounts}
        assert {"6400", "7000", "7020", "4000"} <= codes
        assert len(accounts) >= 40

    def test_add_account_and_reject_duplicate(self, db_conn, org):
        coa = ChartOfAccounts(db_conn, org)
        coa.add("6950", "Festival Expenses", "expense")
        assert coa.get("6950").name == "Festival Expenses"
        with pytest.raises(ValueError):
            coa.add("6950", "Duplicate", "expense")
        with pytest.raises(ValueError):
            coa.add("6960", "Bad Type", "wonky")

    def test_ledger_export_404_when_nothing_categorized(self, owner_client):
        client, org = owner_client
        res = client.get(f"/api/orgs/{org}/books/1999-01/ledger.csv")
        assert res.status_code == 404

    def test_ledger_export_serves_categorized_period(self, owner_client):
        client, org = owner_client
        body = _import(client, org, "2031-08")
        txn = _first_pending(body)
        client.post(
            f"/api/orgs/{org}/books/2031-08/txn/{txn['txn_id']}/confirm",
            json={"account_code": "6400"},
        )
        res = client.get(f"/api/orgs/{org}/books/2031-08/ledger.csv")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/csv")
        assert "6400" in res.text
