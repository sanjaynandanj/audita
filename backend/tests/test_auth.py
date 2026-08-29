"""Identity layer: signup, login, sessions, invites, org management.

Requires the compose postgres service (docker compose up -d postgres).
"""

from fastapi.testclient import TestClient

from app.main import app


def _client() -> TestClient:
    # https base_url so Secure cookies survive the httpx cookie jar.
    return TestClient(app, base_url="https://testserver")


def _signup(client: TestClient, email: str, org_name: str = "Acme & Co", **extra) -> dict:
    res = client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "password": "hunter2hunter2",
            "display_name": "Test User",
            "org_name": org_name,
            **extra,
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


class TestSignup:
    def test_signup_creates_org_and_owner(self, db_conn):
        client = _client()
        me = _signup(client, "owner@example.com")
        assert me["user"]["email"] == "owner@example.com"
        assert len(me["memberships"]) == 1
        assert me["memberships"][0]["role"] == "owner"
        assert me["memberships"][0]["org_name"] == "Acme & Co"

    def test_signup_seeds_default_coa(self, db_conn):
        client = _client()
        me = _signup(client, "owner@example.com")
        org_id = me["memberships"][0]["org_id"]
        row = db_conn.execute(
            "SELECT count(*) AS n FROM coa_accounts WHERE org_id = %s", (org_id,)
        ).fetchone()
        assert row["n"] > 40

    def test_duplicate_email_409(self, db_conn):
        client = _client()
        _signup(client, "dupe@example.com")
        res = client.post(
            "/api/auth/signup",
            json={
                "email": "DUPE@example.com",  # citext: case-insensitive
                "password": "hunter2hunter2",
                "display_name": "X",
                "org_name": "Other",
            },
        )
        assert res.status_code == 409

    def test_validation(self, db_conn):
        client = _client()
        bad = [
            {"email": "not-an-email", "password": "hunter2hunter2", "display_name": "X", "org_name": "O"},
            {"email": "a@b.co", "password": "short", "display_name": "X", "org_name": "O"},
            {"email": "a@b.co", "password": "hunter2hunter2", "display_name": "", "org_name": "O"},
            {"email": "a@b.co", "password": "hunter2hunter2", "display_name": "X"},  # no org, no invite
        ]
        for payload in bad:
            assert client.post("/api/auth/signup", json=payload).status_code == 400


class TestLoginSession:
    def test_login_logout_me(self, db_conn):
        client = _client()
        _signup(client, "user@example.com")
        client.cookies.clear()

        assert client.get("/api/auth/me").status_code == 401

        res = client.post(
            "/api/auth/login", json={"email": "user@example.com", "password": "hunter2hunter2"}
        )
        assert res.status_code == 200
        assert "audita_session" in client.cookies

        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["user"]["display_name"] == "Test User"

        client.post("/api/auth/logout")
        assert client.get("/api/auth/me").status_code == 401

    def test_wrong_password_401(self, db_conn):
        client = _client()
        _signup(client, "user@example.com")
        res = client.post("/api/auth/login", json={"email": "user@example.com", "password": "wrong-pass"})
        assert res.status_code == 401

    def test_forged_cookie_401(self, db_conn):
        client = _client()
        client.cookies.set("audita_session", "forged-token-value")
        assert client.get("/api/auth/me").status_code == 401


class TestInvites:
    def test_invite_flow(self, db_conn):
        owner = _client()
        org_id = _signup(owner, "owner@example.com")["memberships"][0]["org_id"]

        res = owner.post(f"/api/orgs/{org_id}/invites", json={"role": "reviewer"})
        assert res.status_code == 200, res.text
        token = res.json()["invite_token"]

        # Public preview.
        anon = _client()
        preview = anon.get(f"/api/invites/{token}")
        assert preview.status_code == 200
        assert preview.json() == {"org_name": "Acme & Co", "role": "reviewer", "email": ""}

        # Signup via invite joins the org instead of creating one.
        ca = _client()
        me = _signup(ca, "ca@example.com", invite_token=token, org_name="")
        assert len(me["memberships"]) == 1
        assert me["memberships"][0]["org_id"] == org_id
        assert me["memberships"][0]["role"] == "reviewer"

        # One-shot: token dead after acceptance.
        assert anon.get(f"/api/invites/{token}").status_code == 404

    def test_owner_cannot_be_invited_role(self, db_conn):
        owner = _client()
        org_id = _signup(owner, "owner@example.com")["memberships"][0]["org_id"]
        res = owner.post(f"/api/orgs/{org_id}/invites", json={"role": "owner"})
        assert res.status_code == 400

    def test_invite_requires_owner(self, db_conn):
        owner = _client()
        org_id = _signup(owner, "owner@example.com")["memberships"][0]["org_id"]
        token = owner.post(f"/api/orgs/{org_id}/invites", json={"role": "preparer"}).json()["invite_token"]

        member = _client()
        _signup(member, "member@example.com", invite_token=token, org_name="")
        res = member.post(f"/api/orgs/{org_id}/invites", json={"role": "viewer"})
        assert res.status_code == 403

    def test_accept_invite_logged_in(self, db_conn):
        owner = _client()
        org_id = _signup(owner, "owner@example.com")["memberships"][0]["org_id"]
        token = owner.post(f"/api/orgs/{org_id}/invites", json={"role": "viewer"}).json()["invite_token"]

        other = _client()
        _signup(other, "other@example.com", org_name="Their Own Org")
        res = other.post(f"/api/invites/{token}/accept")
        assert res.status_code == 200
        roles = {m["org_id"]: m["role"] for m in res.json()["memberships"]}
        assert roles[org_id] == "viewer"
        assert len(roles) == 2


class TestMembers:
    def test_member_management_and_isolation(self, db_conn):
        owner = _client()
        org_id = _signup(owner, "owner@example.com")["memberships"][0]["org_id"]
        token = owner.post(f"/api/orgs/{org_id}/invites", json={"role": "preparer"}).json()["invite_token"]
        member = _client()
        member_id = _signup(member, "member@example.com", invite_token=token, org_name="")["user"]["user_id"]

        members = owner.get(f"/api/orgs/{org_id}/members").json()["members"]
        assert {m["email"] for m in members} == {"owner@example.com", "member@example.com"}

        # Promote to reviewer.
        res = owner.patch(f"/api/orgs/{org_id}/members/{member_id}", json={"role": "reviewer"})
        assert res.status_code == 200

        # A stranger in another org gets 404 (org hidden), not 403.
        stranger = _client()
        _signup(stranger, "stranger@example.com", org_name="Stranger Org")
        assert stranger.get(f"/api/orgs/{org_id}/members").status_code == 404

        # Non-owner member gets 403.
        assert member.get(f"/api/orgs/{org_id}/members").status_code == 403

        # Last owner is protected.
        owner_id = owner.get("/api/auth/me").json()["user"]["user_id"]
        res = owner.patch(f"/api/orgs/{org_id}/members/{owner_id}", json={"role": "viewer"})
        assert res.status_code == 400
        assert owner.delete(f"/api/orgs/{org_id}/members/{owner_id}").status_code == 400

        # Removing the member works.
        assert owner.delete(f"/api/orgs/{org_id}/members/{member_id}").status_code == 200
        assert member.get(f"/api/orgs/{org_id}/members").status_code == 404
