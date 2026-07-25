"""Review Agent tests: deterministic P&L + variance from two months of
ledger, each flag kind, no-key narration gating, verify flow, and
verification survival across rebuilds (content-derived flag ids)."""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="audita-test-review-")
os.environ.setdefault("AUDITA_DATA_DIR", _TMP)
os.environ.pop("GEMINI_API_KEY", None)

from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.books.coa import Account  # noqa: E402
from app.books.store import Ledger, new_txn  # noqa: E402
from app.main import app, ledger_store  # noqa: E402
from app.review.compute import (  # noqa: E402
    ReviewWorkbook,
    compute_flags,
    compute_pnl,
    prior_period_of,
)
from app.review.store import AlreadyVerified, ReviewStore  # noqa: E402

client = TestClient(app)

ACCOUNTS = [
    Account("4000", "Sales — Domestic", "income"),
    Account("6000", "Salaries & Wages", "expense"),
    Account("6100", "Rent", "expense"),
    Account("7000", "GST Input — CGST", "tax"),
]


def _txn(date, desc, ref, amount, account, status="confirmed"):
    txn = new_txn(date, desc, ref, Decimal(amount), "test:1")
    txn.status = status
    txn.source = "human" if status == "confirmed" else ""
    txn.account_code = account if status in ("coded", "confirmed") else ""
    return txn


def _ledger(period, txns):
    return Ledger(period=period, created_at="t", txns=txns)


PRIOR = _ledger("2026-01", [
    _txn("05-01-2026", "CUSTOMER PAYMENT ACME RETAIL", "U1", "100000", "4000"),
    _txn("07-01-2026", "SALARY STAFF", "N1", "-40000", "6000"),
    _txn("10-01-2026", "RENT OFFICE LANDLORD", "R1", "-30000", "6100"),
])

CURRENT = _ledger("2026-02", [
    _txn("05-02-2026", "CUSTOMER PAYMENT ACME RETAIL", "U2", "120000", "4000"),
    _txn("07-02-2026", "SALARY STAFF", "N2", "-90000", "6000"),          # +125% variance
    _txn("10-02-2026", "RENT OFFICE LANDLORD", "R2", "-30000", "6100"),  # round sum
    _txn("15-02-2026", "NEFT ZETA CONSULTING FEES", "U3", "-15500", "6100"),  # new party
    _txn("20-02-2026", "MYSTERY UPI", "U4", "-777", "", status="pending"),    # never counted
])


class TestPriorPeriod:
    def test_rollover(self):
        assert prior_period_of("2026-02") == "2026-01"
        assert prior_period_of("2026-01") == "2025-12"


class TestComputePnl:
    def test_signed_totals_and_summary(self):
        lines, summary = compute_pnl(CURRENT, PRIOR, ACCOUNTS)
        by_code = {line.account_code: line for line in lines}
        assert by_code["4000"].current == "120000"
        assert by_code["4000"].prior == "100000"
        assert by_code["4000"].change == "20000"
        assert by_code["4000"].change_pct == "20.0"
        assert summary["income"] == "120000"
        assert summary["expense"] == "-135500"
        assert summary["net_result"] == "-15500"

    def test_pending_never_enters_pnl(self):
        lines, _ = compute_pnl(CURRENT, PRIOR, ACCOUNTS)
        assert "" not in {line.account_code for line in lines}
        total = sum(Decimal(line.current) for line in lines)
        assert total == Decimal("120000") - 90000 - 30000 - 15500


class TestComputeFlags:
    def test_variance_flag_fires_beyond_threshold(self):
        flags = compute_flags(CURRENT, PRIOR, ACCOUNTS)
        variance = {f.account_code: f for f in flags if f.kind == "variance"}
        # 6000: -40000 -> -90000 (125%); 6100: -30000 -> -45500 (51.7%)
        assert set(variance) == {"6000", "6100"}
        assert variance["6000"].amount == "-50000"
        assert "125.0%" in variance["6000"].title
        # 4000 moved 20% — below the 25% threshold, no flag
        assert "4000" not in variance

    def test_new_activity_flag(self):
        flags = compute_flags(CURRENT, PRIOR, ACCOUNTS)
        new = [f for f in flags if f.kind == "new_activity"]
        assert any("ZETA CONSULTING" in f.title for f in new)
        # existing counterparties don't fire
        assert not any("ACME" in f.title for f in new)

    def test_round_sum_flag(self):
        flags = compute_flags(CURRENT, PRIOR, ACCOUNTS)
        round_sums = [f for f in flags if f.kind == "round_sum"]
        amounts = {f.amount for f in round_sums}
        assert "-30000" in amounts       # rent
        assert "-90000" in amounts       # salary
        assert "-15500" not in amounts   # not round
        assert "-777" not in amounts     # pending never flagged

    def test_gst_drift_flag_only_with_register(self):
        flags = compute_flags(CURRENT, PRIOR, ACCOUNTS)
        assert not any(f.kind == "gst_drift" for f in flags)
        flags = compute_flags(CURRENT, PRIOR, ACCOUNTS,
                              gst_register_tax_total=Decimal("1800"))
        drift = [f for f in flags if f.kind == "gst_drift"]
        assert len(drift) == 1
        assert drift[0].amount == "-1800"  # ledger has no GST input postings

    def test_flag_ids_are_content_stable(self):
        a = compute_flags(CURRENT, PRIOR, ACCOUNTS)
        b = compute_flags(CURRENT, PRIOR, ACCOUNTS)
        assert [f.flag_id for f in a] == [f.flag_id for f in b]


