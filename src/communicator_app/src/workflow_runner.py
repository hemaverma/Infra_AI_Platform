"""Workflow execution helpers shared by all Azure Function triggers."""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations and rejects string forms).

import logging
import os
from typing import Any, Optional

from agent_framework.exceptions import WorkflowCheckpointException
from pydantic import BaseModel
from workflow.builder import build_storage, build_workflow
from workflow.queue_envelopes import (
    HitlRequestEnvelope,
    workflow_checkpoint_id,
    workflow_instance_id,
    workflow_internet_message_id,
    workflow_prefix,
    workflow_resume_payload,
)

logger = logging.getLogger(__name__)


def _to_jsonable(obj: Any) -> Any:
    """Recursively convert Pydantic models to plain dicts for json.dumps."""
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_jsonable(v) for v in obj]
    return obj


def _pending_to_hitl_messages(
    workflow_instance_id: str,
    workflow_prefix: str,
    internet_message_id: Optional[str],
    checkpoint_id: str,
    pending_events: list,
) -> list[dict]:
    """Map `request_info` events captured from the workflow stream to `hitl-queue` envelopes."""
    messages: list[dict] = []
    for event in pending_events:
        data = event.data
        msg_id = getattr(data, "internet_message_id", None) or internet_message_id
        approval_type = data.event_type.split("-")[0]  # "command" or "email"
        envelope = HitlRequestEnvelope(
            queueName=os.environ.get("HITL_QUEUE_NAME", "hitl-queue"),
            eventType=data.event_type,
            workflowInstanceId=workflow_instance_id,
            workflowPrefix=workflow_prefix,
            checkpointId=checkpoint_id,
            internetMessageId=msg_id,
            approvalType=approval_type,
            adaptiveCardMessage=data.display_message,
        )
        messages.append(envelope.model_dump(by_alias=True))
    return messages


async def _collect_workflow_run_events(
    workflow,
    *args,
    **kwargs,
) -> tuple[list, Any]:
    """Run the workflow stream and collect pause events plus terminal output."""
    pending: list = []
    output: Any = None
    async for event in workflow.run(*args, **kwargs):
        if event.type == "request_info":
            pending.append(event)
        elif event.type == "output":
            output = event.data
    return pending, output


async def _build_pending_result(
    storage,
    workflow,
    envelope: dict[str, Any],
    pending_events: list,
    *,
    internet_message_id: Optional[str],
) -> dict:
    """Build the standard paused-workflow result payload."""
    latest = await storage.get_latest(workflow_name=workflow.name)
    if latest is None:
        raise RuntimeError(
            "workflow paused with pending request_info but no checkpoint was persisted"
        )
    checkpoint_id = latest.checkpoint_id
    hitl_messages = _pending_to_hitl_messages(
        workflow_instance_id=workflow_instance_id(envelope),
        workflow_prefix=workflow_prefix(envelope),
        internet_message_id=internet_message_id,
        checkpoint_id=checkpoint_id,
        pending_events=pending_events,
    )
    return {
        "status": "pending",
        "checkpoint_id": checkpoint_id,
        "hitl_messages": hitl_messages,
    }


def _build_completed_result(output: Any) -> dict:
    """Build the standard completed-workflow result payload."""
    if output is not None:
        return {
            "status": "completed",
            "output": _to_jsonable(output),
            "hitl_messages": [],
        }
    return {"status": "completed-no-output", "hitl_messages": []}


async def _rehydrate_workflow_from_checkpoint(
    workflow,
    checkpoint_id: str,
) -> tuple[list, Any]:
    """Rehydrate a workflow from a checkpoint and collect the emitted events."""
    return await _collect_workflow_run_events(workflow, checkpoint_id=checkpoint_id, stream=True)


async def handle_workflow_message(envelope: dict[str, Any]) -> dict:
    """Run or resume a workflow based solely on whether a checkpoint id is present."""
    storage = build_storage()
    workflow = build_workflow(storage, workflow_instance_id=workflow_instance_id(envelope))
    checkpoint_id = workflow_checkpoint_id(envelope)

    if checkpoint_id:
        try:
            rehydrated_pending, _ = await _rehydrate_workflow_from_checkpoint(workflow, checkpoint_id)
        except WorkflowCheckpointException:
            return {"status": "not-found", "hitl_messages": []}

        if not rehydrated_pending:
            return {"status": "already-resumed", "hitl_messages": []}

        assert len(rehydrated_pending) == 1, (
            "V1 graph guarantees one pause per checkpoint; multi-pause not yet supported"
        )

        request_id = rehydrated_pending[0].request_id
        pending, output = await _collect_workflow_run_events(
            workflow,
            stream=True,
            responses={request_id: workflow_resume_payload(envelope)},
        )

        if pending:
            return await _build_pending_result(
                storage,
                workflow,
                envelope,
                pending,
                internet_message_id=workflow_internet_message_id(envelope),
            )
        return _build_completed_result(output)

    # Idempotency guard: reject duplicate workflowInstanceIds that have already
    # completed or are in-flight. Gated on ENFORCE_WORKFLOW_IDEMPOTENCY so local
    # testing can re-run the same ID repeatedly without clearing checkpoints.
    if os.getenv("ENFORCE_WORKFLOW_IDEMPOTENCY", "false").lower() in ("true", "1", "yes"):
        existing = await storage.get_latest(workflow_name=workflow.name)
        if existing is not None:
            logger.warning(
                "email_received: duplicate workflowInstanceId=%s — existing checkpoint_id=%s; "
                "skipping re-execution (ENFORCE_WORKFLOW_IDEMPOTENCY=true)",
                workflow_instance_id(envelope),
                existing.checkpoint_id,
            )
            return {
                "status": "duplicate",
                "checkpoint_id": existing.checkpoint_id,
                "hitl_messages": [],
            }

    pending, output = await _collect_workflow_run_events(
        workflow,
        envelope,
        stream=True,
    )

    if pending:
        return await _build_pending_result(
            storage,
            workflow,
            envelope,
            pending,
            internet_message_id=workflow_internet_message_id(envelope),
        )
    return _build_completed_result(output)
