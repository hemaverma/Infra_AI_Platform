"""Shared read-only selectors for email extraction fields."""

from workflow.extraction_schema import MaintenanceEmailFields, MaintenanceWindow


def preferred_window(fields: MaintenanceEmailFields) -> MaintenanceWindow | None:
    """Return the preferred window for downstream display and planning."""
    for window in fields.windows:
        if window.kind in ("primary", "rescheduled"):
            return window
    return fields.windows[0] if fields.windows else None


def ticket_value(fields: MaintenanceEmailFields) -> str:
    """Return the primary ticket value for downstream consumers."""
    if fields.vendor_ticket_id:
        return fields.vendor_ticket_id
    return fields.customer_ticket_ids[0] if fields.customer_ticket_ids else ""


def circuit_values(fields: MaintenanceEmailFields) -> list[str]:
    """Return extracted circuit identifiers from the balanced schema."""
    return [asset.value for asset in fields.assets if asset.type == "circuit" and asset.value]


def window_text(fields: MaintenanceEmailFields) -> str:
    """Return a readable maintenance window string."""
    window = preferred_window(fields)
    if window is None:
        return ""
    raw_parts = [part for part in (window.start_raw, window.end_raw) if part]
    if raw_parts:
        return " to ".join(raw_parts)
    normalized_parts = [part for part in (window.start, window.end) if part]
    return " to ".join(normalized_parts)


def summary_text(fields: MaintenanceEmailFields) -> str:
    """Return the most useful summary string for downstream consumers."""
    return fields.work_short_description or fields.work_description
