"""Unified Leads router.

Backs the "Leads" tab in the client dashboard, which surfaces BOTH buying-intent
captures (``type="lead"``) and human-support escalations (``type="escalation"``)
in one filterable table. Rows are written by ``sales.capture_lead`` and
``escalate._do_escalate`` respectively; this router is read + status-update +
export only.

Endpoints
---------
* ``GET    /api/leads``               — paginated list with type/status/range filters
* ``GET    /api/leads/summary``       — 4 KPI cards for the tab header
* ``PATCH  /api/leads/{lead_id}/status`` — drive the lifecycle dropdown
* ``GET    /api/leads/export``        — CSV stream (formula-injection guarded)
"""

from __future__ import annotations

import io
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import Lead, Tenant, get_db
from backend.services.auth import get_current_client
from backend.utils.csv_export import _safe_cell

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/leads", tags=["leads"])


# ── Constants ─────────────────────────────────────────────────────────────────

# Allowed values for the status column. Kept here (not just in the migration)
# so the PATCH endpoint can reject typos at request time rather than letting
# garbage into the DB.
_VALID_STATUSES: tuple[str, ...] = ("new", "contacted", "qualified", "lost")

# Allowed type filter values. The list endpoint also accepts "all" (treated as
# no filter). Persisted rows are always exactly one of "lead" / "escalation".
_VALID_TYPES: tuple[str, ...] = ("lead", "escalation")

# Maps the public ``range`` query-string keyword to a UTC timedelta. ``all``
# bypasses the filter entirely.
_RANGE_DELTAS: dict[str, Optional[timedelta]] = {
    "today": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}


# ── Schemas ───────────────────────────────────────────────────────────────────


class LeadRow(BaseModel):
    """One row in the unified Leads table.

    ``message`` is sourced from the DB column ``interest`` — historic naming
    mismatch we keep at the column level (no rename migration) and translate
    only at the API boundary.
    """

    id: int
    type: str
    status: str
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    message: Optional[str]
    source: str
    visitor_id: Optional[str]
    conversation_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class LeadListResponse(BaseModel):
    """Paginated envelope around ``LeadRow``."""

    items: list[LeadRow]
    page: int
    per_page: int
    total: int
    total_pages: int


class LeadSummary(BaseModel):
    """KPI cards for the Leads tab header."""

    total_all_time: int
    total_this_month: int
    with_contact: int
    escalations_this_month: int


class StatusUpdate(BaseModel):
    status: Literal["new", "contacted", "qualified", "lost"]


# ── Helpers ───────────────────────────────────────────────────────────────────


# Pre-computed allowed sets for filter validation. "all" is a UI convenience
# that means "no filter"; None (param omitted entirely) means the same. We
# accept both rather than forcing the frontend to strip "all" before sending.
_ALLOWED_TYPE_FILTERS: frozenset[str] = frozenset(_VALID_TYPES) | {"all"}
_ALLOWED_STATUS_FILTERS: frozenset[str] = frozenset(_VALID_STATUSES) | {"all"}
_ALLOWED_RANGE_FILTERS: frozenset[str] = frozenset(_RANGE_DELTAS.keys())


def _validate_filter(
    value: Optional[str], allowed: frozenset[str], *, param_name: str
) -> None:
    """Raise HTTP 422 if ``value`` is not None and not in ``allowed``.

    Pre-fix the list/export endpoints silently treated unknown filter values
    as "no filter" (the `!= "all"` check would fail to match, but no other
    branch matched either, so the row was included anyway). That made typos
    impossible to spot from the client — the response looked successful but
    contained the wrong rows. Now any unrecognised value is a hard 422 with
    the allowed values echoed back, so the frontend (or curl user) sees
    exactly what went wrong.
    """
    if value is None:
        return
    if value not in allowed:
        # Sort for stable error messages — easier to assert in tests and
        # easier on humans reading the response.
        raise HTTPException(
            status_code=422,
            detail={
                "error": f"Invalid value for '{param_name}'",
                "got": value,
                "allowed": sorted(allowed),
            },
        )


def _apply_filters(
    q,
    *,
    bot_id: str,
    type_filter: Optional[str],
    status_filter: Optional[str],
    range_filter: Optional[str],
):
    """Apply the standard list-page filters to a Lead query.

    Centralised so the list endpoint and the CSV export endpoint apply
    identical filter semantics — the CSV download should match what's on
    screen, not silently dump everything.

    Args:
        q: SQLAlchemy ``Query`` over the Lead model.
        bot_id: Tenant identifier — always applied as the first filter.
        type_filter: ``"lead"``, ``"escalation"``, or ``"all"``/None.
        status_filter: One of _VALID_STATUSES, or ``"all"``/None.
        range_filter: One of _RANGE_DELTAS keys, or None.

    Returns:
        The query with filters applied. Caller chains ordering / pagination.
    """
    q = q.filter(Lead.bot_id == bot_id)
    if type_filter and type_filter != "all":
        q = q.filter(Lead.type == type_filter)
    if status_filter and status_filter != "all":
        q = q.filter(Lead.status == status_filter)
    if range_filter and range_filter != "all":
        delta = _RANGE_DELTAS.get(range_filter)
        if delta is not None:
            q = q.filter(Lead.created_at >= datetime.now(timezone.utc) - delta)
    return q