class TestReviewStore:
    def _workbook(self):
        pnl, summary = compute_pnl(CURRENT, PRIOR, ACCOUNTS)
        flags = compute_flags(CURRENT, PRIOR, ACCOUNTS)
        return ReviewWorkbook(
            period="2026-02", prior_period="2026-01", created_at="",
            pnl=pnl, summary=summary, flags=flags,
        )

    def test_verify_flow_and_immutability(self, tmp_path):
        store = ReviewStore(tmp_path)
        wb = store.save_new(self._workbook())
        target = wb.flags[0].flag_id
        flag = store.verify_flag("2026-02", target, actor="Asha", ca_signoff="CA 42")
        assert flag.status == "verified"
        assert flag.ca_signoff == "CA 42"
        with pytest.raises(AlreadyVerified):
            store.verify_flag("2026-02", target, actor="Mallory")

    def test_rebuild_preserves_verified_matching_flags(self, tmp_path):
        store = ReviewStore(tmp_path)
        wb = store.save_new(self._workbook())
        target = wb.flags[0].flag_id
        store.verify_flag("2026-02", target, actor="Asha")
        rebuilt = store.save_new(self._workbook())
        by_id = {f.flag_id: f for f in rebuilt.flags}
        assert by_id[target].status == "verified"
        assert by_id[target].verified_by == "Asha"
        assert rebuilt.verified_count == 1
        assert rebuilt.pending_count == len(rebuilt.flags) - 1


class TestReviewApi:
    PERIOD = "2033-02"
    PRIOR_P = "2033-01"

    def _seed_ledgers(self):
        # seed through the app's own store: other test modules re-point
        # AUDITA_DATA_DIR after app import, so the env var can't be trusted
        store = ledger_store
        if store.load(self.PERIOD).txns:
            return
        store.import_txns(self.PRIOR_P, [
            _txn("05-01-2033", "CUSTOMER PAYMENT ACME RETAIL", "U1", "100000", "4000"),
            _txn("07-01-2033", "SALARY STAFF", "N1", "-40000", "6000"),
        ])
        store.import_txns(self.PERIOD, [
            _txn("05-02-2033", "CUSTOMER PAYMENT ACME RETAIL", "U2", "120000", "4000"),
            _txn("07-02-2033", "SALARY STAFF", "N2", "-90000", "6000"),
        ])

    def test_build_requires_categorized_txns(self):
        res = client.post("/api/review/1999-01")
        assert res.status_code == 400

    def test_build_and_get_workbook_no_llm_key(self):
        self._seed_ledgers()
        res = client.post(f"/api/review/{self.PERIOD}")
        assert res.status_code == 200, res.text
        wb = res.json()["workbook"]
        assert wb["prior_period"] == self.PRIOR_P
        assert wb["narrative"] == ""
        assert "not configured" in wb["narrative_note"]
        assert wb["pending_count"] == len(wb["flags"])
        assert any(f["kind"] == "variance" for f in wb["flags"])
        got = client.get(f"/api/review/{self.PERIOD}").json()["workbook"]
        assert got["summary"] == wb["summary"]

    def test_verify_flag_endpoint_and_events(self):
        self._seed_ledgers()
        wb = client.post(f"/api/review/{self.PERIOD}").json()["workbook"]
        flag_id = wb["flags"][0]["flag_id"]
        res = client.post(
            f"/api/review/{self.PERIOD}/flags/{flag_id}/verify",
            json={"actor": "Asha", "ca_signoff": "CA 42"},
        )
        assert res.status_code == 200, res.text
        wb2 = res.json()["workbook"]
        assert wb2["verified_count"] == 1
        second = client.post(
            f"/api/review/{self.PERIOD}/flags/{flag_id}/verify",
            json={"actor": "Mallory"},
        )
        assert second.status_code == 409
        actions = [e["action"] for e in
                   client.get("/api/operations?limit=100").json()["events"]]
        assert "review_computed" in actions
        assert "review_flag_verified" in actions

    def test_get_missing_workbook_404(self):
        res = client.get("/api/review/1998-01")
        assert res.status_code == 404
