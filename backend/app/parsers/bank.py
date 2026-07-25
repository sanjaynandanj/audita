"""Parsers for bank statements and books-side bank ledgers (CSV/XLSX).

Bank statements: date / narration / ref / withdrawal / deposit (or a single
signed amount column). Books ledger (Tally bank ledger export): date /
particulars / vch no / debit / credit — note the mirror: a ledger DEBIT to the
bank account is money IN (+), a statement DEBIT is money OUT (-).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..engine.bank import BankSource, BankTxn
from .tabular import _rows_from_csv, _rows_from_xlsx

_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("date", "txn date", "transaction date", "value date", "tran date", "post date"),
    "description": ("description", "narration", "particulars", "details", "transaction details", "remarks"),
    "ref": ("ref", "ref no", "reference", "cheque no", "chq no", "chq/ref no", "cheque/ref no",
            "utr", "utr no", "vch no", "voucher no", "instrument no"),
    "debit": ("debit", "withdrawal", "withdrawal amt", "withdrawal amount", "dr", "debit amount", "paid out"),
    "credit": ("credit", "deposit", "deposit amt", "deposit amount", "cr", "credit amount", "paid in"),
    "amount": ("amount", "txn amount", "transaction amount"),
}


def _dec(value) -> Decimal:
    if value is None:
        return Decimal("0")
    text = str(value).strip().replace(",", "").replace("₹", "")
    if not text or text in ("-", "--"):
        return Decimal("0")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        d = Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal("0")
    return -d if negative else d


def _load_rows(path: Path) -> list[list]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _rows_from_csv(path)
    if suffix in (".xlsx", ".xls"):
        return _rows_from_xlsx(path)
    raise ValueError(f"Unsupported bank file type: {suffix}")


def _colmap(headers: list) -> dict[str, int]:
    normalized = [str(h or "").strip().lower().replace(".", "").replace("_", " ") for h in headers]
    mapping: dict[str, int] = {}
    for fieldname, aliases in _ALIASES.items():
        for idx, header in enumerate(normalized):
            if header in aliases and fieldname not in mapping:
                mapping[fieldname] = idx
                break
    return mapping


def _parse(path: Path, source: BankSource, books_convention: bool) -> list[BankTxn]:
    rows = _load_rows(path)
    header_idx, colmap = None, {}
    for idx, row in enumerate(rows[:10]):
        candidate = _colmap(row)
        if "date" in candidate and ("amount" in candidate or "debit" in candidate or "credit" in candidate):
            header_idx, colmap = idx, candidate
            break
    if header_idx is None:
        raise ValueError(
            f"Could not locate a header row with Date and Debit/Credit (or Amount) columns in {path.name}."
        )

    def cell(row: list, f: str) -> str:
        i = colmap.get(f)
        if i is None or i >= len(row) or row[i] is None:
            return ""
        return str(row[i]).strip()

    txns: list[BankTxn] = []
    for rownum, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        txn_date = cell(row, "date")
        debit = _dec(cell(row, "debit"))
        credit = _dec(cell(row, "credit"))
        amount = _dec(cell(row, "amount"))
        if not txn_date and debit == 0 and credit == 0 and amount == 0:
            continue
        if amount == 0:
            if books_convention:
                # Ledger view of the bank account: debit = money in, credit = money out
                amount = debit - credit
            else:
                # Statement view: credit = money in, debit = money out
                amount = credit - debit
        if amount == 0:
            continue
        txns.append(BankTxn(
            source=source,
            txn_date=txn_date,
            description=cell(row, "description"),
            ref=cell(row, "ref"),
            amount=amount,
            source_ref=f"{path.name}:row{rownum}",
        ))
    return txns


def parse_bank_statement(path: str | Path) -> list[BankTxn]:
    return _parse(Path(path), BankSource.BANK, books_convention=False)


def parse_bank_ledger(path: str | Path) -> list[BankTxn]:
    return _parse(Path(path), BankSource.BOOKS, books_convention=True)
