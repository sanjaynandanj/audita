"""Chart of accounts — default Indian-SME set, seedable and extendable.

Stored as JSON under data/books/coa.json. Codes are stable identifiers;
ledger entries reference accounts by code.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

ACCOUNT_TYPES = ("income", "cogs", "expense", "tax", "asset", "liability", "equity")

DEFAULT_ACCOUNTS: tuple[tuple[str, str, str], ...] = (
    ("1000", "Cash in Hand", "asset"),
    ("1100", "Bank Accounts", "asset"),
    ("1200", "Accounts Receivable", "asset"),
    ("1300", "Fixed Assets", "asset"),
    ("1400", "Security Deposits", "asset"),
    ("2000", "Accounts Payable", "liability"),
    ("2100", "Loans Payable", "liability"),
    ("2200", "Salaries Payable", "liability"),
    ("3000", "Owner's Capital", "equity"),
    ("3100", "Drawings", "equity"),
    ("4000", "Sales — Domestic", "income"),
    ("4100", "Sales — Exports", "income"),
    ("4200", "Other Income", "income"),
    ("4300", "Interest Income", "income"),
    ("5000", "Purchases — Raw Materials", "cogs"),
    ("5100", "Purchases — Trading Goods", "cogs"),
    ("5200", "Freight Inward", "cogs"),
    ("5300", "Customs Duty", "cogs"),
    ("6000", "Salaries & Wages", "expense"),
    ("6010", "Staff Welfare", "expense"),
    ("6100", "Rent", "expense"),
    ("6110", "Electricity", "expense"),
    ("6200", "Telephone & Internet", "expense"),
    ("6210", "Software & Subscriptions", "expense"),
    ("6300", "Professional Fees", "expense"),
    ("6310", "Audit Fees", "expense"),
    ("6400", "Bank Charges", "expense"),
    ("6410", "Interest Expense", "expense"),
    ("6500", "Travel", "expense"),
    ("6510", "Conveyance", "expense"),
    ("6520", "Vehicle Expenses", "expense"),
    ("6600", "Marketing & Advertising", "expense"),
    ("6700", "Repairs & Maintenance", "expense"),
    ("6710", "Office Supplies", "expense"),
    ("6720", "Printing & Stationery", "expense"),
    ("6800", "Insurance", "expense"),
    ("6900", "Miscellaneous Expenses", "expense"),
    ("7000", "GST Input — CGST", "tax"),
    ("7010", "GST Input — SGST", "tax"),
    ("7020", "GST Input — IGST", "tax"),
    ("7100", "GST Output — CGST", "tax"),
    ("7110", "GST Output — SGST", "tax"),
    ("7120", "GST Output — IGST", "tax"),
    ("7200", "TDS Payable", "tax"),
    ("7300", "Income Tax / Advance Tax", "tax"),
)


@dataclass
class Account:
    code: str
    name: str
    type: str


class ChartOfAccounts:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([Account(c, n, t) for c, n, t in DEFAULT_ACCOUNTS])

    def _write(self, accounts: list[Account]) -> None:
        self.path.write_text(
            json.dumps([asdict(a) for a in accounts], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def list(self) -> list[Account]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return sorted((Account(**a) for a in data), key=lambda a: a.code)

    def get(self, code: str) -> Account:
        for account in self.list():
            if account.code == code:
                return account
        raise KeyError(f"no account with code {code!r}")

    def add(self, code: str, name: str, type: str) -> Account:
        code, name = code.strip(), name.strip()
        if not code or not name:
            raise ValueError("account code and name are required")
        if type not in ACCOUNT_TYPES:
            raise ValueError(f"account type must be one of {', '.join(ACCOUNT_TYPES)}")
        accounts = self.list()
        if any(a.code == code for a in accounts):
            raise ValueError(f"account code {code} already exists")
        account = Account(code=code, name=name, type=type)
        self._write([*accounts, account])
        return account
