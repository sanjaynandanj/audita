"""Auth endpoints: signup, login, logout, me."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from psycopg import Connection

from .. import config
from ..db import get_conn
from .deps import COOKIE_NAME, current_user, session_token
from .service import (
    SESSION_TTL_DAYS,
    EmailTaken,
    InviteInvalid,
    User,
    accept_invite,
    add_membership,
    authenticate,
    create_org,
    create_session,
    create_user,
    delete_session,
    memberships_for,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        raw_token,
        max_age=SESSION_TTL_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,
        path="/",
    )


def _me(conn: Connection, user: User) -> dict:
    return {"user": asdict(user), "memberships": [asdict(m) for m in memberships_for(conn, user.user_id)]}


@router.post("/signup")
async def signup(response: Response, payload: dict = Body(...), conn: Connection = Depends(get_conn)):
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    display_name = str(payload.get("display_name", "")).strip()
    org_name = str(payload.get("org_name", "")).strip()
    invite_token = str(payload.get("invite_token", "")).strip()
    ca_membership_no = str(payload.get("ca_membership_no", "")).strip()

    if "@" not in email or "." not in email.rpartition("@")[2]:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    if not display_name:
        raise HTTPException(status_code=400, detail="Your name is required.")
    if not invite_token and not org_name:
        raise HTTPException(status_code=400, detail="Workspace name is required.")

    try:
        user = create_user(conn, email, password, display_name, ca_membership_no)
    except EmailTaken:
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from None

    if invite_token:
        try:
            accept_invite(conn, invite_token, user.user_id)
        except InviteInvalid as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
    else:
        org_id = create_org(conn, org_name)
        add_membership(conn, user.user_id, org_id, "owner")

    _set_session_cookie(response, create_session(conn, user.user_id))
    return _me(conn, user)


@router.post("/login")
async def login(response: Response, payload: dict = Body(...), conn: Connection = Depends(get_conn)):
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    user = authenticate(conn, email, password)
    if user is None:
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    _set_session_cookie(response, create_session(conn, user.user_id))
    return _me(conn, user)


@router.post("/logout")
async def logout(request: Request, response: Response, conn: Connection = Depends(get_conn)):
    delete_session(conn, session_token(request))
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: User = Depends(current_user), conn: Connection = Depends(get_conn)):
    return _me(conn, user)
