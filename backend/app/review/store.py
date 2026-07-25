"""Review workbook store.

One JSON per period under data/review/. Rebuilding a workbook recomputes
every figure but preserves verification state for flags whose flag_id
still exists (flag_ids are content-derived, so an unchanged finding keeps
its sign-off; a changed finding returns to pending)."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from ..books.store import PERIOD_RE
from .compute import PnlLine, ReviewFlag, ReviewWorkbook


class AlreadyVerified(RuntimeError):
    pass


class ReviewStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, period: str) -> Path:
        if not PERIOD_RE.match(period):
            raise ValueError("period must be YYYY-MM")
        return self.root / f"{period}.json"

    def _save(self, wb: ReviewWorkbook) -> None:
        data = asdict(wb)
        data["verified_count"] = wb.verified_count
        data["pending_count"] = wb.pending_count
        self._path(wb.period).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def exists(self, period: str) -> bool:
        return self._path(period).exists()

    def load(self, period: str) -> ReviewWorkbook:
        data = json.loads(self._path(period).read_text(encoding="utf-8"))
        data.pop("verified_count", None)
        data.pop("pending_count", None)
        data["pnl"] = [PnlLine(**line) for line in data["pnl"]]
        data["flags"] = [ReviewFlag(**flag) for flag in data["flags"]]
        return ReviewWorkbook(**data)

    def save_new(self, wb: ReviewWorkbook) -> ReviewWorkbook:
        """Persist a freshly computed workbook, carrying over verification
        for flags whose flag_id matches the previous build."""
        if self.exists(wb.period):
            previous = {f.flag_id: f for f in self.load(wb.period).flags}
            for flag in wb.flags:
                old = previous.get(flag.flag_id)
                if old is not None and old.status == "verified":
                    flag.status = old.status
                    flag.verified_by = old.verified_by
                    flag.verified_at = old.verified_at
                    flag.ca_signoff = old.ca_signoff
        wb.created_at = datetime.now(UTC).isoformat()
        self._save(wb)
        return wb

    def verify_flag(
        self, period: str, flag_id: str, actor: str, ca_signoff: str = ""
    ) -> ReviewFlag:
        wb = self.load(period)
        for flag in wb.flags:
            if flag.flag_id != flag_id:
                continue
            if flag.status == "verified":
                raise AlreadyVerified(f"flag {flag_id} is already verified")
            flag.status = "verified"
            flag.verified_by = actor
            flag.verified_at = datetime.now(UTC).isoformat()
            flag.ca_signoff = ca_signoff
            self._save(wb)
            return flag
        raise KeyError(f"no flag {flag_id!r} in {period}")

    def set_narrative(self, period: str, narrative: str, note: str = "") -> ReviewWorkbook:
        wb = self.load(period)
        wb.narrative = narrative
        wb.narrative_note = note
        self._save(wb)
        return wb

    def periods(self) -> list[str]:
        return sorted(
            (p.stem for p in self.root.glob("*.json") if PERIOD_RE.match(p.stem)),
            reverse=True,
        )
