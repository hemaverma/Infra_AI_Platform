"""Circuit-resolution message types from the downstream lookup chain."""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations and rejects string forms).

from pydantic import BaseModel, Field


class ResolvedCircuit(BaseModel):
    """A vendor circuit successfully resolved by the Command Center API."""

    source_circuit_hum_id: str
    billing_circuit_id: str = ""
    affected_site: str = ""
    impacted_site: str = ""
    status: str = ""
    vendor: str = ""


class UnmatchedCircuit(BaseModel):
    """A vendor circuit that could not be resolved or was filtered by status."""

    original_circuit_id: str
    stripped_circuit_id: str = ""
    reason: str = "no_match"
    status: str = ""


class MadRouterRow(BaseModel):
    """A single row from the MAD router lookup — one downstream site behind a MAD router."""

    mad_router: str = ""
    site_id: str = ""
    nni_circuit_id: str = ""
    aav_circuit_id: str = ""
    aav_vendor: str = ""


class CircuitResolution(BaseModel):
    """Result of the circuit-to-site lookup chain against Command Center.

    Sources contributing to the final affected/impacted CI lists:
      - matched (API 1)              -> source_z_site_id (affected), source_a_site_id (impacted)
      - mad_router_rows (API 2)      -> site_id (affected), mad_router (impacted)
      - microwave_neighbors (API 3)  -> all neighbor sites (affected)
    """

    matched: list[ResolvedCircuit] = Field(default_factory=list)
    unmatched: list[UnmatchedCircuit] = Field(default_factory=list)
    mad_router_rows: list[MadRouterRow] = Field(default_factory=list)
    microwave_neighbors: dict[str, list[str]] = Field(default_factory=dict)
    error: str = ""
    source: str = ""
