"""ContentSafetyExecutor: Azure AI Content Safety pass-through stub."""

import logging

from agent_framework import Executor, WorkflowContext, handler

from workflow.messages import CleanEmail, SafeEmail
from workflow.state_snapshots import stash_json_state

logger = logging.getLogger(__name__)


class ContentSafetyExecutor(Executor):
    """Pass-through stub for Azure AI Content Safety filtering."""

    def __init__(self) -> None:
        """Initialize with executor id."""
        super().__init__(id="content_safety")

    @handler
    async def safety(self, clean: CleanEmail, ctx: WorkflowContext[SafeEmail]) -> None:
        """Screen email content for harmful material and forward if safe."""
        # Note: out of scope for initial proof of concept workflow
        # TODO(README: Azure AI Content Safety):
        #   - call the Content Safety analyze-text API on clean.body
        #   - short-circuit (yield_output) on harmful-content verdicts
        #   - record category scores in notes for audit
        safe_email = SafeEmail(
            workflow_instance_id=clean.workflow_instance_id,
            internet_message_id=clean.internet_message_id,
            received_at=clean.received_at,
            storage_prefix=clean.storage_prefix,
            subject=clean.subject,
            sender=clean.sender,
            body=clean.body,
            attachments=clean.attachments,
            notes=clean.notes,
        )
        stash_json_state(ctx, "safe_email", safe_email)
        await ctx.send_message(safe_email)
