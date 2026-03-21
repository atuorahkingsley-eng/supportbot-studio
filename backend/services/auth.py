"""
Authentication utilities for SupportBot multi-tenant.
Pure functions only — no database imports at module level to avoid circular imports.
FastAPI dependency functions use lazy Tenant imports via the db session.
"""
from datetime import datetime, timedelta
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24 * 7  # 7 days


# ── Pure utilities (no DB access) ─────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(data: dict, expires_hours: int = TOKEN_EXPIRE_HOURS) -> str:
    expire = datetime.utcnow() + timedelta(hours=expires_hours)
    payload = {**data, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ── FastAPI dependency functions ──────────────────────────────────────────────

async def get_current_client(request: Request, db: Session = Depends(get_db)):
    """Extract authenticated tenant from sb_client_token cookie."""
    from backend.database import Tenant  # lazy import

    token = request.cookies.get("sb_client_token")
    if not token:
        # Also accept Bearer header (for API key fallback path)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_token(token)
    if not payload or payload.get("role") != "client":
        raise HTTPException(status_code=401, detail="Invalid token")

    tenant = db.query(Tenant).filter(Tenant.bot_id == payload["bot_id"]).first()
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=403, detail="Account inactive or not found")

    return tenant


async def get_super_admin(request: Request, db: Session = Depends(get_db)):
    """Verify super admin token from sb_super_token cookie."""
    from backend.database import SuperAdmin  # lazy import

    token = request.cookies.get("sb_super_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_token(token)
    if not payload or payload.get("role") != "super_admin":
        raise HTTPException(status_code=401, detail="Not authorized")

    admin = db.query(SuperAdmin).filter(
        SuperAdmin.username == payload.get("username")
    ).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Super admin not found")

    return payload


async def get_tenant_from_api_key(request: Request, db: Session = Depends(get_db)):
    """Authenticate via X-API-Key header (alternative to cookie auth)."""
    from backend.database import Tenant  # lazy import

    api_key = (
        request.headers.get("X-API-Key")
        or request.headers.get("Authorization", "").replace("Bearer ", "")
    )
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    tenant = db.query(Tenant).filter(
        Tenant.api_key == api_key,
        Tenant.is_active == True,
    ).first()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return tenant
