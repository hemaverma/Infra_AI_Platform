"""LLM extraction output message type."""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations and rejects string forms).

from datetime import datetime

from pydantic import BaseModel, Field

from workflow.extraction_schema import MaintenanceEmailFields


class ExtractedFields(BaseModel):
    """LLM-extracted maintenance fields before normalization."""
    workflow_instance_id: str
    internet_message_id: str
    received_at: datetime
    storage_prefix: str = ""
    subject: str
    sender: str
    fields: MaintenanceEmailFields = Field(default_factory=MaintenanceEmailFields)
