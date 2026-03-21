"""
Auth endpoints: login, logout, me.
Two auth systems: super admin (/api/auth/super/login) and client (/api/auth/login).
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from backend.database import get_db, Tenant, SuperAdmin
from backend.services.auth import (
    hash_password, verify_password, create_token, decode_token,
    get_current_client, get_super_admin,
)
from backend.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_SECURE = False   # Set True in production (HTTPS)
COOKIE_SAMESITE = "lax"


class SuperLoginRequest(BaseModel):
    username: str
    password: str


class ClientLoginRequest(BaseModel):
    email: str
    password: str


# ── Super admin login ──────────────────────────────────────────────────────────

@router.post("/super/login")
def super_login(data: SuperLoginRequest, response: Response, db: Session = Depends(get_db)):
    admin = db.query(SuperAdmin).filter(SuperAdmin.username == data.username).first()
    if not admin or not verify_password(data.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({"role": "super_admin", "username": admin.username})

    response.set_cookie(
        "sb_super_token", token,
        httponly=True, samesite=COOKIE_SAMESITE, secure=COOKIE_SECURE,
        max_age=60 * 60 * 24 * 7,  # 7 days
    )
    return {"token": token, "role": "super_admin"}


# ── Client login ───────────────────────────────────────────────────────────────

@router.post("/login")
def client_login(data: ClientLoginRequest, response: Response, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.owner_email == data.email).first()
    if not tenant or not verify_password(data.password, tenant.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not tenant.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    tenant.last_login_at = datetime.utcnow()
    db.commit()

    token = create_token({"role": "client", "bot_id": tenant.bot_id})

    response.set_cookie(
        "sb_client_token", token,
        httponly=True, samesite=COOKIE_SAMESITE, secure=COOKIE_SECURE,
        max_age=60 * 60 * 24 * 7,
    )
    return {
        "token": token,
        "bot_id": tenant.bot_id,
        "role": "client",
        "company_name": tenant.company_name,
    }


# ── Logout ─────────────────────────────────────────────────────────────────────

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("sb_client_token")
    response.delete_cookie("sb_super_token")
    return {"ok": True}


# ── Me ─────────────────────────────────────────────────────────────────────────

@router.get("/me")
def get_me(request: Request, db: Session = Depends(get_db)):
    """Return current user info regardless of role. Returns 401 if not logged in."""
    # Check super admin first
    super_token = request.cookies.get("sb_super_token")
    if super_token:
        payload = decode_token(super_token)
        if payload and payload.get("role") == "super_admin":
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
        payload = decode_token(client_token)
        if payload and payload.get("role") == "client":
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
    if not verify_password(data.current_password, tenant.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    tenant.password_hash = hash_password(data.new_password)
    db.commit()
    return {"ok": True}
