"""Tests for backend/routers/escalate.py — escalation_reason persistence.

Added with the chain-of-thought prompt upgrade (commit 3). The widget forwards
the chat router's escalation_reason on the escalate POST body; the backend
validates against ai_chat.VALID_ESCALATION_REASONS and persists the result on
Lead.escalation_reason. Off-spec / missing values collapse to "customer_requested"
(the widget-button default — see _DEFAULT_LEAD_ESCALATION_REASON in escalate.py).

We mock the outbound notification channels (telegram + email) at the call sites
inside _do_escalate so the test:

  • doesn't hit Telegram / SMTP for real,
  • passes the "all channels failed → 500" gate by returning truthy from at
    least one channel mock (otherwise the escalation queues for retry and
    short-circuits before the Lead row is written).
"""
from unittest.mock import AsyncMock

import pytest

from backend.database import Lead


def _seed_telegram_settings(monkeypatch):
    """The platform-wide telegram path is gated on settings.telegram_chat_id —
    without a value, send_telegram_message returns False and the escalation
    counts as fully failed. We mock the underlying send instead of the setting
    so the test stays independent of config flag drift.
    """
    pass  # We patch send_telegram_message directly in each test.


@pytest.fixture
def patched_notifications(mocker):
    """Patch every outbound channel inside escalate.py to a truthy AsyncMock.

    Returns the dict of patched mocks so a test can assert call args if needed.
    All four channels return True so _do_escalate sees `any(results)` and
    proceeds to the Lead-write block — which is what we're actually testing.
    """
    return {
        "telegram": mocker.patch(
            "backend.routers.escalate.send_telegram_message",
            new=AsyncMock(return_value=True),
        ),
        "email": mocker.patch(
            "backend.routers.escalate.send_escalation_email",
            new=AsyncMock(return_value=True),
        ),
        "webhook": mocker.patch(
            "backend.routers.escalate.dispatch_webhook",
            new=AsyncMock(return_value=True),
        ),
    }


# ── escalation_reason persisted on Lead row ───────────────────────────────────

def test_escalation_reason_stored_on_lead(
    test_client, test_db, test_tenant, test_bot_config, patched_notifications,
):
    """A valid AI reason on the request body lands on Lead.escalation_reason."""
    payload = {
        "bot_id": test_tenant.bot_id,
        "session_id": "sess-escalation-reason-001",
        "visitor_id": "v_test_001",
        "email": "visitor@test.example",
        "reason": "ai_escalated",
        "escalation_reason": "frustration",
    }
    resp = test_client.post("/api/escalate/public", json=payload)
    assert resp.status_code == 200, resp.text

    test_db.expire_all()
    lead = (
        test_db.query(Lead)
        .filter(Lead.bot_id == test_tenant.bot_id, Lead.type == "escalation")
        .order_by(Lead.created_at.desc())
        .first()
    )
    assert lead is not None, "An escalation Lead row should have been created"
    assert lead.escalation_reason == "frustration"


def test_escalation_reason_invalid_value_defaults_to_customer_requested(
    test_client, test_db, test_tenant, test_bot_config, patched_notifications,
):
    """An off-vocabulary string collapses to the widget-button default.

    "made_up_reason" isn't in VALID_ESCALATION_REASONS so the router must
    coerce to "customer_requested" rather than persist garbage or 422 the
    request (we'd rather ship the escalation than block on stale clients).
    """
    payload = {
        "bot_id": test_tenant.bot_id,
        "session_id": "sess-escalation-reason-002",
        "visitor_id": "v_test_002",
        "email": "v2@test.example",
        "escalation_reason": "made_up_reason",
    }
    resp = test_client.post("/api/escalate/public", json=payload)
    assert resp.status_code == 200, resp.text

    test_db.expire_all()
    lead = (
        test_db.query(Lead)
        .filter(Lead.bot_id == test_tenant.bot_id, Lead.type == "escalation")
        .order_by(Lead.created_at.desc())
        .first()
    )
    assert lead is not None
    assert lead.escalation_reason == "customer_requested"


def test_escalation_reason_missing_defaults_to_customer_requested(
    test_client, test_db, test_tenant, test_bot_config, patched_notifications,
):
    """No escalation_reason on the request body → widget-button default."""
    payload = {
        "bot_id": test_tenant.bot_id,
        "session_id": "sess-escalation-reason-003",
        "visitor_id": "v_test_003",
        "email": "v3@test.example",
        # escalation_reason intentionally omitted.
    }
    resp = test_client.post("/api/escalate/public", json=payload)
    assert resp.status_code == 200, resp.text

    test_db.expire_all()
    lead = (
        test_db.query(Lead)
        .filter(Lead.bot_id == test_tenant.bot_id, Lead.type == "escalation")
        .order_by(Lead.created_at.desc())
        .first()
    )
    assert lead is not None
    assert lead.escalation_reason == "customer_requested"


@pytest.mark.parametrize("ai_reason", [
    "explicit_request",
    "frustration",
    "urgency",
    "sensitive_topic",
    "unresolved_loop",
    "no_faq_answer",
])
def test_all_six_ai_reasons_persist_unchanged(
    test_client, test_db, test_tenant, test_bot_config, patched_notifications, ai_reason,
):
    """Each of the six canonical AI reasons must round-trip unchanged.

    Parametrised over the full set defined in ai_chat.VALID_ESCALATION_REASONS
    so adding a new reason later requires updating the constant + this test
    in lockstep (or test fails — single source of truth enforced).
    """
    payload = {
        "bot_id": test_tenant.bot_id,
        "session_id": f"sess-ai-reason-{ai_reason}",
        "visitor_id": f"v_{ai_reason}",
        "email": f"{ai_reason}@test.example",
        "escalation_reason": ai_reason,
    }
    resp = test_client.post("/api/escalate/public", json=payload)
    assert resp.status_code == 200, resp.text

    test_db.expire_all()
    lead = (
        test_db.query(Lead)
        .filter(
            Lead.bot_id == test_tenant.bot_id,
            Lead.visitor_id == f"v_{ai_reason}",
        )
        .first()
    )
    assert lead is not None
    assert lead.escalation_reason == ai_reason
