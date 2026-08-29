"""Append-only agent event log, org-scoped.

Schema per the design doc's Technical Defaults:
  event_id, org_id, agent, action, input_doc_ref, output_ref, actor, reviewed_by, ts
Inserts only — Postgres triggers (db/migrations/0003_events.sql) reject
UPDATE and DELETE so the trail stays defensible.
"""

from __future__ import annotations

from psycopg import Connection

_COLS = "event_id, agent, action, input_doc_ref, output_ref, actor, reviewed_by, ts"


def _row_dict(row: dict) -> dict:
    return {
        "event_id": row["event_id"],
        "agent": row["agent"],
        "action": row["action"],
        "input_doc_ref": row["input_doc_ref"],
        "output_ref": row["output_ref"],
        "actor": row["actor"],
        "reviewed_by": row["reviewed_by"],
        "ts": row["ts"].isoformat(),
    }


class EventLog:
    def __init__(self, conn: Connection, org_id: str):
        self.conn = conn
        self.org_id = org_id

    def append(
        self,
        agent: str,
        action: str,
        input_doc_ref: str = "",
        output_ref: str = "",
        actor: str = "",
        reviewed_by: str = "",
    ) -> int:
        row = self.conn.execute(
            """
            INSERT INTO agent_events (org_id, agent, action, input_doc_ref, output_ref, actor, reviewed_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING event_id
            """,
            (self.org_id, agent, action, input_doc_ref, output_ref, actor, reviewed_by),
        ).fetchone()
        return int(row["event_id"])

    def recent(self, limit: int = 25) -> list[dict]:
        rows = self.conn.execute(
            f"SELECT {_COLS} FROM agent_events WHERE org_id = %s ORDER BY event_id DESC LIMIT %s",
            (self.org_id, max(1, min(int(limit), 200))),
        ).fetchall()
        return [_row_dict(r) for r in rows]

    def for_output(self, output_ref: str) -> list[dict]:
        rows = self.conn.execute(
            f"SELECT {_COLS} FROM agent_events WHERE org_id = %s AND output_ref = %s ORDER BY event_id",
            (self.org_id, output_ref),
        ).fetchall()
        return [_row_dict(r) for r in rows]
