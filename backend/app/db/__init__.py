"""Postgres connection pool + FastAPI dependency.

The pool opens lazily on first use so tests and scripts can set
AUDITA_DATABASE_URL before anything touches the database.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

# Default matches the docker-compose postgres service (host port 5434).
DEFAULT_URL = "postgresql://audita:audita@localhost:5434/audita"

_pool: ConnectionPool | None = None


def database_url() -> str:
    return os.environ.get("AUDITA_DATABASE_URL", DEFAULT_URL)


def open_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            database_url(),
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_conn() -> Iterator[Connection]:
    """One pooled connection per request; commits on success, rolls back on error."""
    with open_pool().connection() as conn:
        yield conn