def _row_for_response(lead: Lead) -> dict[str, Any]:
    """Project a Lead ORM row into the API shape (interest → message)."""
    return {
        "id": lead.id,
        "type": lead.type,
        "status": lead.status,
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "message": lead.interest,
        "source": lead.source,
        "visitor_id": lead.visitor_id,
        "conversation_id": lead.conversation_id,
        "created_at": lead.created_at,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=LeadListResponse)
def list_leads(
    type: Optional[str] = Query(None, description='"lead", "escalation", or "all"'),
    status: Optional[str] = Query(None, description="new|contacted|qualified|lost|all"),
    range: Optional[str] = Query(None, description="today|7d|30d|all"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
) -> LeadListResponse:
    """Return a filtered, paginated slice of Leads for the current tenant.

    Filters compose with AND. Pagination is 1-indexed (matches the URL the
    user sees in the tab). Newest-first ordering is fixed — every dashboard
    consumer wants it.
    """
    _validate_filter(type, _ALLOWED_TYPE_FILTERS, param_name="type")
    _validate_filter(status, _ALLOWED_STATUS_FILTERS, param_name="status")
    _validate_filter(range, _ALLOWED_RANGE_FILTERS, param_name="range")

    base_q = _apply_filters(
        db.query(Lead),
        bot_id=tenant.bot_id,
        type_filter=type,
        status_filter=status,
        range_filter=range,
    )

    total = base_q.count()
    total_pages = math.ceil(total / per_page) if total else 0

    rows = (
        base_q.order_by(Lead.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return LeadListResponse(
        items=[LeadRow(**_row_for_response(r)) for r in rows],
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )


@router.get("/summary", response_model=LeadSummary)
def lead_summary(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
) -> LeadSummary:
    """KPI cards for the Leads tab header.

    All four numbers are computed against the tenant's rows only.

    * ``total_all_time`` — every row regardless of type
    * ``total_this_month`` — rows created in the last 30 days
    * ``with_contact`` — rows with at least one of email/phone (i.e. visitor
      filled the form rather than skipping it)
    * ``escalations_this_month`` — type=escalation rows in the last 30 days
    """
    bid = tenant.bot_id
    month_ago = datetime.now(timezone.utc) - timedelta(days=30)

    total_all_time = db.query(func.count(Lead.id)).filter(Lead.bot_id == bid).scalar() or 0
    total_this_month = (
        db.query(func.count(Lead.id))
        .filter(Lead.bot_id == bid, Lead.created_at >= month_ago)
        .scalar()
        or 0
    )
    with_contact = (
        db.query(func.count(Lead.id))
        .filter(
            Lead.bot_id == bid,
            (Lead.email.isnot(None)) | (Lead.phone.isnot(None)),
        )
        .scalar()
        or 0
    )
    escalations_this_month = (
        db.query(func.count(Lead.id))
        .filter(
            Lead.bot_id == bid,
            Lead.type == "escalation",
            Lead.created_at >= month_ago,
        )
        .scalar()
        or 0
    )

    return LeadSummary(
        total_all_time=total_all_time,
        total_this_month=total_this_month,
        with_contact=with_contact,
        escalations_this_month=escalations_this_month,
    )


@router.patch("/{lead_id}/status")
def update_lead_status(
    lead_id: int,
    payload: StatusUpdate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
) -> dict[str, Any]:
    """Drive the inline status dropdown in the Leads table.

    Pydantic's ``Literal`` validation rejects bad values before we get here,
    but we still check the lead belongs to the calling tenant — never trust
    an ID parameter on a multi-tenant table.
    """
    lead = (
        db.query(Lead)
        .filter(Lead.id == lead_id, Lead.bot_id == tenant.bot_id)
        .first()
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.status = payload.status
    db.commit()
    db.refresh(lead)
    return {"ok": True, "id": lead.id, "status": lead.status}


@router.get("/export")
def export_leads(
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    range: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    """Stream the currently-filtered Leads view as CSV.

    Filters mirror ``list_leads`` exactly so a user clicking Export gets the
    same rows they see on screen. All free-text cells run through
    ``_safe_cell`` to neutralise spreadsheet formula injection.
    """
    _validate_filter(type, _ALLOWED_TYPE_FILTERS, param_name="type")
    _validate_filter(status, _ALLOWED_STATUS_FILTERS, param_name="status")
    _validate_filter(range, _ALLOWED_RANGE_FILTERS, param_name="range")

    q = _apply_filters(
        db.query(Lead),
        bot_id=tenant.bot_id,
        type_filter=type,
        status_filter=status,
        range_filter=range,
    ).order_by(Lead.created_at.desc())

    rows = q.all()

    filename = f"leads-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"

    def _lead_csv_generator(leads: list):
        import csv, io
        headers = [
            "id", "created_at", "type", "status", "name", "email",
            "phone", "message", "source", "visitor_id", "conversation_id",
        ]
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(headers)
        for lead in leads:
            w.writerow([
                lead.id,
                lead.created_at.isoformat() if lead.created_at else "",
                _safe_cell(lead.type),
                _safe_cell(lead.status),
                _safe_cell(lead.name),
                _safe_cell(lead.email),
                _safe_cell(lead.phone),
                _safe_cell(lead.interest),
                _safe_cell(lead.source),
                _safe_cell(lead.visitor_id),
                lead.conversation_id if lead.conversation_id is not None else "",
            ])
        yield buf.getvalue()

    return StreamingResponse(
        _lead_csv_generator(rows),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
