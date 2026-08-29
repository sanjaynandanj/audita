"""Chart of accounts — default Indian-SME set, seedable and extendable.

One row per (org, code) in coa_accounts; seeded with the default set when
an org's chart is empty. Codes are stable identifiers; ledger entries
reference accounts by code.
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg import Connection

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
    def __init__(self, conn: Connection, org_id: str):
        self.conn = conn
        self.org_id = org_id
        row = conn.execute(
            "SELECT count(*) AS n FROM coa_accounts WHERE org_id = %s", (org_id,)
        ).fetchone()
        if row["n"] == 0:
            conn.cursor().executemany(
                "INSERT INTO coa_accounts (org_id, code, name, type) VALUES (%s, %s, %s, %s)",
                [(org_id, c, n, t) for c, n, t in DEFAULT_ACCOUNTS],
            )

    def list(self) -> list[Account]:
        rows = self.conn.execute(
            "SELECT code, name, type FROM coa_accounts WHERE org_id = %s ORDER BY code",
            (self.org_id,),
        ).fetchall()
        return [Account(**r) for r in rows]

    def get(self, code: str) -> Account:
        row = self.conn.execute(
            "SELECT code, name, type FROM coa_accounts WHERE org_id = %s AND code = %s",
            (self.org_id, code),
        ).fetchone()
        if row is None:
            raise KeyError(f"no account with code {code!r}")
        return Account(**row)

    def add(self, code: str, name: str, type: str) -> Account:
        code, name = code.strip(), name.strip()
        if not code or not name:
            raise ValueError("account code and name are required")
        if type not in ACCOUNT_TYPES:
            raise ValueError(f"account type must be one of {', '.join(ACCOUNT_TYPES)}")
        exists = self.conn.execute(
            "SELECT 1 FROM coa_accounts WHERE org_id = %s AND code = %s", (self.org_id, code)
        ).fetchone()
        if exists:
            raise ValueError(f"account code {code} already exists")
        self.conn.execute(
            "INSERT INTO coa_accounts (org_id, code, name, type) VALUES (%s, %s, %s, %s)",
            (self.org_id, code, name, type),
        )
        return Account(code=code, name=name, type=type)
