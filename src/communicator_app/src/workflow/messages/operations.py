"""Operations-flow message types: approval gate output, operations command, and result.

The cross-phase HITL pause payload lives in ``workflow.messages.hitl`` because
it is shared with the draft-review gate.
"""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations and rejects string forms).

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from workflow.extraction_schema import MaintenanceEmailFields


class OperationsRequest(BaseModel):
    """Single proposed operation against the downstream change-management system.

    Each request maps to a create/update/delete of a maintenance ticket.
    """

    op: str  # one of: "create_ticket", "update_ticket", "delete_ticket"
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovedOperationsPlan(BaseModel):
    """Operator-approved plan consumed by OperationsCommandExecutor.

    Drives the downstream change-management system once the approval gate clears.
    """

    workflow_instance_id: str
    internet_message_id: str
    received_at: datetime
    storage_prefix: str = ""
    subject: str
    sender: str
    fields: MaintenanceEmailFields = Field(default_factory=MaintenanceEmailFields)
    approved_operations: list[OperationsRequest] = Field(default_factory=list)
    approved: bool = True


class CommandResult(BaseModel):
    """Output of the operations command step carrying results and extracted fields."""
    workflow_instance_id: str
    internet_message_id: str
    received_at: datetime
    storage_prefix: str = ""
    subject: str
    sender: str
    fields: MaintenanceEmailFields = Field(default_factory=MaintenanceEmailFields)
    command_outputs: dict[str, Any] = Field(default_factory=dict)
