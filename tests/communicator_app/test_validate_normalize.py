"""Behavior tests for the validate/normalize executor."""

import asyncio
from datetime import datetime, timezone

import workflow.executors.validate_normalize as normalize_module
from workflow.executors.validate_normalize import ValidateNormalizeExecutor
from workflow.messages import ExtractedFields, MaintenanceEmailFields, NormalizedFields


class _RecordingContext:
    def __init__(self) -> None:
        self.messages: list[NormalizedFields] = []
        self.state: dict[str, object] = {}

    async def send_message(self, message: NormalizedFields) -> None:
        self.messages.append(message)

    def set_state(self, key: str, value: object) -> None:
        self.state[key] = value


def test_validate_normalize_uploads_blob_artifact_when_storage_prefix_is_available(monkeypatch):
    """Test normalization persists the JSON artifact under the staged prefix."""
    extracted = ExtractedFields(
        workflow_instance_id="wf-normalize",
        internet_message_id="msg-normalize",
        received_at=datetime(2026, 5, 13, tzinfo=timezone.utc),
        storage_prefix="workflow-123",
        subject="Vendor maintenance notice",
        sender="noc@vendor.example",
        fields=MaintenanceEmailFields(vendor_ticket_id="NCC-24173"),
    )
    upload_calls: list[tuple[str, str, str]] = []

    monkeypatch.setattr(
        normalize_module,
        "upload_json_artifact",
        lambda storage_prefix, artifact_name, payload: upload_calls.append(
            (storage_prefix, artifact_name, payload.workflow_instance_id)
        ),
    )

    context = _RecordingContext()
    executor = ValidateNormalizeExecutor()

    asyncio.run(executor.normalize(extracted, context))

    assert len(context.messages) == 1
    assert context.messages[0].storage_prefix == "workflow-123"
    assert upload_calls == [("workflow-123", "normalized-result.json", "wf-normalize")]
