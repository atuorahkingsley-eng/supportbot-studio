"""Brand Voice DNA endpoints — tenant-scoped, JWT-cookie auth.

Endpoints:
  POST   /api/brand-voice/analyze   — run Claude, upsert the row (5/hour)
  GET    /api/brand-voice           — current profile (or 404 if none)
  PUT    /api/brand-voice           — toggle is_active
  DELETE /api/brand-voice           — wipe the row

Rate limit on /analyze is intentionally tight (5/hour). Each call is a
paid Claude API request and tenants only need to run this when the
samples actually change.
"""
import json
from datetime import datetime
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db, BrandVoice, Tenant
from backend.services.auth import get_current_client
from backend.services.brand_voice_analyzer import (
    analyze_brand_voice,
    BrandVoiceAnalysisError,
)
from backend.services.rate_limit import limiter


router = APIRouter(prefix="/api/brand-voice", tags=["brand-voice"])
log = structlog.get_logger(__name__)


# ── Request / response schemas ────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    # Min length avoids wasting a Claude call on a couple of words.
    samples: str = Field(..., min_length=20)


class ToggleRequest(BaseModel):
    is_active: bool


class BrandVoiceResponse(BaseModel):
    id: int
    bot_id: str
    tone: Optional[str]
    vocabulary: Optional[str]
    personality_traits: List[str]  # decoded from JSON column for the client
    avoid: Optional[str]
    raw_samples: Optional[str]
    is_active: bool
    generated_at: Optional[datetime]
    updated_at: Optional[datetime]


def _serialize(row: BrandVoice) -> BrandVoiceResponse:
    """Convert ORM row → response model, decoding the JSON traits list."""
    traits: List[str] = []
    if row.personality_traits:
        try:
            parsed = json.loads(row.personality_traits)
            if isinstance(parsed, list):
                traits = [str(t) for t in parsed]
        except json.JSONDecodeError:
            # Bad data on disk — return empty list rather than 500.
            traits = []
    return BrandVoiceResponse(
        id=row.id,
        bot_id=row.bot_id,
        tone=row.tone,
        vocabulary=row.vocabulary,
        personality_traits=traits,
        avoid=row.avoid,
        raw_samples=row.raw_samples,
        is_active=row.is_active,
        generated_at=row.generated_at,
        updated_at=row.updated_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=BrandVoiceResponse)
@limiter.limit("5/hour")
async def analyze(
    request: Request,
    data: AnalyzeRequest,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    """Extract a fresh voice profile from samples and upsert by bot_id."""
    try:
        profile = await analyze_brand_voice(data.samples, tenant.bot_id)
    except BrandVoiceAnalysisError as e:
        # 502 — we're a gateway to Claude here. The tenant's request was
        # well-formed; the upstream call is what failed.
        raise HTTPException(status_code=502, detail=str(e))

    row = db.query(BrandVoice).filter(BrandVoice.bot_id == tenant.bot_id).first()
    traits_json = json.dumps(profile["personality_traits"])

    if row:
        row.tone = profile["tone"]
        row.vocabulary = profile["vocabulary"]
        row.personality_traits = traits_json
        row.avoid = profile["avoid"]
        row.raw_samples = profile["raw_samples"]
        row.generated_at = datetime.utcnow()
        # Re-analysis preserves is_active — tenant doesn't have to re-toggle.
    else:
        row = BrandVoice(
            bot_id=tenant.bot_id,
            tone=profile["tone"],
            vocabulary=profile["vocabulary"],
            personality_traits=traits_json,
            avoid=profile["avoid"],
            raw_samples=profile["raw_samples"],
            is_active=False,  # opt-in after review
            generated_at=datetime.utcnow(),
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    log.info("brand_voice.upserted", bot_id=tenant.bot_id, voice_id=row.id)
    return _serialize(row)


@router.get("", response_model=BrandVoiceResponse)
def get_voice(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    row = db.query(BrandVoice).filter(BrandVoice.bot_id == tenant.bot_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="No brand voice profile")
    return _serialize(row)


@router.put("", response_model=BrandVoiceResponse)
def toggle_active(
    data: ToggleRequest,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    """Toggle is_active without re-running Claude."""
    row = db.query(BrandVoice).filter(BrandVoice.bot_id == tenant.bot_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="No brand voice profile")
    row.is_active = data.is_active
    db.commit()
    db.refresh(row)
    log.info("brand_voice.toggled", bot_id=tenant.bot_id, is_active=row.is_active)
    return _serialize(row)


@router.delete("")
def delete_voice(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    row = db.query(BrandVoice).filter(BrandVoice.bot_id == tenant.bot_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="No brand voice profile")
    db.delete(row)
    db.commit()
    log.info("brand_voice.deleted", bot_id=tenant.bot_id)
    return {"ok": True}
