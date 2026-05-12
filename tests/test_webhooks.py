"""Tests for HMAC webhook-signature plumbing and outbound dispatch.

The webhook sender at ``backend/services/webhook_sender.py`` signs each
outbound body with HMAC-SHA256 using the per-tenant secret, encoding the
JSON once into bytes so both sender and receiver hash exactly the same
input. Tests pin three contracts:

  1. ``_sign_payload`` produces a verifiable ``sha256=<hex>`` string
     that round-trips through ``hmac.compare_digest`` with the same
     secret + body bytes.
  2. Any drift — wrong body, wrong secret, even whitespace differences —
     breaks verification (proves the body is hashed BYTE-for-byte, not
     re-encoded by the receiver).
  3. The ``lead_captured`` flow at ``POST /api/sales/leads/capture``
     actually emits the signed POST: ``httpx.AsyncClient.post`` is
     called with a ``content=`` bytes body and an
     ``X-SupportBot-Signature: sha256=…`` header.

Nothing here hits a real receiver — ``httpx.AsyncClient.post`` is
mocked at the boundary, so the test exercises our code, not the
network.
"""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.database import WebhookConfig
from backend.services.webhook_sender import (
    SIGNATURE_HEADER,
    _sign_payload,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _expected_signature(body: bytes, secret: str) -> str:
    """Mirror of ``_sign_payload`` written from scratch so the test isn't
    just asserting that the function equals itself."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


# ── 1. Valid signature round-trips ────────────────────────────────────────────

def test_valid_signature_passes_verification():
    """Sign a body, then verify with the same secret + body. The verifier
    is the canonical idiom Stripe / GitHub docs ship: hmac.compare_digest
    over the hex digest. If this drifts, every receiver in the wild
    breaks."""
    secret = "shhh-its-a-secret"
    body = json.dumps({"event": "lead_captured", "id": 1}, separators=(",", ":")).encode("utf-8")

    signed = _sign_payload(body, secret)
    assert signed.startswith("sha256=")

    # Receiver-side verification, written the way docs tell integrators
    # to write it. compare_digest, not == — defends against timing attacks.
    received_digest = signed.split("=", 1)[1]
    expected_digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(received_digest, expected_digest)


# ── 2. Tampered body fails verification ───────────────────────────────────────

def test_invalid_signature_fails_verification():
    """Sign body A, then verify with body B. The digest MUST differ —
    this is the whole point of signing. If this ever passes, the secret
    isn't being mixed into the hash and the system is wide open."""
    secret = "shhh-its-a-secret"
    body_a = b'{"event":"lead_captured","id":1}'
    body_b = b'{"event":"lead_captured","id":2}'  # different ID

    sig_a = _sign_payload(body_a, secret)
    sig_b_expected = _expected_signature(body_b, secret)
    received_digest_a = sig_a.split("=", 1)[1]
    digest_b = sig_b_expected.split("=", 1)[1]

    assert not hmac.compare_digest(received_digest_a, digest_b)


# ── 3. Wrong secret fails verification ────────────────────────────────────────

def test_wrong_secret_fails_verification():
    """Same body, different secret → different signature. Catches the
    tenant-isolation failure mode: if WebhookConfig.secret is ignored
    and the signer falls back to a global key, all tenants would share
    the same digest for the same body — and a leak of one secret would
    impersonate all tenants."""
    body = b'{"event":"lead_captured"}'

    sig_correct = _sign_payload(body, "tenant-A-secret")
    sig_wrong = _sign_payload(body, "tenant-B-secret")

    assert sig_correct != sig_wrong
    # Verify both digests separately so a passing assertion above can't be
    # a false negative from the strings happening to share a prefix.
    d1 = sig_correct.split("=", 1)[1]
    d2 = sig_wrong.split("=", 1)[1]
    assert not hmac.compare_digest(d1, d2)


# ── 4. Whitespace sensitivity ─────────────────────────────────────────────────

def test_signature_is_whitespace_sensitive():
    """``_post_signed_json`` uses ``separators=(",", ":")`` so the JSON
    has NO whitespace between keys/values. Receivers must hash the raw
    body bytes they receive, NOT a re-serialised version — re-encoding
    with default separators inserts ``", "`` and ``": "`` and the digest
    drifts.

    This test pins the contract by signing two byte-equivalent payloads
    that DIFFER only in whitespace and asserting the signatures differ.
    """
    secret = "secret"
    compact = b'{"event":"lead_captured","id":1}'
    pretty = b'{"event": "lead_captured", "id": 1}'  # adds spaces — same JSON semantically

    sig_compact = _sign_payload(compact, secret)
    sig_pretty = _sign_payload(pretty, secret)

    assert sig_compact != sig_pretty, (
        "Whitespace in the body MUST change the signature — otherwise "
        "receivers that re-serialise before verifying will silently accept "
        "tampered payloads."
    )


# ── 5. End-to-end: lead capture fires a signed webhook ────────────────────────

@pytest.mark.asyncio
async def test_webhook_fires_on_lead_captured(
    test_client, test_db, test_tenant, auth_headers, mocker,
):
    """Wire up a custom_https webhook for the tenant, fire
    ``POST /api/sales/leads/capture``, and assert the outbound POST
    carries (a) bytes content, (b) a ``X-SupportBot-Signature: sha256=…``
    header signed with the tenant's secret over those exact bytes.

    The receiver itself is replaced with an AsyncMock returning a fake
    200 — so we're testing OUR signing path, not anyone's server. The
    AsyncMock is patched on ``httpx.AsyncClient.post`` so it intercepts
    every webhook the sender attempts in this test.
    """
    secret = "test-webhook-secret-12345"
    test_db.add(WebhookConfig(
        bot_id=test_tenant.bot_id,
        platform="custom_https",
        webhook_url="https://example.test/hook",
        enabled=True,
        notify_on="all",          # fan-out gate for lead_captured
        secret=secret,
    ))
    test_db.commit()

    # Mock the boundary: any httpx.AsyncClient.post call returns 200
    # without touching the network. capture the args so we can inspect
    # the actual signed body the sender emitted.
    fake_response = MagicMock()
    fake_response.status_code = 200
    post_mock = mocker.patch(
        "httpx.AsyncClient.post",
        new=AsyncMock(return_value=fake_response),
    )

    resp = test_client.post(
        "/api/sales/leads/capture",
        json={
            "email": "buyer@example.com",
            "name": "Buyer",
            "phone": "+15555550199",
            "interest": "Pro plan",
            "source": "chat_capture",
            "buying_signal_score": 4,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    # Exactly one webhook configured → exactly one outbound POST.
    assert post_mock.await_count == 1, (
        f"Expected 1 outbound webhook POST, got {post_mock.await_count}"
    )

    # Pull the call args. _post_signed_json calls
    #     client.post(url, content=body, headers=headers, timeout=...)
    call = post_mock.await_args
    sent_url = call.args[0] if call.args else call.kwargs.get("url")
    sent_body = call.kwargs.get("content")
    sent_headers = call.kwargs.get("headers", {})

    assert sent_url == "https://example.test/hook"
    assert isinstance(sent_body, bytes), (
        "Body must be bytes so signer + receiver hash the exact same input."
    )

    # Signature header present and correctly formed.
    assert SIGNATURE_HEADER in sent_headers
    assert sent_headers[SIGNATURE_HEADER].startswith("sha256=")

    # Now verify: re-sign the bytes we just observed with the tenant's
    # secret. The sender's header must match — that proves the secret
    # was sourced from THIS WebhookConfig row, not a global / wrong key.
    expected = _expected_signature(sent_body, secret)
    assert hmac.compare_digest(sent_headers[SIGNATURE_HEADER], expected), (
        "Signature in the outbound header does not match an HMAC-SHA256 of "
        "the body with the WebhookConfig.secret — the signer is using the "
        "wrong key or hashing the wrong bytes."
    )

    # And the body really IS the lead_captured envelope — not some
    # unrelated request that happened to fly through this mock.
    payload = json.loads(sent_body.decode("utf-8"))
    assert payload["event"] == "lead_captured"
    assert payload["event_type"] == "lead_captured"
    assert payload["bot_id"] == test_tenant.bot_id
    assert payload["data"]["contact"]["email"] == "buyer@example.com"
