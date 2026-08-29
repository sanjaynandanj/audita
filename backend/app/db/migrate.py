"""Minimal forward-only migration runner.

SQL files in app/db/migrations/ named NNNN_label.sql are applied in
lexicographic order exactly once, tracked in schema_migrations.
"""

from __future__ import annotations

from pathlib import Path

from psycopg import Connection
from psycopg.rows import tuple_row

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def migrate(conn: Connection) -> list[str]:
    """Apply pending migrations. Returns the names applied this run."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name text PRIMARY KEY,
            applied_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT name FROM schema_migrations")
        done = {row[0] for row in cur.fetchall()}

    applied: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in done:
            continue
        conn.execute(path.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
        applied.append(path.name)
    conn.commit()
    return applied
