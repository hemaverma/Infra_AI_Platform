"""OperationsCommandExecutor: pass-through stub for the post-approval command step.

In the original deployment this executor sent change-management API calls to
a downstream change-management system. For the public release the target
downstream system has not been decided, so this implementation is a
deterministic no-op that records the approved operations and emits a
CommandResult with status="stub-ok" so the rest of the workflow runs.
"""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations).

import logging

from agent_framework import Executor, WorkflowContext, handler

from workflow.messages import ApprovedOperationsPlan, CommandResult
from workflow.state_snapshots import stash_json_state

logger = logging.getLogger(__name__)


class OperationsCommandExecutor(Executor):
    """Execute operator-approved operations as a deterministic stub.

    Replace the per-operation stub with a real integration when the public
    scenario is decided.
    """

    def __init__(self) -> None:
        """Initialize with executor id."""
        super().__init__(id="operations_command")

    @handler
    async def run_commands(self, plan: ApprovedOperationsPlan, ctx: WorkflowContext[CommandResult]) -> None:
        """Run the approved operations and emit a CommandResult."""
        if not plan.approved:
            raise ValueError(
                "operations_command received a rejected plan; the workflow graph should route "
                "rejections to terminate_rejected"
            )

        if not plan.approved_operations:
            logger.info(
                "operations_command: no approved operations for workflow_instance_id=%s; emitting empty CommandResult",
                plan.workflow_instance_id,
            )
            command_result = CommandResult(
                workflow_instance_id=plan.workflow_instance_id,
                internet_message_id=plan.internet_message_id,
                received_at=plan.received_at,
                storage_prefix=plan.storage_prefix,
                subject=plan.subject,
                sender=plan.sender,
                fields=plan.fields,
                command_outputs={"operations": {"executed": [], "approved": plan.approved}},
            )
            stash_json_state(ctx, "command_result", command_result)
            await ctx.send_message(command_result)
            return

        # Stub: pretend each operation succeeded; record what we would have called.
        executed = []
        for op in plan.approved_operations:
            logger.info("operations_command: STUB call op=%s payload=%s", op.op, op.payload)
            executed_item = {
                "op": op.op,
                "payload": op.payload,
                "status": "stub-ok",
                "result": op.metadata.get("stub_create_result", {}),
            }
            executed.append(executed_item)

        command_result = CommandResult(
            workflow_instance_id=plan.workflow_instance_id,
            internet_message_id=plan.internet_message_id,
            received_at=plan.received_at,
            storage_prefix=plan.storage_prefix,
            subject=plan.subject,
            sender=plan.sender,
            fields=plan.fields,
            command_outputs={"operations": {"executed": executed, "approved": plan.approved}},
        )
        stash_json_state(ctx, "command_result", command_result)
        await ctx.send_message(command_result)
