"""EmailValidateExecutor: vendor allow-list and spam validation pass-through stub."""

import logging
import os

from agent_framework import Executor, WorkflowContext, handler

from workflow.messages import EmailDoc, RejectedEmail, ValidatedEmail
from workflow.state_snapshots import stash_json_state

logger = logging.getLogger(__name__)


def _allowed_sender_domains() -> set[str] | None:
    """Return normalized sender-domain allow-list, or None for allow-all."""
    raw = os.environ.get("EMAIL_ALLOWED_SENDER_DOMAINS", "")
    token = raw.strip()
    if not token or token == "*":
        return None
    return {
        item.strip().lower().lstrip("@")
        for item in raw.split(",")
        if item.strip()
    }


def _sender_domain(sender: str) -> str:
    """Extract and normalize the sender domain, or empty string if malformed."""
    if "@" not in sender:
        return ""
    return sender.rsplit("@", 1)[-1].strip().lower()


class EmailValidateExecutor(Executor):
    """Validate sender against vendor allow-list and spam rules."""

    def __init__(self) -> None:
        """Initialize with executor id."""
        super().__init__(id="email_validate")

    @handler
    async def validate(
        self,
        doc: EmailDoc,
        ctx: WorkflowContext[ValidatedEmail | RejectedEmail, dict],
    ) -> None:
        """Run validation checks and route to preprocess or terminate_rejected."""
        allowed = _allowed_sender_domains()
        sender_domain = _sender_domain(doc.sender)

        if allowed is not None and sender_domain not in allowed:
            rejected = RejectedEmail(
                workflow_instance_id=doc.workflow_instance_id,
                internet_message_id=doc.internet_message_id,
                received_at=doc.received_at,
                subject=doc.subject,
                sender=doc.sender,
                reason="sender_not_allowlisted",
            )
            stash_json_state(ctx, "rejected_email", rejected)
            await ctx.send_message(rejected)
            return

        validated_email = ValidatedEmail(
            workflow_instance_id=doc.workflow_instance_id,
            internet_message_id=doc.internet_message_id,
            received_at=doc.received_at,
            storage_prefix=doc.storage_prefix,
            subject=doc.subject,
            sender=doc.sender,
            body=doc.body,
            attachments=doc.attachments,
            notes={
                "validation": {
                    "sender_domain": sender_domain,
                    "allowlist_source": "env:EMAIL_ALLOWED_SENDER_DOMAINS",
                }
            },
        )
        stash_json_state(ctx, "validated_email", validated_email)
        await ctx.send_message(validated_email)
