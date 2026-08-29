"""Shared test fixtures.

Postgres-backed tests use the docker-compose postgres service (host port
5433). A dedicated audita_test database is created once per session and
migrated; tables are truncated around each test that touches the DB.
Pure tests (matcher, parsers, bank engine) never request these fixtures
and run without Postgres.
"""

from __future__ import annotations

import os
import tempfile

TEST_DATABASE_URL = os.environ.setdefault(
    "AUDITA_DATABASE_URL", "postgresql://audita:audita@localhost:5434/audita_test"
)
# Isolate file leftovers (upload tempdir, dev secret_key) before app.config loads.
os.environ.setdefault("AUDITA_DATA_DIR", tempfile.mkdtemp(prefix="audita-test-"))
os.environ.pop("GEMINI_API_KEY", None)

import psycopg  # noqa: E402
import pytest  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from app.db import close_pool  # noqa: E402
from app.db.migrate import migrate  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _close_pool():
    yield
    close_pool()


def _admin_url() -> str:
    # Same server, maintenance DB, for CREATE DATABASE.
    base, _, _dbname = TEST_DATABASE_URL.rpartition("/")
    return f"{base}/postgres"


@pytest.fixture(scope="session")
def test_db() -> str:
    """Create + migrate the test database once per session. Returns its URL."""
    dbname = TEST_DATABASE_URL.rpartition("/")[2]
    with psycopg.connect(_admin_url(), autocommit=True) as admin:
        exists = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
        ).fetchone()
        if not exists:
            admin.execute(f'CREATE DATABASE "{dbname}"')
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        migrate(conn)
    return TEST_DATABASE_URL


@pytest.fixture
def db_conn(test_db: str):
    """A clean connection: truncates all app tables before the test."""
    with psycopg.connect(test_db, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            # replica role bypasses the agent_events append-only triggers
            # for test cleanup only.
            cur.execute("SET session_replication_role = replica")
            cur.execute(
                """
                SELECT string_agg(quote_ident(tablename), ', ')
                FROM pg_tables
                WHERE schemaname = 'public' AND tablename <> 'schema_migrations'
                """
            )
            tables = cur.fetchone()["string_agg"]
            if tables:
                cur.execute(f"TRUNCATE {tables} RESTART IDENTITY CASCADE")
            cur.execute("SET session_replication_role = DEFAULT")
        conn.commit()
        yield conn


@pytest.fixture
def org(db_conn) -> str:
    """A fresh org, committed so the app's pool connections can see it."""
    row = db_conn.execute("INSERT INTO orgs (name) VALUES ('Test Org') RETURNING org_id").fetchone()
    db_conn.commit()
    return str(row["org_id"])


def make_client(db_conn, email: str, role: str = "", org_id: str = ""):
    """A TestClient signed in as a fresh user.

    No role/org: owner of a brand-new org. With role+org_id: joins that org
    at the given role via an invite created directly in the DB.
    """
    import hashlib
    import secrets

    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app, base_url="https://testserver")
    payload = {
        "email": email,
        "password": "test-password-1",
        "display_name": email.split("@")[0].title(),
        "ca_membership_no": "ICAI-000111" if role == "reviewer" else "",
    }
    if role and org_id:
        raw = secrets.token_urlsafe(32)
        db_conn.execute(
            """
            INSERT INTO invites (org_id, token_hash, role, created_by, expires_at)
            VALUES (%s, %s, %s, (SELECT user_id FROM users LIMIT 1), now() + interval '1 day')
            """,
            (org_id, hashlib.sha256(raw.encode()).hexdigest(), role),
        )
        db_conn.commit()
        payload["invite_token"] = raw
    else:
        payload["org_name"] = "Test Workspace"
    res = client.post("/api/auth/signup", json=payload)
    assert res.status_code == 200, res.text
    return client, res.json()["memberships"][0]["org_id"]


@pytest.fixture
def owner_client(db_conn):
    """(client, org_id): an owner session in a fresh org."""
    return make_client(db_conn, "owner@test.local")
