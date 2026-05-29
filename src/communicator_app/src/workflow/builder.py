# workflow/builder.py
"""Wire the per-step executors into the vendor-email-response workflow graph.

Single source of truth for `BASE_WORKFLOW_NAME`, the on-disk `CHECKPOINT_DIR`,
and the `allowed_checkpoint_types` allow-list. `function_app.py` imports
`build_storage` and `build_workflow` from here so the Service Bus consumer and
the HTTP test trigger share an identical graph. Happy-path approvals continue
through the operations command and draft sending; valid rejections branch to
the shared `terminate_rejected` terminal executor.
"""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations and rejects string forms).

import os
from pathlib import Path
from typing import Callable, Mapping

from agent_framework import CheckpointStorage, Workflow, WorkflowBuilder
from azure.identity import AzureCliCredential, DefaultAzureCredential

from workflow.checkpoint_storage import Utf8FileCheckpointStorage
from workflow.executors.content_safety import ContentSafetyExecutor
from workflow.executors.draft_reply import DraftReplyExecutor
from workflow.executors.email_validate import EmailValidateExecutor
from workflow.executors.extract import FieldExtractionExecutor
from workflow.executors.hitl_review_draft import HitlReviewDraftExecutor
from workflow.executors.hitl_operations_approval import HitlOperationsApprovalExecutor
from workflow.executors.ingest import EmailIngestExecutor
from workflow.executors.preprocess import PreprocessExecutor
from workflow.executors.send_reply import SendReplyExecutor
from workflow.executors.terminate_rejected import TerminateRejectedExecutor
from workflow.executors.validate_normalize import ValidateNormalizeExecutor
from workflow.executors.operations_command import OperationsCommandExecutor
from workflow.messages import RejectedEmail, ValidatedEmail

# Resolve `<app-root>/checkpoints/` regardless of CWD so the Service Bus
# consumer and the HTTP test trigger hit the same directory inside the
# Functions container.
CHECKPOINT_DIR = Path(__file__).resolve().parent.parent / "checkpoints"
# Base name only; per-instance `Workflow.name` is composed by
# `build_workflow_name` so checkpoint storage can address one workflow
# instance per inbound email.
BASE_WORKFLOW_NAME = "vendor-email-response"

# Allow-list of every dataclass that travels through the workflow. Both
# `FileCheckpointStorage` and `CosmosCheckpointStorage` rehydrate these by
# import path; missing entries surface at resume time as deserialization
# errors. `MaintenanceEmailFields` is included because it is nested inside
# `ExtractedFields`, `NormalizedFields`, and `CommandResult`. Keep entries
# one-per-line with a trailing comment so future additions follow the
# convention.
ALLOWED_CHECKPOINT_TYPES = [
    "workflow.extraction_schema:MaintenanceEmailFields",  # nested inside Extracted/Normalized/CommandResult
    "workflow.extraction_schema:MaintenanceWindow",  # nested inside MaintenanceEmailFields
    "workflow.extraction_schema:MaintenanceAsset",  # nested inside MaintenanceEmailFields
    "workflow.extraction_schema:MaintenanceScope",  # nested inside MaintenanceEmailFields
    "pydantic_core._pydantic_core:TzInfo",  # timezone-aware datetime fields (received_at)
    # workflow.messages package — entries reflect the defining submodule (not the
    # `__init__` re-export path) because Pydantic preserves `__module__` from
    # the class definition, which is what checkpoint rehydration matches.
    "workflow.messages.email:EmailDoc",  # ingest output; carries internet_message_id + attachments
    "workflow.messages.email:ValidatedEmail",  # email_validate pass output
    "workflow.messages.email:RejectedEmail",  # email_validate reject output; consumed by terminate_rejected
    "workflow.messages.email:AttachmentContent",  # materialized attachment text
    "workflow.messages.email:CleanEmail",  # preprocess output
    "workflow.messages.email:SafeEmail",  # content_safety output
    "workflow.messages.extraction:ExtractedFields",  # extract output
    "workflow.messages.circuits:ResolvedCircuit",  # nested inside CircuitResolution
    "workflow.messages.circuits:UnmatchedCircuit",  # nested inside CircuitResolution
    "workflow.messages.circuits:MadRouterRow",  # nested inside CircuitResolution
    "workflow.messages.circuits:CircuitResolution",  # nested inside NormalizedFields
    "workflow.messages.normalization:DuplicateChgMatch",  # nested inside NormalizedFields
    "workflow.messages.normalization:NormalizedFields",  # validate_normalize output; HITL pause #1 input
    "workflow.messages.hitl:HitlRequest",  # cross-phase HITL request_info payload (operations approval + draft review)
    "workflow.messages.operations:OperationsRequest",  # nested inside ApprovedOperationsPlan
    "workflow.messages.operations:ApprovedOperationsPlan",  # HITL pause #1 response replay output
    "workflow.messages.operations:CommandResult",  # operations_command output
    "workflow.messages.draft:DraftReply",  # draft_reply output
    "workflow.messages.draft:ReviewedDraft",  # HITL pause #2 response replay output
]


