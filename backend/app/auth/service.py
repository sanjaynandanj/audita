"""Identity: users, orgs, memberships, sessions, invites.

Tokens (session + invite) are opaque secrets.token_urlsafe values; only
their sha256 hex digest is stored, so a DB leak exposes no usable tokens.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from psycopg import Connection, errors

from ..books.coa import DEFAULT_ACCOUNTS
from .passwords import hash_password, verify_password

SESSION_TTL_DAYS = 30
INVITE_TTL_DAYS = 7

ROLES = ("owner", "preparer", "reviewer", "viewer")
INVITE_ROLES = ("preparer", "reviewer", "viewer")


class EmailTaken(Exception):
    pass


class InviteInvalid(Exception):
    pass


@dataclass
class User:
    user_id: str
    email: str
    display_name: str
    ca_membership_no: str


@dataclass
class Membership:
    org_id: str
    org_name: str
    role: str


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def _user_row(row: dict) -> User:
    return User(
        user_id=str(row["user_id"]),
        email=str(row["email"]),
        display_name=row["display_name"],
        ca_membership_no=row["ca_membership_no"],
    )


# -- users / orgs -----------------------------------------------------------


def create_user(
    conn: Connection, email: str, password: str, display_name: str, ca_membership_no: str = ""
) -> User:
    try:
        row = conn.execute(
            """
            INSERT INTO users (email, password_hash, display_name, ca_membership_no)
            VALUES (%s, %s, %s, %s)
            RETURNING user_id, email, display_name, ca_membership_no
            """,
            (email.strip(), hash_password(password), display_name.strip(), ca_membership_no.strip()),
        ).fetchone()
    except errors.UniqueViolation:
        raise EmailTaken(email) from None
    return _user_row(row)


def create_org(conn: Connection, name: str) -> str:
    row = conn.execute(
        "INSERT INTO orgs (name) VALUES (%s) RETURNING org_id", (name.strip(),)
    ).fetchone()
    org_id = str(row["org_id"])
    conn.cursor().executemany(
        "INSERT INTO coa_accounts (org_id, code, name, type) VALUES (%s, %s, %s, %s)",
        [(org_id, c, n, t) for c, n, t in DEFAULT_ACCOUNTS],
    )
    return org_id


def add_membership(conn: Connection, user_id: str, org_id: str, role: str) -> None:
    conn.execute(
        """
        INSERT INTO memberships (user_id, org_id, role) VALUES (%s, %s, %s)
        ON CONFLICT (user_id, org_id) DO NOTHING
        """,
        (user_id, org_id, role),
    )


def memberships_for(conn: Connection, user_id: str) -> list[Membership]:
    rows = conn.execute(
        """
        SELECT m.org_id, o.name AS org_name, m.role
        FROM memberships m JOIN orgs o USING (org_id)
        WHERE m.user_id = %s
        ORDER BY m.created_at
        """,
        (user_id,),
    ).fetchall()
    return [Membership(org_id=str(r["org_id"]), org_name=r["org_name"], role=r["role"]) for r in rows]


def membership_role(conn: Connection, user_id: str, org_id: str) -> str | None:
    row = conn.execute(
        "SELECT role FROM memberships WHERE user_id = %s AND org_id = %s",
        (user_id, org_id),
    ).fetchone()
    return row["role"] if row else None


def authenticate(conn: Connection, email: str, password: str) -> User | None:
    row = conn.execute(
        """
        SELECT user_id, email, password_hash, display_name, ca_membership_no
        FROM users WHERE email = %s
        """,
        (email.strip(),),
    ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return None
    return _user_row(row)


# -- sessions ---------------------------------------------------------------


def create_session(conn: Connection, user_id: str) -> str:
    raw = secrets.token_urlsafe(32)
    conn.execute(
        """
        INSERT INTO sessions (token_hash, user_id, expires_at)
        VALUES (%s, %s, now() + make_interval(days => %s))
        """,
        (_hash_token(raw), user_id, SESSION_TTL_DAYS),
    )
    return raw


def resolve_session(conn: Connection, raw: str) -> User | None:
    if not raw:
        return None
    row = conn.execute(
        """
        SELECT s.session_id, s.expires_at, u.user_id, u.email, u.display_name, u.ca_membership_no
        FROM sessions s JOIN users u USING (user_id)
        WHERE s.token_hash = %s AND s.expires_at > now()
        """,
        (_hash_token(raw),),
    ).fetchone()
    if row is None:
        return None
    # Sliding renewal past the half-life.
    conn.execute(
        """
        UPDATE sessions
        SET last_seen_at = now(),
            expires_at = CASE
                WHEN expires_at < now() + make_interval(days => %s) / 2
                THEN now() + make_interval(days => %s)
                ELSE expires_at
            END
        WHERE session_id = %s
        """,
        (SESSION_TTL_DAYS, SESSION_TTL_DAYS, row["session_id"]),
    )
    return _user_row(row)


def delete_session(conn: Connection, raw: str) -> None:
    if raw:
        conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_hash_token(raw),))


# -- invites ----------------------------------------------------------------


def create_invite(
    conn: Connection, org_id: str, role: str, email: str, created_by: str
) -> str:
    if role not in INVITE_ROLES:
        raise ValueError(f"role must be one of {', '.join(INVITE_ROLES)}")
    raw = secrets.token_urlsafe(32)
    conn.execute(
        """
        INSERT INTO invites (org_id, token_hash, role, email, created_by, expires_at)
        VALUES (%s, %s, %s, %s, %s, now() + make_interval(days => %s))
        """,
        (org_id, _hash_token(raw), role, email.strip(), created_by, INVITE_TTL_DAYS),
    )
    return raw


def get_invite(conn: Connection, raw: str) -> dict | None:
    """Valid (unaccepted, unexpired) invite, or None."""
    row = conn.execute(
        """
        SELECT i.invite_id, i.org_id, o.name AS org_name, i.role, i.email
        FROM invites i JOIN orgs o USING (org_id)
        WHERE i.token_hash = %s AND i.accepted_by IS NULL AND i.expires_at > now()
        """,
        (_hash_token(raw),),
    ).fetchone()
    if row is None:
        return None
    return {
        "invite_id": str(row["invite_id"]),
        "org_id": str(row["org_id"]),
        "org_name": row["org_name"],
        "role": row["role"],
        "email": row["email"],
    }


def accept_invite(conn: Connection, raw: str, user_id: str) -> Membership:
    invite = get_invite(conn, raw)
    if invite is None:
        raise InviteInvalid("Invite link is invalid, expired, or already used.")
    conn.execute(
        "UPDATE invites SET accepted_by = %s, accepted_at = now() WHERE invite_id = %s",
        (user_id, invite["invite_id"]),
    )
    add_membership(conn, user_id, invite["org_id"], invite["role"])
    return Membership(org_id=invite["org_id"], org_name=invite["org_name"], role=invite["role"])
