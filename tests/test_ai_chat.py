"""Unit tests for backend/services/ai_chat.py.

Covers the chain-of-thought prompt upgrade (commit b2c4e6f8a1d3 + follow-up):

  • parse_metadata() correctly extracts the new ESCALATE_META sidecar tag
    alongside the existing LANG and SALES_META tags, and strips ALL of them
    from the customer-visible reply.
  • build_system_prompt() injects custom_instructions when present, omits
    the block when blank/None, and sanitizes control characters / over-length
    input through _sanitize_custom_instructions.

Pure unit tests — no DB, no HTTP, no mocking of the Anthropic client. They
exercise the parsing + prompt-composition logic directly, which is where the
new behaviour lives. The end-to-end chat-flow integration tests in
test_chat.py cover the chat router's consumption of these fields separately.
"""
from types import SimpleNamespace

import pytest

from backend.services.ai_chat import (
    build_system_prompt,
    parse_metadata,
    _sanitize_custom_instructions,
)


# ── parse_metadata: ESCALATE_META extraction ──────────────────────────────────

def test_parse_metadata_extracts_escalate_meta_single_tag():
    """ESCALATE_META alone is parsed and stripped from the reply."""
    raw = (
        "I'll connect you with a human agent right away. ESCALATE\n"
        'ESCALATE_META:{"reason":"explicit_request"}'
    )
    result = parse_metadata(raw)

    assert result["escalate_meta"] == {"reason": "explicit_request"}
    # Tag must not leak into reply.
    assert "ESCALATE_META" not in result["reply"]
    assert '"reason"' not in result["reply"]
    # ESCALATE keyword stays — the router strips it separately.
    assert "ESCALATE" in result["reply"]


def test_parse_metadata_extracts_escalate_meta_with_sales_meta():
    """All three tags together — every one parsed, none leak into reply."""
    raw = (
        "I understand you're frustrated. Let me get a human to help. ESCALATE\n"
        'LANG:en\n'
        'ESCALATE_META:{"reason":"frustration"}\n'
        'SALES_META:{"buying_signal":1,"intent":"general","action":"none"}'
    )
    result = parse_metadata(raw)

    assert result["escalate_meta"] == {"reason": "frustration"}
    assert result["sales_meta"] == {
        "buying_signal": 1,
        "intent": "general",
        "action": "none",
    }
    assert result["detected_language"] == "en"
    # None of the three sidecar tags should appear in the reply.
    assert "ESCALATE_META" not in result["reply"]
    assert "SALES_META" not in result["reply"]
    assert "LANG:" not in result["reply"]


def test_parse_metadata_no_escalate_meta_returns_none():
    """Tag absent → escalate_meta is None, reply unchanged."""
    raw = "I can help with that. Our hours are 9-5 EST."
    result = parse_metadata(raw)

    assert result["escalate_meta"] is None
    assert result["sales_meta"] is None
    assert result["reply"] == raw


def test_parse_metadata_malformed_escalate_meta_strips_tag():
    """Tag present but JSON unparseable → reply still cleaned, meta is None.

    Defence against a model that emits ``ESCALATE_META:{not json`` — we must
    never leak the literal "ESCALATE_META:" string to the customer.
    """
    raw = (
        "Looking into that for you. ESCALATE\n"
        'ESCALATE_META:{not valid json'
    )
    result = parse_metadata(raw)

    assert result["escalate_meta"] is None
    assert "ESCALATE_META" not in result["reply"]


def test_parse_metadata_escalate_meta_before_sales_meta_in_wire_order():
    """Order on the wire shouldn't matter — extraction is by prefix scan."""
    raw = (
        "Connecting you now. ESCALATE\n"
        'ESCALATE_META:{"reason":"urgency"}\n'
        'SALES_META:{"buying_signal":3,"intent":"pricing_inquiry","action":"offer_demo"}\n'
        'LANG:en'
    )
    result = parse_metadata(raw)

    assert result["escalate_meta"] == {"reason": "urgency"}
    assert result["sales_meta"]["action"] == "offer_demo"
    assert result["detected_language"] == "en"
    assert "ESCALATE_META" not in result["reply"]
    assert "SALES_META" not in result["reply"]


