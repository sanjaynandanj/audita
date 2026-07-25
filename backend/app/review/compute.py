"""Deterministic review computation.

Everything here is pure Decimal arithmetic over the categorized ledger
(coded + confirmed entries only — pending never enters a figure). The LLM
never touches this module; it only narrates the output.

Sign convention (inherited from the ledger): + is money into the bank
account, - is money out. P&L lines show the signed net movement per
account; income naturally lands positive, spend negative.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal

from ..books.coa import Account
from ..books.store import Ledger

PNL_TYPES = ("income", "cogs", "expense")
GST_INPUT_CODES = ("7000", "7010", "7020")

DEFAULT_VARIANCE_PCT = Decimal("25")        # flag when |change| exceeds this %
DEFAULT_VARIANCE_MIN = Decimal("10000")     # ...and the absolute change exceeds this
ROUND_SUM_UNIT = Decimal("10000")           # amounts divisible by this are "suspiciously round"


@dataclass
class PnlLine:
    account_code: str
    account_name: str
    account_type: str
    current: str            # signed net movement this period
    prior: str              # signed net movement prior period
    change: str             # current - prior
    change_pct: str         # "" when prior is 0


@dataclass
class ReviewFlag:
    flag_id: str
    kind: str               # variance | new_activity | round_sum | gst_drift
    account_code: str
    title: str
    detail: str             # every number here is computed, never narrated
    amount: str
    status: str = "pending"  # pending | verified
    verified_by: str = ""
    verified_at: str = ""
    ca_signoff: str = ""


def _flag_id(kind: str, key: str) -> str:
    return hashlib.sha256(f"{kind}:{key}".encode()).hexdigest()[:12]


def _account_totals(ledger: Ledger) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for txn in ledger.txns:
        if txn.status in ("coded", "confirmed"):
            totals[txn.account_code] = totals.get(txn.account_code, Decimal("0")) + Decimal(txn.amount)
    return totals


def _counterparty_key(description: str) -> str:
    """Deterministic counterparty token: first three alphabetic words."""
    words = [w for w in description.upper().split() if w.isalpha()]
    return " ".join(words[:3])


def compute_pnl(
    current: Ledger, prior: Ledger, accounts: list[Account]
) -> tuple[list[PnlLine], dict]:
    acc_by_code = {a.code: a for a in accounts}
    cur_totals = _account_totals(current)
    pri_totals = _account_totals(prior)

    lines: list[PnlLine] = []
    group_totals = {t: Decimal("0") for t in PNL_TYPES}
    for code in sorted(set(cur_totals) | set(pri_totals)):
        account = acc_by_code.get(code)
        acc_type = account.type if account else "unknown"
        cur = cur_totals.get(code, Decimal("0"))
        pri = pri_totals.get(code, Decimal("0"))
        change = cur - pri
        pct = ""
        if pri != 0:
            pct = str((change / abs(pri) * 100).quantize(Decimal("0.1")))
        lines.append(PnlLine(
            account_code=code,
            account_name=account.name if account else code,
            account_type=acc_type,
            current=str(cur), prior=str(pri), change=str(change), change_pct=pct,
        ))
        if acc_type in group_totals:
            group_totals[acc_type] += cur

    net = sum((group_totals[t] for t in PNL_TYPES), Decimal("0"))
    summary = {
        "income": str(group_totals["income"]),
        "cogs": str(group_totals["cogs"]),
        "expense": str(group_totals["expense"]),
        "net_result": str(net),
    }
    return lines, summary


def compute_flags(
    current: Ledger,
    prior: Ledger,
    accounts: list[Account],
    gst_register_tax_total: Decimal | None = None,
    variance_pct: Decimal = DEFAULT_VARIANCE_PCT,
    variance_min: Decimal = DEFAULT_VARIANCE_MIN,
) -> list[ReviewFlag]:
    acc_by_code = {a.code: a for a in accounts}
    cur_totals = _account_totals(current)
    pri_totals = _account_totals(prior)
    flags: list[ReviewFlag] = []

    def name(code: str) -> str:
        account = acc_by_code.get(code)
        return f"{code} {account.name}" if account else code

    # (a) variance beyond threshold, on accounts with a prior baseline
    for code in sorted(set(cur_totals) | set(pri_totals)):
        cur = cur_totals.get(code, Decimal("0"))
        pri = pri_totals.get(code, Decimal("0"))
        if pri == 0:
            continue
        change = cur - pri
        pct = abs(change) / abs(pri) * 100
        if pct > variance_pct and abs(change) > variance_min:
            flags.append(ReviewFlag(
                flag_id=_flag_id("variance", code),
                kind="variance",
                account_code=code,
                title=f"{name(code)} moved {pct.quantize(Decimal('0.1'))}% vs prior period",
                detail=(f"current {cur}, prior {pri}, change {change} "
                        f"(threshold {variance_pct}% and {variance_min})"),
                amount=str(change),
            ))

    # (b) new counterparties: activity in current with no prior-period presence
    prior_parties = {_counterparty_key(t.description) for t in prior.txns
                     if t.status in ("coded", "confirmed")}
    seen: dict[str, Decimal] = {}
    for txn in current.txns:
        if txn.status not in ("coded", "confirmed"):
            continue
        key = _counterparty_key(txn.description)
        if key and key not in prior_parties:
            seen[key] = seen.get(key, Decimal("0")) + Decimal(txn.amount)
    for key, total in sorted(seen.items()):
        flags.append(ReviewFlag(
            flag_id=_flag_id("new_activity", key),
            kind="new_activity",
            account_code="",
            title=f"New counterparty: {key}",
            detail=f"no matching narration in prior period; net movement {total}",
            amount=str(total),
        ))

    # (c) suspiciously round sums
    for txn in current.txns:
        if txn.status not in ("coded", "confirmed"):
            continue
        amount = Decimal(txn.amount)
        if amount != 0 and abs(amount) >= ROUND_SUM_UNIT and abs(amount) % ROUND_SUM_UNIT == 0:
            flags.append(ReviewFlag(
                flag_id=_flag_id("round_sum", txn.txn_id),
                kind="round_sum",
                account_code=txn.account_code,
                title=f"Round-sum entry {amount} — {txn.description[:60]}",
                detail=f"{txn.txn_date} ref {txn.ref or '—'} coded to {name(txn.account_code)}",
                amount=str(amount),
            ))

    # (d) GST input control drift vs the confirmed purchase register
    if gst_register_tax_total is not None:
        gst_ledger_total = sum(
            (abs(cur_totals.get(code, Decimal("0"))) for code in GST_INPUT_CODES),
            Decimal("0"),
        )
        drift = gst_ledger_total - gst_register_tax_total
        if drift != 0:
            flags.append(ReviewFlag(
                flag_id=_flag_id("gst_drift", current.period),
                kind="gst_drift",
                account_code="7000",
                title=f"GST input control drift of {drift}",
                detail=(f"GST input accounts total {gst_ledger_total} vs confirmed purchase "
                        f"register tax {gst_register_tax_total}"),
                amount=str(drift),
            ))

    return flags


@dataclass
class ReviewWorkbook:
    period: str
    prior_period: str
    created_at: str
    pnl: list = field(default_factory=list)          # list[PnlLine]
    summary: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)        # list[ReviewFlag]
    narrative: str = ""                              # LLM output, advice only
    narrative_note: str = ""
    txn_counts: dict = field(default_factory=dict)

    @property
    def verified_count(self) -> int:
        return sum(1 for f in self.flags if f.status == "verified")

    @property
    def pending_count(self) -> int:
        return sum(1 for f in self.flags if f.status == "pending")


def prior_period_of(period: str) -> str:
    year, month = int(period[:4]), int(period[5:7])
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"
