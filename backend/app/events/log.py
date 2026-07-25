"""Append-only agent event log.

Schema per the design doc's Technical Defaults:
  event_id, agent, action, input_doc_ref, output_ref, actor, reviewed_by, ts
Inserts only — SQLite triggers physically reject UPDATE and DELETE so the
trail stays defensible. Postgres swap in a later phase keeps the same shape.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_events (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    agent         TEXT NOT NULL,
    action        TEXT NOT NULL,
    input_doc_ref TEXT NOT NULL DEFAULT '',
    output_ref    TEXT NOT NULL DEFAULT '',
    actor         TEXT NOT NULL DEFAULT '',
    reviewed_by   TEXT NOT NULL DEFAULT '',
    ts            TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS agent_events_no_update
BEFORE UPDATE ON agent_events
BEGIN
    SELECT RAISE(ABORT, 'agent_events is append-only');
END;
CREATE TRIGGER IF NOT EXISTS agent_events_no_delete
BEFORE DELETE ON agent_events
BEGIN
    SELECT RAISE(ABORT, 'agent_events is append-only');
END;
"""


class EventLog:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def append(
        self,
        agent: str,
        action: str,
        input_doc_ref: str = "",
        output_ref: str = "",
        actor: str = "",
        reviewed_by: str = "",
    ) -> int:
        ts = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO agent_events (agent, action, input_doc_ref, output_ref, actor, reviewed_by, ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (agent, action, input_doc_ref, output_ref, actor, reviewed_by, ts),
            )
            return int(cur.lastrowid)

    def recent(self, limit: int = 25) -> list[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM agent_events ORDER BY event_id DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
            return [dict(r) for r in rows]

    def for_output(self, output_ref: str) -> list[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM agent_events WHERE output_ref = ? ORDER BY event_id",
                (output_ref,),
            ).fetchall()
            return [dict(r) for r in rows]
