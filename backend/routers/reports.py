from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from backend.database import get_db, ReportSchedule, Tenant
from backend.services.auth import get_current_client

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ReportScheduleSchema(BaseModel):
    frequency: str = "daily"
    send_via: str = "telegram"
    send_at_hour: int = 8
    send_on_day: Optional[int] = None
    enabled: bool = True


class ReportScheduleResponse(ReportScheduleSchema):
    id: int
    last_sent_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("", response_model=ReportScheduleResponse)
def get_report_schedule(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    schedule = db.query(ReportSchedule).filter(
        ReportSchedule.bot_id == tenant.bot_id
    ).first()
    if not schedule:
        schedule = ReportSchedule(bot_id=tenant.bot_id)
        db.add(schedule)
        db.commit()
        db.refresh(schedule)
    return schedule


@router.put("", response_model=ReportScheduleResponse)
def update_report_schedule(
    data: ReportScheduleSchema,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    schedule = db.query(ReportSchedule).filter(
        ReportSchedule.bot_id == tenant.bot_id
    ).first()
    if not schedule:
        schedule = ReportSchedule(bot_id=tenant.bot_id)
        db.add(schedule)

    schedule.frequency = data.frequency
    schedule.send_via = data.send_via
    schedule.send_at_hour = data.send_at_hour
    schedule.send_on_day = data.send_on_day
    schedule.enabled = data.enabled

    db.commit()
    db.refresh(schedule)
    return schedule
