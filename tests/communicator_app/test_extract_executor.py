"""Behavior tests for the extraction executor."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import workflow.executors.extract as extract_module
from workflow.executors.extract import FieldExtractionExecutor
from workflow.messages import AttachmentContent, ExtractedFields, MaintenanceEmailFields, SafeEmail


class _RecordingContext:
    def __init__(self) -> None:
        self.messages: list[ExtractedFields] = []
        self.state: dict[str, object] = {}

    async def send_message(self, message: ExtractedFields) -> None:
        self.messages.append(message)

    def set_state(self, key: str, value: object) -> None:
        self.state[key] = value


class _FakeAgent:
    def __init__(self, value: object) -> None:
        self.value = value
        self.prompts: list[str] = []

    async def run(self, prompt: str):
        self.prompts.append(prompt)
        return SimpleNamespace(value=self.value)


def _sample_safe_email() -> SafeEmail:
    return SafeEmail(
        workflow_instance_id="wf-extract",
        internet_message_id="msg-extract",
        received_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
        subject="Updated maintenance for NCC-24173",
        sender="noc@vendor.example",
        body="LAX-NYC-OC192-001 outage window 2026-05-12 01:00 UTC.",
        attachments=[],
        notes={},
    )


def test_extract_uses_stub_path_when_agent_disabled(monkeypatch):
    """Test executor behavior when live extraction is disabled."""
    monkeypatch.setattr(extract_module, "extraction_agent_enabled", lambda: False)

    context = _RecordingContext()
    executor = FieldExtractionExecutor()

    asyncio.run(executor.extract(_sample_safe_email(), context))

    assert len(context.messages) == 1
    message = context.messages[0]
    assert message.fields.vendor_ticket_id == "NCC-24173"
    assert message.fields.intent == "reschedule"
    assert message.fields.assets[0].value == "LAX-NYC-OC192-001"
    assert context.state["extracted_fields"]["workflow_instance_id"] == "wf-extract"
    assert context.state["extracted_fields"]["fields"]["vendor_ticket_id"] == "NCC-24173"


def test_extract_uses_rendered_prompty_input_when_agent_enabled(monkeypatch):
    """Test executor behavior when live extraction is enabled."""
    fake_agent = _FakeAgent(MaintenanceEmailFields(vendor_ticket_id="AGENT-123"))
    monkeypatch.setattr(extract_module, "extraction_agent_enabled", lambda: True)
    monkeypatch.setattr(
        extract_module,
        "build_extraction_prompt_input",
        lambda safe, include_candidate_hints=False: "PACKET",
    )
    monkeypatch.setattr(extract_module, "render_extraction_prompt", lambda packet: f"PROMPTY::{packet}")

    context = _RecordingContext()
    executor = FieldExtractionExecutor()
    executor._agent = fake_agent

    asyncio.run(executor.extract(_sample_safe_email(), context))

    assert fake_agent.prompts == ["PROMPTY::PACKET"]
    assert len(context.messages) == 1
    assert context.messages[0].fields.vendor_ticket_id == "AGENT-123"
    assert context.state["extracted_fields"]["fields"]["vendor_ticket_id"] == "AGENT-123"


def test_extract_uploads_blob_artifact_when_storage_prefix_is_available(monkeypatch):
    """Test extraction persists a staged JSON artifact when storage_prefix is present."""
    safe = _sample_safe_email().model_copy(update={"storage_prefix": "workflow-123"})
    upload_calls: list[tuple[str, str, str]] = []

    monkeypatch.setattr(extract_module, "extraction_agent_enabled", lambda: False)
    monkeypatch.setattr(
        extract_module,
        "upload_json_artifact",
        lambda storage_prefix, artifact_name, payload: upload_calls.append(
            (storage_prefix, artifact_name, payload.workflow_instance_id)
        ),
    )

    context = _RecordingContext()
    executor = FieldExtractionExecutor()

    asyncio.run(executor.extract(safe, context))

    assert upload_calls == [("workflow-123", "extraction-result.json", "wf-extract")]


def test_extract_stub_reads_circuits_from_materialized_csv_attachment(monkeypatch):
    """Test fallback extraction can mine circuit ids from structured CSV attachments."""
    safe = SafeEmail(
        workflow_instance_id="wf-extract",
        internet_message_id="msg-extract",
        received_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
        subject="Vendor Maintenance Notification - Change Request CR-0001",
        sender="noreply@vendor.example",
        body="Change Request #: CR-0001\nStart Date & Time: 05/19/26 04:01:00 UTC.",
        attachments=[
            AttachmentContent(
                filename="circuits.csv",
                content="Circuit ID,Severity\nSYN-NYC-001,Switch to Protect\n",
            )
        ],
        notes={},
    )
    monkeypatch.setattr(extract_module, "extraction_agent_enabled", lambda: False)

    context = _RecordingContext()
    executor = FieldExtractionExecutor()

    asyncio.run(executor.extract(safe, context))

    assert len(context.messages) == 1
    assert context.messages[0].fields.vendor_ticket_id == "CR-0001"
    assert context.messages[0].fields.customer_ticket_ids == []
    assert context.messages[0].fields.assets[0].value == "SYN-NYC-001"


def test_extract_falls_back_to_default_fields_when_agent_returns_unexpected_value(monkeypatch):
    """Test executor behavior when the agent returns an invalid response shape."""
    fake_agent = _FakeAgent({"unexpected": "value"})
    monkeypatch.setattr(extract_module, "extraction_agent_enabled", lambda: True)
    monkeypatch.setattr(
        extract_module,
        "build_extraction_prompt_input",
        lambda safe, include_candidate_hints=False: "PACKET",
    )
    monkeypatch.setattr(extract_module, "render_extraction_prompt", lambda packet: packet)

    context = _RecordingContext()
    executor = FieldExtractionExecutor()
    executor._agent = fake_agent

    with pytest.raises(Exception):
        asyncio.run(executor.extract(_sample_safe_email(), context))

    assert context.messages == []


def test_extract_rejects_out_of_range_confidence_values(monkeypatch):
    """Test executor behavior when the agent returns schema-invalid confidence scores."""
    fake_agent = _FakeAgent(MaintenanceEmailFields(intent_confidence=5, impact_confidence=5).model_copy(
        update={"intent_confidence": 88}
    ))
    monkeypatch.setattr(extract_module, "extraction_agent_enabled", lambda: True)
    monkeypatch.setattr(
        extract_module,
        "build_extraction_prompt_input",
        lambda safe, include_candidate_hints=False: "PACKET",
    )
    monkeypatch.setattr(extract_module, "render_extraction_prompt", lambda packet: packet)

    context = _RecordingContext()
    executor = FieldExtractionExecutor()
    executor._agent = fake_agent

    with pytest.raises(Exception):
        asyncio.run(executor.extract(_sample_safe_email(), context))

    assert context.messages == []
