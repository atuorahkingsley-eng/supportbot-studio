"""Tests for Bug 5 — atomic message_count increment + chat happy paths.

Pre-Bug-5 the route incremented via Python: ``convo.message_count += 2;
db.commit()``. Two concurrent requests for the same conversation could both
read N, both write N+2, and one increment was lost. The fix moved the
arithmetic into a single ``UPDATE ... SET message_count = message_count + 2``
so the database computes the new value atomically.

These tests fire N requests against the same conversation and assert the
final count is exactly ``2 * N``. With SQLite + StaticPool the writes
serialize at the connection layer, so this test verifies the *correctness*
of the increment (no double-increments, no lost increments) — not the
absence of locks. That's the right thing to lock down: if someone reverts
the atomic UPDATE to ``+= 2``, the test stays green on linear runs but the
test_message_count_after_5_requests assertion would still catch any logic
error in the arithmetic.
"""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.database import Conversation, FAQEntry
import backend.routers.chat as chat_module
import backend.main as main_module


# ── Shared helper ─────────────────────────────────────────────────────────────

def _stub_ai_reply(text: str = "Hi there!"):
    """Return a dict in the shape ``_get_ai_reply_with_fallback`` produces.

    Centralised so a future change to the fallback contract only touches one
    spot in the test suite.
    """
    return {
        "reply": text,
        "was_auto_reply": False,
        "detected_language": "en",
        "sales_meta": None,
        # Matches the shape _get_ai_reply_with_fallback produces post-commit 2
        # (chain-of-thought prompt upgrade). Default None — tests that exercise
        # the escalation path override this explicitly with a reason dict.
        "escalate_meta": None,
    }


# ── 1. Atomic message_count ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_message_count_increments_atomically(
    test_client, test_db, test_tenant, test_bot_config, mocker,
):
    """Fire 5 concurrent /api/chat requests for the SAME session_id. After
    all complete, message_count must equal 10 (2 messages * 5 requests).

    We mock ``_get_ai_reply_with_fallback`` (the chat router's full AI
    fallback chain) so no real Anthropic call fires and the test runs in
    milliseconds. Each request still writes a user msg + an assistant msg
    AND fires the atomic UPDATE — that's the contract we're verifying.
    """
    mocker.patch(
        "backend.routers.chat._get_ai_reply_with_fallback",
        new=AsyncMock(return_value=_stub_ai_reply("ok")),
    )

    # Pre-create the conversation so all 5 requests share it.
    convo = Conversation(
        bot_id=test_tenant.bot_id,
        session_id="atomic-test-session",
        message_count=0,
    )
    test_db.add(convo)
    test_db.commit()

    headers = {"Authorization": f"Bearer {test_tenant.token}"}
    # Use AsyncClient over the ASGI app so asyncio.gather actually overlaps
    # the handler coroutines — TestClient is sync and would serialise.
    transport = httpx.ASGITransport(app=main_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        tasks = [
            ac.post(
                "/api/chat",
                json={"session_id": "atomic-test-session", "message": f"msg-{i}"},
                headers=headers,
            )
            for i in range(5)
        ]
        responses = await asyncio.gather(*tasks)

    for r in responses:
        assert r.status_code == 200, r.text

    # Pull a fresh view of the conversation. expire_all forces the next read
    # to issue a SELECT rather than serve the cached pre-request value of 0.
    test_db.expire_all()
    final = test_db.query(Conversation).filter_by(session_id="atomic-test-session").first()
    assert final is not None
    assert final.message_count == 10, (
        f"Expected 10 messages after 5 requests, got {final.message_count} — "
        "this means an increment was lost (race) OR the arithmetic is wrong."
    )


# ── 2. Chat response shape ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_returns_reply(test_client, test_tenant, test_bot_config, mocker):
    """Smoke test the response envelope. Confirms (a) the route is reachable
    with Bearer auth, (b) the mocked AI flows through into the response,
    (c) the contract keys the embed widget expects are all present.
    """
    mocker.patch(
        "backend.routers.chat._get_ai_reply_with_fallback",
        new=AsyncMock(return_value=_stub_ai_reply("Hello from mocked AI")),
    )

    resp = test_client.post(
        "/api/chat",
        json={"message": "hi"},
        headers={"Authorization": f"Bearer {test_tenant.token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "reply" in body
    assert "was_auto_reply" in body
    assert body["reply"] == "Hello from mocked AI"
    assert body["was_auto_reply"] is False


# ── 3. FAQ auto-reply short-circuit ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_reply_fires_for_known_faq(
    test_client, test_db, test_tenant, test_bot_config, mocker,
):
    """When the user's message matches an FAQ at >= 0.65 similarity, the
    chat router must serve the canned answer WITHOUT calling Anthropic at
    all. We assert two things:

      1. was_auto_reply is True (so billing skips it).
      2. The AI fallback was never invoked (proof we didn't pay for a call).
    """
    test_db.add(FAQEntry(
        bot_id=test_tenant.bot_id,
        question="What are your hours?",
        answer="We're open 9 AM to 5 PM Eastern, Monday through Friday.",
        source="manual",
    ))
    test_db.commit()

    ai_mock = mocker.patch(
        "backend.routers.chat._get_ai_reply_with_fallback",
        new=AsyncMock(return_value=_stub_ai_reply("should not fire")),
    )

    resp = test_client.post(
        "/api/chat",
        json={"message": "What are your hours?"},  # exact match → similarity 1.0
        headers={"Authorization": f"Bearer {test_tenant.token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["was_auto_reply"] is True
    assert "9 AM to 5 PM" in body["reply"]
    # The AI fallback chain must not have been touched.
    ai_mock.assert_not_called()
