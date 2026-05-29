# workflow/clients/blob_client.py
"""Azure Blob Storage helpers for the vendor-email pipeline.

Per architecture.md §3.4, the upstream email communicator Logic App stages
each message in a single configured container (default `email-staging`)
under a per-instance prefix:

```text
<container>/
  <storage_prefix>/
    email.json
    attachments/
      001-original.pdf
      002-circuit-list.xlsx
```

`storage_prefix` is opaque to this module — today it equals
`workflowInstanceId`, but downstream code must not rely on that. The
`email.json` `attachments` field carries **filenames only** (e.g.
`"001-original.pdf"`) which resolve against `<storage_prefix>/attachments/`.

This module wraps the small surface of `azure-storage-blob` we need:

- `download_email_json(storage_prefix)` — fetch and parse the staged
    `email.json` payload.
- `build_attachment_blob_paths(filenames, storage_prefix)` — convert staged
    attachment filenames into container-relative blob paths.
- `download_attachment_blobs(blob_names)` — download staged attachment blobs
    into a local temp directory and return the local paths.
- `upload_json_artifact(storage_prefix, artifact_name, payload)` — upload a
    JSON artifact under the same staged prefix as `email.json`.

Auth follows the same pattern as `workflow/agent.py`: `AzureCliCredential`
when `AUTH_MODE=azurecli`, otherwise `DefaultAzureCredential`.

Configuration (read from env / `local.settings.json`):

- `EMAIL_BLOB_ACCOUNT_URL` — e.g. `https://<account>.blob.core.windows.net`.
    Required for runtime ingest and attachment download.
- `EMAIL_BLOB_CONTAINER` — fixed staging container name. Defaults to
  `email-staging` per the architecture contract.

Downloaded blobs are staged under `<tempdir>/vendor-email-staging/` using the
blob path layout so downstream executors can read them from disk.
"""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations and rejects string forms).

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import AzureCliCredential, DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_EMAIL_JSON_NAME = "email.json"
_ATTACHMENTS_SUBDIR = "attachments"
_DEFAULT_CONTAINER = "email-staging"
_DEFAULT_LOCAL_DIR_NAME = "vendor-email-staging"
_JSON_CONTENT_TYPE = "application/json; charset=utf-8"


def _credential():
    """Credential matching the auth selection in `workflow/agent.py`."""
    if os.getenv("AUTH_MODE", "").lower() == "azurecli":
        return AzureCliCredential()
    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


def _container_name() -> str:
    """Return the staging container; defaults to `email-staging` per the contract."""
    return os.environ.get("EMAIL_BLOB_CONTAINER", _DEFAULT_CONTAINER)


def _normalize_prefix(storage_prefix: str) -> str:
    """Strip surrounding slashes; `storage_prefix` is opaque otherwise."""
    return storage_prefix.strip("/")


def _local_staging_root() -> Path:
    """Return the fixed local temp root used to stage downloaded blobs."""
    root = Path(tempfile.gettempdir()) / _DEFAULT_LOCAL_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def _local_path_for_blob(blob_name: str) -> Path:
    """Map a container-relative blob path to a safe local temp path."""
    parts = [part for part in blob_name.split("/") if part]
    if not parts or any(part in (".", "..") for part in parts):
        raise ValueError(f"blob path {blob_name!r} is not a safe relative blob path")
    return _local_staging_root().joinpath(*parts)


def _safe_filename(filename: str) -> str:
    """Reject path traversal / absolute paths embedded in attachment filenames."""
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name:
        raise ValueError(f"attachment filename {filename!r} is not a simple file name")
    return safe_name


