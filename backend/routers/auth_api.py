"""
Auth endpoints: login, logout, me.
Two auth systems: super admin (/api/auth/super/login) and client (/api/auth/login).
"""
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

import structlog
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

from backend.database import get_db, Tenant, SuperAdmin
from backend.services.auth import (
    hash_password, verify_password, create_token, decode_token,
    get_current_client, get_super_admin, validate_password_strength,
)
from backend.services.rate_limit import limiter
from backend.config import settings

log = structlog.get_logger(__name__)

# Dummy bcrypt hash used in login endpoints to prevent timing-based email
# enumeration (CWE-208). We always call verify_password even when the user
# doesn't exist — the timing difference between "user not found (sub-ms)"
# and "wrong password (~100ms bcrypt)" would otherwise reveal whether an
# email/username is registered.
_DUMMY_HASH = hash_password("dummy-password-never-matches")

# Same algorithm constant the auth service uses for encode/decode. Kept
# local rather than importing the private constant from services/auth so a
# rename there doesn't silently break this file.
_JWT_ALGORITHM = "HS256"


def _decode_or_401(token: str) -> dict:
    """Decode a JWT, raising a typed 401 on every failure mode.

    Replaces the silent ``decode_token() -> None`` call at the /me endpoint,
    where an expired or malformed cookie previously bubbled out as a generic
    "Not authenticated" 401 — opaque to the frontend, which now needs to
    distinguish "log back in" from "your session ended".

    Behaviour:
      * ExpiredSignatureError → 401 "Token expired — please log in again"
      * InvalidTokenError / JWTError → 401 "Invalid token"
      * Any other Exception → log via structlog, return 401 "Invalid token"
        (internal details NEVER reach the response body)

    Args:
        token: The raw JWT string from the cookie.

    Returns:
        The decoded claims dict on success.

    Raises:
        HTTPException(401): On any decode failure.
    """
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[_JWT_ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please log in again")
    except JWTError:
        # python-jose folds malformed/invalid-signature/wrong-algo all under
        # JWTError, which is what pyjwt would surface as InvalidTokenError.
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        # Anything else (e.g. corrupted settings, unexpected library error)
        # — log structurally for ops visibility, return generic 401.
        log.error("jwt_decode.unexpected_error", error=str(e)[:300])
        raise HTTPException(status_code=401, detail="Invalid token")

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Cookie Secure flag: True in production (HTTPS), False only when ENV=dev
# so localhost http still accepts the cookie. Mirrors the boot-guard convention
# in backend/config.py — same env var, same semantics.
COOKIE_SECURE = os.getenv("ENV", "production") != "dev"
COOKIE_SAMESITE = "lax"


class SuperLoginRequest(BaseModel):
    username: str
    password: str


class ClientLoginRequest(BaseModel):
    email: str
    password: str


# ── Super admin login ──────────────────────────────────────────────────────────

@router.post("/super/login")
@limiter.limit("5/15 minutes")
def super_login(request: Request, data: SuperLoginRequest, response: Response, db: Session = Depends(get_db)):
    admin = db.query(SuperAdmin).filter(SuperAdmin.username == data.username).first()
    candidate = admin.password_hash if admin else _DUMMY_HASH
    if not verify_password(data.password, candidate) or not admin:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({"role": "super_admin", "username": admin.username})

    response.set_cookie(
        "sb_super_token", token,
        httponly=True, samesite=COOKIE_SAMESITE, secure=COOKIE_SECURE,
        max_age=60 * 60 * 24 * 7,  # 7 days
    )
    # Token lives ONLY in the HttpOnly cookie. Returning it in the body too
    # would let any XSS payload read the JWT from JS — defeats the point of
    # HttpOnly. Programmatic API-key clients use Authorization: Bearer instead.
    return {"role": "super_admin"}


# ── Client login ───────────────────────────────────────────────────────────────

@router.post("/login")
@limiter.limit("5/15 minutes")
def client_login(request: Request, data: ClientLoginRequest, response: Response, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.owner_email == data.email).first()
    candidate = tenant.password_hash if tenant else _DUMMY_HASH
    if not verify_password(data.password, candidate) or not tenant:
        raise HTTPException(status_code=401, detail="Invalid credentials")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not tenant.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    tenant.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token = create_token({"role": "client", "bot_id": tenant.bot_id})

    response.set_cookie(
        "sb_client_token", token,
        httponly=True, samesite=COOKIE_SAMESITE, secure=COOKIE_SECURE,
        max_age=60 * 60 * 24 * 7,
    )
    # Token lives ONLY in the HttpOnly cookie. See super_login for rationale.
    return {
        "bot_id": tenant.bot_id,
        "role": "client",
        "company_name": tenant.company_name,
    }


# ── Logout ─────────────────────────────────────────────────────────────────────

@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Revoke any presented tokens by jti, then clear cookies.

    Pre-fix this endpoint only deleted cookies — but a JWT copied out before
    logout (e.g. via dev-tools or stolen by malware) stayed valid until its
    natural expiry. Now we add the jti to the RevokedToken denylist so the
    token is rejected on the next request even if it's replayed.

    Decoding is best-effort: a malformed or already-expired token must not
    fail the logout. We swallow per-token errors so the cookies always clear.
    Legacy tokens issued before jti shipped have payload['jti'] == None and
    are skipped (they expire naturally).
    """
    from backend.database import RevokedToken  # lazy import — mirrors auth.py

    now = datetime.now(timezone.utc)
    for cookie_name in ("sb_client_token", "sb_super_token"):
        token = request.cookies.get(cookie_name)
        if not token:
            continue
        try:
            payload = decode_token(token)
            jti = payload.get("jti") if payload else None
            if jti:
                db.add(RevokedToken(jti=jti, revoked_at=now))
        except Exception:
            # Best-effort: a corrupted token must not block logout.
            pass
    try:
        db.commit()
    except Exception:
        # UNIQUE collision (re-revoking same jti) is a no-op by design.
        db.rollback()

    response.delete_cookie("sb_client_token")
    response.delete_cookie("sb_super_token")
    return {"ok": True}


# ── Me ─────────────────────────────────────────────────────────────────────────

@router.get("/me")
def get_me(request: Request, db: Session = Depends(get_db)):
    """Return current user info regardless of role. Returns 401 if not logged in."""
    # Check super admin first
    # _decode_or_401 raises typed 401s (expired vs invalid) so the frontend
    # can show the right "log in again" message rather than the opaque
    # "not authenticated" the silent decode_token() previously emitted.
    super_token = request.cookies.get("sb_super_token")
    if super_token:
        payload = _decode_or_401(super_token)
        if payload.get("role") == "super_admin":
            admin = db.query(SuperAdmin).filter(
                SuperAdmin.username == payload.get("username")
            ).first()
            if admin:
                return {
                    "role": "super_admin",
                    "username": admin.username,
                }

    # Check client token
    client_token = request.cookies.get("sb_client_token")
    if client_token:
        payload = _decode_or_401(client_token)
        if payload.get("role") == "client":
            tenant = db.query(Tenant).filter(
                Tenant.bot_id == payload.get("bot_id"),
                Tenant.is_active == True,
            ).first()
            if tenant:
                return {
                    "role": "client",
                    "bot_id": tenant.bot_id,
                    "company_name": tenant.company_name,
                    "owner_email": tenant.owner_email,
                    "plan": tenant.plan,
                    "messages_used": tenant.messages_used_this_month,
                    "message_limit": tenant.monthly_message_limit,
                }

    raise HTTPException(status_code=401, detail="Not authenticated")


# ── Change password (client self-service) ─────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.put("/change-password")
def change_password(
    data: ChangePasswordRequest,
    tenant: Tenant = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    # Server-side mirror of the frontend min-length check — never trust the UI.
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    # bcrypt silently truncates input past 72 bytes — two distinct long passwords
    # could hash identically. Reject at the boundary so the user picks a shorter
    # one. Same fence as admin.py:reset_tenant_password / change_super_password.
    if len(data.new_password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password must be 72 bytes or fewer (bcrypt limit)")
    strength_error = validate_password_strength(data.new_password)
    if strength_error:
        raise HTTPException(status_code=400, detail=strength_error)
    if not verify_password(data.current_password, tenant.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    tenant.password_hash = hash_password(data.new_password)
    db.commit()
    return {"ok": True}
