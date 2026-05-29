"""Helpers for preparing structured prompt input for email extraction."""

import csv
import io
import os
import re
from typing import Literal

from workflow.messages import AttachmentContent, SafeEmail

_EXTRACTION_CANDIDATE_HINTS_ENV = "ENABLE_EXTRACTION_CANDIDATE_HINTS"
_EXTRACTION_PROMPT_EMAIL_FORMAT_ENV = "EXTRACTION_PROMPT_EMAIL_FORMAT"
_DEFAULT_EXTRACTION_PROMPT_EMAIL_FORMAT = "markdown"
_SUPPORTED_EXTRACTION_PROMPT_EMAIL_FORMATS = ("markdown", "xml")

PromptEmailFormat = Literal["markdown", "xml"]

_TICKET_PATTERNS = [
    re.compile(r"\b(?:CHG|INC|CR)-?\d+\b", re.IGNORECASE),
    re.compile(r"\bNCC-\d+\b", re.IGNORECASE),
    re.compile(r"\bN\d{6}-\d{4}\b", re.IGNORECASE),
    re.compile(r"\bME[:\-_]\d{4}-\d{5}\b", re.IGNORECASE),
]
_CIRCUIT_PATTERNS = [
    re.compile(r"\b[A-Z]{3}-[A-Z]{3}-[A-Z0-9-]+\b"),
    re.compile(r"\b[A-Z0-9-]+/[A-Z0-9-]+/[A-Z0-9./-]+", re.IGNORECASE),
    re.compile(r"/[A-Z0-9-]+/[A-Z0-9./-]+", re.IGNORECASE),
]
_WINDOW_PATTERN = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})"
    r"(?:[ T]\d{1,2}:\d{2}(?::\d{2})?\s*(?:UTC|ET|CT|PT|MT|EST|EDT|CST|CDT|PST|PDT)?)?\b",
    re.IGNORECASE,
)


def extraction_candidate_hints_enabled() -> bool:
    """Return True when deterministic candidate hints should be injected into the prompt."""
    return os.getenv(_EXTRACTION_CANDIDATE_HINTS_ENV, "").lower() in ("true", "1", "yes")


def configured_extraction_prompt_email_format() -> PromptEmailFormat:
    """Return the configured email packet rendering format for extraction prompts."""
    return _normalize_prompt_email_format(os.getenv(_EXTRACTION_PROMPT_EMAIL_FORMAT_ENV, ""))


def build_extraction_prompt_input(
    email: SafeEmail,
    *,
    include_candidate_hints: bool = False,
    prompt_email_format: PromptEmailFormat | str | None = None,
) -> str:
    """Build structured text passed to the extraction LLM call."""
    resolved_format = _normalize_prompt_email_format(prompt_email_format)
    attachments = load_csv_prompt_sections(email.attachments)
    candidate_hints = None
    if include_candidate_hints:
        candidate_hints = build_candidate_hints(email.subject, email.body, email.attachments)

    if resolved_format == "xml":
        return _build_xml_extraction_prompt_input(
            email,
            attachments=attachments,
            candidate_hints=candidate_hints,
        )

    return _build_markdown_extraction_prompt_input(
        email,
        attachments=attachments,
        candidate_hints=candidate_hints,
    )


def _build_markdown_extraction_prompt_input(
    email: SafeEmail,
    *,
    attachments: list[dict[str, str]],
    candidate_hints: dict[str, list[str]] | None,
) -> str:
    """Build a simple Markdown email packet for extraction prompts."""
    sections = [
        "# Email Packet",
        f"- Subject: {_markdown_inline_text(email.subject)}",
        f"- From: {_markdown_inline_text(email.sender)}",
        "",
        "## Current Message Body",
        email.body.strip() or "(empty)",
    ]

    if candidate_hints is not None:
        sections.extend([
            "",
            "## Candidate Hints",
            f"- Ticket candidates: {_format_hint_values(candidate_hints['ticket_candidates'])}",
            f"- Circuit candidates: {_format_hint_values(candidate_hints['circuit_candidates'])}",
            f"- Window candidates: {_format_hint_values(candidate_hints['window_candidates'])}",
            f"- Attachment names: {_format_hint_values(candidate_hints['attachment_names'])}",
        ])

    if attachments:
        sections.extend(["", "## Attachments"])
        for attachment in attachments:
            sections.extend([
                f"### {attachment['filename']}",
                f"Status: {attachment['status']}",
                attachment["content"],
            ])

    return "\n".join(section for section in sections if section is not None)


def _build_xml_extraction_prompt_input(
    email: SafeEmail,
    *,
    attachments: list[dict[str, str]],
    candidate_hints: dict[str, list[str]] | None,
) -> str:
    """Build the legacy XML-style email packet for extraction prompts."""
    sections = [
        "<email_packet>",
        f"email_subject: {email.subject}",
        f"email_from: {email.sender}",
        "",
        "<current_message_body>",
        email.body.strip(),
        "</current_message_body>",
    ]

    if candidate_hints is not None:
        sections.extend([
            "",
            "<candidate_hints>",
            f"ticket_candidates: {_format_hint_values(candidate_hints['ticket_candidates'])}",
            f"circuit_candidates: {_format_hint_values(candidate_hints['circuit_candidates'])}",
            f"window_candidates: {_format_hint_values(candidate_hints['window_candidates'])}",
            f"attachment_names: {_format_hint_values(candidate_hints['attachment_names'])}",
            "</candidate_hints>",
        ])

    if attachments:
        sections.extend(["", "<attachments>"])
        for attachment in attachments:
            sections.append(
                f'<attachment filename="{attachment["filename"]}" status="{attachment["status"]}">'
            )
            sections.append(attachment["content"])
            sections.append("</attachment>")
        sections.append("</attachments>")

    sections.append("</email_packet>")
    return "\n".join(section for section in sections if section is not None)


