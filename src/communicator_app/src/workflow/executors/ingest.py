"""EmailIngestExecutor: resolve a `workflow-queue` start envelope into a typed `EmailDoc`.

The host (`function_app.py`) hands this executor the snake_case form of the
architecture's `email.received` envelope. The executor:

1. Pulls the architecture identifiers (`workflow_instance_id`,
   `internet_message_id`, `received_at`, `storage_prefix`) directly off the
   envelope.
2. Downloads the staged `email.json` payload from Azure Blob Storage at
   `<container>/<storage_prefix>/email.json` (architecture.md §3.4) and
   lifts the sender/subject/body/attachments off it. The container is
   configuration (`EMAIL_BLOB_CONTAINER`, default `email-staging`); the
   `storage_prefix` is opaque per the contract.
3. Converts each attachment filename in `email.json` into a staged blob path
    under `<storage_prefix>/attachments/` and carries those blob paths forward.
    `PreprocessExecutor` performs the actual download.
4. Emits a fully-populated `EmailDoc` for the rest of the pipeline.
"""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations and rejects string forms).

import logging
import os
from datetime import datetime
from pathlib import Path

from agent_framework import Executor, WorkflowContext, handler

from workflow.clients.blob_client import (
    build_attachment_blob_paths,
    download_email_json,
)
from workflow.messages import EmailDoc
from workflow.state_snapshots import stash_json_state

logger = logging.getLogger(__name__)

# Default allow-list. CSV is the only format the downstream extractor handles
# today; PDF/XLSX/etc. are ignored until preprocess gains a parser. Override
# with `EMAIL_ALLOWED_ATTACHMENT_EXTENSIONS` (comma-separated, no leading dot,
# case-insensitive). Set to `*` to disable filtering.
_DEFAULT_ALLOWED_EXTENSIONS = "csv"


def _allowed_extensions() -> set[str] | None:
    """Return the lowercase extension allow-list, or `None` to allow everything."""
    raw = os.environ.get("EMAIL_ALLOWED_ATTACHMENT_EXTENSIONS", _DEFAULT_ALLOWED_EXTENSIONS)
    if raw.strip() == "*":
        return None
    return {ext.strip().lower().lstrip(".") for ext in raw.split(",") if ext.strip()}


def _filter_attachments(filenames: list[str]) -> list[str]:
    """Drop attachments whose extension is not in the allow-list; log each skip."""
    allowed = _allowed_extensions()
    if allowed is None:
        return filenames
    kept: list[str] = []
    for name in filenames:
        ext = Path(name).suffix.lower().lstrip(".")
        if ext in allowed:
            kept.append(name)
        else:
            logger.warning(
                "email_ingest: skipping attachment %r (extension %r not in allow-list %s)",
                name, ext, sorted(allowed),
            )
    return kept


def _parse_received_at(value) -> datetime:
    """Coerce the envelope's `received_at` (datetime or ISO 8601 string) to `datetime`."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Pydantic round-trips with `Z` suffix; fromisoformat needs `+00:00`.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise TypeError(f"received_at must be datetime or ISO 8601 string, got {type(value).__name__}")


class EmailIngestExecutor(Executor):
    """Resolve the start envelope into a typed `EmailDoc` for the downstream graph."""

    def __init__(self) -> None:
        """Initialize with executor id."""
        super().__init__(id="email_ingest")

    @handler
    async def ingest(self, payload: dict, ctx: WorkflowContext[EmailDoc]) -> None:
        """Resolve the start envelope into a typed EmailDoc."""
        workflow_instance_id = payload["workflowInstanceId"]
        internet_message_id = payload["internetMessageId"]
        received_at = _parse_received_at(payload["receivedAt"])
        storage_prefix = payload["storagePrefix"]

        ctx.set_state("workflow_instance_id", workflow_instance_id)

        # `attachments` carries staged blob paths, not downloaded local files.
        # That keeps ingest focused on metadata resolution and avoids local file
        # side effects before validation has run. Preprocess performs the actual
        # download and any later text extraction / merge.
        email_json = download_email_json(storage_prefix)
        attachment_filenames = _filter_attachments(
            list(email_json.get("attachments", []) or [])
        )
        attachments = build_attachment_blob_paths(attachment_filenames, storage_prefix)

        email_doc = EmailDoc(
            workflow_instance_id=workflow_instance_id,
            internet_message_id=internet_message_id,
            received_at=received_at,
            storage_prefix=storage_prefix,
            subject=email_json.get("subject", ""),
            sender=email_json.get("senderEmail", ""),
            body=email_json.get("body", ""),
            attachments=attachments,
        )
        stash_json_state(ctx, "email_doc", email_doc)
        await ctx.send_message(email_doc)
