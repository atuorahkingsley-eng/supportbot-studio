"""Tests for Bug 4 — JWT edge cases at /api/auth/me.

The endpoint at backend/routers/auth_api.py:_decode_or_401 turns each jose
exception into a typed 401 with a body the frontend can branch on. Before
the fix the silent ``decode_token() -> None`` path produced an opaque 401
that the SPA couldn't tell apart from "no cookie at all".

Login / role-mismatch tests live here too — same auth surface, same file
the test spec asked for.
"""

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from backend.config import settings
from backend.database import SuperAdmin
from backend.services.auth import create_token, hash_password


# ── 1. Happy-path login ───────────────────────────────────────────────────────

def test_valid_token_returns_200(test_client, test_tenant):
    """POST /api/auth/login with the fixture tenant's real credentials
    returns 200 plus an identity payload. The token itself rides back in
    an HttpOnly cookie (intentionally NOT in the body — see super_login's
    docstring) so we assert on the body shape, not on the cookie value."""
    resp = test_client.post(
        "/api/auth/login",
        json={"email": test_tenant.owner_email, "password": test_tenant.raw_password},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["bot_id"] == test_tenant.bot_id
    assert body["role"] == "client"
    # Cookie must be set HttpOnly so XSS can't read it. TestClient surfaces
    # cookies via .cookies; presence is enough to prove the set-cookie ran.
    assert "sb_client_token" in resp.cookies


# ── 2. Expired token ──────────────────────────────────────────────────────────

def test_expired_token_returns_401(test_client, test_tenant):
    """An exp claim 1h in the past trips ``ExpiredSignatureError`` inside
    ``_decode_or_401``, which converts it to a typed 401. The detail string
    matters — the SPA branches on it to render "log in again" vs
    "your session has ended"."""
    expired_token = jwt.encode(
        {
            "role": "client",
            "bot_id": test_tenant.bot_id,
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "jti": "expired-jti-12345",
        },
        settings.jwt_secret_key,
        algorithm="HS256",
    )
    resp = test_client.get(
        "/api/auth/me",
        cookies={"sb_client_token": expired_token},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert "detail" in body
    # Confirm the typed message — not just the generic "Not authenticated".
    assert "expired" in body["detail"].lower()


# ── 3. Malformed token ────────────────────────────────────────────────────────

def test_malformed_token_returns_401(test_client):
    """A garbage string doesn't even tokenise as JWT — jose raises
    JWTError, ``_decode_or_401`` converts it to 401 "Invalid token".
    Crucial that this is NOT a 500: a malformed cookie is a USER bug, not
    a server bug, and a 500 here would page the on-call."""
    resp = test_client.get(
        "/api/auth/me",
        cookies={"sb_client_token": "not.a.real.token"},
    )
    assert resp.status_code == 401
    assert "detail" in resp.json()


# ── 4. Missing token entirely ─────────────────────────────────────────────────

def test_missing_token_returns_401(test_client):
    """No cookie, no Authorization header → /me hits its final
    ``raise HTTPException(401, "Not authenticated")``. The earlier
    ``_decode_or_401`` paths must never run when there's nothing to
    decode — assertion here covers that branch."""
    resp = test_client.get("/api/auth/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"


# ── 5. Wrong role hitting a super-admin endpoint ──────────────────────────────

def test_wrong_role_returns_401(test_client, test_db, test_tenant):
    """A valid signature on a token whose ``role`` claim isn't
    ``super_admin`` must NOT pass the super-admin guard. Production
    returns 401 ("Not authorized") for this case rather than 403 — 403
    is reserved for an authenticated user whose account is inactive
    (see ``get_current_client``).

    Picked ``/api/admin/system`` as the target endpoint: it's the
    simplest super-admin-only route and doesn't require additional
    request body.
    """
    # The test_tenant fixture's JWT carries role="client". Hitting a
    # super-admin route with it should be rejected at the role check
    # inside get_super_admin BEFORE the DB lookup.
    resp = test_client.get(
        "/api/admin/system",
        headers={"Authorization": f"Bearer {test_tenant.token}"},
    )
    assert resp.status_code == 401
    assert "detail" in resp.json()


# ── Extra: a super-admin token CAN reach the same endpoint ────────────────────
# Not in the spec, but a positive control nails down that 401 above is a
# role-mismatch failure, not a "endpoint always rejects" failure.

def test_super_admin_token_reaches_super_endpoint(test_client, test_db):
    """Sanity check: with a valid super-admin token, the same endpoint
    returns 200. Without this, test_wrong_role_returns_401 could pass for
    the wrong reason (e.g. the endpoint always 401s)."""
    # Seed a SuperAdmin row so the DB lookup inside get_super_admin matches.
    admin = SuperAdmin(username="test_admin", password_hash=hash_password("anything"))
    test_db.add(admin)
    test_db.commit()

    super_token = create_token({"role": "super_admin", "username": "test_admin"})
    resp = test_client.get(
        "/api/admin/system",
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # /system reports DB stats; on the test in-memory engine we expect
    # the dialect-aware path to return 0 MB without crashing (Bug 9 fix).
    assert "db_size_mb" in body
