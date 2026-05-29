"""Email lifecycle message types: ingest -> validate -> clean/safe."""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations and rejects string forms).

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EmailDoc(BaseModel):
    """Typed representation of an ingested email plus staged attachment blob paths."""
    workflow_instance_id: str
    internet_message_id: str
    received_at: datetime
    storage_prefix: str = ""
    subject: str
    sender: str
    body: str
    attachments: list[str] = Field(default_factory=list)


class ValidatedEmail(BaseModel):
    """Email that passed sender and spam validation checks."""
    workflow_instance_id: str
    internet_message_id: str
    received_at: datetime
    storage_prefix: str = ""
    subject: str
    sender: str
    body: str
    attachments: list[str] = Field(default_factory=list)
    notes: dict[str, Any] = Field(default_factory=dict)


class RejectedEmail(BaseModel):
    """Email rejected by validation (e.g. sender not allow-listed).

    Carries only the metadata needed by `TerminateRejectedExecutor` to format
    the terminal output payload; body and attachments are intentionally omitted
    because rejection terminates the workflow before preprocessing.
    """
    workflow_instance_id: str
    internet_message_id: str
    received_at: datetime
    subject: str
    sender: str
    reason: str


class AttachmentContent(BaseModel):
    """Materialized attachment content passed between downstream executors."""

    filename: str
    content: str


class CleanEmail(BaseModel):
    """Email with sanitized body HTML and attachment content materialized."""
    workflow_instance_id: str
    internet_message_id: str
    received_at: datetime
    storage_prefix: str = ""
    subject: str
    sender: str
    body: str
    attachments: list[AttachmentContent] = Field(default_factory=list)
    notes: dict[str, Any] = Field(default_factory=dict)


class SafeEmail(BaseModel):
    """Email that passed content safety screening with attachment content."""
    workflow_instance_id: str
    internet_message_id: str
    received_at: datetime
    storage_prefix: str = ""
    subject: str
    sender: str
    body: str
    attachments: list[AttachmentContent] = Field(default_factory=list)
    notes: dict[str, Any] = Field(default_factory=dict)
