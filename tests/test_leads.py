"""Tests for Bug 10 — filter-parameter validation on /api/leads.

Pre-fix the list / export endpoints silently treated unknown values for
``type`` / ``status`` / ``range`` as "no filter". A typo like
``range=yesterday`` returned every row, and the frontend had no way to
notice. The fix routes every query param through ``_validate_filter``
which raises HTTP 422 with the allowed values echoed back.

Status-update + CSV export coverage rounds out the file — the PATCH path
also has its own Pydantic ``Literal`` validation that we want pinned.
"""

from datetime import datetime, timedelta

import pytest

from backend.database import Lead


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_lead(db, *, bot_id, **overrides):
    """Insert one Lead row with sensible defaults; return the committed row."""
    fields = dict(
        bot_id=bot_id,
        email="lead@example.com",
        name="A Lead",
        phone="+15555550100",
        interest="pricing",
        source="chat_capture",
        type="lead",
        status="new",
        buying_signal_score=3,
    )
    fields.update(overrides)
    lead = Lead(**fields)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


# ── 1. Invalid range ──────────────────────────────────────────────────────────

def test_invalid_range_returns_422(test_client, test_tenant, auth_headers):
    """``range=yesterday`` is not in the allowed set
    {today, 7d, 30d, all}. The validator raises 422 and includes the
    parameter name + allowed values in the detail payload so the
    frontend can render the error without a translation layer."""
    resp = test_client.get("/api/leads?range=yesterday", headers=auth_headers)
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    # detail is a dict per our validator — assert the contract shape.
    assert isinstance(detail, dict)
    assert detail["got"] == "yesterday"
    assert "today" in detail["allowed"]
    assert "all" in detail["allowed"]


# ── 2. Invalid type ───────────────────────────────────────────────────────────

def test_invalid_type_returns_422(test_client, test_tenant, auth_headers):
    """Same gate, different param. Catches typos like ``type=Lead`` or
    ``type=leads`` (plural)."""
    resp = test_client.get("/api/leads?type=unknown", headers=auth_headers)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["got"] == "unknown"
    # Allowed set is {lead, escalation, all}; sorted alphabetically.
    assert detail["allowed"] == ["all", "escalation", "lead"]


# ── 3. Invalid status ─────────────────────────────────────────────────────────

def test_invalid_status_returns_422(test_client, test_tenant, auth_headers):
    """Status filter accepts the four lifecycle values + 'all'.
    ``maybe`` is not one of them — should 422, not silently match-all."""
    resp = test_client.get("/api/leads?status=maybe", headers=auth_headers)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["got"] == "maybe"
    assert set(detail["allowed"]) == {"all", "new", "contacted", "qualified", "lost"}


# ── 4. Valid filter combo ─────────────────────────────────────────────────────

def test_valid_filters_return_200(test_client, test_tenant, auth_headers, test_db):
    """A fully-valid filter triple should return the standard
    LeadListResponse envelope. Production keys are
    {items, page, per_page, total, total_pages}; the spec phrasing
    ('leads', 'total', 'page') predated the unified router so we assert
    on the actual contract.

    We seed one matching row so the list isn't empty — gives us
    confidence the filter pipeline doesn't reject valid inputs.
    """
    _make_lead(test_db, bot_id=test_tenant.bot_id, type="lead", status="new")

    resp = test_client.get(
        "/api/leads?range=7d&type=lead&status=new",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "per_page" in body
    assert "total_pages" in body
    assert body["total"] >= 1
    assert len(body["items"]) >= 1


# ── 5. Status update — valid value ────────────────────────────────────────────

def test_status_update_accepts_valid_values(
    test_client, test_db, test_tenant, auth_headers,
):
    """PATCH .../status with a value in the Literal type should persist
    and return ok. Reload from a fresh session to prove the write hit
    the DB (not just the in-memory ORM cache)."""
    lead = _make_lead(test_db, bot_id=test_tenant.bot_id, status="new")
    lead_id = lead.id

    resp = test_client.patch(
        f"/api/leads/{lead_id}/status",
        json={"status": "contacted"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "contacted"

    # Force a fresh read so we see what the route's session committed,
    # not what our fixture session cached.
    test_db.expire_all()
    refreshed = test_db.query(Lead).filter_by(id=lead_id).first()
    assert refreshed.status == "contacted"


# ── 6. Status update — invalid value ──────────────────────────────────────────

def test_status_update_rejects_invalid_value(
    test_client, test_db, test_tenant, auth_headers,
):
    """``status="maybe"`` isn't in the Literal — Pydantic v2 surfaces
    this as 422 before the handler even runs, so the bad value never
    touches the DB."""
    lead = _make_lead(test_db, bot_id=test_tenant.bot_id, status="new")

    resp = test_client.patch(
        f"/api/leads/{lead.id}/status",
        json={"status": "maybe"},
        headers=auth_headers,
    )
    assert resp.status_code == 422

    test_db.expire_all()
    refreshed = test_db.query(Lead).filter_by(id=lead.id).first()
    # Confirm the DB row was NOT modified by the rejected PATCH.
    assert refreshed.status == "new"


# ── 7. CSV export ─────────────────────────────────────────────────────────────

def test_export_csv_returns_file(
    test_client, test_db, test_tenant, auth_headers,
):
    """Three leads in, three leads + header row out. The Content-Type
    must signal CSV so browsers offer download instead of inline-rendering."""
    for i in range(3):
        _make_lead(
            test_db,
            bot_id=test_tenant.bot_id,
            email=f"lead{i}@example.com",
            name=f"Lead {i}",
        )

    resp = test_client.get("/api/leads/export", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")

    text = resp.text
    # Split on CRLF or LF — csv.writer emits \r\n on Windows.
    lines = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln]
    # 1 header row + 3 data rows.
    assert len(lines) == 4, f"Expected 4 lines (header + 3 leads), got {len(lines)}: {lines!r}"
    # First line must be the header — check one column name.
    assert "email" in lines[0]
    # Data rows must include the seeded emails.
    joined = "\n".join(lines[1:])
    assert "lead0@example.com" in joined
    assert "lead1@example.com" in joined
    assert "lead2@example.com" in joined
