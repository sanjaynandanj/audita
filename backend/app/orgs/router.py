"""Org management: invites and members. Owner-only except invite preview/accept."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Body, Depends, HTTPException
from psycopg import Connection

from ..auth.deps import AuthContext, current_user, require_role
from ..auth.service import (
    INVITE_TTL_DAYS,
    ROLES,
    InviteInvalid,
    User,
    accept_invite,
    create_invite,
    get_invite,
    memberships_for,
)
from ..db import get_conn

router = APIRouter(prefix="/api", tags=["orgs"])


def _owner_count(conn: Connection, org_id: str) -> int:
    row = conn.execute(
        "SELECT count(*) AS n FROM memberships WHERE org_id = %s AND role = 'owner'", (org_id,)
    ).fetchone()
    return row["n"]


@router.post("/orgs/{org_id}/invites")
async def api_create_invite(
    payload: dict = Body(...),
    ctx: AuthContext = Depends(require_role("owner")),
    conn: Connection = Depends(get_conn),
):
    role = str(payload.get("role", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    try:
        raw = create_invite(conn, ctx.org_id, role, email, ctx.user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "invite_token": raw,
        "invite_path": f"/signup?invite={raw}",
        "role": role,
        "expires_days": INVITE_TTL_DAYS,
    }


@router.get("/orgs/{org_id}/invites")
async def api_list_invites(
    ctx: AuthContext = Depends(require_role("owner")),
    conn: Connection = Depends(get_conn),
):
    rows = conn.execute(
        """
        SELECT invite_id, role, email, created_at, expires_at
        FROM invites
        WHERE org_id = %s AND accepted_by IS NULL AND expires_at > now()
        ORDER BY created_at DESC
        """,
        (ctx.org_id,),
    ).fetchall()
    return {
        "invites": [
            {
                "invite_id": str(r["invite_id"]),
                "role": r["role"],
                "email": r["email"],
                "created_at": r["created_at"].isoformat(),
                "expires_at": r["expires_at"].isoformat(),
            }
            for r in rows
        ]
    }


@router.get("/invites/{token}")
async def api_preview_invite(token: str, conn: Connection = Depends(get_conn)):
    invite = get_invite(conn, token)
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite link is invalid, expired, or already used.")
    return {"org_name": invite["org_name"], "role": invite["role"], "email": invite["email"]}


@router.post("/invites/{token}/accept")
async def api_accept_invite(
    token: str,
    user: User = Depends(current_user),
    conn: Connection = Depends(get_conn),
):
    try:
        accept_invite(conn, token, user.user_id)
    except InviteInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"memberships": [asdict(m) for m in memberships_for(conn, user.user_id)]}


@router.get("/orgs/{org_id}/members")
async def api_list_members(
    ctx: AuthContext = Depends(require_role("owner")),
    conn: Connection = Depends(get_conn),
):
    rows = conn.execute(
        """
        SELECT u.user_id, u.email, u.display_name, u.ca_membership_no, m.role, m.created_at
        FROM memberships m JOIN users u USING (user_id)
        WHERE m.org_id = %s
        ORDER BY m.created_at
        """,
        (ctx.org_id,),
    ).fetchall()
    return {
        "members": [
            {
                "user_id": str(r["user_id"]),
                "email": str(r["email"]),
                "display_name": r["display_name"],
                "ca_membership_no": r["ca_membership_no"],
                "role": r["role"],
                "joined_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    }


@router.patch("/orgs/{org_id}/members/{user_id}")
async def api_set_member_role(
    user_id: str,
    payload: dict = Body(...),
    ctx: AuthContext = Depends(require_role("owner")),
    conn: Connection = Depends(get_conn),
):
    role = str(payload.get("role", "")).strip()
    if role not in ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {', '.join(ROLES)}")
    current = conn.execute(
        "SELECT role FROM memberships WHERE org_id = %s AND user_id = %s",
        (ctx.org_id, user_id),
    ).fetchone()
    if current is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    if current["role"] == "owner" and role != "owner" and _owner_count(conn, ctx.org_id) == 1:
        raise HTTPException(status_code=400, detail="An org must keep at least one owner.")
    conn.execute(
        "UPDATE memberships SET role = %s WHERE org_id = %s AND user_id = %s",
        (role, ctx.org_id, user_id),
    )
    return {"ok": True}


@router.delete("/orgs/{org_id}/members/{user_id}")
async def api_remove_member(
    user_id: str,
    ctx: AuthContext = Depends(require_role("owner")),
    conn: Connection = Depends(get_conn),
):
    current = conn.execute(
        "SELECT role FROM memberships WHERE org_id = %s AND user_id = %s",
        (ctx.org_id, user_id),
    ).fetchone()
    if current is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    if current["role"] == "owner" and _owner_count(conn, ctx.org_id) == 1:
        raise HTTPException(status_code=400, detail="An org must keep at least one owner.")
    conn.execute(
        "DELETE FROM memberships WHERE org_id = %s AND user_id = %s",
        (ctx.org_id, user_id),
    )
    return {"ok": True}
