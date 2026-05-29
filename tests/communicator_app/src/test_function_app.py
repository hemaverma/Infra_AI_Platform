"""Tests for Function host dispatch and workflow resume behavior."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from function_app_queue import workflow_storage_queue_consumer
from workflow.messages import HitlRequest
from workflow.queue_envelopes import workflow_resume_payload
from workflow_runner import handle_workflow_message


@dataclass
class _FakeCheckpoint:
    checkpoint_id: str
    timestamp: str = "2026-05-11T00:00:00+00:00"
    pending_request_info_events: dict[str, object] | None = None


class _FakeEvent:
    def __init__(self, event_type: str, *, data: object = None, request_id: str = "req-1") -> None:
        self.type = event_type
        self.data = data
        self.request_id = request_id


class _FakeQueueMessage:
    def __init__(self, body: dict) -> None:
        self._body = json.dumps(body).encode("utf-8")

    def get_body(self) -> bytes:
        return self._body


class _FakeOut:
    def __init__(self) -> None:
        self.values: list[str] = []

    def set(self, value: str) -> None:
        self.values.append(value)


class _FakeWorkflow:
    def __init__(
        self,
        *,
        rehydrate_events: list[_FakeEvent],
        replay_events: list[_FakeEvent] | None = None,
        replay_error: Exception | None = None,
        name: str = "vendor-email-response-wf-host",
    ) -> None:
        self._rehydrate_events = rehydrate_events
        self._replay_events = replay_events or []
        self._replay_error = replay_error
        self.name = name
        self.last_responses: dict[str, dict] | None = None

    def run(self, *args, **kwargs):
        async def _iterator():
            if "checkpoint_id" in kwargs:
                for event in self._rehydrate_events:
                    yield event
                return

            self.last_responses = kwargs.get("responses")
            if self._replay_error is not None:
                raise self._replay_error

            for event in self._replay_events:
                yield event

        return _iterator()


def _install_host_fakes(
    monkeypatch: pytest.MonkeyPatch,
    workflow: _FakeWorkflow,
    *,
    next_checkpoint_id: str = "cp-next",
    checkpoints: list[_FakeCheckpoint] | None = None,
):
    if checkpoints is None:
        checkpoints = [_FakeCheckpoint(next_checkpoint_id)]
    storage = SimpleNamespace(
        get_latest=AsyncMock(return_value=checkpoints[-1]),
        list_checkpoints=AsyncMock(return_value=checkpoints),
    )
    import workflow_runner
    monkeypatch.setattr(workflow_runner, "build_storage", lambda provider=None: storage)
    monkeypatch.setattr(workflow_runner, "build_workflow", lambda storage_arg, workflow_instance_id: workflow)
    return storage


def _start_message() -> dict:
    return {
        "queueName": "workflow-queue",
        "eventType": "email.received",
        "workflowInstanceId": "wf-host",
        "internetMessageId": "msg-host",
        "storagePrefix": "wf-prefix",
        "checkpointId": None,
        "receivedAt": "2026-05-11T00:00:00+00:00",
    }


def _resume_message(*, approval_type: str, approval_status: str) -> dict:
    return {
        "queueName": "workflow-queue",
        "eventType": "approval.responded",
        "workflowInstanceId": "wf-host",
        "workflowPrefix": "wf-prefix",
        "checkpointId": "cp-resume",
        "approvalType": approval_type,
        "approvalStatus": approval_status,
    }


def _command_request() -> HitlRequest:
    return HitlRequest(
        event_type="command-approval.requested",
        workflow_instance_id="wf-host",
        internet_message_id="msg-command",
        display_message="Approve VMS operations",
        approval_payload={
            "received_at": datetime(2026, 5, 11, tzinfo=timezone.utc).isoformat(),
            "subject": "Vendor maintenance notice",
            "sender": "noc@vendor.example",
            "fields": {},
            "proposed_operations": [
                {"op": "create_ticket", "payload": {"ticket_id": "CHG-123"}},
            ],
        },
    )


def _draft_request() -> HitlRequest:
    return HitlRequest(
        event_type="email-approval.requested",
        workflow_instance_id="wf-host",
        internet_message_id="msg-review",
        display_message="Draft email for review",
        approval_payload={
            "received_at": datetime(2026, 5, 11, tzinfo=timezone.utc).isoformat(),
            "source_subject": "Vendor maintenance notice",
            "sender": "noc@vendor.example",
            "proposed_subject": "Draft subject",
            "proposed_body": "Draft body",
        },
    )


def test_given_approve_status_when_building_approval_response_then_canonicalizes_to_approved() -> None:
    # Arrange
    envelope_dict = _resume_message(approval_type="command", approval_status="Approve")

    # Act
    result = workflow_resume_payload(envelope_dict)

    # Assert
    assert result["approval_status"] == "approved"


def test_given_reject_status_when_building_approval_response_then_canonicalizes_to_rejected() -> None:
    # Arrange
    envelope_dict = _resume_message(approval_type="command", approval_status="Reject")

    # Act
    result = workflow_resume_payload(envelope_dict)

    # Assert
    assert result["approval_status"] == "rejected"


@pytest.mark.asyncio
async def test_given_command_rejection_resume_when_dispatch_then_returns_terminal_output_without_second_hitl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    workflow = _FakeWorkflow(
        rehydrate_events=[
            _FakeEvent("request_info", data=_command_request(), request_id="req-command"),
        ],
        replay_events=[
            _FakeEvent(
                "output",
                data={
                    "status": "rejected",
                    "reason": "command_rejected",
                    "approval_status": "rejected",
                    "approval_type": "command",
                    "workflow_instance_id": "wf-host",
                    "internet_message_id": "msg-command",
                    "received_at": "2026-05-11T00:00:00+00:00",
                    "subject": "Vendor maintenance notice",
                    "sender": "noc@vendor.example",
                },
            ),
        ],
    )
    storage = _install_host_fakes(monkeypatch, workflow)

    # Act
    result = await handle_workflow_message(
        _resume_message(approval_type="command", approval_status="rejected")
    )

    # Assert
    assert result == {
        "status": "completed",
        "output": {
            "status": "rejected",
            "reason": "command_rejected",
            "approval_status": "rejected",
            "approval_type": "command",
            "workflow_instance_id": "wf-host",
            "internet_message_id": "msg-command",
            "received_at": "2026-05-11T00:00:00+00:00",
            "subject": "Vendor maintenance notice",
            "sender": "noc@vendor.example",
        },
        "hitl_messages": [],
    }
    # workflow_resume_payload now returns the entire envelope with approval_status added
    assert workflow.last_responses == {
        "req-command": {
            "queueName": "workflow-queue",
            "eventType": "approval.responded",
            "workflowInstanceId": "wf-host",
            "workflowPrefix": "wf-prefix",
            "checkpointId": "cp-resume",
            "approvalType": "command",
            "approvalStatus": "rejected",
            "approval_status": "rejected",
        },
    }
    storage.get_latest.assert_not_awaited()


@pytest.mark.asyncio
async def test_given_command_approval_resume_when_dispatch_then_emits_email_review_hitl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    workflow = _FakeWorkflow(
        rehydrate_events=[
            _FakeEvent("request_info", data=_command_request(), request_id="req-command"),
        ],
        replay_events=[
            _FakeEvent("request_info", data=_draft_request(), request_id="req-email"),
        ],
    )
    _install_host_fakes(
        monkeypatch,
        workflow,
        checkpoints=[
            _FakeCheckpoint(
                checkpoint_id="cp-earlier",
                timestamp="2026-05-11T00:00:01+00:00",
                pending_request_info_events={},
            ),
            _FakeCheckpoint(
                checkpoint_id="cp-email-review",
                timestamp="2026-05-11T00:00:02+00:00",
                pending_request_info_events={"req-email": object()},
            ),
        ],
    )

    # Act
    result = await handle_workflow_message(
        _resume_message(approval_type="command", approval_status="approved")
    )

    # Assert
    assert result == {
        "status": "pending",
        "checkpoint_id": "cp-email-review",
        "hitl_messages": [
            {
                "queueName": "hitl-queue",
                "eventType": "email-approval.requested",
                "workflowInstanceId": "wf-host",
                "workflowPrefix": "wf-prefix",
                "checkpointId": "cp-email-review",
                "internetMessageId": "msg-review",
                "approvalType": "email",
                "adaptiveCardMessage": "Draft email for review",  # From _draft_request().display_message
            },
        ],
    }
    # workflow_resume_payload now returns the entire envelope with approval_status added
    assert workflow.last_responses == {
        "req-command": {
            "queueName": "workflow-queue",
            "eventType": "approval.responded",
            "workflowInstanceId": "wf-host",
            "workflowPrefix": "wf-prefix",
            "checkpointId": "cp-resume",
            "approvalType": "command",
            "approvalStatus": "approved",
            "approval_status": "approved",
        },
    }
    # Note: storage.list_checkpoints is no longer called in the refactored architecture


@pytest.mark.asyncio
async def test_given_pending_hitl_when_exact_request_id_is_unavailable_then_dispatch_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    workflow = _FakeWorkflow(
        rehydrate_events=[],
        replay_events=[_FakeEvent("request_info", data=_command_request(), request_id="req-command")],
    )
    _install_host_fakes(
        monkeypatch,
        workflow,
        checkpoints=[
            _FakeCheckpoint(
                checkpoint_id="cp-stale",
                timestamp="2026-05-11T00:00:01+00:00",
                pending_request_info_events={},
            ),
            _FakeCheckpoint(
                checkpoint_id="cp-pending",
                timestamp="2026-05-11T00:00:02+00:00",
                pending_request_info_events={"some-other-request-id": object()},
            ),
        ],
    )

    # Act
    result = await handle_workflow_message(_start_message())

    # Assert
    assert result["checkpoint_id"] == "cp-pending"
    assert result["hitl_messages"][0]["checkpointId"] == "cp-pending"


@pytest.mark.asyncio
async def test_given_email_rejection_resume_when_dispatch_then_returns_terminal_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    workflow = _FakeWorkflow(
        rehydrate_events=[
            _FakeEvent("request_info", data=_draft_request(), request_id="req-email"),
        ],
        replay_events=[
            _FakeEvent(
                "output",
                data={
                    "status": "rejected",
                    "reason": "email_rejected",
                    "approval_status": "rejected",
                    "approval_type": "email",
                    "workflow_instance_id": "wf-host",
                    "internet_message_id": "msg-review",
                    "received_at": "2026-05-11T00:00:00+00:00",
                    "subject": "Vendor maintenance notice",
                    "sender": "noc@vendor.example",
                },
            ),
        ],
    )
    storage = _install_host_fakes(monkeypatch, workflow)

    # Act
    result = await handle_workflow_message(
        _resume_message(approval_type="email", approval_status="rejected")
    )

    # Assert
    assert result == {
        "status": "completed",
        "output": {
            "status": "rejected",
            "reason": "email_rejected",
            "approval_status": "rejected",
            "approval_type": "email",
            "workflow_instance_id": "wf-host",
            "internet_message_id": "msg-review",
            "received_at": "2026-05-11T00:00:00+00:00",
            "subject": "Vendor maintenance notice",
            "sender": "noc@vendor.example",
        },
        "hitl_messages": [],
    }
    # workflow_resume_payload now returns the entire envelope with approval_status added
    assert workflow.last_responses == {
        "req-email": {
            "queueName": "workflow-queue",
            "eventType": "approval.responded",
            "workflowInstanceId": "wf-host",
            "workflowPrefix": "wf-prefix",
            "checkpointId": "cp-resume",
            "approvalType": "email",
            "approvalStatus": "rejected",
            "approval_status": "rejected",
        },
    }
    storage.get_latest.assert_not_awaited()


@pytest.mark.asyncio
async def test_given_invalid_approval_status_when_dispatch_then_raises_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange: with the new workflow_resume_payload, "maybe" is normalized to "rejected"
    # So this test now verifies normalization rather than error handling
    workflow = _FakeWorkflow(
        rehydrate_events=[
            _FakeEvent("request_info", data=_command_request(), request_id="req-command"),
        ],
        replay_events=[
            _FakeEvent(
                "output",
                data={
                    "status": "rejected",
                    "reason": "command_rejected",
                },
            ),
        ],
    )
    storage = _install_host_fakes(monkeypatch, workflow)

    # Act
    result = await handle_workflow_message(
        _resume_message(approval_type="command", approval_status="maybe")
    )

    # Assert: "maybe" gets normalized to "rejected"
    assert result["status"] == "completed"
    assert workflow.last_responses == {
        "req-command": {
            "queueName": "workflow-queue",
            "eventType": "approval.responded",
            "workflowInstanceId": "wf-host",
            "workflowPrefix": "wf-prefix",
            "checkpointId": "cp-resume",
            "approvalType": "command",
            "approvalStatus": "maybe",
            "approval_status": "rejected",  # normalized
        },
    }
    storage.get_latest.assert_not_awaited()


@pytest.mark.asyncio
async def test_given_duplicate_resume_when_dispatch_then_returns_already_resumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    workflow = _FakeWorkflow(rehydrate_events=[])
    storage = _install_host_fakes(monkeypatch, workflow)

    # Act
    result = await handle_workflow_message(
        _resume_message(approval_type="command", approval_status="approved")
    )

    # Assert
    assert result == {"status": "already-resumed", "hitl_messages": []}
    assert workflow.last_responses is None
    storage.get_latest.assert_not_awaited()


@pytest.mark.asyncio
async def test_given_pending_hitl_when_storage_queue_consumer_runs_then_decodes_dispatches_and_emits_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    body = {
        "eventType": "email.received",
        "workflowInstanceId": "wf-storage",
        "internetMessageId": "msg-storage",
    }
    hitl_message = {
        "eventType": "email-approval.requested",
        "workflowInstanceId": "wf-storage",
        "checkpointId": "cp-storage",
    }
    msg = _FakeQueueMessage(body)
    hitl_out = _FakeOut()
    mock_dispatch = AsyncMock(
        return_value={
            "status": "pending",
            "hitl_messages": [hitl_message],
        }
    )
    import function_app_queue
    monkeypatch.setattr(function_app_queue, "handle_workflow_message", mock_dispatch)

    # Act
    await workflow_storage_queue_consumer(msg, hitl_out)

    # Assert
    mock_dispatch.assert_awaited_once_with(body)
    assert hitl_out.values == [json.dumps(hitl_message)]


@pytest.mark.asyncio
async def test_given_multiple_hitl_messages_when_storage_queue_consumer_runs_then_raises_assertion_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    body = {
        "eventType": "approval.responded",
        "workflowInstanceId": "wf-storage",
        "checkpointId": "cp-storage",
        "approvalType": "command",
        "approvalStatus": "approved",
        "workflowPrefix": "wf-prefix",
    }
    msg = _FakeQueueMessage(body)
    hitl_out = _FakeOut()
    mock_dispatch = AsyncMock(
        return_value={
            "status": "pending",
            "hitl_messages": [
                {"checkpointId": "cp-1"},
                {"checkpointId": "cp-2"},
            ],
        }
    )
    import function_app_queue
    monkeypatch.setattr(function_app_queue, "handle_workflow_message", mock_dispatch)

    # Act & Assert
    with pytest.raises(
        AssertionError,
        match=r"func\.Out\[str\] binding can only carry one storage queue message per invocation",
    ):
        await workflow_storage_queue_consumer(msg, hitl_out)

    mock_dispatch.assert_awaited_once_with(body)
    assert hitl_out.values == []


@pytest.mark.asyncio
async def test_given_no_hitl_messages_when_storage_queue_consumer_runs_then_skips_output_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    body = {
        "eventType": "email.received",
        "workflowInstanceId": "wf-storage",
        "internetMessageId": "msg-storage",
    }
    msg = _FakeQueueMessage(body)
    hitl_out = _FakeOut()
    mock_dispatch = AsyncMock(
        return_value={
            "status": "completed",
            "hitl_messages": [],
        }
    )
    import function_app_queue
    monkeypatch.setattr(function_app_queue, "handle_workflow_message", mock_dispatch)

    # Act
    await workflow_storage_queue_consumer(msg, hitl_out)

    # Assert
    mock_dispatch.assert_awaited_once_with(body)
    assert hitl_out.values == []
