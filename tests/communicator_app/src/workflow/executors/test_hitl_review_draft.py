"""Tests for the draft-review HITL executor."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from workflow.executors.hitl_review_draft import HitlReviewDraftExecutor
from workflow.messages import DraftReply, HitlRequest, ReviewedDraft


def _sample_request() -> HitlRequest:
    return HitlRequest(
        event_type="email-approval.requested",
        workflow_instance_id="wf-review",
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


@pytest.mark.asyncio
async def test_given_draft_when_request_review_then_stashes_json_request() -> None:
    # Arrange
    executor = HitlReviewDraftExecutor()
    fake_ctx = MagicMock()
    fake_ctx.request_info = AsyncMock()

    # Act
    await executor.request_review(
        DraftReply(
            workflow_instance_id="wf-review",
            internet_message_id="msg-review",
            received_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
            source_subject="Vendor maintenance notice",
            sender="noc@vendor.example",
            subject="Draft subject",
            body="Draft body",
        ),
        fake_ctx,
    )

    # Assert
    fake_ctx.request_info.assert_awaited_once()
    request_data = fake_ctx.request_info.call_args.kwargs["request_data"]
    assert request_data.event_type == "email-approval.requested"
    assert request_data.workflow_instance_id == "wf-review"
    assert request_data.internet_message_id == "msg-review"
    # Check that approval_payload contains the draft details
    payload = request_data.approval_payload
    assert payload["source_subject"] == "Vendor maintenance notice"
    assert payload["sender"] == "noc@vendor.example"
    assert payload["proposed_subject"] == "Draft subject"
    assert payload["proposed_body"] == "Draft body"


@pytest.mark.asyncio
async def test_given_rejected_approval_status_when_on_review_then_emits_rejected_draft() -> None:
    # Arrange
    executor = HitlReviewDraftExecutor()
    fake_ctx = MagicMock()
    fake_ctx.send_message = AsyncMock()

    # Act
    await executor.on_review(
        _sample_request(),
        {"approval_status": "rejected"},
        fake_ctx,
    )

    # Assert
    fake_ctx.send_message.assert_awaited_once_with(
        ReviewedDraft(
            workflow_instance_id="wf-review",
            internet_message_id="msg-review",
            received_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
            source_subject="Vendor maintenance notice",
            sender="noc@vendor.example",
            subject="Draft subject",
            body="Draft body",
            approved=False,
        )
    )
    fake_ctx.set_state.assert_called_once()
    state_key, state_value = fake_ctx.set_state.call_args.args
    assert state_key == "reviewed_draft"
    assert state_value["approved"] is False


@pytest.mark.asyncio
async def test_given_invalid_approval_status_when_on_review_then_raises_value_error() -> None:
    # Arrange
    executor = HitlReviewDraftExecutor()
    fake_ctx = MagicMock()
    fake_ctx.send_message = AsyncMock()

    # Act & Assert
    with pytest.raises(ValueError, match="unsupported approval_status"):
        await executor.on_review(
            _sample_request(),
            {"approval_status": "maybe"},
            fake_ctx,
        )

    fake_ctx.send_message.assert_not_called()
