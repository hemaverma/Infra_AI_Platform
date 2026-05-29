"""Normalization message types: ready for HITL review."""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations and rejects string forms).

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from workflow.extraction_schema import MaintenanceEmailFields
from workflow.messages.circuits import CircuitResolution, UnmatchedCircuit


class DuplicateChgMatch(BaseModel):
    """A potential duplicate CHG found in ServiceNow via change-request-search.

    ``matches_vendor_ticket`` applies Rule 6: True when any
    ``external_references[*].u_reference_value.value`` on the existing CHG
    equals the vendor ticket from the inbound email.
    """

    chg_number: str = ""
    sys_id: str = ""
    short_description: str = ""
    state: str = ""
    start_date: str = ""
    end_date: str = ""
    vendor_ticket_id: str = ""
    change_request_url: str = ""
    matches_vendor_ticket: bool = False


class NormalizedFields(BaseModel):
    """Validated and normalized maintenance fields ready for HITL review."""
    workflow_instance_id: str
    internet_message_id: str
    received_at: datetime
    storage_prefix: str = ""
    subject: str
    sender: str
    fields: MaintenanceEmailFields = Field(default_factory=MaintenanceEmailFields)
    affected_sites: list[str] = Field(default_factory=list)
    impacted_sites: list[str] = Field(default_factory=list)
    unmatched_circuits: list[UnmatchedCircuit] = Field(default_factory=list)
    circuit_resolution: Optional[CircuitResolution] = None
    duplicate_chgs: list[DuplicateChgMatch] = Field(default_factory=list)
