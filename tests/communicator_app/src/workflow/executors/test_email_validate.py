"""Tests for the email validate executor."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from workflow.executors.email_validate import EmailValidateExecutor
from workflow.messages import EmailDoc, RejectedEmail, ValidatedEmail


def _sample_doc(*, sender: str = "noc@vendor.example") -> EmailDoc:
    return EmailDoc(
        workflow_instance_id="wf-email-validate",
        internet_message_id="msg-email-validate",
        received_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        storage_prefix="wf-email-validate",
        subject="Vendor maintenance notice",
        sender=sender,
        body="Body text",
        attachments=["wf-email-validate/attachments/circuits.csv"],
    )


@pytest.mark.asyncio
async def test_given_allowlisted_sender_when_validate_then_sends_validated_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("EMAIL_ALLOWED_SENDER_DOMAINS", "vendor.example")
    executor = EmailValidateExecutor()
    fake_ctx = MagicMock()
    fake_ctx.send_message = AsyncMock()
    fake_ctx.yield_output = AsyncMock()
    doc = _sample_doc(sender="NOC@VENDOR.EXAMPLE")

    # Act
    await executor.validate(doc, fake_ctx)

    # Assert
    fake_ctx.yield_output.assert_not_called()
    fake_ctx.send_message.assert_awaited_once()
    sent = fake_ctx.send_message.await_args.args[0]
    assert isinstance(sent, ValidatedEmail)
    assert sent.sender == "NOC@VENDOR.EXAMPLE"
    assert sent.notes["validation"]["sender_domain"] == "vendor.example"
    assert sent.notes["validation"]["allowlist_source"] == "env:EMAIL_ALLOWED_SENDER_DOMAINS"
    fake_ctx.set_state.assert_called_once_with(
        "validated_email",
        {
            "workflow_instance_id": "wf-email-validate",
            "internet_message_id": "msg-email-validate",
            "received_at": "2026-06-01T12:00:00Z",
            "storage_prefix": "wf-email-validate",
            "subject": "Vendor maintenance notice",
            "sender": "NOC@VENDOR.EXAMPLE",
            "body": "Body text",
            "attachments": ["wf-email-validate/attachments/circuits.csv"],
            "notes": {
                "validation": {
                    "sender_domain": "vendor.example",
                    "allowlist_source": "env:EMAIL_ALLOWED_SENDER_DOMAINS",
                }
            },
        },
    )


@pytest.mark.asyncio
async def test_given_non_allowlisted_sender_when_validate_then_sends_rejected_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("EMAIL_ALLOWED_SENDER_DOMAINS", "vendor.example")
    executor = EmailValidateExecutor()
    fake_ctx = MagicMock()
    fake_ctx.send_message = AsyncMock()
    fake_ctx.yield_output = AsyncMock()
    doc = _sample_doc(sender="noc@other.example")

    # Act
    await executor.validate(doc, fake_ctx)

    # Assert
    fake_ctx.yield_output.assert_not_called()
    fake_ctx.send_message.assert_awaited_once()
    sent = fake_ctx.send_message.await_args.args[0]
    assert isinstance(sent, RejectedEmail)
    assert sent.reason == "sender_not_allowlisted"
    assert sent.sender == "noc@other.example"
    assert sent.workflow_instance_id == "wf-email-validate"
    fake_ctx.set_state.assert_called_once_with(
        "rejected_email",
        {
            "workflow_instance_id": "wf-email-validate",
            "internet_message_id": "msg-email-validate",
            "received_at": "2026-06-01T12:00:00Z",
            "subject": "Vendor maintenance notice",
            "sender": "noc@other.example",
            "reason": "sender_not_allowlisted",
        },
    )


@pytest.mark.asyncio
async def test_given_wildcard_allowlist_when_validate_then_allows_sender(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("EMAIL_ALLOWED_SENDER_DOMAINS", "*")
    executor = EmailValidateExecutor()
    fake_ctx = MagicMock()
    fake_ctx.send_message = AsyncMock()
    fake_ctx.yield_output = AsyncMock()
    doc = _sample_doc(sender="noc@unknown.example")

    # Act
    await executor.validate(doc, fake_ctx)

    # Assert
    fake_ctx.yield_output.assert_not_called()
    fake_ctx.send_message.assert_awaited_once()
    sent = fake_ctx.send_message.await_args.args[0]
    assert isinstance(sent, ValidatedEmail)
    assert sent.notes["validation"]["sender_domain"] == "unknown.example"
    fake_ctx.set_state.assert_called_once()
    assert fake_ctx.set_state.call_args.args[0] == "validated_email"


@pytest.mark.asyncio
async def test_given_malformed_sender_when_allowlist_configured_then_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("EMAIL_ALLOWED_SENDER_DOMAINS", "vendor.example")
    executor = EmailValidateExecutor()
    fake_ctx = MagicMock()
    fake_ctx.send_message = AsyncMock()
    fake_ctx.yield_output = AsyncMock()
    doc = _sample_doc(sender="not-an-email")

    # Act
    await executor.validate(doc, fake_ctx)

    # Assert
    fake_ctx.yield_output.assert_not_called()
    fake_ctx.send_message.assert_awaited_once()
    sent = fake_ctx.send_message.await_args.args[0]
    assert isinstance(sent, RejectedEmail)
    assert sent.reason == "sender_not_allowlisted"
    assert sent.sender == "not-an-email"
    fake_ctx.set_state.assert_called_once()
    assert fake_ctx.set_state.call_args.args[0] == "rejected_email"


@pytest.mark.asyncio
async def test_given_allowlist_env_unset_when_validate_then_defaults_to_allow_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.delenv("EMAIL_ALLOWED_SENDER_DOMAINS", raising=False)
    executor = EmailValidateExecutor()
    fake_ctx = MagicMock()
    fake_ctx.send_message = AsyncMock()
    fake_ctx.yield_output = AsyncMock()
    doc = _sample_doc(sender="noc@default-allowed.example")

    # Act
    await executor.validate(doc, fake_ctx)

    # Assert
    fake_ctx.yield_output.assert_not_called()
    fake_ctx.send_message.assert_awaited_once()
    fake_ctx.set_state.assert_called_once()
    assert fake_ctx.set_state.call_args.args[0] == "validated_email"