# ── build_system_prompt: custom_instructions injection ────────────────────────

def _make_bot_config(custom_instructions=None, agent_name="Aria", business_name="Acme"):
    """Build a bot_config stub for prompt-composition tests.

    SimpleNamespace mirrors the SQLAlchemy ORM row's attribute-access shape
    without dragging in the DB engine — build_system_prompt() only does
    getattr(bot_config, ...) so a namespace works identically.
    """
    return SimpleNamespace(
        agent_name=agent_name,
        business_name=business_name,
        custom_instructions=custom_instructions,
    )


def test_build_system_prompt_includes_custom_instructions_when_set():
    """custom_instructions text appears AFTER the platform rules + FAQ."""
    cfg = _make_bot_config(
        custom_instructions="Always mention our 30-day free trial when discussing pricing."
    )
    prompt = build_system_prompt(cfg, faqs=[])

    assert "ADDITIONAL INSTRUCTIONS FROM THE BUSINESS:" in prompt
    assert "30-day free trial" in prompt
    # Reminder that platform rules win on conflict must be present.
    assert "do NOT override" in prompt
    # Custom block sits AFTER the escalation rules — recency-bias defence.
    assert prompt.index("ESCALATION RULES:") < prompt.index("ADDITIONAL INSTRUCTIONS FROM THE BUSINESS:")


def test_build_system_prompt_omits_block_when_custom_instructions_blank():
    """None / empty / whitespace-only → no block emitted at all."""
    for blank in (None, "", "   ", "\n\n"):
        cfg = _make_bot_config(custom_instructions=blank)
        prompt = build_system_prompt(cfg, faqs=[])
        assert "ADDITIONAL INSTRUCTIONS FROM THE BUSINESS:" not in prompt, (
            f"blank value {blank!r} should produce no custom-instructions block"
        )


def test_build_system_prompt_includes_internal_reasoning_at_top():
    """INTERNAL REASONING block must precede the identity / FAQ blocks."""
    cfg = _make_bot_config()
    prompt = build_system_prompt(cfg, faqs=[])

    assert "INTERNAL REASONING" in prompt
    # Reasoning block must come BEFORE identity envelopes — that's the
    # whole point of "Claude must reason before reading FAQs / replying".
    assert prompt.index("INTERNAL REASONING") < prompt.index("<agent_name>")
    assert prompt.index("INTERNAL REASONING") < prompt.index("ESCALATION RULES:")


def test_build_system_prompt_includes_escalation_rules_with_meta_tag_instruction():
    """ESCALATE_META instruction must appear alongside the ESCALATE keyword."""
    cfg = _make_bot_config()
    prompt = build_system_prompt(cfg, faqs=[])

    assert "ESCALATION RULES:" in prompt
    assert "ESCALATE_META:" in prompt
    # The six canonical reasons must all be listed in the prompt — the
    # router validates against this exact set.
    for reason in (
        "explicit_request",
        "frustration",
        "urgency",
        "sensitive_topic",
        "unresolved_loop",
        "no_faq_answer",
    ):
        assert reason in prompt


# ── _sanitize_custom_instructions ─────────────────────────────────────────────

def test_sanitize_custom_instructions_strips_control_chars():
    """Null bytes / control chars must be stripped — same defence as identity sanitizer."""
    dirty = "Be friendly.\x00\x07\x1f Be brief."
    cleaned = _sanitize_custom_instructions(dirty)
    assert "\x00" not in cleaned
    assert "\x07" not in cleaned
    assert "\x1f" not in cleaned
    assert "Be friendly." in cleaned
    assert "Be brief." in cleaned


def test_sanitize_custom_instructions_caps_length():
    """Over-length input must be truncated at max_len."""
    long_text = "x" * 5000
    cleaned = _sanitize_custom_instructions(long_text, max_len=2000)
    assert len(cleaned) <= 2000


def test_sanitize_custom_instructions_returns_empty_for_blank():
    """None / empty / whitespace must all collapse to empty string."""
    for blank in (None, "", "   \n  ", "\t"):
        assert _sanitize_custom_instructions(blank) == ""
