from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from backend.database import get_db, BotConfig

router = APIRouter(prefix="/api/config", tags=["config"])


class BotConfigSchema(BaseModel):
    business_name: str
    agent_name: str
    brand_color: str
    welcome_message: str
    escalation_email: str


class BotConfigResponse(BotConfigSchema):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=BotConfigResponse)
def get_config(db: Session = Depends(get_db)):
    config = db.query(BotConfig).first()
    if not config:
        config = BotConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


@router.put("", response_model=BotConfigResponse)
def update_config(data: BotConfigSchema, db: Session = Depends(get_db)):
    config = db.query(BotConfig).first()
    if not config:
        config = BotConfig()
        db.add(config)

    config.business_name = data.business_name
    config.agent_name = data.agent_name
    config.brand_color = data.brand_color
    config.welcome_message = data.welcome_message
    config.escalation_email = data.escalation_email
    config.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(config)
    return config