def build_attachment_blob_paths(filenames: list[str], storage_prefix: str) -> list[str]:
    """Build container-relative blob paths for staged attachments."""
    blob_prefix = _normalize_prefix(storage_prefix)
    attachment_paths: list[str] = []
    for filename in filenames:
        safe_name = _safe_filename(filename)
        if blob_prefix:
            attachment_paths.append(f"{blob_prefix}/{_ATTACHMENTS_SUBDIR}/{safe_name}")
        else:
            attachment_paths.append(f"{_ATTACHMENTS_SUBDIR}/{safe_name}")
    return attachment_paths


def _download_blob(svc: BlobServiceClient, container: str, blob_name: str, dest: Path) -> Path:
    """Download `<container>/<blob_name>` to `dest`, replacing any prior local copy."""
    logger.info("blob_client: downloading container=%s blob=%s dest=%s", container, blob_name, dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    blob = svc.get_blob_client(container=container, blob=blob_name)
    try:
        stream = blob.download_blob()
        # Write to a sibling temp file then rename so a partial download never
        # leaves a truncated file at the stable local path.
        tmp = dest.with_suffix(dest.suffix + ".part")
        with tmp.open("wb") as fp:
            for chunk in stream.chunks():
                fp.write(chunk)
        tmp.replace(dest)
    except ResourceNotFoundError:
        logger.error("blob_client: blob not found container=%s blob=%s", container, blob_name)
        raise
    return dest


def _serialize_json_payload(payload: Any) -> bytes:
    """Serialize a payload to UTF-8 JSON bytes."""
    if isinstance(payload, BaseModel):
        data = payload.model_dump(mode="json")
    else:
        data = payload
    return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")


def download_email_json(storage_prefix: str) -> dict:
    """Download and parse `<storage_prefix>/email.json` from Blob Storage."""
    account_url = os.environ["EMAIL_BLOB_ACCOUNT_URL"]
    container = _container_name()
    blob_prefix = _normalize_prefix(storage_prefix)
    blob_name = f"{blob_prefix}/{_EMAIL_JSON_NAME}" if blob_prefix else _EMAIL_JSON_NAME
    dest = _local_path_for_blob(blob_name)

    credential = _credential()
    try:
        with BlobServiceClient(account_url=account_url, credential=credential) as svc:
            _download_blob(svc, container, blob_name, dest)
    finally:
        credential.close()

    with dest.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def upload_json_artifact(storage_prefix: str, artifact_name: str, payload: Any) -> str | None:
    """Upload a JSON artifact under `<storage_prefix>/` and return its blob name."""
    blob_prefix = _normalize_prefix(storage_prefix)
    if not blob_prefix:
        logger.warning(
            "blob_client: skipping artifact upload for %s because storage_prefix is empty",
            artifact_name,
        )
        return None

    account_url = os.environ["EMAIL_BLOB_ACCOUNT_URL"]
    container = _container_name()
    safe_artifact_name = _safe_filename(artifact_name)
    blob_name = f"{blob_prefix}/{safe_artifact_name}"
    body = _serialize_json_payload(payload)

    credential = _credential()
    try:
        with BlobServiceClient(account_url=account_url, credential=credential) as svc:
            logger.info("blob_client: uploading container=%s blob=%s", container, blob_name)
            blob = svc.get_blob_client(container=container, blob=blob_name)
            blob.upload_blob(
                body,
                overwrite=True,
                content_settings=ContentSettings(content_type=_JSON_CONTENT_TYPE),
            )
    finally:
        credential.close()

    return blob_name


def download_attachment_blobs(blob_names: list[str]) -> list[Path]:
    """Download staged attachment blobs and return their local temp paths."""
    if not blob_names:
        return []

    account_url = os.environ["EMAIL_BLOB_ACCOUNT_URL"]
    container = _container_name()

    paths: list[Path] = []
    credential = _credential()
    try:
        with BlobServiceClient(account_url=account_url, credential=credential) as svc:
            for blob_name in blob_names:
                dest = _local_path_for_blob(blob_name)
                paths.append(_download_blob(svc, container, blob_name, dest))
    finally:
        credential.close()
    return paths
