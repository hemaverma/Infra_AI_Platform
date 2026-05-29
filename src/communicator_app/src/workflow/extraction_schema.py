"""Structured extraction schema for vendor maintenance emails.

These models define the extractor contract used for structured output. Field
descriptions are intentionally concrete because they flow into the generated
JSON Schema and can be used by the LLM as field-level guidance.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MaintenanceWindow(BaseModel):
    """Maintenance window extracted from a vendor notice."""

    model_config = ConfigDict(extra="forbid")

    window_id: str = Field(
        default="",
        description=(
            "Stable local identifier for this extracted window within one result, "
            "such as 'window-1'. This value is referenced by scopes[].window_refs "
            "and should be unique within the result."
        ),
    )
    kind: Literal["primary", "backup", "rescheduled", "unknown"] = Field(
        default="unknown",
        description=(
            "Relationship of this window to the main work plan. Use 'primary' for the "
            "main planned window, 'backup' for fallback dates or backup windows rather "
            "than a second concurrent maintenance, "
            "'rescheduled' when the email explicitly replaces a prior window, and "
            "'unknown' when the role is unclear."
        ),
    )
    start_raw: str = Field(
        default="",
        description="Exact start-time text copied from the email for this window.",
    )
    end_raw: str = Field(
        default="",
        description="Exact end-time text copied from the email for this window.",
    )
    timezone_raw: str = Field(
        default="",
        description=(
            "Timezone text stated for this window, such as 'CDT', 'ET', or 'UTC'. "
            "Leave empty when no timezone is present."
        ),
    )
    start: str = Field(
        default="",
        description=(
            "Normalized local start timestamp derived from start_raw, formatted as "
            "YYYY-MM-DDTHH:MM:SS without a UTC offset. Leave empty when the timestamp "
            "is uncertain."
        ),
    )
    end: str = Field(
        default="",
        description=(
            "Normalized local end timestamp derived from end_raw, formatted as "
            "YYYY-MM-DDTHH:MM:SS without a UTC offset. Leave empty when the timestamp "
            "is uncertain."
        ),
    )
    timezone_normalized: str = Field(
        default="",
        description=(
            "Normalized IANA timezone name derived from timezone_raw for this window, "
            "such as 'America/Chicago' or 'UTC'. Leave empty when the raw timezone "
            "cannot be normalized confidently."
        ),
    )


class MaintenanceAsset(BaseModel):
    """Asset identifier extracted from a vendor notice."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(
        default="",
        description=(
            "Stable local identifier for this extracted asset within one result, such "
            "as 'asset-1'. This value is referenced by scopes[].asset_refs and should "
            "be unique within the result."
        ),
    )
    type: Literal["circuit", "site_id", "alias_id", "other"] = Field(
        default="other",
        description=(
            "Kind of asset identifier. Use 'circuit' for telecom circuits, 'site_id' "
            "for operator or vendor site identifiers, 'alias_id' for alternate IDs, "
            "and 'other' when the identifier does not fit the other categories."
        ),
    )
    value: str = Field(
        default="",
        description="Exact asset identifier value as written in the email or attachment text.",
    )


class MaintenanceScope(BaseModel):
    """Grouping that ties assets to windows and location hints."""

    model_config = ConfigDict(extra="forbid")

    scope_id: str = Field(
        default="",
        description=(
            "Stable local identifier for this scope grouping within one result, such "
            "as 'scope-1'."
        ),
    )
    asset_refs: list[str] = Field(
        default_factory=list,
        description=(
            "List of asset_id values that belong to this scope. Only include asset "
            "references supported explicitly or strongly implied by the email content."
        ),
    )
    window_refs: list[str] = Field(
        default_factory=list,
        description=(
            "List of window_id values that apply to this scope. Only include window "
            "references supported explicitly or strongly implied by the email content."
        ),
    )
    location_hints: list[str] = Field(
        default_factory=list,
        description=(
            "Free-text location cues tied to this scope, such as market names, cities, "
            "CLLI values, endpoint labels, or route segments."
        ),
    )


