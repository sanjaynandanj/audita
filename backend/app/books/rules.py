"""Deterministic categorization rules.

A rule maps a case-insensitive substring of a transaction's description or
ref to an account code. Rules apply in priority order (lower number wins,
ties broken by creation time); the first hit categorizes the transaction
with source=rule. No fuzz, no guessing — a rule either matches or it
doesn't, so a rule hit is user-authored intent, not an LLM opinion.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from psycopg import Connection

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


_RULE_COLS = "rule_id, priority, field, contains, account_code, created_by, created_at"


class RuleStore:
    def __init__(self, conn: Connection, org_id: str):
        self.conn = conn
        self.org_id = org_id

    def list(self) -> list[Rule]:
        rows = self.conn.execute(
            f"SELECT {_RULE_COLS} FROM categorization_rules WHERE org_id = %s "
            "ORDER BY priority, created_at",
            (self.org_id,),
        ).fetchall()
        return [Rule(**r) for r in rows]

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
        dupe = self.conn.execute(
            "SELECT 1 FROM categorization_rules "
            "WHERE org_id = %s AND field = %s AND lower(contains) = lower(%s)",
            (self.org_id, field, contains),
        ).fetchone()
        if dupe:
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
        self.conn.execute(
            "INSERT INTO categorization_rules "
            "(org_id, rule_id, priority, field, contains, account_code, created_by, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (self.org_id, rule.rule_id, rule.priority, rule.field, rule.contains,
             rule.account_code, rule.created_by, rule.created_at),
        )
        return rule

    def remove(self, rule_id: str) -> Rule:
        row = self.conn.execute(
            f"DELETE FROM categorization_rules WHERE org_id = %s AND rule_id = %s RETURNING {_RULE_COLS}",
            (self.org_id, rule_id),
        ).fetchone()
        if row is None:
            raise KeyError(f"no rule {rule_id!r}")
        return Rule(**row)


def apply_rules(rules: list[Rule], description: str, ref: str) -> Rule | None:
    """Return the first matching rule in priority order, or None."""
    haystacks = {"description": description.lower(), "ref": ref.lower()}
    for rule in rules:
        if rule.contains.lower() in haystacks[rule.field]:
            return rule
    return None
