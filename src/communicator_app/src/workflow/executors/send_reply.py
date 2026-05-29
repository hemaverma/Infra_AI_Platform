"""SendReplyExecutor: terminal executor that yields the final reviewed draft as workflow output."""

import logging

from agent_framework import Executor, WorkflowContext, handler
from typing_extensions import Never

from workflow.messages import ReviewedDraft
from workflow.state_snapshots import stash_json_state

logger = logging.getLogger(__name__)


class SendReplyExecutor(Executor):
    """Terminal executor that yields the final reviewed draft as workflow output."""

    def __init__(self) -> None:
        """Initialize with executor id."""
        super().__init__(id="send_reply")

    @handler
    async def send(self, reviewed: ReviewedDraft, ctx: WorkflowContext[Never, dict]) -> None:
        """Log the final draft and yield it as the workflow output."""
        if not reviewed.approved:
            raise ValueError(
                "send_reply received a rejected draft; the workflow graph should route "
                "rejections to terminate_rejected"
            )

        # TODO(README: Outbound reply send via Logic Apps):
        #   POST the final draft to the Logic Apps connector that drafts and sends the email.
        #   Today we log the final reviewed draft and yield the workflow output.
        logger.info(
            "send_reply: workflow_instance_id=%s approved=%s sender=%s cc_addresses=%s "
            "source_subject=%s subject=%s body=%s",
            reviewed.workflow_instance_id,
            reviewed.approved,
            reviewed.sender,
            reviewed.cc_addresses,
            reviewed.source_subject,
            reviewed.subject,
            reviewed.body,
        )
        final_output = {
            "workflow_instance_id": reviewed.workflow_instance_id,
            "internet_message_id": reviewed.internet_message_id,
            "received_at": reviewed.received_at.isoformat(),
            "source_subject": reviewed.source_subject,
            "sender": reviewed.sender,
            "cc_addresses": reviewed.cc_addresses,
            "approved": reviewed.approved,
            "subject": reviewed.subject,
            "body": reviewed.body,
        }
        stash_json_state(ctx, "final_output", final_output)
        await ctx.yield_output(final_output)
