"""Tests for the preprocess executor."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from workflow.executors import preprocess as preprocess_module
from workflow.messages import AttachmentContent, CleanEmail, ValidatedEmail


@pytest.mark.asyncio
async def test_given_blob_paths_when_preprocess_then_downloads_attachments_and_emits_clean_email() -> None:
    # Arrange
    fake_ctx = MagicMock()
    fake_ctx.send_message = AsyncMock()
    executor = preprocess_module.PreprocessExecutor()
    csv_path = Path("C:/temp/vendor-email-staging/workflow-123/attachments/circuits.csv")
    download_attachment_blobs = MagicMock(return_value=[csv_path])
    validated = ValidatedEmail(
        workflow_instance_id="workflow-123",
        internet_message_id="<LOGIC_APP_INTERNET_MESSAGE_ID>@vendor.example",
        received_at=datetime(2026, 5, 7, 16, 49, 51, tzinfo=timezone.utc),
        subject="Vendor Maintenance Notification - Change Request #CR-0001",
        sender="noreply@vendor.example",
        body="Body text",
        attachments=["workflow-123/attachments/circuits.csv"],
    )

    csv_text = "Circuit ID,Severity\nSYN-NYC-001,Switch to Protect\n"

    with (
        patch.object(preprocess_module, "download_attachment_blobs", download_attachment_blobs),
        patch.object(Path, "read_text", return_value=csv_text),
    ):
        # Act
        await executor.preprocess(validated, fake_ctx)

    # Assert
    download_attachment_blobs.assert_called_once_with(["workflow-123/attachments/circuits.csv"])
    fake_ctx.send_message.assert_awaited_once_with(
        CleanEmail(
            workflow_instance_id="workflow-123",
            internet_message_id="<LOGIC_APP_INTERNET_MESSAGE_ID>@vendor.example",
            received_at=datetime(2026, 5, 7, 16, 49, 51, tzinfo=timezone.utc),
            subject="Vendor Maintenance Notification - Change Request #CR-0001",
            sender="noreply@vendor.example",
            body="Body text",
            attachments=[
                AttachmentContent(
                    filename="circuits.csv",
                    content=csv_text,
                )
            ],
            notes={},
        )
    )


def test_given_html_body_when_clean_email_body_then_returns_sanitized_html() -> None:
    # Arrange
    html_body = (
        "<html><head><title>ignored</title><style>.hidden{display:none}</style></head>"
        "<body><div>Hello&nbsp;team,</div><div><b>Maintenance window</b> tonight.</div>"
        "<script>alert('ignore');</script><div>Thanks,<br>Network Ops</div></body></html>"
    )

    # Act
    result = preprocess_module._clean_email_body(html_body)

    # Assert
    assert result == "Hello team,\nMaintenance window tonight.\nThanks,\nNetwork Ops"


def test_given_heading_and_table_html_when_clean_email_body_then_preserves_table_structure() -> None:
    # Arrange
    html_body = (
        "<html><body><h2 class='headline'>Maintenance Summary</h2>"
        "<table style='width:100%'><tr><th scope='col'>Window</th><th>Owner</th></tr>"
        "<tr><td colspan='2' onclick='alert(1)'>Tonight</td></tr></table>"
        "<style>table{display:none}</style><script>console.log('ignore')</script></body></html>"
    )

    # Act
    result = preprocess_module._clean_email_body(html_body)

    # Assert
    assert result == (
        "<h2>Maintenance Summary</h2>"
        "<table><tr><th scope=\"col\">Window</th><th>Owner</th></tr>"
        "<tr><td colspan=\"2\">Tonight</td></tr></table>"
    )


def test_given_representative_vendor_email_html_when_clean_email_body_then_keeps_headings_and_tables() -> None:
    # Arrange
    html_body = (
        "<html><body><div><table bgcolor='#f0f0f0' style='border:solid #ccc 1px'><tbody>"
        "<tr><td colspan='2' bgcolor='#b35900'><h1><font color='white'>Vendor One</font></h1>"
        "<blockquote><font color='white'>Maintenance Notifications</font><br></blockquote></td></tr>"
        "<tr><td colspan='2'><div class='container-fluid'><b>Dates and Times</b> "
        "<small>(All times are local)</small>"
        "<table border='1' width='700'><tbody>"
        "<tr><td valign='top'>Customer</td><td valign='top'>OPERATOR</td></tr>"
        "<tr><td valign='top'>Planned Start</td><td valign='top'>05/08/2026 12:00AM EDT</td></tr>"
        "</tbody></table><br><b>Circuits:</b><table border='1' width='100%'><thead bgcolor='#ffffcc'>"
        "<tr><th>Customer</th><th>Impact</th></tr></thead><tbody>"
        "<tr><td>OPERATOR COMMUNICATIONS</td><td>Loss of Service</td></tr>"
        "</tbody></table></div></td></tr></tbody></table></div></body></html>"
    )

    # Act
    result = preprocess_module._clean_email_body(html_body)

    # Assert
    assert result == (
        "<table><tbody><tr><td colspan=\"2\"><h1>Vendor One</h1>Maintenance Notifications\n"
        "</td></tr><tr><td colspan=\"2\">Dates and Times (All times are local)"
        "<table><tbody><tr><td>Customer</td><td>OPERATOR</td></tr>"
        "<tr><td>Planned Start</td><td>05/08/2026 12:00AM EDT</td></tr></tbody></table>"
        "\nCircuits:<table><thead><tr><th>Customer</th><th>Impact</th></tr></thead><tbody>"
        "<tr><td>OPERATOR COMMUNICATIONS</td><td>Loss of Service</td></tr></tbody></table>"
        "\n</td></tr></tbody></table>"
    )


def test_given_breaks_and_list_html_when_clean_email_body_then_preserves_block_markup() -> None:
    # Arrange
    html_body = (
        "<html><body><div>Intro line<br>Follow-up line</div>"
        "<ul><li>First item</li><li>Second item</li></ul></body></html>"
    )

    # Act
    result = preprocess_module._clean_email_body(html_body)

    # Assert
    assert result == "Intro line\nFollow-up line\nFirst item\nSecond item"


def test_given_links_and_inline_markup_when_clean_email_body_then_keeps_safe_attributes_only() -> None:
    # Arrange
    html_body = (
        "<html><body><p class='copy'>Review the <a href='https://example.test/runbook' "
        "style='color:red' onclick='open()' target='_blank'>runbook</a> and "
        "<strong data-testid='emphasis'>notify</strong> the <span id='team'>on-call team</span>.</p></body></html>"
    )

    # Act
    result = preprocess_module._clean_email_body(html_body)

    # Assert
    assert result == "Review the runbook and notify the on-call team."


def test_given_presentational_and_noisy_tags_when_clean_email_body_then_unwraps_or_removes_them() -> None:
    # Arrange
    html_body = (
        "<html><body><font color='red'><h3>Maintenance Summary</h3></font>"
        "<p><span class='copy'>Review details</span><iframe src='about:blank'></iframe>"
        "<svg><circle></circle></svg></p></body></html>"
    )

    # Act
    result = preprocess_module._clean_email_body(html_body)

    # Assert
    assert result == "<h3>Maintenance Summary</h3>Review details"


def test_given_plain_text_body_when_clean_email_body_then_preserves_text() -> None:
    # Arrange
    body = "Circuit update &amp; next steps\r\n\r\nLine 2"

    # Act
    result = preprocess_module._clean_email_body(body)

    # Assert
    assert result == "Circuit update & next steps\n\nLine 2"


@pytest.mark.asyncio
async def test_given_attachment_download_failure_when_preprocess_then_propagates_error() -> None:
    # Arrange
    fake_ctx = MagicMock()
    fake_ctx.send_message = AsyncMock()
    executor = preprocess_module.PreprocessExecutor()
    download_attachment_blobs = MagicMock(side_effect=FileNotFoundError("attachment missing"))
    validated = ValidatedEmail(
        workflow_instance_id="workflow-123",
        internet_message_id="<LOGIC_APP_INTERNET_MESSAGE_ID>@vendor.example",
        received_at=datetime(2026, 5, 7, 16, 49, 51, tzinfo=timezone.utc),
        subject="subject",
        sender="noreply@vendor.example",
        body="Body text",
        attachments=["workflow-123/attachments/circuits.csv"],
    )

    with patch.object(preprocess_module, "download_attachment_blobs", download_attachment_blobs):
        # Act & Assert
        with pytest.raises(FileNotFoundError, match="attachment missing"):
            await executor.preprocess(validated, fake_ctx)

    fake_ctx.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_given_downloaded_csv_when_preprocess_then_reads_full_csv_contents() -> None:
    # Arrange
    fake_ctx = MagicMock()
    fake_ctx.send_message = AsyncMock()
    executor = preprocess_module.PreprocessExecutor()
    csv_path = Path("C:/temp/vendor-email-staging/workflow-123/attachments/circuits.csv")
    validated = ValidatedEmail(
        workflow_instance_id="workflow-123",
        internet_message_id="msg-123",
        received_at=datetime(2026, 5, 7, 16, 49, 51, tzinfo=timezone.utc),
        subject="subject",
        sender="noreply@vendor.example",
        body="Body text",
        attachments=["workflow-123/attachments/circuits.csv"],
    )

    with (
        patch.object(preprocess_module, "download_attachment_blobs", MagicMock(return_value=[csv_path])),
        patch.object(Path, "read_text", return_value="Circuit ID,Window\nABC-123,2026-05-12 01:00 UTC\n"),
    ):
        # Act
        await executor.preprocess(validated, fake_ctx)

    # Assert
    sent_message = fake_ctx.send_message.await_args.args[0]
    assert sent_message.attachments == [
        AttachmentContent(
            filename="circuits.csv",
            content="Circuit ID,Window\nABC-123,2026-05-12 01:00 UTC\n",
        )
    ]