def _approval_decision(message: object) -> bool:
    """Return the branch-driving approval decision from a HITL response message."""
    approved = getattr(message, "approved", None)
    if type(approved) is not bool:
        raise ValueError(
            "workflow approval routing requires a boolean 'approved' field; "
            f"got {type(approved).__name__}"
        )
    return approved


def _is_approved(message: object) -> bool:
    """Select the happy path for valid approvals."""
    return _approval_decision(message) is True


def _is_rejected(message: object) -> bool:
    """Select the shared rejection terminal for valid rejections."""
    return _approval_decision(message) is False


def _is_validated(message: object) -> bool:
    """Route email_validate pass results onward to preprocess."""
    return isinstance(message, ValidatedEmail)


def _is_validation_rejected(message: object) -> bool:
    """Route email_validate failures to the shared rejection terminal."""
    return isinstance(message, RejectedEmail)


def build_workflow_name(workflow_instance_id: str) -> str:
    """Compose the per-instance MAF `Workflow.name`.

    `workflow_instance_id` is the architecture's `workflowInstanceId` carried on
    every inbound `workflow-queue` envelope; embedding it here is what lets the
    host enumerate checkpoints for one workflow instance at a time when it
    resolves paused HITL state.
    """
    return f"{BASE_WORKFLOW_NAME}-{workflow_instance_id}"


def _cosmos_credential() -> object:
    """Resolve the credential passed to `CosmosCheckpointStorage`.

    Cosmos checkpoint storage uses RBAC-only auth. Local development can opt
    into `AzureCliCredential` with `AUTH_MODE=azurecli`; all other environments
    use `DefaultAzureCredential` (managed identity in ACA / Azure Functions).
    """
    auth_mode = os.getenv("AUTH_MODE", "")
    if auth_mode.lower() == "azurecli":
        return AzureCliCredential()
    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


# ---------------------------------------------------------------------------
# Checkpoint storage factory
# ---------------------------------------------------------------------------
# Each provider is implemented as a zero-arg callable that reads its own env
# vars and returns a `CheckpointStorage`. New providers register themselves in
# `_STORAGE_FACTORIES` below; `build_storage()` is a thin lookup that dispatches
# on `VENDOR_CHECKPOINT_PROVIDER`. This keeps the cosmos dependency import lazy
# (file-only deployments don't need it installed) and keeps the factory open for
# future backends (Redis, SQL, etc.) without touching the dispatcher.


def _file_checkpoint_storage() -> CheckpointStorage:
    """Local on-disk checkpoints under `<app-root>/checkpoints/`."""
    return Utf8FileCheckpointStorage(
        CHECKPOINT_DIR,
        allowed_checkpoint_types=ALLOWED_CHECKPOINT_TYPES,
    )


