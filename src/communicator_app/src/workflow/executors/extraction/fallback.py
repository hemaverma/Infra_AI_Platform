"""Deterministic fallback extraction helpers for the field extraction executor."""

import re
from typing import Literal

from workflow.executors.extraction.prompt_input import build_candidate_hints
from workflow.extraction_schema import MaintenanceAsset, MaintenanceEmailFields, MaintenanceScope, MaintenanceWindow
from workflow.messages import SafeEmail


_IntentValue = Literal[
    "create_new",
    "reschedule",
    "add_assets",
    "remove_assets",
    "cancel",
    "informational",
    "inquiry",
    "unknown",
]
_ImpactValue = Literal[
    "outage",
    "degradation_no_impact_due_to_redundancy",
    "degradation_reduced_capacity",
    "no_impact",
    "regulatory_impact",
    "unknown",
]
_LONG_CHG_PATTERN = re.compile(r"^CHG-?\d{9,12}$", re.IGNORECASE)


def build_fallback_extraction(safe: SafeEmail) -> MaintenanceEmailFields:
    """Build a simple deterministic balanced-schema fallback result."""
    hints = build_candidate_hints(safe.subject, safe.body, safe.attachments)
    intent, intent_reasoning = _classify_intent(safe.subject, safe.body)
    impact_category, impact_reasoning = _classify_impact(safe.body)
    vendor_ticket_id, customer_ticket_ids = _split_ticket_candidates(hints["ticket_candidates"])

    assets = [
        MaintenanceAsset(asset_id=f"asset-{index}", type="circuit", value=value)
        for index, value in enumerate(hints["circuit_candidates"], start=1)
    ]

    windows: list[MaintenanceWindow] = []
    if hints["window_candidates"]:
        windows.append(
            MaintenanceWindow(
                window_id="window-1",
                kind="primary",
                start_raw=hints["window_candidates"][0],
                timezone_raw=_extract_timezone(hints["window_candidates"][0]),
            )
        )

    scopes: list[MaintenanceScope] = []
    if assets and windows:
        scopes.append(
            MaintenanceScope(
                scope_id="scope-1",
                asset_refs=[asset.asset_id for asset in assets],
                window_refs=[window.window_id for window in windows],
            )
        )

    return MaintenanceEmailFields(
        intent=intent,
        intent_confidence=3,
        intent_reasoning=intent_reasoning,
        vendor_ticket_id=vendor_ticket_id,
        customer_ticket_ids=customer_ticket_ids,
        work_short_description=(safe.subject or safe.body[:80]).strip(),
        work_description=safe.body[:400].strip(),
        windows=windows,
        assets=assets,
        scopes=scopes,
        impact_category=impact_category,
        impact_confidence=3,
        impact_reasoning=impact_reasoning,
        notes=["Deterministic fallback used lightweight candidate hints."],
    )


def _classify_intent(subject: str, body: str) -> tuple[_IntentValue, str]:
    """Classify the email intent using lightweight lexical signals."""
    combined = f"{subject}\n{body}".lower()
    if any(token in combined for token in ("cancelled", "canceled", "cancel")):
        return "cancel", "Cancellation language was found in the subject or body."
    if any(token in combined for token in ("updated", "rescheduled", "changed")):
        return "reschedule", "Update or reschedule language was found in the subject or body."
    if any(token in combined for token in ("question", "please confirm", "can you")):
        return "inquiry", "Question-style language was found in the subject or body."
    if any(token in combined for token in ("started", "completed", "ended")):
        return "informational", "Informational status language was found in the subject or body."
    return "create_new", "No update, cancellation, inquiry, or status signal was found."


def _classify_impact(body: str) -> tuple[_ImpactValue, str]:
    """Classify impact using lightweight lexical signals."""
    lowered = body.lower()
    if "no impact" in lowered or "non-service affecting" in lowered:
        return "no_impact", "No-impact language was found in the email body."
    if "reduced capacity" in lowered:
        return "degradation_reduced_capacity", "Reduced-capacity language was found in the email body."
    if "redundancy" in lowered:
        return (
            "degradation_no_impact_due_to_redundancy",
            "Redundancy language suggests degraded but absorbed impact.",
        )
    if "outage" in lowered or "service affecting" in lowered:
        return "outage", "Outage or service-affecting language was found in the email body."
    return "unknown", "No deterministic impact signal was found in the email body."


def _extract_timezone(value: str) -> str:
    """Return the first timezone token found in a time-window hint."""
    match = re.search(r"\b(?:UTC|ET|CT|PT|MT|EST|EDT|CST|CDT|PST|PDT)\b", value, re.IGNORECASE)
    return match.group(0) if match else ""


def _split_ticket_candidates(values: list[str]) -> tuple[str, list[str]]:
    """Split deterministic ticket hints into vendor-native and customer-side IDs."""
    vendor_ticket_id = ""
    customer_ticket_ids: list[str] = []

    for value in values:
        if _LONG_CHG_PATTERN.fullmatch(value):
            customer_ticket_ids.append(value)
            continue
        if not vendor_ticket_id:
            vendor_ticket_id = value

    return vendor_ticket_id, customer_ticket_ids
