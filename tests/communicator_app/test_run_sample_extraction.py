"""Tests for the local JSON-sample extraction runner."""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import workflow.run_sample_extraction as runner_module
from workflow.messages import MaintenanceEmailFields
from workflow.run_sample_extraction import load_local_settings_values, load_sample_safe_email, run_extraction


def test_load_sample_safe_email_uses_envelope_metadata(tmp_path: Path):
    """Test sample loading with staged email JSON and workflow envelope JSON."""
    email_sample = tmp_path / "email.json"
    email_sample.write_text(
        json.dumps(
            {
                "internetMessageId": "<email-msg>",
                "workflowInstanceId": "email-workflow",
                "receivedAt": "2026-05-04T18:23:11Z",
                "senderEmail": "noc@vendor.example",
                "subject": "Maintenance notice",
                "body": "Circuit CHG-7821 on 2026-05-12 01:00 UTC.",
                "attachments": ["https://example.com/file.csv"],
            }
        ),
        encoding="utf-8",
    )
    envelope_sample = tmp_path / "envelope.json"
    envelope_sample.write_text(
        json.dumps(
            {
                "workflowInstanceId": "envelope-workflow",
                "internetMessageId": "<envelope-msg>",
                "storagePrefix": "inbound/demo/",
                "receivedAt": "2026-05-05T01:02:03Z",
            }
        ),
        encoding="utf-8",
    )

    safe = load_sample_safe_email(email_sample, envelope_sample)

    assert safe.workflow_instance_id == "envelope-workflow"
    assert safe.internet_message_id == "<envelope-msg>"
    assert safe.subject == "Maintenance notice"
    assert safe.notes["storage_prefix"] == "inbound/demo/"


def test_load_sample_safe_email_applies_preprocess_cleanup_and_keeps_csv_only(tmp_path: Path):
    """Test sample loading mirrors preprocess cleanup before prompt rendering and extraction."""
    email_sample = tmp_path / "email.json"
    attachments_dir = tmp_path / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)
    csv_path = attachments_dir / "circuits.csv"
    csv_path.write_text("Circuit ID,Severity\nABC-123,Outage\n", encoding="utf-8")
    ics_path = attachments_dir / "calendar.ics"
    ics_path.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n", encoding="utf-8")
    email_sample.write_text(
        json.dumps(
            {
                "internetMessageId": "<email-msg>",
                "workflowInstanceId": "email-workflow",
                "receivedAt": "2026-05-04T18:23:11Z",
                "senderEmail": "noc@vendor.example",
                "subject": "Maintenance notice",
                "body": (
                    "<html><body><div>Hello<br>team</div>"
                    "<table><tr><td>Window</td><td>Tonight</td></tr></table></body></html>"
                ),
                "attachments": ["attachments/circuits.csv", "attachments/calendar.ics"],
            }
        ),
        encoding="utf-8",
    )

    safe = load_sample_safe_email(email_sample, None)

    assert safe.body == "Hello\nteam\n<table><tr><td>Window</td><td>Tonight</td></tr></table>"
    assert safe.attachments == [
        runner_module.AttachmentContent(
            filename="circuits.csv",
            content="Circuit ID,Severity\nABC-123,Outage\n",
        )
    ]


def test_run_extraction_returns_executor_output(monkeypatch):
    """Test the sample runner delegates to the extraction executor."""

    class FakeExecutor:
        async def extract(self, safe_email, context):
            await context.send_message(
                runner_module.ExtractedFields(
                    workflow_instance_id=safe_email.workflow_instance_id,
                    internet_message_id=safe_email.internet_message_id,
                    received_at=safe_email.received_at,
                    subject=safe_email.subject,
                    sender=safe_email.sender,
                    fields=MaintenanceEmailFields(vendor_ticket_id="RUNNER-123"),
                )
            )

    monkeypatch.setattr(runner_module, "FieldExtractionExecutor", FakeExecutor)
    safe = load_sample_safe_email()

    result = asyncio.run(run_extraction(safe))

    assert result.fields.vendor_ticket_id == "RUNNER-123"


def test_load_local_settings_values_sets_missing_environment_values(tmp_path: Path, monkeypatch):
    """Test local.settings.json values are loaded for direct Python execution."""
    settings_path = tmp_path / "local.settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "Values": {
                    "_comment_example": "ignored",
                    "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
                    "AUTH_MODE": "azurecli",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AUTH_MODE", raising=False)

    load_local_settings_values(settings_path)

    assert os.environ["AZURE_OPENAI_ENDPOINT"] == "https://example.openai.azure.com/"
    assert os.environ["AUTH_MODE"] == "azurecli"


def test_load_local_settings_values_preserves_existing_environment_values(tmp_path: Path, monkeypatch):
    """Test shell-provided environment values take precedence over local.settings.json."""
    settings_path = tmp_path / "local.settings.json"
    settings_path.write_text(
        json.dumps({"Values": {"AZURE_OPENAI_ENDPOINT": "https://file-value.example/"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://env-value.example/")

    load_local_settings_values(settings_path)

    assert os.environ["AZURE_OPENAI_ENDPOINT"] == "https://env-value.example/"


def test_extracted_fields_model_dump_json_serializes_datetime():
    """Test the runner's JSON-mode dump path serializes datetimes."""
    result = runner_module.ExtractedFields(
        workflow_instance_id="wf-json",
        internet_message_id="msg-json",
        received_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
        subject="subject",
        sender="sender@example.com",
        fields=MaintenanceEmailFields(vendor_ticket_id="JSON-123"),
    )

    payload = result.model_dump(mode="json")

    assert payload["received_at"] == "2026-05-06T00:00:00Z"
