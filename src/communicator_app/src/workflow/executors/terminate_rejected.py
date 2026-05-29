"""Shared terminal executor for valid command and email rejection outcomes."""

import logging
from datetime import datetime

from agent_framework import Executor, WorkflowContext, handler
from typing_extensions import Never

from workflow.messages import ApprovedOperationsPlan, RejectedEmail, ReviewedDraft
from workflow.state_snapshots import stash_json_state

logger = logging.getLogger(__name__)


def _rejection_output(
    *,
    approval_type: str,
    workflow_instance_id: str,
    internet_message_id: str,
    received_at: datetime,
    subject: str,
    sender: str,
    reason: str | None = None,
) -> dict:
    return {
        "status": "rejected",
        "reason": reason if reason is not None else f"{approval_type}_rejected",
        "approval_status": "rejected",
        "approval_type": approval_type,
        "workflow_instance_id": workflow_instance_id,
        "internet_message_id": internet_message_id,
        "received_at": received_at.isoformat(),
        "subject": subject,
        "sender": sender,
    }


class TerminateRejectedExecutor(Executor):
    """Yield one final workflow output for valid business rejections."""

    def __init__(self) -> None:
        """Initialize with executor id."""
        super().__init__(id="terminate_rejected")

    @handler
    async def terminate_command_rejection(
        self,
        plan: ApprovedOperationsPlan,
        ctx: WorkflowContext[Never, dict],
    ) -> None:
        """Terminate the workflow after a rejected command-approval decision."""
        if plan.approved:
            raise ValueError("terminate_rejected received an approved command plan")

        logger.info(
            "terminate_rejected: workflow_instance_id=%s approval_type=command",
            plan.workflow_instance_id,
        )
        final_output = _rejection_output(
            approval_type="command",
            workflow_instance_id=plan.workflow_instance_id,
            internet_message_id=plan.internet_message_id,
            received_at=plan.received_at,
            subject=plan.subject,
            sender=plan.sender,
        )
        stash_json_state(ctx, "final_output", final_output)
        await ctx.yield_output(final_output)

    @handler
    async def terminate_email_rejection(
        self,
        reviewed: ReviewedDraft,
        ctx: WorkflowContext[Never, dict],
    ) -> None:
        """Terminate the workflow after a rejected draft-review decision."""
        if reviewed.approved:
            raise ValueError("terminate_rejected received an approved draft review")

        logger.info(
            "terminate_rejected: workflow_instance_id=%s approval_type=email",
            reviewed.workflow_instance_id,
        )
        final_output = _rejection_output(
            approval_type="email",
            workflow_instance_id=reviewed.workflow_instance_id,
            internet_message_id=reviewed.internet_message_id,
            received_at=reviewed.received_at,
            subject=reviewed.source_subject,
            sender=reviewed.sender,
        )
        stash_json_state(ctx, "final_output", final_output)
        await ctx.yield_output(final_output)

    @handler
    async def terminate_validation_rejection(
        self,
        rejected: RejectedEmail,
        ctx: WorkflowContext[Never, dict],
    ) -> None:
        """Terminate the workflow after a failed pre-flight validation check."""
        logger.info(
            "terminate_rejected: workflow_instance_id=%s approval_type=validation reason=%s",
            rejected.workflow_instance_id,
            rejected.reason,
        )
        final_output = _rejection_output(
            approval_type="validation",
            workflow_instance_id=rejected.workflow_instance_id,
            internet_message_id=rejected.internet_message_id,
            received_at=rejected.received_at,
            subject=rejected.subject,
            sender=rejected.sender,
            reason=rejected.reason,
        )
        stash_json_state(ctx, "final_output", final_output)
        await ctx.yield_output(final_output)
