"""In-process MAF message types exchanged between workflow executors.

Distinct from ``workflow.queue_envelopes``, which holds the on-the-wire
Service Bus envelopes. This package groups the in-process types by
workflow phase:

* ``email``         — ingest, validation, preprocessing
* ``extraction``    — LLM-extracted fields before normalization
* ``circuits``      — circuit-resolution lookup results
* ``normalization`` — validated/normalized fields ready for HITL review
* ``hitl``          — cross-phase HITL pause-request payload (operations + draft)
* ``operations``    — approved operations plan and command result
* ``draft``         — generated reply drafts and reviewed drafts

All public types are re-exported here so existing imports
(``from workflow.messages import …``) continue to work unchanged.

Note: classes' ``__module__`` reflects their defining submodule, so the
``ALLOWED_CHECKPOINT_TYPES`` allow-list in ``workflow.builder`` must use
the full submodule path (e.g. ``workflow.messages.email:EmailDoc``).
Bump checkpoints when adding/moving types — see README troubleshooting.
"""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations and rejects string forms).

from workflow.extraction_schema import (
    MaintenanceAsset,
    MaintenanceEmailFields,
    MaintenanceScope,
    MaintenanceWindow,
)
from workflow.messages.circuits import (
    CircuitResolution,
    MadRouterRow,
    ResolvedCircuit,
    UnmatchedCircuit,
)
from workflow.messages.draft import DraftReply, ReviewedDraft
from workflow.messages.email import (
    AttachmentContent,
    CleanEmail,
    EmailDoc,
    RejectedEmail,
    SafeEmail,
    ValidatedEmail,
)
from workflow.messages.extraction import ExtractedFields
from workflow.messages.hitl import HitlRequest
from workflow.messages.normalization import DuplicateChgMatch, NormalizedFields
from workflow.messages.operations import (
    ApprovedOperationsPlan,
    CommandResult,
    OperationsRequest,
)

__all__ = [
    # extraction_schema re-exports
    "MaintenanceAsset",
    "MaintenanceEmailFields",
    "MaintenanceScope",
    "MaintenanceWindow",
    # email lifecycle
    "AttachmentContent",
    "CleanEmail",
    "EmailDoc",
    "RejectedEmail",
    "SafeEmail",
    "ValidatedEmail",
    # extraction
    "ExtractedFields",
    # circuit resolution
    "CircuitResolution",
    "MadRouterRow",
    "ResolvedCircuit",
    "UnmatchedCircuit",
    # normalization
    "DuplicateChgMatch",
    "NormalizedFields",
    # HITL pause payload (cross-phase: operations + draft review)
    "HitlRequest",
    # operations
    "ApprovedOperationsPlan",
    "CommandResult",
    "OperationsRequest",
    # draft
    "DraftReply",
    "ReviewedDraft",
]
