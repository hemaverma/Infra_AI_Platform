"""Service Bus queue envelope models for the vendor-email workflow.

These Pydantic v2 models pin the wire contracts defined in
`docs/design/architecture.md` §3.4.
Each envelope round-trips both snake_case (Python) and camelCase
(JSON) field names via field aliases.

Distinct from the `workflow.messages` package, which holds the in-process MAF
message types exchanged between executors. This module covers only the
on-the-wire Service Bus envelopes (`workflow-queue`, `hitl-queue`) and the
helpers that unpack inbound dicts into those models.
"""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations and rejects string forms).

from datetime import datetime
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


def workflow_instance_id(message: dict[str, Any]) -> str:
    """Return the workflow instance id for an inbound workflow message."""
    value = message.get("workflowInstanceId")
    if not value:
        raise ValueError("workflow message missing workflowInstanceId")
    return str(value)


def workflow_checkpoint_id(message: dict[str, Any]) -> Optional[str]:
    """Return checkpoint id when the inbound workflow message provides one."""
    value = message.get("checkpointId")
    return str(value) if value is not None else None


def workflow_prefix(message: dict[str, Any]) -> str:
    """Return the transport prefix used when emitting HITL envelopes."""
    value = message.get("storagePrefix") or message.get("workflowPrefix")
    return str(value) if value is not None else ""


def workflow_internet_message_id(message: dict[str, Any]) -> Optional[str]:
    """Return internet message id when present on the inbound payload."""
    value = message.get("internetMessageId")
    return str(value) if value is not None else None


def workflow_resume_payload(message: dict[str, Any]) -> dict[str, Any]:
    """Return the executor response payload, normalizing approvalStatus to 'approved'/'rejected'."""
    response = dict(message)
    approval_status = response.get("approvalStatus")
    if isinstance(approval_status, str):
        normalized = (
            "approved"
            if approval_status.strip().lower() in ("approved", "approve", "true", "yes", "1")
            else "rejected"
        )
        # Convert camelCase to snake_case for executor compatibility
        response["approval_status"] = normalized
    return response


class WorkflowQueueStartEnvelope(BaseModel):
    """Logic App → Agent Workflow start message on `workflow-queue`."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    queue_name: Literal["workflow-queue"] = Field(alias="queueName")
    event_type: Literal["email.received"] = Field(alias="eventType")
    workflow_instance_id: str = Field(alias="workflowInstanceId")
    internet_message_id: str = Field(alias="internetMessageId")
    storage_prefix: str = Field(alias="storagePrefix")
    checkpoint_id: Optional[str] = Field(default=None, alias="checkpointId")
    received_at: datetime = Field(alias="receivedAt")


class WorkflowQueueResumeEnvelope(BaseModel):
    """HITL Workflow → Agent Workflow resume message on `workflow-queue`."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    queue_name: Literal["workflow-queue"] = Field(alias="queueName")
    event_type: Literal["approval.responded"] = Field(alias="eventType")
    workflow_instance_id: str = Field(alias="workflowInstanceId")
    workflow_prefix: str = Field(alias="workflowPrefix")
    checkpoint_id: str = Field(alias="checkpointId")
    approval_type: Literal["command", "email"] = Field(alias="approvalType")
    approval_status: str = Field(alias="approvalStatus")


WorkflowQueueEnvelope = Union[WorkflowQueueStartEnvelope, WorkflowQueueResumeEnvelope]
"""Discriminated union for inbound workflow-queue messages (dispatch on eventType)."""


class HitlRequestEnvelope(BaseModel):
    """Agent Workflow → HITL Workflow approval request on `hitl-queue`.

    Covers both `command-approval.requested` and `email-approval.requested`
    event types. The `approval_type` and `event_type` literals discriminate
    the two cases while sharing a single model.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    queue_name: Literal["hitl-queue"] = Field(alias="queueName")
    event_type: Literal["command-approval.requested", "email-approval.requested"] = Field(alias="eventType")
    workflow_instance_id: str = Field(alias="workflowInstanceId")
    workflow_prefix: str = Field(alias="workflowPrefix")
    checkpoint_id: str = Field(alias="checkpointId")
    internet_message_id: Optional[str] = Field(default=None, alias="internetMessageId")
    approval_type: Literal["command", "email"] = Field(alias="approvalType")
    adaptive_card_message: str = Field(alias="adaptiveCardMessage")
