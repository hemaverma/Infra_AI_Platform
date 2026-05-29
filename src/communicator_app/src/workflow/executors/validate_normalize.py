"""ValidateNormalizeExecutor: pass-through normalize step.

The original deployment performed circuit-to-site resolution and a
duplicate change-request check against an external carrier-lookup API.
That integration has been removed for the public release; the target
downstream system has not been decided. This executor now passes the
extracted fields through with empty circuit-resolution and duplicate-CHG
lists so the downstream HITL and command executors still run end-to-end.
"""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations).

from agent_framework import Executor, WorkflowContext, handler

from workflow.clients.blob_client import upload_json_artifact
from workflow.messages import CircuitResolution, ExtractedFields, NormalizedFields
from workflow.state_snapshots import stash_json_state


class ValidateNormalizeExecutor(Executor):
    """Pass-through normalize step. Wire in a real lookup when the public scenario is decided."""

    def __init__(self) -> None:
        """Initialize with executor id."""
        super().__init__(id="validate_normalize")

    @handler
    async def normalize(self, extracted: ExtractedFields, ctx: WorkflowContext[NormalizedFields]) -> None:
        """Pass the extracted fields through with empty resolution and emit a NormalizedFields message.

        Preserves the message envelope contract so downstream HITL and command
        executors still receive a well-formed NormalizedFields payload. When a
        real lookup integration is wired in, populate ``affected_sites``,
        ``impacted_sites``, ``unmatched_circuits``, ``circuit_resolution``, and
        ``duplicate_chgs`` here.
        """
        resolution = CircuitResolution(source="stub")
        normalized_fields = NormalizedFields(
            workflow_instance_id=extracted.workflow_instance_id,
            internet_message_id=extracted.internet_message_id,
            received_at=extracted.received_at,
            storage_prefix=extracted.storage_prefix,
            subject=extracted.subject,
            sender=extracted.sender,
            fields=extracted.fields,
            affected_sites=[],
            impacted_sites=[],
            unmatched_circuits=[],
            circuit_resolution=resolution,
            duplicate_chgs=[],
        )
        stash_json_state(ctx, "normalized_fields", normalized_fields)
        upload_json_artifact(extracted.storage_prefix, "normalized-result.json", normalized_fields)
        await ctx.send_message(normalized_fields)
