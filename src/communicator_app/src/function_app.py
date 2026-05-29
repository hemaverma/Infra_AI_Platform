"""Azure Functions v2 host for the vendor-email-response workflow.

Architecture alignment (see `docs/design/architecture.md` §3.4):

* The logical inbound queue `%WorkflowQueueName%` and outbound queue
    `%HitlQueueName%` are shared across transport types.
* Service Bus registration is gated by `ENABLE_SERVICEBUS_TRIGGERS`.
* Azure Storage Queue registration is gated by
    `ENABLE_STORAGE_QUEUE_TRIGGERS`.
* An optional HTTP twin `/api/workflow-queue` (gated by
    `ENABLE_HTTP_TEST_TRIGGERS`) accepts the exact same envelopes for local
    end-to-end testing without queue infrastructure. The HTTP path returns the
    envelopes that *would* have been published to `hitl-queue` in the response
    body so callers can inspect transport without binding to a queue transport.

Checkpoint and transport identifiers
------------------------------------
Per architecture §3.4 the workflow transport currently carries three related
identifiers:

* `workflowInstanceId` — embedded in `Workflow.name` via `build_workflow_name`.
    This participates in checkpoint lookup because the host uses it when
    rebuilding the workflow instance.
* `workflowPrefix` — opaque transport metadata echoed on HITL envelopes. It is
    currently used as a storage-oriented handle, but it does not participate in
    checkpoint creation or checkpoint lookup.
* `checkpointId` — the MAF checkpoint id selected after each paused superstep
    by inspecting the workflow instance's visible checkpoints and choosing the
    newest checkpoint that still carries pending HITL state.

The host never trusts MAF's per-event `request_id` across the wire — it is
re-derived on resume by replaying the rehydrate stream and capturing the
re-emitted `request_info` event id. See workflow_runner module for details.
"""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations and rejects string forms).

import os

import azure.functions as func
from debug_listener import start_debug_listener

start_debug_listener()

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Register Service Bus trigger if enabled
if os.getenv("ENABLE_SERVICEBUS_TRIGGERS", "false").lower() in ("true", "1", "yes"):
    from function_app_sb import bp as sb_bp
    app.register_blueprint(sb_bp)

# Register Storage Queue trigger if enabled (enabled by default)
if os.getenv("ENABLE_STORAGE_QUEUE_TRIGGERS", "true").lower() in ("true", "1", "yes"):
    from function_app_queue import bp as queue_bp
    app.register_blueprint(queue_bp)

# Register HTTP test endpoint if enabled (enabled by default)
if os.getenv("ENABLE_HTTP_TEST_TRIGGERS", "true").lower() in ("true", "1", "yes"):
    from function_app_http import bp as http_bp
    app.register_blueprint(http_bp)
