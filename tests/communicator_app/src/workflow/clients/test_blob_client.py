"""Tests for blob storage helper functions."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workflow.clients import blob_client


def _build_blob_service_client(blob_mock: MagicMock) -> MagicMock:
    """Create a context-manager BlobServiceClient mock returning a blob mock."""
    service_client = MagicMock()
    service_client.__enter__.return_value = service_client
    service_client.__exit__.return_value = None
    service_client.get_blob_client.return_value = blob_mock
    return service_client


def test_given_prefixed_value_when_normalize_prefix_then_trims_surrounding_slashes() -> None:
    # Act
    result = blob_client._normalize_prefix("/vendor/workflow/")

    # Assert
    assert result == "vendor/workflow"


@pytest.mark.parametrize("filename", ["../circuits.csv", "nested/circuits.csv", ""])
def test_given_invalid_filename_when_safe_filename_then_raises_value_error(filename: str) -> None:
    # Act & Assert
    with pytest.raises(ValueError, match="simple file name"):
        blob_client._safe_filename(filename)


def test_given_email_blob_when_download_email_json_then_returns_parsed_payload(
    tmp_path: Path,
) -> None:
    # Arrange
    credential = MagicMock()
    stream = MagicMock()
    stream.chunks.return_value = [b'{"subject":"Hello","attachments":["circuits.csv"]}']
    blob = MagicMock()
    blob.download_blob.return_value = stream
    service_client = _build_blob_service_client(blob)

    with patch.dict(
        os.environ,
        {
            "EMAIL_BLOB_ACCOUNT_URL": "https://storage.example",
            "EMAIL_BLOB_CONTAINER": "email-staging",
        },
        clear=False,
    ):
        with patch.object(blob_client.tempfile, "gettempdir", return_value=str(tmp_path)):
            with patch.object(blob_client, "_credential", return_value=credential):
                with patch.object(blob_client, "BlobServiceClient", return_value=service_client):
                    # Act
                    result = blob_client.download_email_json("workflow-123")

    # Assert
    assert result == {"subject": "Hello", "attachments": ["circuits.csv"]}
    service_client.get_blob_client.assert_called_once_with(
        container="email-staging",
        blob="workflow-123/email.json",
    )
    credential.close.assert_called_once_with()


def test_given_missing_blob_account_url_when_download_email_json_then_raises_key_error() -> None:
    # Arrange
    with patch.dict(os.environ, {}, clear=True):
        # Act & Assert
        with pytest.raises(KeyError, match="EMAIL_BLOB_ACCOUNT_URL"):
            blob_client.download_email_json("workflow-123")


def test_given_json_payload_when_upload_json_artifact_then_uploads_blob() -> None:
    # Arrange
    credential = MagicMock()
    blob = MagicMock()
    service_client = _build_blob_service_client(blob)

    with patch.dict(
        os.environ,
        {
            "EMAIL_BLOB_ACCOUNT_URL": "https://storage.example",
            "EMAIL_BLOB_CONTAINER": "email-staging",
        },
        clear=False,
    ):
        with patch.object(blob_client, "_credential", return_value=credential):
            with patch.object(blob_client, "BlobServiceClient", return_value=service_client):
                # Act
                result = blob_client.upload_json_artifact(
                    "workflow-123",
                    "draft-reply.json",
                    {"subject": "Hello", "body": "Body text"},
                )

    # Assert
    assert result == "workflow-123/draft-reply.json"
    service_client.get_blob_client.assert_called_once_with(
        container="email-staging",
        blob="workflow-123/draft-reply.json",
    )
    upload_args, upload_kwargs = blob.upload_blob.call_args
    assert json.loads(upload_args[0].decode("utf-8")) == {"subject": "Hello", "body": "Body text"}
    assert upload_kwargs["overwrite"] is True
    assert upload_kwargs["content_settings"].content_type == "application/json; charset=utf-8"
    credential.close.assert_called_once_with()


def test_given_empty_storage_prefix_when_upload_json_artifact_then_skips_upload() -> None:
    # Act
    result = blob_client.upload_json_artifact("", "draft-reply.json", {"subject": "Hello"})

    # Assert
    assert result is None


def test_given_attachment_filenames_when_build_attachment_blob_paths_then_returns_blob_paths() -> None:
    # Act
    result = blob_client.build_attachment_blob_paths(["circuits.csv", "notes.csv"], "workflow-123")

    # Assert
    assert result == [
        "workflow-123/attachments/circuits.csv",
        "workflow-123/attachments/notes.csv",
    ]


def test_given_attachment_blob_paths_when_download_attachment_blobs_then_returns_local_paths(
    tmp_path: Path,
) -> None:
    # Arrange
    credential = MagicMock()
    stream = MagicMock()
    stream.chunks.side_effect = [[b"circuit,data\n"], [b"note,data\n"]]
    blob = MagicMock()
    blob.download_blob.return_value = stream
    service_client = _build_blob_service_client(blob)

    with patch.dict(
        os.environ,
        {
            "EMAIL_BLOB_ACCOUNT_URL": "https://storage.example",
            "EMAIL_BLOB_CONTAINER": "email-staging",
        },
        clear=False,
    ):
        with patch.object(blob_client.tempfile, "gettempdir", return_value=str(tmp_path)):
            with patch.object(blob_client, "_credential", return_value=credential):
                with patch.object(blob_client, "BlobServiceClient", return_value=service_client):
                    # Act
                    result = blob_client.download_attachment_blobs([
                        "workflow-123/attachments/circuits.csv",
                        "workflow-123/attachments/notes.csv",
                    ])

    # Assert
    assert result == [
        tmp_path / "vendor-email-staging" / "workflow-123" / "attachments" / "circuits.csv",
        tmp_path / "vendor-email-staging" / "workflow-123" / "attachments" / "notes.csv",
    ]
    assert service_client.get_blob_client.call_args_list == [
        ((), {"container": "email-staging", "blob": "workflow-123/attachments/circuits.csv"}),
        ((), {"container": "email-staging", "blob": "workflow-123/attachments/notes.csv"}),
    ]
    credential.close.assert_called_once_with()


def test_given_missing_attachment_blob_when_download_attachment_blobs_then_raises_resource_not_found(
    tmp_path: Path,
) -> None:
    # Arrange
    credential = MagicMock()
    blob = MagicMock()
    blob.download_blob.side_effect = blob_client.ResourceNotFoundError("missing")
    service_client = _build_blob_service_client(blob)

    with patch.dict(
        os.environ,
        {
            "EMAIL_BLOB_ACCOUNT_URL": "https://storage.example",
            "EMAIL_BLOB_CONTAINER": "email-staging",
        },
        clear=False,
    ):
        with patch.object(blob_client.tempfile, "gettempdir", return_value=str(tmp_path)):
            with patch.object(blob_client, "_credential", return_value=credential):
                with patch.object(blob_client, "BlobServiceClient", return_value=service_client):
                    # Act & Assert
                    with pytest.raises(blob_client.ResourceNotFoundError):
                        blob_client.download_attachment_blobs(["workflow-123/attachments/circuits.csv"])

    service_client.get_blob_client.assert_called_once_with(
        container="email-staging",
        blob="workflow-123/attachments/circuits.csv",
    )
    credential.close.assert_called_once_with()
