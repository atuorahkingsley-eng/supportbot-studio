"""Tests for backend/routers/config_api.py — custom_instructions field.

Added with the chain-of-thought prompt upgrade (commit 3). The field is a
per-tenant free-text override appended to the system prompt AFTER all platform
rules (see ai_chat.build_system_prompt > custom_block). Storage rules:

  • >2000 chars → 422 (length validator)
  • "" (after strip) → NULL in DB (PUT handler treats empty as clear)
  • None on request body → don't touch DB (back-compat with old clients)
  • Leading / trailing whitespace stripped before length check + storage

These tests exercise the HTTP boundary, not just the pydantic model — so we
also catch routing / dependency-override issues alongside validation.
"""
import pytest

from backend.database import BotConfig


# ── GET /api/config ───────────────────────────────────────────────────────────

def test_get_config_returns_custom_instructions_field(
    test_client, test_db, test_tenant, test_bot_config, auth_headers,
):
    """GET must always return the field in the response envelope, even when null."""
    # Seed a value so we can assert it round-trips.
    cfg = test_db.query(BotConfig).filter(BotConfig.bot_id == test_tenant.bot_id).first()
    cfg.custom_instructions = "Always greet returning customers by name."
    test_db.commit()

    resp = test_client.get("/api/config", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "custom_instructions" in body
    assert body["custom_instructions"] == "Always greet returning customers by name."


def test_get_config_returns_null_custom_instructions_for_fresh_tenant(
    test_client, test_tenant, test_bot_config, auth_headers,
):
    """Field is always present in the response envelope; null is the default."""
    resp = test_client.get("/api/config", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["custom_instructions"] is None


# ── PUT /api/config — happy path ──────────────────────────────────────────────

def test_put_config_saves_custom_instructions(
    test_client, test_db, test_tenant, test_bot_config, auth_headers,
):
    """A valid string round-trips into the DB column."""
    payload = {
        "business_name": "Test Co",
        "agent_name": "TestBot",
        "brand_color": "#000000",
        "welcome_message": "Hi!",
        "escalation_email": "ops@test.example",
        "voice_enabled": True,
        "custom_instructions": "Always mention our 30-day return policy.",
    }
    resp = test_client.put("/api/config", json=payload, headers=auth_headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["custom_instructions"] == "Always mention our 30-day return policy."

    # Verify persistence in DB (expire_all so we re-SELECT, not serve cached row).
    test_db.expire_all()
    cfg = test_db.query(BotConfig).filter(BotConfig.bot_id == test_tenant.bot_id).first()
    assert cfg.custom_instructions == "Always mention our 30-day return policy."


def test_put_config_strips_leading_trailing_whitespace(
    test_client, test_db, test_tenant, test_bot_config, auth_headers,
):
    """Whitespace is stripped before storage (matches _sanitize_custom_instructions)."""
    payload = {
        "business_name": "Test Co",
        "agent_name": "TestBot",
        "brand_color": "#000000",
        "welcome_message": "Hi!",
        "voice_enabled": True,
        "custom_instructions": "   Be concise.   \n",
    }
    resp = test_client.put("/api/config", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["custom_instructions"] == "Be concise."


# ── PUT /api/config — empty string clears to NULL ─────────────────────────────

def test_put_config_empty_string_saves_null_not_empty(
    test_client, test_db, test_tenant, test_bot_config, auth_headers,
):
    """Empty string (after strip) must store as NULL, not the literal "".

    Per spec: "Treat empty string as NULL". This protects the prompt builder
    from emitting an empty ADDITIONAL INSTRUCTIONS block — that block is gated
    on truthy custom_instructions, so "" vs None must collapse to the same
    "no override" semantics.
    """
    # Seed a non-null value first so the test confirms the PUT actually clears it.
    cfg = test_db.query(BotConfig).filter(BotConfig.bot_id == test_tenant.bot_id).first()
    cfg.custom_instructions = "something to clear"
    test_db.commit()

    payload = {
        "business_name": "Test Co",
        "agent_name": "TestBot",
        "brand_color": "#000000",
        "welcome_message": "Hi!",
        "voice_enabled": True,
        "custom_instructions": "",
    }
    resp = test_client.put("/api/config", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    # Response: null (not "")
    assert resp.json()["custom_instructions"] is None

    # DB: NULL (not "")
    test_db.expire_all()
    cfg = test_db.query(BotConfig).filter(BotConfig.bot_id == test_tenant.bot_id).first()
    assert cfg.custom_instructions is None, (
        "Empty string must be persisted as NULL, not as the empty string. "
        f"Got {cfg.custom_instructions!r}."
    )


def test_put_config_whitespace_only_saves_null(
    test_client, test_db, test_tenant, test_bot_config, auth_headers,
):
    """A string of only whitespace strips to "" which then collapses to NULL."""
    cfg = test_db.query(BotConfig).filter(BotConfig.bot_id == test_tenant.bot_id).first()
    cfg.custom_instructions = "kept"
    test_db.commit()

    payload = {
        "business_name": "Test Co",
        "agent_name": "TestBot",
        "brand_color": "#000000",
        "welcome_message": "Hi!",
        "voice_enabled": True,
        "custom_instructions": "   \n\t  ",
    }
    resp = test_client.put("/api/config", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["custom_instructions"] is None


# ── PUT /api/config — over-length → 422 ───────────────────────────────────────

def test_put_config_over_2000_chars_returns_422(
    test_client, test_tenant, test_bot_config, auth_headers,
):
    """>2000 chars must be rejected at the validation boundary, not truncated."""
    payload = {
        "business_name": "Test Co",
        "agent_name": "TestBot",
        "brand_color": "#000000",
        "welcome_message": "Hi!",
        "voice_enabled": True,
        "custom_instructions": "x" * 2001,
    }
    resp = test_client.put("/api/config", json=payload, headers=auth_headers)
    assert resp.status_code == 422, resp.text
    # FastAPI/pydantic returns a structured error envelope — make sure the
    # field name is in the error so the UI can surface it to the user.
    body = resp.json()
    assert "custom_instructions" in str(body)


def test_put_config_exactly_2000_chars_is_allowed(
    test_client, test_db, test_tenant, test_bot_config, auth_headers,
):
    """The boundary itself (exactly 2000) is valid — the check is > 2000."""
    payload = {
        "business_name": "Test Co",
        "agent_name": "TestBot",
        "brand_color": "#000000",
        "welcome_message": "Hi!",
        "voice_enabled": True,
        "custom_instructions": "y" * 2000,
    }
    resp = test_client.put("/api/config", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["custom_instructions"]) == 2000


# ── PUT /api/config — None preserves stored value (back-compat) ───────────────

def test_put_config_null_field_preserves_existing_value(
    test_client, test_db, test_tenant, test_bot_config, auth_headers,
):
    """Field absent / null on the request body: stored value must NOT be wiped.

    This is the back-compat guarantee for older frontends that don't yet send
    the field. The PUT handler distinguishes "client didn't send" (None) from
    "client sent empty" ("") — only the latter clears the column.
    """
    cfg = test_db.query(BotConfig).filter(BotConfig.bot_id == test_tenant.bot_id).first()
    cfg.custom_instructions = "preserve me"
    test_db.commit()

    # Payload deliberately OMITS custom_instructions.
    payload = {
        "business_name": "Test Co",
        "agent_name": "TestBot",
        "brand_color": "#000000",
        "welcome_message": "Hi!",
        "voice_enabled": True,
    }
    resp = test_client.put("/api/config", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text

    test_db.expire_all()
    cfg = test_db.query(BotConfig).filter(BotConfig.bot_id == test_tenant.bot_id).first()
    assert cfg.custom_instructions == "preserve me", (
        "A PUT without the custom_instructions field must NOT clobber the stored value — "
        "this is the back-compat guarantee for older clients."
    )
