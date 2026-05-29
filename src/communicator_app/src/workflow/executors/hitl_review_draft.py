"""HitlReviewDraftExecutor: single HITL pause via request_info / response_handler.

Implements the canonical Microsoft Agent Framework HITL pattern documented at
https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop?pivots=programming-language-python
(reference: `JudgeExecutor`).

This executor owns HITL **semantics** (pause the workflow, mint a request_id,
match the response back into a typed envelope). It does not own HITL
**transport** \u2014 ferrying the request to the operator's UI and replaying the
operator's answer is the host's responsibility. The host is
`function_app.py`; see its module docstring for the host-side flow.
"""

import logging

from agent_framework import Executor, WorkflowContext, handler, response_handler

from workflow.executors.hitl_operations_approval import _coerce_approval_response
from workflow.messages import DraftReply, HitlRequest, ReviewedDraft
from workflow.state_snapshots import stash_json_state

logger = logging.getLogger(__name__)


class HitlReviewDraftExecutor(Executor):
    """Pause the workflow once after drafting and resume on the operator's reply.

    Wire-level shape:
      * `request_review` calls `ctx.request_info(HitlDraftRequest, response_type=dict)`.
        MAF emits a `WorkflowEvent` with `type == "request_info"`,
        `request_id`, and `data == <HitlDraftRequest instance>` to the host.
      * The host (`function_app.workflow_queue_consumer`) emits an outbound
        `email-approval.requested` envelope on `hitl-queue`; the HITL workflow
        posts a Teams adaptive card via Logic Apps.
      * The reviewer's answer returns on `workflow-queue` as an
        `approval.responded` envelope and is replayed via
        `workflow.run(stream=True, responses={request_id: dict})`.
      * MAF dispatches the dict to `on_review`, which emits the typed
        `ReviewedDraft` with an `approved` boolean that the workflow graph uses
        for routing.
      * `workflow.builder` routes `approved=True` to `SendReplyExecutor` and
        `approved=False` to `TerminateRejectedExecutor`, so rejected draft
        reviews terminate the workflow instead of sending the reply.

    TODO(README: HITL transport via Logic Apps and Teams adaptive cards).
    """

    def __init__(self) -> None:
        """Initialize with executor id."""
        super().__init__(id="hitl_review_draft")

    @handler
    async def request_review(self, draft: DraftReply, ctx: WorkflowContext[ReviewedDraft, dict]) -> None:
        """Pause the workflow and request operator review of the draft."""
        # Format the display message with CC if present
        display_parts = []
        if draft.cc_addresses:
            display_parts.append(f"**CC:** {', '.join(draft.cc_addresses)}")
        display_parts.append(f"**Subject:** {draft.subject}")
        display_parts.append("---")
        display_parts.append(draft.body)
        display_message = "\n\n".join(display_parts)

        await ctx.request_info(
            request_data=HitlRequest(
                event_type="email-approval.requested",
                workflow_instance_id=draft.workflow_instance_id,
                internet_message_id=draft.internet_message_id,
                display_message=display_message,
                approval_payload={
                    "received_at": draft.received_at.isoformat(),
                    "source_subject": draft.source_subject,
                    "sender": draft.sender,
                    "proposed_cc_addresses": draft.cc_addresses,
                    "proposed_subject": draft.subject,
                    "proposed_body": draft.body,
                },
            ),
            response_type=dict,
        )

    @response_handler
    async def on_review(
        self,
        original_request: HitlRequest,
        response: dict,
        ctx: WorkflowContext[ReviewedDraft, dict],
    ) -> None:
        """Resume after operator review and emit the ReviewedDraft."""
        approved = _coerce_approval_response(response)

        payload = original_request.approval_payload
        reviewed_draft = ReviewedDraft(
            workflow_instance_id=original_request.workflow_instance_id,
            internet_message_id=original_request.internet_message_id,
            received_at=payload["received_at"],
            source_subject=payload["source_subject"],
            sender=payload["sender"],
            cc_addresses=response.get("cc_addresses", payload.get("proposed_cc_addresses", [])),
            subject=response.get("subject", payload["proposed_subject"]),
            body=response.get("body", payload["proposed_body"]),
            approved=approved,
        )
        stash_json_state(ctx, "reviewed_draft", reviewed_draft)
        await ctx.send_message(reviewed_draft)
