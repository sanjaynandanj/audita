"""FastAPI auth dependencies: session resolution + org-scoped RBAC."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from psycopg import Connection

from ..db import get_conn
from .service import User, membership_role, resolve_session

COOKIE_NAME = "audita_session"

ROLE_RANK = {"viewer": 0, "preparer": 1, "reviewer": 2, "owner": 3}


@dataclass
class AuthContext:
    user: User
    org_id: str
    role: str


def session_token(request: Request) -> str:
    return request.cookies.get(COOKIE_NAME, "")


def optional_user(request: Request, conn: Connection = Depends(get_conn)) -> User | None:
    return resolve_session(conn, session_token(request))


def current_user(request: Request, conn: Connection = Depends(get_conn)) -> User:
    user = resolve_session(conn, session_token(request))
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return user


def _role_in_org(conn: Connection, user: User, org_id: str) -> str:
    try:
        uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found.") from None
    role = membership_role(conn, user.user_id, org_id)
    if role is None:
        # 404, not 403: don't reveal which orgs exist.
        raise HTTPException(status_code=404, detail="Not found.")
    return role


def require_role_for_org(conn: Connection, user: User, org_id: str, min_role: str) -> AuthContext:
    role = _role_in_org(conn, user, org_id)
    if ROLE_RANK[role] < ROLE_RANK[min_role]:
        raise HTTPException(status_code=403, detail=f"Requires the {min_role} role.")
    return AuthContext(user=user, org_id=org_id, role=role)


def require_role(min_role: str):
    """Dependency factory: resolves session -> membership in the {org_id} path param."""

    def dep(
        org_id: str,
        user: User = Depends(current_user),
        conn: Connection = Depends(get_conn),
    ) -> AuthContext:
        return require_role_for_org(conn, user, org_id, min_role)

    return dep