class MaintenanceEmailFields(BaseModel):
    """Schema fields extracted from a vendor maintenance email."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["v1"] = Field(
        default="v1",
        description="Extraction schema version. The application currently sets this to 'v1'.",
    )
    intent: Literal[
        "create_new",
        "reschedule",
        "add_assets",
        "remove_assets",
        "cancel",
        "informational",
        "inquiry",
        "unknown",
    ] = Field(
        default="unknown",
        description=(
            "Overall action implied by the vendor email. Use 'create_new' for a new "
            "maintenance notice, 'reschedule' for changed timing, 'add_assets' or "
            "'remove_assets' for scope updates, 'cancel' for cancellations, "
            "'informational' for started/completed/status notices, 'inquiry' for a "
            "question or request for confirmation, and 'unknown' when the intent is unclear."
        ),
    )
    intent_confidence: int = Field(
        default=1,
        ge=1,
        le=5,
        description=(
            "Confidence score from 1 to 5 for the selected intent label. Use 1 for low "
            "confidence and 5 for high confidence. A label of 'unknown' can still have high "
            "confidence when it is the best classification for the evidence in the email."
        ),
    )
    intent_reasoning: str = Field(
        default="",
        description="Short explanation of the evidence that supports the chosen intent.",
    )
    vendor_name: str = Field(
        default="",
        description=(
            "Vendor or carrier name stated or strongly implied by the email content. "
            "Leave empty if it cannot be determined confidently."
        ),
    )
    vendor_ticket_id: str = Field(
        default="",
        description=(
            "Vendor's primary native maintenance or reference ticket number for this "
            "notice. Prefer a vendor-labeled body reference when present, except that "
            "long CHG identifiers should not go here even when body-labeled as Change "
            "Request values. Do not put customer-side CHG numbers here. If the email "
            "only shows a likely customer-side CHG and no separate vendor-native "
            "ticket, leave this field empty rather than guessing."
        ),
    )
    customer_ticket_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Internal change-management ticket identifiers belonging to the "
            "customer/operator who received this notice \u2014 typically appearing in "
            "subject prefixes, reply chains, prior acknowledgements, or other internal "
            "references. Long CHG identifiers (~9\u201312 digits after the CHG prefix) "
            "usually belong here, including body-labeled Change Request values when no "
            "separate vendor-native ticket is provided."
        ),
    )
    work_short_description: str = Field(
        default="",
        description=(
            "Brief summary of the maintenance work, ideally a concise operator-friendly "
            "headline rather than a full paragraph."
        ),
    )
    work_description: str = Field(
        default="",
        description="Longer plain-language description of the planned work and expected effect.",
    )
    other_references: list[str] = Field(
        default_factory=list,
        description=(
            "Other reference identifiers mentioned in the email that are relevant but are "
            "not the primary vendor ticket and not customer-side ticket IDs."
        ),
    )
    windows: list[MaintenanceWindow] = Field(
        default_factory=list,
        description=(
            "All maintenance windows explicitly supported by the email, including primary, "
            "alternate, backup, or rescheduled windows."
        ),
    )
    assets: list[MaintenanceAsset] = Field(
        default_factory=list,
        description=(
            "All extracted circuits, site identifiers, alias IDs, or similar asset values "
            "mentioned in the email or provided attachment text."
        ),
    )
    scopes: list[MaintenanceScope] = Field(
        default_factory=list,
        description=(
            "Optional groupings that tie assets to specific windows or location hints. "
            "When one maintenance appears to affect the full extracted set, prefer a "
            "single scope linking all extracted assets to all extracted windows. Create "
            "multiple scopes only when the email or attachment content supports different "
            "asset-to-window or asset-to-location groupings. Leave scopes empty when there "
            "are no assets, no windows, or no defensible relationship between them."
        ),
    )
    impact_category: Literal[
        "outage",
        "degradation_no_impact_due_to_redundancy",
        "degradation_reduced_capacity",
        "no_impact",
        "regulatory_impact",
        "unknown",
    ] = Field(
        default="unknown",
        description=(
            "Best-fit impact category described by the vendor. Use 'outage' for service "
            "loss, 'degradation_no_impact_due_to_redundancy' when redundancy avoids customer "
            "impact, 'degradation_reduced_capacity' for reduced capacity or partial service, "
            "'no_impact' for explicitly non-service-affecting work, 'regulatory_impact' "
            "when the notice warns about a regulatory or compliance risk affecting "
            "downstream service, and 'unknown' when impact is unclear."
        ),
    )
    impact_confidence: int = Field(
        default=1,
        ge=1,
        le=5,
        description=(
            "Confidence score from 1 to 5 for the selected impact label. Use 1 for low "
            "confidence and 5 for high confidence. A label of 'unknown' can still have high "
            "confidence when it is the best classification for the evidence in the email."
        ),
    )
    impact_reasoning: str = Field(
        default="",
        description="Short explanation of the evidence that supports the chosen impact category.",
    )
    impact_raw_text: str = Field(
        default="",
        description=(
            "Exact impact-related language from the email, such as outage, degradation, "
            "or no-impact statements."
        ),
    )
    notes: list[str] = Field(
        default_factory=list,
        description=(
            "Additional extraction notes, caveats, or ambiguities that do not fit other "
            "fields but would help downstream review."
        ),
    )


def validate_maintenance_email_fields(value: Any) -> MaintenanceEmailFields:
    """Revalidate a MaintenanceEmailFields payload against the current schema."""
    if isinstance(value, MaintenanceEmailFields):
        return MaintenanceEmailFields.model_validate(value.model_dump(mode="json"))
    if hasattr(value, "model_dump"):
        try:
            payload = value.model_dump(mode="json")
        except TypeError:
            payload = value.model_dump()
        return MaintenanceEmailFields.model_validate(payload)
    return MaintenanceEmailFields.model_validate(value)
