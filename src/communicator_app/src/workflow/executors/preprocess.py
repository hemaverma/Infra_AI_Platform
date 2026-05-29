"""Preprocess email bodies and materialize CSV attachments.

Cleaning policy for HTML email bodies:
- keep only heading and table tags: h1-h6, table, thead, tbody, tfoot, tr, th, td, caption
- convert br tags to newline text
- add newline boundaries for div, p, and li before unwrapping them
- decompose noisy tags such as script, style, head, meta, title, iframe, svg, and form controls
- unwrap all other remaining tags so visible text is preserved without keeping extra markup
"""

import logging
import re
from pathlib import Path

from agent_framework import Executor, WorkflowContext, handler
from bs4 import BeautifulSoup, Comment

from workflow.clients.blob_client import download_attachment_blobs
from workflow.messages import AttachmentContent, CleanEmail, ValidatedEmail
from workflow.state_snapshots import stash_json_state

logger = logging.getLogger(__name__)

_DROP_TAGS = {
    "button",
    "canvas",
    "embed",
    "form",
    "head",
    "iframe",
    "img",
    "input",
    "label",
    "link",
    "meta",
    "noscript",
    "object",
    "option",
    "script",
    "select",
    "style",
    "svg",
    "textarea",
    "title",
}
_KEPT_TAGS = {
    "caption",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
}
_NEWLINE_BOUNDARY_TAGS = ("div", "li", "p")
_ALLOWED_ATTRIBUTES = {
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
}


def _normalize_text(value: str) -> str:
    """Collapse whitespace while preserving paragraph boundaries."""
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    normalized_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.split("\n")]

    collapsed_lines: list[str] = []
    previous_blank = True
    for line in normalized_lines:
        if not line:
            if not previous_blank and collapsed_lines:
                collapsed_lines.append("")
            previous_blank = True
            continue
        collapsed_lines.append(line)
        previous_blank = False

    while collapsed_lines and not collapsed_lines[-1]:
        collapsed_lines.pop()

    return "\n".join(collapsed_lines)


def _normalize_text_nodes(soup: BeautifulSoup) -> None:
    """Replace non-breaking spaces in text nodes without flattening the HTML tree."""
    for text_node in list(soup.find_all(string=True)):
        if isinstance(text_node, Comment):
            text_node.extract()
            continue
        updated_value = str(text_node).replace("\xa0", " ")
        if updated_value != str(text_node):
            text_node.replace_with(updated_value)


def _strip_unwanted_attributes(tag) -> None:
    """Remove styling, event handlers, and nonessential attributes from a kept tag."""
    allowed_attributes = _ALLOWED_ATTRIBUTES.get(tag.name, set())
    for attribute_name in list(tag.attrs):
        normalized_name = attribute_name.lower()
        if normalized_name.startswith("on") or normalized_name == "style":
            del tag.attrs[attribute_name]
            continue
        if normalized_name in {"class", "id", "data-testid"}:
            del tag.attrs[attribute_name]
            continue
        if normalized_name not in allowed_attributes:
            del tag.attrs[attribute_name]


def _prepare_tag_for_unwrap(tag) -> None:
    """Add newline text for common block wrappers before unwrapping them."""
    if tag.name in _NEWLINE_BOUNDARY_TAGS and (not tag.contents or str(tag.contents[-1]) != "\n"):
        tag.append("\n")


def _sanitize_tags(soup: BeautifulSoup) -> None:
    """Keep only heading and table tags, dropping or unwrapping the rest."""
    for tag in list(soup.find_all(True)):
        if tag.parent is None:
            continue
        if tag.name in _DROP_TAGS:
            tag.decompose()
            continue
        if tag.name == "br":
            tag.replace_with("\n")
            continue
        if tag.name in _KEPT_TAGS:
            _strip_unwanted_attributes(tag)
            continue
        _prepare_tag_for_unwrap(tag)
        if tag.parent is not None:
            tag.unwrap()


def _serialize_sanitized_html(soup: BeautifulSoup) -> str:
    """Return sanitized body markup without document-level wrappers when possible."""
    container = soup.body or soup
    html = "".join(str(child) for child in container.contents).strip()
    html = re.sub(r"[ \t]+\n", "\n", html)
    html = re.sub(r"\n[ \t]+", "\n", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def _clean_email_body(body: str) -> str:
    """Convert likely-HTML email bodies into lightly sanitized HTML."""
    if not body:
        return ""

    soup = BeautifulSoup(body, "html.parser")
    if not soup.find(True):
        return _normalize_text(soup.get_text())

    _normalize_text_nodes(soup)
    _sanitize_tags(soup)
    return _serialize_sanitized_html(soup)


def _load_csv_attachments(blob_names: list[str]) -> list[AttachmentContent]:
    """Download staged CSV blobs and return filename/content payloads."""
    attachments: list[AttachmentContent] = []
    for path in download_attachment_blobs(blob_names):
        resolved_path = Path(path)
        if resolved_path.suffix.lower() != ".csv":
            continue
        attachments.append(AttachmentContent(
            filename=resolved_path.name,
            content=resolved_path.read_text(encoding="utf-8-sig", errors="replace"),
        ))
    return attachments


class PreprocessExecutor(Executor):
    """Sanitize email HTML using the module policy and materialize CSV payloads."""

    def __init__(self) -> None:
        """Initialize with executor id."""
        super().__init__(id="preprocess")

    @handler
    async def preprocess(self, validated: ValidatedEmail, ctx: WorkflowContext[CleanEmail]) -> None:
        """Preprocess the validated email into a sanitized HTML format."""
        materialized_attachments = _load_csv_attachments(validated.attachments)
        cleaned_body = _clean_email_body(validated.body)

        clean_email = CleanEmail(
            workflow_instance_id=validated.workflow_instance_id,
            internet_message_id=validated.internet_message_id,
            received_at=validated.received_at,
            storage_prefix=validated.storage_prefix,
            subject=validated.subject,
            sender=validated.sender,
            body=cleaned_body,
            attachments=materialized_attachments,
            notes={},
        )
        stash_json_state(ctx, "clean_email", clean_email)
        await ctx.send_message(clean_email)
