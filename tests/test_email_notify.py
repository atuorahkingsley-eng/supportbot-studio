"""Tests for Resend HTTPS escalation email delivery.

Each test mocks ``httpx.AsyncClient`` so no real network calls are made.
The transport mock returns a ``MagicMock`` shaped like ``httpx.Response``;
tests assert on the request shape (URL, auth header, JSON payload) and
the function's True/False return contract.

Pre-migration these tests covered ``smtplib.SMTP_SSL`` and a startup probe.
Both code paths are gone — the new path is a single HTTPS POST.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.config import settings
from backend.services.email_notify import send_escalation_email


def _make_response(status_code: int = 200, json_body: dict | None = None, text: str = "") -> MagicMock:
    """Build a ``httpx.Response``-shaped mock.

    Returning a real ``httpx.Response`` would require constructing a Request
    too, which is needless ceremony for a unit test. A MagicMock with the
    attributes the code under test reads is enough.
    """
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_body if json_body is not None else {}
    return resp


def _patch_async_client(response_mock: MagicMock) -> patch:
    """Patch ``httpx.AsyncClient`` so ``async with httpx.AsyncClient(...) as client``
    yields a stub whose ``.post`` returns ``response_mock``.

    Returns the unstarted ``patch`` so each test owns its own enter/exit
    lifecycle. Async-context-manager support is wired manually because
    ``MagicMock`` doesn't auto-magic ``__aenter__`` / ``__aexit__``.
    """
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=response_mock)

    async_cm = MagicMock()
    async_cm.__aenter__ = AsyncMock(return_value=mock_client)
    async_cm.__aexit__ = AsyncMock(return_value=False)

    return patch("backend.services.email_notify.httpx.AsyncClient", return_value=async_cm)


def _configure_resend():
    """Set settings so the function passes its pre-flight credential checks."""
    settings.resend_api_key = "re_test_key_abc123"
    settings.resend_from_email = "SupportBot <alerts@example.com>"


@pytest.mark.asyncio
async def test_returns_false_when_api_key_missing():
    """No API key configured -> function returns False without making an HTTP call.

    Pre-flight gate prevents the function from ever hitting the network with
    an empty Authorization header (which would be a 401 and waste a round-trip).
    """
    settings.resend_api_key = ""
    settings.resend_from_email = "SupportBot <alerts@example.com>"

    with patch("backend.services.email_notify.httpx.AsyncClient") as mock_client:
        result = await send_escalation_email(
            to_email="admin@example.com",
            bot_name="Test Bot",
            visitor_message="I need help",
            session_id="sess_001",
        )

    assert result is False
    mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_returns_false_when_from_email_missing():
    """No from-address configured -> function returns False without making an
    HTTP call. Pre-flight gate prevents shipping a malformed payload to Resend."""
    settings.resend_api_key = "re_test_key"
    settings.resend_from_email = ""

    with patch("backend.services.email_notify.httpx.AsyncClient") as mock_client:
        result = await send_escalation_email(
            to_email="admin@example.com",
            bot_name="Test Bot",
            visitor_message="I need help",
            session_id="sess_001",
        )

    assert result is False
    mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_posts_to_resend_with_bearer_auth_and_correct_payload():
    """Happy path: function POSTs to Resend with the right URL, headers, and
    JSON payload, then returns True on a 200 response.

    The shape of the payload is part of the API contract — if a future edit
    breaks it (e.g. wrong key name like ``"From"`` instead of ``"from"``,
    or moving ``to`` to a string instead of a list), this test catches it.
    """
    _configure_resend()
    response_mock = _make_response(status_code=200, json_body={"id": "abc-123"})

    with _patch_async_client(response_mock) as mock_cm:
        result = await send_escalation_email(
            to_email="admin@example.com",
            bot_name="Demo Bot",
            visitor_message="Please help me",
            session_id="sess_002",
            contact_name="John Doe",
            contact_email="john@example.com",
            contact_phone="+234 800 000 0000",
        )

    assert result is True

    # One POST, to the right URL.
    mock_client_instance = mock_cm.return_value.__aenter__.return_value
    mock_client_instance.post.assert_awaited_once()
    call_args = mock_client_instance.post.call_args
    assert call_args.args[0] == "https://api.resend.com/emails"

    # Bearer-token auth header.
    headers = call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer re_test_key_abc123"
    assert headers["Content-Type"] == "application/json"

    # Payload shape: from / to (list) / subject / text / html.
    payload = call_args.kwargs["json"]
    assert payload["from"] == "SupportBot <alerts@example.com>"
    assert payload["to"] == ["admin@example.com"]
    assert "Demo Bot" in payload["subject"]
    assert "Please help me" in payload["text"]
    assert "John Doe" in payload["text"]
    assert "john@example.com" in payload["text"]
    assert "+234 800 000 0000" in payload["text"]
    assert "<html>" in payload["html"]


@pytest.mark.asyncio
async def test_returns_true_on_202_accepted():
    """Resend documents 200 as the success status, but the function accepts
    any 2xx (including 202) to be defensive against API behaviour changes."""
    _configure_resend()
    response_mock = _make_response(status_code=202, json_body={"id": "xyz-789"})

    with _patch_async_client(response_mock):
        result = await send_escalation_email(
            to_email="admin@example.com",
            bot_name="Bot",
            visitor_message="msg",
            session_id="s",
        )

    assert result is True


@pytest.mark.asyncio
async def test_returns_false_on_4xx():
    """Bad request (e.g. unverified sender domain -> 403, malformed payload ->
    422) returns False so the caller falls back to the PendingEscalation retry
    queue."""
    _configure_resend()
    response_mock = _make_response(
        status_code=403,
        text='{"message":"The domain is not verified."}',
    )

    with _patch_async_client(response_mock):
        result = await send_escalation_email(
            to_email="admin@example.com",
            bot_name="Bot",
            visitor_message="msg",
            session_id="s",
        )

    assert result is False


@pytest.mark.asyncio
async def test_returns_false_on_5xx():
    """Resend outage / transient server error returns False — caller's retry
    queue handles re-delivery on the next scheduler tick."""
    _configure_resend()
    response_mock = _make_response(status_code=503, text="Service unavailable")

    with _patch_async_client(response_mock):
        result = await send_escalation_email(
            to_email="admin@example.com",
            bot_name="Bot",
            visitor_message="msg",
            session_id="s",
        )

    assert result is False


@pytest.mark.asyncio
async def test_returns_false_on_network_error():
    """Network error (timeout, DNS failure, TLS handshake) returns False
    rather than raising — callers treat this function as fire-and-forget."""
    _configure_resend()

    async_cm = MagicMock()
    async_cm.__aenter__ = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    async_cm.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "backend.services.email_notify.httpx.AsyncClient",
        return_value=async_cm,
    ):
        result = await send_escalation_email(
            to_email="admin@example.com",
            bot_name="Bot",
            visitor_message="msg",
            session_id="s",
        )

    assert result is False


@pytest.mark.asyncio
async def test_omits_contact_block_when_no_details_provided():
    """When no contact details are captured, the body still renders cleanly
    with a fallback note — never a stray ``None`` or empty line."""
    _configure_resend()
    response_mock = _make_response(status_code=200, json_body={"id": "id"})

    with _patch_async_client(response_mock) as mock_cm:
        await send_escalation_email(
            to_email="admin@example.com",
            bot_name="Bot",
            visitor_message="msg",
            session_id="s",
        )

    mock_client_instance = mock_cm.return_value.__aenter__.return_value
    payload = mock_client_instance.post.call_args.kwargs["json"]
    assert "No contact details provided" in payload["text"]
    assert "No contact details provided" in payload["html"]
    assert "None" not in payload["text"]