def build_candidate_hints(
    subject: str,
    body: str,
    attachments: list[AttachmentContent],
) -> dict[str, list[str]]:
    """Build lightweight deterministic hints for the LLM extractor."""
    combined_text = "\n".join(part for part in (subject, body) if part)
    ticket_candidates: list[str] = []
    for pattern in _TICKET_PATTERNS:
        ticket_candidates.extend(match.group(0) for match in pattern.finditer(combined_text))

    circuit_candidates = _extract_circuit_candidates(combined_text)
    circuit_candidates.extend(_extract_attachment_circuit_candidates(attachments))

    window_candidates = [match.group(0).strip() for match in _WINDOW_PATTERN.finditer(combined_text)]
    attachment_names = [attachment.filename.strip() for attachment in attachments if attachment.filename.strip()]

    return {
        "ticket_candidates": _dedupe(ticket_candidates),
        "circuit_candidates": _dedupe(circuit_candidates),
        "window_candidates": _dedupe(window_candidates),
        "attachment_names": _dedupe(attachment_names),
    }


def load_csv_prompt_sections(attachments: list[AttachmentContent]) -> list[dict[str, str]]:
    """Load normalized CSV text blocks from materialized attachment content."""
    sections: list[dict[str, str]] = []
    for attachment in attachments:
        filename = attachment.filename.strip()
        if not filename or not filename.lower().endswith(".csv"):
            continue

        rows_text = _read_csv_as_rows_text(attachment.content)
        sections.append({
            "filename": filename,
            "status": "loaded",
            "content": rows_text or "(empty csv)",
        })
    return sections


def _normalize_prompt_email_format(value: str | None) -> PromptEmailFormat:
    """Normalize configured email packet format and validate supported values."""
    normalized = (value or "").strip().lower()
    if not normalized:
        return _DEFAULT_EXTRACTION_PROMPT_EMAIL_FORMAT
    if normalized in _SUPPORTED_EXTRACTION_PROMPT_EMAIL_FORMATS:
        return normalized
    supported = ", ".join(_SUPPORTED_EXTRACTION_PROMPT_EMAIL_FORMATS)
    raise ValueError(
        f"Unsupported extraction prompt email format '{value}'. Expected one of: {supported}."
    )


def _format_hint_values(values: list[str]) -> str:
    """Render candidate-hint lists consistently for prompt sections."""
    return ", ".join(values) if values else "(none)"


def _markdown_inline_text(value: str) -> str:
    """Return a safe inline Markdown value for compact header lines."""
    normalized = value.strip()
    return normalized if normalized else "(empty)"


def _extract_attachment_circuit_candidates(attachments: list[AttachmentContent]) -> list[str]:
    """Mine circuit-like values from materialized CSV attachment content."""
    circuit_candidates: list[str] = []
    for attachment in attachments:
        filename = attachment.filename.strip()
        if not filename or not filename.lower().endswith(".csv"):
            continue

        if not attachment.content.strip():
            continue

        rows_text = _read_csv_as_rows_text(attachment.content)
        circuit_candidates.extend(_extract_circuit_candidates(rows_text))

    return _dedupe(circuit_candidates)


def _extract_circuit_candidates(text: str) -> list[str]:
    """Extract circuit-like identifiers while filtering out obvious date fragments."""
    candidates: list[str] = []
    for pattern in _CIRCUIT_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0).strip()
            if _looks_like_circuit_candidate(value):
                candidates.append(value)
    return _drop_suffix_only_candidates(_dedupe(candidates))


def _looks_like_circuit_candidate(value: str) -> bool:
    """Require at least one alphabetic character so dates like /19/26 are ignored."""
    return bool(re.search(r"[A-Za-z]", value))


def _drop_suffix_only_candidates(values: list[str]) -> list[str]:
    """Drop shorter slash-delimited suffixes when a longer full circuit id is present."""
    filtered: list[str] = []
    for value in values:
        if any(other != value and other.endswith(value) for other in values):
            continue
        filtered.append(value)
    return filtered


def _read_csv_as_rows_text(content: str) -> str:
    """Render CSV content into compact row-oriented text."""
    handle = io.StringIO(content)
    sample = handle.read(4096)
    handle.seek(0)

    try:
        has_header = csv.Sniffer().has_header(sample) if sample.strip() else True
    except csv.Error:
        has_header = False

    rendered_rows: list[str] = []

    if has_header:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader, start=1):
            pairs = [f"{key}={str(value or '').strip()}" for key, value in row.items() if str(value or '').strip()]
            if pairs:
                rendered_rows.append(f"ROW {row_index} | " + " | ".join(pairs))
        return "\n".join(rendered_rows)

    reader = csv.reader(handle)
    for row_index, row in enumerate(reader, start=1):
        values = [value.strip() for value in row if value.strip()]
        if values:
            rendered_rows.append(f"ROW {row_index} | " + " | ".join(values))
    return "\n".join(rendered_rows)


def _dedupe(values: list[str]) -> list[str]:
    """Keep the first occurrence of each non-empty value while preserving order."""
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped
