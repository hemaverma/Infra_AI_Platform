"""Tests for the email ingest executor."""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from workflow.executors import ingest as ingest_module
from workflow.messages import EmailDoc


def test_given_wildcard_env_when_allowed_extensions_then_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("EMAIL_ALLOWED_ATTACHMENT_EXTENSIONS", "*")

    # Act
    result = ingest_module._allowed_extensions()

    # Assert
    assert result is None


def test_given_mixed_attachment_types_when_filter_attachments_then_keeps_allowed_extensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("EMAIL_ALLOWED_ATTACHMENT_EXTENSIONS", "csv")

    # Act
    result = ingest_module._filter_attachments(["circuits.csv", "notes.CSV", "diagram.pdf"])

    # Assert
    assert result == ["circuits.csv", "notes.CSV"]


def test_given_iso_timestamp_when_parse_received_at_then_returns_datetime() -> None:
    # Act
    result = ingest_module._parse_received_at("2026-05-07T16:49:51Z")

    # Assert
    assert result == datetime(2026, 5, 7, 16, 49, 51, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_given_blob_payload_when_ingest_then_emits_email_doc_with_blob_paths() -> None:
    # Arrange
    fake_ctx = MagicMock()
    fake_ctx.send_message = AsyncMock()
    executor = ingest_module.EmailIngestExecutor()
    download_email_json = MagicMock(
        return_value={
            "subject": "Vendor Maintenance Notification - Change Request CR-0001",
            "senderEmail": "noreply@vendor.example",
            "body": "Body text",
            "attachments": ["circuits.csv", "ignore.pdf"],
        }
    )
    build_attachment_blob_paths = MagicMock(
        return_value=[
            "next-communicator-08dd4a3e-5b07-4e1a-9b3f-1c6d2e8f9a01/attachments/circuits.csv"
        ]
    )

    payload = {
        "workflowInstanceId": "next-communicator-08dd4a3e-5b07-4e1a-9b3f-1c6d2e8f9a01",
        "internetMessageId": "<LOGIC_APP_INTERNET_MESSAGE_ID>@vendor.example",
        "receivedAt": "2026-05-07T16:49:51Z",
        "storagePrefix": "next-communicator-08dd4a3e-5b07-4e1a-9b3f-1c6d2e8f9a01",
    }

    with patch.dict(os.environ, {"EMAIL_ALLOWED_ATTACHMENT_EXTENSIONS": "csv"}, clear=False):
        with patch.object(ingest_module, "download_email_json", download_email_json):
            with patch.object(ingest_module, "build_attachment_blob_paths", build_attachment_blob_paths):
                # Act
                await executor.ingest(payload, fake_ctx)

    # Assert
    download_email_json.assert_called_once_with(
        "next-communicator-08dd4a3e-5b07-4e1a-9b3f-1c6d2e8f9a01"
    )
    build_attachment_blob_paths.assert_called_once_with(
        ["circuits.csv"],
        "next-communicator-08dd4a3e-5b07-4e1a-9b3f-1c6d2e8f9a01",
    )
    fake_ctx.set_state.assert_has_calls([
        call(
            "workflow_instance_id",
            "next-communicator-08dd4a3e-5b07-4e1a-9b3f-1c6d2e8f9a01",
        ),
        call(
            "email_doc",
            {
                "workflow_instance_id": "next-communicator-08dd4a3e-5b07-4e1a-9b3f-1c6d2e8f9a01",
                "internet_message_id": "<LOGIC_APP_INTERNET_MESSAGE_ID>@vendor.example",
                "received_at": "2026-05-07T16:49:51Z",
                "storage_prefix": "next-communicator-08dd4a3e-5b07-4e1a-9b3f-1c6d2e8f9a01",
                "subject": "Vendor Maintenance Notification - Change Request CR-0001",
                "sender": "noreply@vendor.example",
                "body": "Body text",
                "attachments": [
                    "next-communicator-08dd4a3e-5b07-4e1a-9b3f-1c6d2e8f9a01/attachments/circuits.csv",
                ],
            },
        ),
    ])
    fake_ctx.send_message.assert_awaited_once_with(
        EmailDoc(
            workflow_instance_id="next-communicator-08dd4a3e-5b07-4e1a-9b3f-1c6d2e8f9a01",
            internet_message_id="<LOGIC_APP_INTERNET_MESSAGE_ID>@vendor.example",
            received_at=datetime(2026, 5, 7, 16, 49, 51, tzinfo=timezone.utc),
            storage_prefix="next-communicator-08dd4a3e-5b07-4e1a-9b3f-1c6d2e8f9a01",
            subject="Vendor Maintenance Notification - Change Request CR-0001",
            sender="noreply@vendor.example",
            body="Body text",
            attachments=["next-communicator-08dd4a3e-5b07-4e1a-9b3f-1c6d2e8f9a01/attachments/circuits.csv"],
        )
    )


@pytest.mark.asyncio
async def test_given_blob_download_failure_when_ingest_then_propagates_error(
) -> None:
    # Arrange
    fake_ctx = MagicMock()
    fake_ctx.send_message = AsyncMock()
    executor = ingest_module.EmailIngestExecutor()
    download_email_json = MagicMock(side_effect=FileNotFoundError("email.json missing"))

    payload = {
        "workflowInstanceId": "next-communicator-08dd4a3e-5b07-4e1a-9b3f-1c6d2e8f9a01",
        "internetMessageId": "<LOGIC_APP_INTERNET_MESSAGE_ID>@vendor.example",
        "receivedAt": "2026-05-07T16:49:51Z",
        "storagePrefix": "next-communicator-08dd4a3e-5b07-4e1a-9b3f-1c6d2e8f9a01",
    }

    with patch.object(ingest_module, "download_email_json", download_email_json):
        # Act & Assert
        with pytest.raises(FileNotFoundError, match="email.json missing"):
            await executor.ingest(payload, fake_ctx)

    download_email_json.assert_called_once_with(
        "next-communicator-08dd4a3e-5b07-4e1a-9b3f-1c6d2e8f9a01"
    )
    fake_ctx.send_message.assert_not_called()
