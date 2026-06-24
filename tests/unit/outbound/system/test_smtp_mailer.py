from datetime import UTC, datetime
from email.message import EmailMessage
from unittest.mock import AsyncMock, patch

import pytest

from app.domain.value_objects.email import Email
from app.outbound.adapters.system.smtp_mailer import SmtpMailer

_TO = Email("user@example.com")
_TOKEN = "secret-reset-token-123"
_EXPIRES_AT = datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC)


def _mailer(**overrides: object) -> SmtpMailer:
    params: dict[str, object] = {
        "host": "smtp.example.com",
        "port": 587,
        "username": "relay-user",
        "password": "relay-pass",
        "from_email": "noreply@yomochi.app",
        "use_starttls": True,
        "timeout": 10.0,
    }
    params.update(overrides)
    return SmtpMailer(**params)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_send_password_reset_calls_aiosmtplib_with_expected_kwargs() -> None:
    with patch(
        "app.outbound.adapters.system.smtp_mailer.aiosmtplib.send",
        new_callable=AsyncMock,
    ) as mock_send:
        await _mailer().send_password_reset(_TO, _TOKEN, _EXPIRES_AT)

    mock_send.assert_awaited_once()
    _, kwargs = mock_send.call_args
    assert kwargs["hostname"] == "smtp.example.com"
    assert kwargs["port"] == 587
    assert kwargs["start_tls"] is True
    assert kwargs["timeout"] == 10.0
    assert kwargs["username"] == "relay-user"
    assert kwargs["password"] == "relay-pass"


@pytest.mark.asyncio
async def test_send_password_reset_builds_correct_message() -> None:
    with patch(
        "app.outbound.adapters.system.smtp_mailer.aiosmtplib.send",
        new_callable=AsyncMock,
    ) as mock_send:
        await _mailer().send_password_reset(_TO, _TOKEN, _EXPIRES_AT)

    message = mock_send.call_args.args[0]
    assert isinstance(message, EmailMessage)
    assert message["From"] == "noreply@yomochi.app"
    assert message["To"] == "user@example.com"
    assert message["Subject"] == "Reset your Yomochi password"
    body = message.get_content()
    assert _TOKEN in body
    assert _EXPIRES_AT.isoformat() in body


@pytest.mark.asyncio
async def test_blank_credentials_passed_as_none() -> None:
    with patch(
        "app.outbound.adapters.system.smtp_mailer.aiosmtplib.send",
        new_callable=AsyncMock,
    ) as mock_send:
        await _mailer(username="", password="").send_password_reset(_TO, _TOKEN, _EXPIRES_AT)

    _, kwargs = mock_send.call_args
    assert kwargs["username"] is None
    assert kwargs["password"] is None


@pytest.mark.asyncio
async def test_password_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    with patch(
        "app.outbound.adapters.system.smtp_mailer.aiosmtplib.send",
        new_callable=AsyncMock,
    ):
        await _mailer().send_password_reset(_TO, _TOKEN, _EXPIRES_AT)

    rendered = caplog.text
    assert "relay-pass" not in rendered
    assert _TOKEN not in rendered


@pytest.mark.asyncio
async def test_send_failure_propagates() -> None:
    with (
        patch(
            "app.outbound.adapters.system.smtp_mailer.aiosmtplib.send",
            new_callable=AsyncMock,
            side_effect=RuntimeError("smtp down"),
        ),
        pytest.raises(RuntimeError, match="smtp down"),
    ):
        await _mailer().send_password_reset(_TO, _TOKEN, _EXPIRES_AT)
