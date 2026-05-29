"""HITL (human-in-the-loop) pause-request payload shared across review gates.

This module holds transport types that are intentionally cross-phase: they are
sent by any executor that needs to suspend the workflow for operator review.
Today that includes both the operations approval gate
(``hitl_operations_approval``) and the draft email review gate
(``hitl_review_draft``); the ``event_type`` discriminator on
:class:`HitlRequest` distinguishes them.
"""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations and rejects string forms).

from typing import Any, Literal

from pydantic import BaseModel, Field


class HitlRequest(BaseModel):
    """Unified HITL pause payload for both the operator approval gate and draft email review.

    `event_type` discriminates the two cases:
    * ``"command-approval.requested"`` — operator reviews proposed operations
      against the downstream change-management system.
    * ``"email-approval.requested"``   — operator reviews a draft email reply.

    `display_message` is the pre-formatted human-readable message shown to the operator (built in the executor).
    `approval_payload` carries the executor-specific data needed by the response handler.
    """

    event_type: Literal["command-approval.requested", "email-approval.requested"]
    workflow_instance_id: str
    internet_message_id: str
    display_message: str
    approval_payload: dict[str, Any] = Field(default_factory=dict)