def _cosmos_checkpoint_storage() -> CheckpointStorage:
    """Azure Cosmos DB checkpoints for multi-replica ACA deploys."""
    try:
        from agent_framework_azure_cosmos import CosmosCheckpointStorage
    except ImportError as exc:
        raise RuntimeError(
            "VENDOR_CHECKPOINT_PROVIDER=cosmos but agent-framework-azure-cosmos "
            "is not installed. Add it to requirements.txt and reinstall."
        ) from exc

    return CosmosCheckpointStorage(
        endpoint=os.getenv("AZURE_COSMOS_ENDPOINT"),
        database_name=os.getenv("AZURE_COSMOS_DATABASE_NAME"),
        container_name=os.getenv("AZURE_COSMOS_CONTAINER_NAME"),
        credential=_cosmos_credential(),
        allowed_checkpoint_types=ALLOWED_CHECKPOINT_TYPES,
    )


_STORAGE_FACTORIES: Mapping[str, Callable[[], CheckpointStorage]] = {
    "file": _file_checkpoint_storage,
    "cosmos": _cosmos_checkpoint_storage,
}

DEFAULT_CHECKPOINT_PROVIDER = "file"


def build_storage(provider: str | None = None) -> CheckpointStorage:
    """Build the workflow's checkpoint storage by provider name.

    Resolution order: explicit `provider` arg → `VENDOR_CHECKPOINT_PROVIDER` env
    var → `DEFAULT_CHECKPOINT_PROVIDER`. Unknown providers raise `ValueError`
    listing the registered names so misconfigurations surface at startup, not
    at first checkpoint write.
    """
    if provider is None:
        provider = os.getenv("VENDOR_CHECKPOINT_PROVIDER", DEFAULT_CHECKPOINT_PROVIDER)
    key = provider.lower()
    try:
        factory = _STORAGE_FACTORIES[key]
    except KeyError as exc:
        valid = ", ".join(sorted(_STORAGE_FACTORIES))
        raise ValueError(
            f"Unknown checkpoint provider {provider!r}. Valid options: {valid}."
        ) from exc
    return factory()


def build_workflow(storage: CheckpointStorage, workflow_instance_id: str) -> Workflow:
    """Instantiate executors and chain them into the v1 linear graph.

    `workflow_instance_id` is required: `Workflow.name` embeds it so the host can
    address one MAF workflow instance per inbound email envelope when checking
    idempotency and when resolving paused HITL checkpoints. Inbound
    `workflow-queue` envelopes always carry the `workflowInstanceId`.
    Pre-flight validation failures and rejections from either HITL pause are
    routed to `TerminateRejectedExecutor`; only validated/approved messages
    stay on the send-email path.
    """
    ingest = EmailIngestExecutor()
    email_validate = EmailValidateExecutor()
    preprocess = PreprocessExecutor()
    content_safety = ContentSafetyExecutor()
    extract = FieldExtractionExecutor()
    validate_normalize = ValidateNormalizeExecutor()
    hitl_operations_approval = HitlOperationsApprovalExecutor()
    operations_command = OperationsCommandExecutor()
    draft_reply = DraftReplyExecutor()
    hitl_review = HitlReviewDraftExecutor()
    send_reply = SendReplyExecutor()
    terminate_rejected = TerminateRejectedExecutor()

    return (
        WorkflowBuilder(
            start_executor=ingest,
            name=build_workflow_name(workflow_instance_id),
            checkpoint_storage=storage,
        )
        .add_edge(ingest, email_validate)
        .add_edge(email_validate, preprocess, condition=_is_validated)
        .add_edge(email_validate, terminate_rejected, condition=_is_validation_rejected)
        .add_edge(preprocess, content_safety)
        .add_edge(content_safety, extract)
        .add_edge(extract, validate_normalize)
        .add_edge(validate_normalize, hitl_operations_approval)
        .add_edge(hitl_operations_approval, operations_command, condition=_is_approved)
        .add_edge(hitl_operations_approval, terminate_rejected, condition=_is_rejected)
        .add_edge(operations_command, draft_reply)
        .add_edge(draft_reply, hitl_review)
        .add_edge(hitl_review, send_reply, condition=_is_approved)
        .add_edge(hitl_review, terminate_rejected, condition=_is_rejected)
        .build()
    )
