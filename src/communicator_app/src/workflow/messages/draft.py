"""Draft reply message types: generation and operator review."""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations and rejects string forms).

from datetime import datetime

from pydantic import BaseModel, Field


class DraftReply(BaseModel):
    """LLM-generated or stub email reply draft."""
    workflow_instance_id: str
    internet_message_id: str
    received_at: datetime
    storage_prefix: str = ""
    source_subject: str
    sender: str
    cc_addresses: list[str] = Field(default_factory=list)
    subject: str
    body: str


class ReviewedDraft(BaseModel):
    """Operator-reviewed draft with approval decision."""
    workflow_instance_id: str
    internet_message_id: str
    received_at: datetime
    source_subject: str
    sender: str
    cc_addresses: list[str] = Field(default_factory=list)
    subject: str
    body: str
    approved: bool
