"""HitlOperationsApprovalExecutor: HITL pause to approve proposed operations.

Same canonical MAF HITL pattern as HitlReviewDraftExecutor (request_info +
response_handler). The operator reviews which operations are about to run
against the downstream change-management system (create/update/delete
maintenance tickets) BEFORE the writes execute.
"""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations).

import logging

from agent_framework import Executor, WorkflowContext, handler, response_handler

from workflow.extraction_views import (
    circuit_values,
    summary_text,
    ticket_value,
    window_text,
)
from workflow.messages import (
    ApprovedOperationsPlan,
    HitlRequest,
    MaintenanceEmailFields,
    NormalizedFields,
    OperationsRequest,
)
from workflow.state_snapshots import stash_json_state

logger = logging.getLogger(__name__)


def _parse_approved_value(raw_approved: object) -> bool:
    if isinstance(raw_approved, bool):
        return raw_approved

    if isinstance(raw_approved, str):
        normalized = raw_approved.strip().lower()
        if normalized in ("true", "1", "yes", "approved", "approve"):
            return True
        if normalized in ("false", "0", "no", "rejected", "reject"):
            return False

    raise ValueError(f"unsupported approval value: {raw_approved!r}")


def _coerce_approval_response(response: dict) -> bool:
    raw_status = response.get("approval_status")
    if raw_status is not None:
        if not isinstance(raw_status, str):
            raise ValueError(f"approval_status must be a string, got {type(raw_status).__name__}")

        normalized_status = raw_status.strip().lower()
        if normalized_status not in ("approved", "approve", "rejected", "reject"):
            raise ValueError(f"unsupported approval_status: {raw_status}")

        status_value = normalized_status in ("approved", "approve")
        if "approved" in response:
            approved_value = _parse_approved_value(response["approved"])
            if approved_value is not status_value:
                raise ValueError("approval_status conflicts with approved")
        return status_value

    if "approved" not in response:
        raise ValueError("approval response missing approved or approval_status")

    return _parse_approved_value(response["approved"])


class HitlOperationsApprovalExecutor(Executor):
    """Pause the workflow before the operations command runs; resume on operator sign-off.

    Wire-level shape:
      * `request_approval` builds a proposed operations plan from `NormalizedFields`
        and calls `ctx.request_info(HitlRequest, response_type=dict)`.
      * The host ferries the request to the operator UI (today: log line;
        production: Logic Apps + Teams adaptive card per STORY-NN).
      * The operator's response replays via `workflow.run(responses={...})` and
        is dispatched into `on_approval`, which emits an `ApprovedOperationsPlan`
        with an `approved` boolean that the workflow graph uses for routing.
      * `workflow.builder` routes `approved=True` to `OperationsCommandExecutor`
        and `approved=False` to `TerminateRejectedExecutor`, so rejected plans
        stop the workflow before any downstream command runs.

    Today the proposed plan is a single deterministic stub (`create_ticket`).
    Production decides operations from extracted fields + downstream change-mgmt
    state; see STORY-NN (operations planning logic).
    """

    def __init__(self) -> None:
        """Initialize with executor id."""
        super().__init__(id="hitl_operations_approval")

    @handler
    async def request_approval(
        self,
        normalized: NormalizedFields,
        ctx: WorkflowContext[ApprovedOperationsPlan, dict],
    ) -> None:
        """Propose operations and pause for operator approval."""
        proposed = _propose_operations(normalized)
        await ctx.request_info(
            request_data=HitlRequest(
                event_type="command-approval.requested",
                workflow_instance_id=normalized.workflow_instance_id,
                internet_message_id=normalized.internet_message_id,
                display_message=_format_command_card(normalized.fields, proposed),
                approval_payload={
                    "received_at": normalized.received_at.isoformat(),
                    "storage_prefix": normalized.storage_prefix,
                    "subject": normalized.subject,
                    "sender": normalized.sender,
                    "fields": normalized.fields.model_dump(),
                    "proposed_operations": [op.model_dump() for op in proposed],
                },
            ),
            response_type=dict,
        )

    @response_handler
    async def on_approval(
        self,
        original_request: HitlRequest,
        response: dict,
        ctx: WorkflowContext[ApprovedOperationsPlan, dict],
    ) -> None:
        """Resume after operator approval and emit the ApprovedOperationsPlan."""
        approved = _coerce_approval_response(response)

        # If the operator supplied an explicit operation list use it; otherwise
        # accept the proposed list as-is. Each item may be an OperationsRequest, a
        # plain dict, or a partial dict — coerce defensively.
        payload = original_request.approval_payload
        operator_ops = response.get("operations")
        if operator_ops is not None:
            operations = [_coerce_operation(o) for o in operator_ops]
        else:
            operations = [_coerce_operation(o) for o in payload.get("proposed_operations", [])]

        approved_operations_plan = ApprovedOperationsPlan(
            workflow_instance_id=original_request.workflow_instance_id,
            internet_message_id=original_request.internet_message_id,
            received_at=payload["received_at"],
            storage_prefix=payload.get("storage_prefix", ""),
            subject=payload["subject"],
            sender=payload["sender"],
            fields=payload.get("fields", {}),
            approved_operations=operations if approved else [],
            approved=approved,
        )
        stash_json_state(ctx, "approved_operations_plan", approved_operations_plan)
        await ctx.send_message(approved_operations_plan)


def _format_command_card(fields: MaintenanceEmailFields, proposed_operations: list[OperationsRequest]) -> str:
    """Build the adaptive card body for an operations approval request."""
    ops_lines = [f"- **{op.op}**: {op.payload}" for op in proposed_operations]
    ops_text = "\n".join(ops_lines) if ops_lines else "_(none)_"
    ticket = ticket_value(fields) or "—"
    circuits_list = circuit_values(fields)
    circuits = ", ".join(circuits_list) if circuits_list else "—"
    window = window_text(fields) or "—"
    summary = summary_text(fields) or "—"
    return (
        f"**Ticket:** {ticket}\n\n"
        f"**Circuits:** {circuits}\n\n"
        f"**Window:** {window}\n\n"
        f"**Summary:** {summary}\n\n"
        f"### Proposed Operations\n\n{ops_text}"
    )


def _propose_operations(normalized: NormalizedFields) -> list[OperationsRequest]:
    """Build the proposed operations plan from extracted fields. v1: one create per ticket."""
    fields = normalized.fields
    ticket = ticket_value(fields)
    if not ticket:
        return []

    stub_chg_number = _stub_chg_number()
    stub_market_cc_dls = _stub_market_cc_dls(normalized)
    return [
        OperationsRequest(
            op="create_ticket",
            payload={
                "ticket_id": ticket,
                "circuit_ids": circuit_values(fields),
                "maintenance_window": window_text(fields),
                "summary": summary_text(fields),
            },
            metadata={
                "stub_create_result": {
                    "chg_number": stub_chg_number,
                    "market_cc_dls": stub_market_cc_dls,
                }
            },
        )
    ]


def _stub_chg_number() -> str:
    """Return a fixed mock CHG number for the stubbed create path."""
    return "CHG0000001"


def _stub_market_cc_dls(normalized: NormalizedFields) -> list[str]:
    """Return fixed mock market DLs for the stubbed create path."""
    del normalized
    return ["market-dl-stub@example.com"]


def _coerce_operation(value: object) -> OperationsRequest:
    if isinstance(value, OperationsRequest):
        return value
    if isinstance(value, dict):
        return OperationsRequest(**value)
    raise TypeError(f"unsupported operation type: {type(value).__name__}")
