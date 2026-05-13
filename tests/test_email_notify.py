"""Tests for Zoho SMTP escalation email delivery.

Each test mocks ``smtplib.SMTP_SSL`` so no real network calls are made.
"""
import os
import asyncio
from unittest.mock import ANY, patch, MagicMock

import pytest

import backend.services.email_notify as email_mod
from backend.config import settings
from backend.services.email_notify import send_escalation_email


def _reset_probe_globals():
    email_mod._smtp_port = None
    email_mod._smtp_use_ssl = True


@pytest.mark.asyncio
async def test_send_escalation_email_skips_when_creds_missing():
    """When SMTP credentials are not configured, the function returns False
    without instantiating SMTP_SSL."""
    settings.zoho_smtp_user = ""
    settings.zoho_smtp_password = ""

    with patch("smtplib.SMTP_SSL") as mock:
        result = await send_escalation_email(
            to_email="test@example.com",
            bot_name="Test Bot",
            visitor_message="I need help",
            session_id="sess_001",
        )

    assert result is False
    mock.assert_not_called()


@pytest.mark.asyncio
async def test_send_escalation_email_uses_ssl_on_configured_port():
    """When credentials are set, SMTP_SSL is called with the configured host
    and port, then login and sendmail are invoked with the right user."""
    settings.zoho_smtp_user = "smtp-user@example.com"
    settings.zoho_smtp_password = "smtp-password"
    settings.zoho_smtp_host = "smtp.zoho.com"
    settings.zoho_smtp_port = 465

    with patch("smtplib.SMTP_SSL") as mock:
        mock_instance = MagicMock()
        mock.return_value.__enter__.return_value = mock_instance

        result = await send_escalation_email(
            to_email="admin@example.com",
            bot_name="Demo Bot",
            visitor_message="Help me",
            session_id="sess_002",
            contact_name="John Doe",
            contact_email="john@example.com",
            contact_phone="+234 800 000 0000",
        )

    assert result is True
    mock.assert_called_once_with("smtp.zoho.com", 465, context=ANY)
    mock_instance.login.assert_called_once_with(
        "smtp-user@example.com", "smtp-password"
    )
    mock_instance.sendmail.assert_called_once()
    args, _ = mock_instance.sendmail.call_args
    assert args[0] == "smtp-user@example.com"  # From
    assert args[1] == "admin@example.com"       # To


# ── Startup probe tests ───────────────────────────────────────────────────────

def test_probe_uses_preferred_port_when_reachable():
    """Preferred port reachable -> cache pins to it.
    Given preferred=465, probe succeeds on first try.
    """
    _reset_probe_globals()
    settings.zoho_smtp_user = "test@zoho.com"
    settings.zoho_smtp_password = "testpass"
    settings.zoho_smtp_host = "smtp.zoho.com"
    settings.zoho_smtp_port = 465

    with patch("socket.create_connection") as mock_conn:
        mock_conn.return_value.__enter__ = lambda s: s
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)

        email_mod.configure_smtp_at_startup()

    assert email_mod._smtp_port == 465
    assert email_mod._smtp_use_ssl is True
    assert mock_conn.call_count == 1
    assert mock_conn.call_args[0][0] == ("smtp.zoho.com", 465)


def test_probe_falls_back_when_preferred_blocked():
    """Preferred=587 blocked -> falls back to 465.
    First probe (587) raises OSError. Second probe (465) succeeds.
    """
    _reset_probe_globals()
    settings.zoho_smtp_user = "test@zoho.com"
    settings.zoho_smtp_password = "testpass"
    settings.zoho_smtp_host = "smtp.zoho.com"
    settings.zoho_smtp_port = 587

    def side_effect(address, timeout=3.0):
        host, port = address
        if port == 587:
            raise OSError("Connection refused")
        return MagicMock(
            __enter__=lambda s: s,
            __exit__=MagicMock(return_value=False),
        )

    with patch("socket.create_connection", side_effect=side_effect):
        email_mod.configure_smtp_at_startup()

    assert email_mod._smtp_port == 465
    assert email_mod._smtp_use_ssl is True


def test_probe_skipped_when_credentials_missing():
    """No credentials -> probe never runs.
    socket.create_connection should never be called.
    """
    _reset_probe_globals()
    settings.zoho_smtp_user = ""
    settings.zoho_smtp_password = ""

    with patch("socket.create_connection") as mock_conn:
        email_mod.configure_smtp_at_startup()

    mock_conn.assert_not_called()
    assert email_mod._smtp_port is None

