"""Draft replies for supported workflow outcomes."""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agent_framework import Executor, WorkflowContext, handler
from pydantic import BaseModel, ConfigDict, Field

from workflow.agent import build_default_agent, email_draft_agent_enabled
from workflow.clients.blob_client import upload_json_artifact
from workflow.extraction_views import ticket_value, window_text
from workflow.messages import CommandResult, DraftReply
from workflow.state_snapshots import stash_json_state

logger = logging.getLogger(__name__)


class ReplyScenario(str, Enum):
    """Supported draft-reply scenarios."""

    CREATE_ACK = "create_ack"


@dataclass(frozen=True)
class _ReplyPlan:
    """Resolved inputs for drafting a reply."""

    scenario: ReplyScenario
    ticket: str
    chg_number: str
    cc_addresses: list[str]
    window: str
    source_subject: str


_CREATE_SUCCESS_STATUSES = {"ok", "stub-ok", "success", "succeeded", "created", "completed"}

_INSTRUCTIONS = (
    "Draft a concise vendor reply for a successfully created downstream change request. "
    "Put the downstream CHG number in the subject line next to the existing vendor ticket when one is available. "
    "In the body, acknowledge receipt of the maintenance notice and confirm that the change request was created. "
    "Keep the tone brief and operational, and do not invent details. "
    "Return JSON with subject and body only. Keep the body under 80 words."
)


class _DraftOutput(BaseModel):
    """Structured output for the happy-path reply drafter."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(default="")
    body: str = Field(default="")


def _successful_create_outcome(command_outputs: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first successful create-ticket execution row."""
    executed = command_outputs.get("operations", {}).get("executed")
    if not isinstance(executed, list):
        return None

    for item in executed:
        if (
            isinstance(item, dict)
            and item.get("op") == "create_ticket"
            and str(item.get("status", "")).strip().lower() in _CREATE_SUCCESS_STATUSES
        ):
            return item

    return None


def _extract_reply_context(outcome: dict[str, Any]) -> tuple[str, list[str]]:
    """Return the stubbed CHG number and market CC lists for replies."""
    result = outcome.get("result")
    payload = outcome.get("payload")
    result_data = result if isinstance(result, dict) else {}
    payload_data = payload if isinstance(payload, dict) else {}
    chg_number = str(result_data.get("chg_number") or payload_data.get("chg_number") or "").strip()
    market_cc_dls = result_data.get("market_cc_dls")
    cc_addresses = []
    if isinstance(market_cc_dls, list):
        cc_addresses = [str(address).strip() for address in market_cc_dls if str(address).strip()]
    return chg_number, cc_addresses


def _build_ack_subject(ticket: str, chg_number: str) -> str:
    """Build the acknowledgment subject line."""
    if ticket:
        return f"Re: {ticket} | {chg_number}"
    return f"Re: {chg_number}"


def _build_ack_body(ticket: str, chg_number: str, window: str) -> str:
    """Build the acknowledgment body for successful creates."""
    ticket_clause = f" for ticket {ticket}" if ticket else ""
    window_clause = f" for window {window}" if window else ""
    return (
        f"Acknowledged receipt of the maintenance notice{ticket_clause}{window_clause}. "
        f"Downstream CHG {chg_number} has been created and the impacted market teams have been copied."
    )


def _resolve_reply_plan(result: CommandResult) -> _ReplyPlan | None:
    """Resolve the supported reply scenario for a command result."""
    create_outcome = _successful_create_outcome(result.command_outputs or {})
    if create_outcome is None:
        return None

    chg_number, cc_addresses = _extract_reply_context(create_outcome)
    if not chg_number:
        return None

    return _ReplyPlan(
        scenario=ReplyScenario.CREATE_ACK,
        ticket=ticket_value(result.fields),
        chg_number=chg_number,
        cc_addresses=cc_addresses,
        window=window_text(result.fields),
        source_subject=result.subject,
    )


class DraftReplyExecutor(Executor):
    """Draft an acknowledgment email for successful create outcomes only."""

    def __init__(self) -> None:
        """Initialize with executor id and deferred agent construction."""
        super().__init__(id="draft_reply")
        self._agent = None

    def _ensure_agent(self):
        if self._agent is None:
            self._agent = build_default_agent(
                name="reply_drafter",
                instructions=_INSTRUCTIONS,
                response_format=_DraftOutput,
            )
        return self._agent

    async def _build_reply_content(
        self,
        plan: _ReplyPlan,
    ) -> tuple[str, str]:
        """Build reply content using the LLM when enabled, else use fallback text."""
        fallback_subject, fallback_body = self._build_fallback_content(plan)
        if not email_draft_agent_enabled():
            return fallback_subject, fallback_body

        draft = await self._draft_with_agent(plan)
        return draft.subject or fallback_subject, draft.body or fallback_body

    def _build_fallback_content(self, plan: _ReplyPlan) -> tuple[str, str]:
        """Build deterministic fallback content for a resolved reply plan."""
        if plan.scenario is ReplyScenario.CREATE_ACK:
            return (
                _build_ack_subject(plan.ticket, plan.chg_number),
                _build_ack_body(plan.ticket, plan.chg_number, plan.window),
            )

        raise ValueError(f"Unsupported reply scenario: {plan.scenario}")

    @handler
    async def draft(self, result: CommandResult, ctx: WorkflowContext[DraftReply]) -> None:
        """Generate a draft reply from the command result."""
        plan = _resolve_reply_plan(result)
        if plan is None:
            create_outcome = _successful_create_outcome(result.command_outputs or {})
            if create_outcome is not None:
                logger.warning(
                    "draft_reply: skipping draft for workflow_instance_id=%s; "
                    "successful create outcome is missing a stub CHG number",
                    result.workflow_instance_id,
                )
                return

            logger.info(
                "draft_reply: skipping draft for workflow_instance_id=%s; "
                "no successful create_ticket outcome found",
                result.workflow_instance_id,
            )
            return

        subject, body = await self._build_reply_content(plan)

        draft_reply = DraftReply(
            workflow_instance_id=result.workflow_instance_id,
            internet_message_id=result.internet_message_id,
            received_at=result.received_at,
            storage_prefix=result.storage_prefix,
            source_subject=result.subject,
            sender=result.sender,
            cc_addresses=plan.cc_addresses,
            subject=subject,
            body=body,
        )

        stash_json_state(ctx, "draft_reply", draft_reply)
        upload_json_artifact(result.storage_prefix, "draft-reply.json", draft_reply)
        await ctx.send_message(draft_reply)

    async def _draft_with_agent(self, plan: _ReplyPlan) -> _DraftOutput:
        """Draft the happy-path acknowledgment with the shared LLM agent."""
        agent = self._ensure_agent()
        prompt = (
            "Draft a reply for this successful create outcome.\n"
            f"Source subject: {plan.source_subject}\n"
            f"Vendor ticket: {plan.ticket or '(none)'}\n"
            f"Created downstream CHG: {plan.chg_number}\n"
            f"Maintenance window: {plan.window or '(none)'}\n"
            "Requirements: put the downstream CHG in the subject next to the vendor ticket when available, "
            "acknowledge receipt, confirm the change request was created, and keep it concise."
        )
        response = await agent.run(prompt)
        return _DraftOutput.model_validate(response.value)
