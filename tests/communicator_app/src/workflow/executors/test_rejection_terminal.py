"""Tests for explicit rejection routing and the shared rejection terminal."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from workflow.executors.send_reply import SendReplyExecutor
from workflow.executors.terminate_rejected import TerminateRejectedExecutor
from workflow.executors.operations_command import OperationsCommandExecutor
from workflow.messages import ApprovedOperationsPlan, MaintenanceEmailFields, ReviewedDraft


def _sample_plan(*, approved: bool) -> ApprovedOperationsPlan:
    return ApprovedOperationsPlan(
        workflow_instance_id="wf-reject-command",
        internet_message_id="msg-reject-command",
        received_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
        subject="Vendor maintenance notice",
        sender="noc@vendor.example",
        fields=MaintenanceEmailFields(),
        approved_operations=[],
        approved=approved,
    )


def _sample_review(*, approved: bool) -> ReviewedDraft:
    return ReviewedDraft(
        workflow_instance_id="wf-reject-email",
        internet_message_id="msg-reject-email",
        received_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
        source_subject="Vendor maintenance notice",
        sender="noc@vendor.example",
        subject="Draft subject",
        body="Draft body",
        approved=approved,
    )


@pytest.mark.asyncio
async def test_given_rejected_command_plan_when_terminate_then_yields_terminal_output() -> None:
    # Arrange
    executor = TerminateRejectedExecutor()
    fake_ctx = MagicMock()
    fake_ctx.yield_output = AsyncMock()

    # Act
    await executor.terminate_command_rejection(_sample_plan(approved=False), fake_ctx)

    # Assert
    fake_ctx.yield_output.assert_awaited_once_with({
        "status": "rejected",
        "reason": "command_rejected",
        "approval_status": "rejected",
        "approval_type": "command",
        "workflow_instance_id": "wf-reject-command",
        "internet_message_id": "msg-reject-command",
        "received_at": "2026-05-11T00:00:00+00:00",
        "subject": "Vendor maintenance notice",
        "sender": "noc@vendor.example",
    })
    fake_ctx.set_state.assert_called_once_with(
        "final_output",
        {
            "status": "rejected",
            "reason": "command_rejected",
            "approval_status": "rejected",
            "approval_type": "command",
            "workflow_instance_id": "wf-reject-command",
            "internet_message_id": "msg-reject-command",
            "received_at": "2026-05-11T00:00:00+00:00",
            "subject": "Vendor maintenance notice",
            "sender": "noc@vendor.example",
        },
    )


@pytest.mark.asyncio
async def test_given_rejected_draft_when_terminate_then_yields_terminal_output() -> None:
    # Arrange
    executor = TerminateRejectedExecutor()
    fake_ctx = MagicMock()
    fake_ctx.yield_output = AsyncMock()

    # Act
    await executor.terminate_email_rejection(_sample_review(approved=False), fake_ctx)

    # Assert
    fake_ctx.yield_output.assert_awaited_once_with({
        "status": "rejected",
        "reason": "email_rejected",
        "approval_status": "rejected",
        "approval_type": "email",
        "workflow_instance_id": "wf-reject-email",
        "internet_message_id": "msg-reject-email",
        "received_at": "2026-05-11T00:00:00+00:00",
        "subject": "Vendor maintenance notice",
        "sender": "noc@vendor.example",
    })
    fake_ctx.set_state.assert_called_once_with(
        "final_output",
        {
            "status": "rejected",
            "reason": "email_rejected",
            "approval_status": "rejected",
            "approval_type": "email",
            "workflow_instance_id": "wf-reject-email",
            "internet_message_id": "msg-reject-email",
            "received_at": "2026-05-11T00:00:00+00:00",
            "subject": "Vendor maintenance notice",
            "sender": "noc@vendor.example",
        },
    )


@pytest.mark.asyncio
async def test_given_approved_draft_when_send_reply_then_stashes_final_output() -> None:
    # Arrange
    executor = SendReplyExecutor()
    fake_ctx = MagicMock()
    fake_ctx.yield_output = AsyncMock()

    # Act
    await executor.send(_sample_review(approved=True), fake_ctx)

    # Assert
    fake_ctx.set_state.assert_called_once()
    state_key, state_value = fake_ctx.set_state.call_args.args
    assert state_key == "final_output"
    assert state_value["workflow_instance_id"] == "wf-reject-email"
    assert state_value["approved"] is True
    fake_ctx.yield_output.assert_awaited_once_with(state_value)


@pytest.mark.asyncio
async def test_given_rejected_plan_when_operations_command_runs_then_raises_value_error() -> None:
    # Arrange
    executor = OperationsCommandExecutor()
    fake_ctx = MagicMock()
    fake_ctx.send_message = AsyncMock()

    # Act & Assert
    with pytest.raises(ValueError, match="terminate_rejected"):
        await executor.run_commands(_sample_plan(approved=False), fake_ctx)

    fake_ctx.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_given_rejected_draft_when_send_reply_runs_then_raises_value_error() -> None:
    # Arrange
    executor = SendReplyExecutor()
    fake_ctx = MagicMock()
    fake_ctx.yield_output = AsyncMock()

    # Act & Assert
    with pytest.raises(ValueError, match="terminate_rejected"):
        await executor.send(_sample_review(approved=False), fake_ctx)

    fake_ctx.yield_output.assert_not_called()
