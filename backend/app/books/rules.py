"""Deterministic categorization rules.

A rule maps a case-insensitive substring of a transaction's description or
ref to an account code. Rules apply in priority order (lower number wins,
ties broken by creation time); the first hit categorizes the transaction
with source=rule. No fuzz, no guessing — a rule either matches or it
doesn't, so a rule hit is user-authored intent, not an LLM opinion.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

RULE_FIELDS = ("description", "ref")


@dataclass
class Rule:
    rule_id: str
    priority: int
    field: str          # description | ref
    contains: str       # case-insensitive substring
    account_code: str
    created_by: str
    created_at: str


class RuleStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    def _write(self, rules: list[Rule]) -> None:
        self.path.write_text(
            json.dumps([asdict(r) for r in rules], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def list(self) -> list[Rule]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        rules = [Rule(**r) for r in data]
        rules.sort(key=lambda r: (r.priority, r.created_at))
        return rules

    def add(
        self, field: str, contains: str, account_code: str,
        created_by: str, priority: int = 100,
    ) -> Rule:
        field, contains = field.strip(), contains.strip()
        if field not in RULE_FIELDS:
            raise ValueError(f"rule field must be one of {', '.join(RULE_FIELDS)}")
        if len(contains) < 3:
            raise ValueError("rule pattern must be at least 3 characters")
        if not account_code:
            raise ValueError("account_code is required")
        rules = self.list()
        if any(
            r.field == field and r.contains.lower() == contains.lower() for r in rules
        ):
            raise ValueError(f"a rule on {field} containing {contains!r} already exists")
        rule = Rule(
            rule_id=secrets.token_hex(4),
            priority=int(priority),
            field=field,
            contains=contains,
            account_code=account_code,
            created_by=created_by,
            created_at=datetime.now(UTC).isoformat(),
        )
        self._write([*rules, rule])
        return rule

    def remove(self, rule_id: str) -> Rule:
        rules = self.list()
        for rule in rules:
            if rule.rule_id == rule_id:
                self._write([r for r in rules if r.rule_id != rule_id])
                return rule
        raise KeyError(f"no rule {rule_id!r}")


def apply_rules(rules: list[Rule], description: str, ref: str) -> Rule | None:
    """Return the first matching rule in priority order, or None."""
    haystacks = {"description": description.lower(), "ref": ref.lower()}
    for rule in rules:
        if rule.contains.lower() in haystacks[rule.field]:
            return rule
    return None
