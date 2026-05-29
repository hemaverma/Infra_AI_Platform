---
description: Runtime guide for the communicator app and its approval-driven workflow behavior.
author: NExT team
ms.date: 2026-05-11
ms.topic: how-to
keywords:
  - communicator app
  - workflow
  - hitl
  - service bus
  - requests
estimated_reading_time: 10
---

<!-- markdownlint-disable MD013 -->

# Vendor Email Response App

## What this demonstrates

A Python Azure Functions v2 app for Azure Container Apps that implements the
**Agent Workflow** half of the dual-workflow architecture in
[`design/architecture.md`](../../design/architecture.md) §3.4. The app
consumes envelopes from the logical `workflow-queue` transport surface, drives a
Microsoft Agent Framework workflow built from eleven per-step `Executor`
modules, pauses twice for human-in-the-loop (HITL) review by publishing
envelopes to the logical `hitl-queue`, and resumes when the matching
`approval.responded` envelope returns on `workflow-queue`.

The workflow now branches explicitly after each HITL pause. Approved responses
continue on the main path. Valid business rejections terminate through the
shared `terminate_rejected` executor. Invalid approval input is an error path,
not a business-terminal branch.

Two executors call the LLM end-to-end so the agent factory wiring is exercised: `FieldExtractionExecutor` (always on) and `DraftReplyExecutor` (gated on `ENABLE_AGENT_EMAIL_DRAFT=true`).

## Architecture

![Agent Workflow Architecture](assets/agent-workflow-architecture.drawio.png)

Workflow graph (explicit approve or reject branches after each HITL gate):

![Agent Workflow Graph](assets/agent-workflow-graph.drawio.png)

### Three identifiers

- `workflowInstanceId`: Owned by the email-ingest stage upstream. Embedded in
  `Workflow.name = f"{BASE_WORKFLOW_NAME}-{workflowInstanceId}"` so each email
  has its own checkpoint stream. Carried on every envelope.
- `checkpointId`: Owned by `CheckpointStorage`. Identifies the specific paused
  state. Minted per pause, returned to `hitl-queue`, replayed on
  `approval.responded`.
- MAF `request_id`: Owned by the MAF runtime and kept host-internal.
  Re-discovered by replaying the rehydrated workflow stream and capturing the
  `request_info` event for that checkpoint. Never carried on the wire.

Durable state lives in `./checkpoints/` via `FileCheckpointStorage` by default. Set `VENDOR_CHECKPOINT_PROVIDER=cosmos` (with `AZURE_COSMOS_ENDPOINT` / `AZURE_COSMOS_DATABASE_NAME` / `AZURE_COSMOS_CONTAINER_NAME`) to swap in `CosmosCheckpointStorage` for multi-replica ACA deploys. Cosmos auth is RBAC-only via `AzureCliCredential` or `DefaultAzureCredential`, and both providers go through the single `build_storage()` factory in `workflow/builder.py`.

> [!IMPORTANT]
> Cosmos checkpoint bootstrap currently requires the database and container to exist ahead of time when you authenticate with Microsoft Entra ID and native RBAC. The installed `agent-framework-azure-cosmos` package tries to auto-create them on first use, but that path issues `create_database_if_not_exists()` and `create_container_if_not_exists()` calls and can fail with `CosmosHttpResponseError: (Forbidden) ... POST /dbs/<db>/colls/ ... cannot be authorized by AAD token in data plane`.
>
> Pre-create the resources before setting `VENDOR_CHECKPOINT_PROVIDER=cosmos`. With the checked-in app settings, use database `vendor-email-response`, container `workflow-checkpoints`, and partition key `/workflow_name`. If you override the Cosmos env vars, create resources that match those values instead.
> [!NOTE]
> If the app can save and resume Cosmos-backed checkpoints but the Azure portal cannot browse `workflow-checkpoints`, check Data Explorer's auth mode first. In the portal, Data Explorer can default to key-based auth when `Enable Entra ID (RBAC)` is set to `Automatic`. For RBAC-only checkpoint access, set that option to `True` and reauthenticate with the `Login for Entra ID RBAC` flow if prompted. A portal error such as `Authorization header doesn't conform to the required format` can be a Data Explorer auth-mode mismatch for your signed-in user rather than missing checkpoint data.

## Prerequisites

- Python 3.11+.
- Azure Functions Core Tools v4 (only for `func start` smoke tests).
- Azure OpenAI deployment reachable from your machine. Set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_MODEL` (the deployment name) and run `az login`.
- Optional: Azurite if you want to exercise the Azure Storage Queue trigger locally with `StorageQueueConnection=UseDevelopmentStorage=true`.
- Optional: a Service Bus emulator if you want to exercise the SB trigger. The HTTP twin (`/api/workflow-queue`) is the default local path.

## Setup

From the repository root, with the virtual environment activated:

```bash
# Install dependencies
task app:deps

# Copy and configure local settings
cp src/communicator_app/src/local.settings.json.sample src/communicator_app/src/local.settings.json
# Edit local.settings.json: Storage Queue is on by default and Service Bus is
# off by default. Toggle ENABLE_STORAGE_QUEUE_TRIGGERS /
# ENABLE_SERVICEBUS_TRIGGERS as needed. Use StorageQueueConnection for
# connection-string or Azurite auth, or StorageQueueConnection__queueServiceUri
# for identity-based auth.
az login
```

## Queue transport options

The app now supports three entrypoint surfaces that all reuse the same
dispatcher, workflow envelopes, and HITL output contract:

- Service Bus trigger, gated by `ENABLE_SERVICEBUS_TRIGGERS`
- Azure Storage Queue trigger, gated by `ENABLE_STORAGE_QUEUE_TRIGGERS`
- HTTP twin at `POST /api/workflow-queue` for local testing

All three paths reuse `WorkflowQueueName` and `HitlQueueName` as the logical
inbound and outbound queue names.

### Azure Storage Queue settings

| Setting | Purpose |
| --- | --- |
| `ENABLE_STORAGE_QUEUE_TRIGGERS` | Enables Azure Storage Queue trigger and output bindings |
| `ENABLE_SERVICEBUS_TRIGGERS` | Enables Service Bus trigger and output bindings |
| `WorkflowQueueName` | Shared inbound queue name for `email.received` and `approval.responded` |
| `HitlQueueName` | Shared outbound queue name for `command-approval.requested` and `email-approval.requested` |
| `StorageQueueConnection` | Connection string for the queue bindings |
| `StorageQueueConnection__queueServiceUri` | Identity-based queue endpoint, for example `https://<account>.queue.core.windows.net` |
| `StorageQueueConnection__credential` | Optional user-assigned identity selector, typically `managedidentity` |
| `StorageQueueConnection__clientID` | Optional user-assigned managed identity client ID |
| `ServiceBusConnection` | Service Bus connection string or namespace-based binding configuration |

> [!IMPORTANT]
> Use `StorageQueueConnection` for both auth models. If both
> `StorageQueueConnection` and `StorageQueueConnection__queueServiceUri` are
> set, the exact `StorageQueueConnection` value wins.

- Default local transport flags: `ENABLE_STORAGE_QUEUE_TRIGGERS=true`, `ENABLE_SERVICEBUS_TRIGGERS=false`, `ENABLE_HTTP_TEST_TRIGGERS=true`
- Connection string or Azurite: set `StorageQueueConnection`
- System-assigned managed identity: clear `StorageQueueConnection` and set `StorageQueueConnection__queueServiceUri`
- User-assigned managed identity: also set `StorageQueueConnection__credential=managedidentity` and `StorageQueueConnection__clientID=<user-assigned-managed-identity-client-id>`

Quick static check:

```bash
cd src/communicator_app/src
python -c "from workflow.builder import build_workflow, build_storage; \
  print(build_workflow(build_storage(), workflow_instance_id='demo').name)"
# -> vendor-email-response-demo
```

## Local testing

Two paths produce the same result. Both exercise the same envelope contract from
architecture.md §3.4.

### Option A — HTTP twin (no Service Bus required)

Fastest path. The host registers `workflow_queue_consumer_http` at
`POST /api/workflow-queue` when `ENABLE_HTTP_TEST_TRIGGERS=true`. The route accepts
both `email.received` and `approval.responded` envelopes. Output that would have
gone to `hitl-queue` is returned in the response body so you can copy
`checkpointId` between requests without an SB emulator.

Start the function app from the repo root:

```bash
task app:start
```

The bundled [`requests.http`](requests.http) (VS Code REST Client) automates
the happy path and includes separate reject-and-stop scenarios with chained
variables. Equivalent curl for the approve path:

```bash
# 1. Start workflow (email.received) → first HITL pause
START=$(curl -s -X POST -H 'Content-Type: application/json' \
  http://localhost:7071/api/workflow-queue \
  -d @samples/workflow_queue_email_received.json)
echo "$START" | jq .
CMD_CP=$(echo "$START" | jq -r '.result.hitl_messages[0].checkpointId')

# 2. Resume — approve VMS plan (approvalType: command) → second HITL pause
RESUME1=$(curl -s -X POST -H 'Content-Type: application/json' \
  http://localhost:7071/api/workflow-queue \
  -d "$(jq --arg cp "$CMD_CP" '.checkpointId=$cp' \
       samples/workflow_queue_approval_responded_command.json)")
echo "$RESUME1" | jq .
EMAIL_CP=$(echo "$RESUME1" | jq -r '.result.hitl_messages[0].checkpointId')

# 3. Resume — approve draft (approvalType: email) → workflow completes
curl -s -X POST -H 'Content-Type: application/json' \
  http://localhost:7071/api/workflow-queue \
  -d "$(jq --arg cp "$EMAIL_CP" '.checkpointId=$cp' \
       samples/workflow_queue_approval_responded_email.json)" | jq .
```

To clear checkpoints between test runs (or change `@workflowInstanceId` in
`requests.http`):

```bash
task app:checkpoints:clear
```

#### Workflow idempotency

By default (`ENFORCE_WORKFLOW_IDEMPOTENCY=false`) the host allows re-running the
same `workflowInstanceId` repeatedly, which is convenient during local iteration.
In production, set `ENFORCE_WORKFLOW_IDEMPOTENCY=true` to reject duplicate
`email.received` envelopes whose `workflowInstanceId` already has checkpoints on
disk. The response will return `{"status": "duplicate"}` without re-executing the
workflow.

### Option B — Functions Core Tools with Service Bus

```bash
task app:start
# In another shell, push samples/workflow_queue_email_received.json onto the
# configured `WorkflowQueueName` queue (Azure portal, SB emulator, or `az servicebus`).
# The host emits `command-approval.requested` on `hitl-queue`. Forward the consumed message
# (or extract the `checkpointId` from logs) into the resume samples and publish
# them onto `WorkflowQueueName` to drive either the approve path or one of the
# rejection terminals.
```

### Option C — Functions Core Tools with Azure Storage Queue

Configure one of these before starting the host:

- Connection-string auth: set `StorageQueueConnection` to a storage
  connection string. For local development, the sample uses
  `UseDevelopmentStorage=true`, which requires Azurite.
- Identity-based auth: clear `StorageQueueConnection`, set
  `StorageQueueConnection__queueServiceUri`, and authenticate with the
  identity that has Queue Data Contributor access to the storage account.

```bash
task app:start
# In another shell, enqueue samples/workflow_queue_email_received.json onto
# the configured `WorkflowQueueName` queue. The host emits the outbound
# HITL envelope to `HitlQueueName`. Enqueue the corresponding
# approval.responded sample back onto `WorkflowQueueName` to resume.
```

For a portal-driven walkthrough that reuses the same `workflowInstanceId`
values as [src/requests.http](src/requests.http), see
[STORAGE-QUEUE-TESTING.md](STORAGE-QUEUE-TESTING.md).

### Envelope contract (architecture.md §3.4)

`workflow-queue` (Agent Workflow consumes; HITL Workflow produces resume responses):

- `email.received`: Upstream to this app. Requires `workflowInstanceId`,
  `internetMessageId`, `storagePrefix`, and `receivedAt`.
- `approval.responded`: HITL Workflow to this app. Requires
  `workflowInstanceId`, `workflowPrefix`, `checkpointId`, `approvalType`
  (`command` or `email`), and `approvalStatus` (`approved` or `rejected`).

`hitl-queue` (this app produces; HITL Workflow consumes):

- `command-approval.requested`: Uses `approvalType: command` and carries
  `adaptiveCardMessage` rendering the proposed VMS operations and email
  fields.
- `email-approval.requested`: Uses `approvalType: email` and carries the
  proposed subject and body for draft review.

Pydantic v2 models for all four envelopes live in
[`workflow/queue_envelopes.py`](workflow/queue_envelopes.py); samples in
[`samples/`](samples/) round-trip through them and are validated as part of the
local smoke test.

### How HITL works

The workflow has two HITL pauses, each independently checkpointed. The host
treats both pauses uniformly: drain the event stream up to quiescence, capture
each `request_info` event, look up the latest `checkpointId` from
`CheckpointStorage` for that workflow instance, and emit one `hitl-queue`
envelope per pending request on the continuing path. A rejected response yields
terminal workflow output instead of a second HITL envelope.

> [!NOTE]
> The body of the HITL request and response payloads (the `adaptiveCardMessage`
> and `approvalStatus` shapes) are placeholders. Production binds them to the
> Teams Adaptive Card's submit-action payload.

#### Pause 1 — Operations plan approval (`approvalType: command`)

`HitlOperationsApprovalExecutor` proposes a list of downstream change-management
operations (create / update / delete maintenance tickets) from the extracted
fields and calls
`ctx.request_info(OperationsApprovalRequest, response_type=dict)`. The host
publishes a `command-approval.requested` envelope on `hitl-queue` carrying the
proposed plan. On `approval.responded`, the workflow either continues through
`OperationsCommandExecutor` and `DraftReplyExecutor`, or terminates immediately
through `terminate_rejected`.

`approvalStatus: rejected` is a valid business rejection. It stops the
workflow after resume, does not execute change-management writes, does not
emit an email approval request, and does not send an outbound reply.

An invalid command approval payload is not treated as rejection. It raises an
error so the bad input is visible as an execution issue rather than being
silently normalized into a business outcome.

#### Pause 2 — Draft email review (`approvalType: email`)

`HitlReviewDraftExecutor` calls `ctx.request_info(HitlDraftRequest, response_type=dict)`
with the proposed reply subject and body. The host publishes an
`email-approval.requested` envelope on `hitl-queue`. On `approval.responded` the
workflow either runs `SendReplyExecutor` or terminates through
`terminate_rejected`.

`approvalStatus: rejected` is a valid business rejection at the email stage.
It stops the workflow after resume and no outbound reply is sent. Invalid email
approval input remains an error path.

This mirrors the canonical MAF HITL pattern documented at
<https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop?pivots=programming-language-python>
and the upstream
[`guessing_game_with_human_input.py`](https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/human-in-the-loop/guessing_game_with_human_input.py)
sample.

#### Idempotency

Replaying a consumed `checkpointId` (network retry, redrive, dead-letter replay)
returns `{"status": "already-resumed"}` because the rehydrated workflow has no
pending `request_info` for that checkpoint. The host does not advance state.

## Sample input

- `samples/workflow_queue_email_received.json`: `workflow-queue` /
  `email.received`
- `samples/workflow_queue_approval_responded_command.json`: `workflow-queue` /
  `approval.responded` for `command`
- `samples/workflow_queue_approval_responded_email.json`: `workflow-queue` /
  `approval.responded` for `email`
- `samples/workflow_queue_approval_rejected_command.json`: `workflow-queue` /
  `approval.responded` for a rejected `command` decision
- `samples/workflow_queue_approval_rejected_email.json`: `workflow-queue` /
  `approval.responded` for a rejected `email` decision
- `samples/hitl_queue_command_request.json`: `hitl-queue` /
  `command-approval.requested` reference shape
- `samples/hitl_queue_email_request.json`: `hitl-queue` /
  `email-approval.requested` reference shape
- `samples/email.json`: Example staged `email.json` payload to upload under
  `<storagePrefix>/email.json`

`EmailIngestExecutor` reads `email.json` from the prefix on the inbound envelope.
Runtime ingest reads from Azure Blob Storage. For unit tests, mock
`workflow.clients.blob_client.download_email_json(...)` and
`workflow.clients.blob_client.download_attachment_blobs(...)` directly.

## Troubleshooting

- **Connection errors to Azure OpenAI (`APIConnectionError: Connection error.`)** — the Azure OpenAI resource has a network firewall with `defaultAction: Deny`. Only allow-listed IPs and VNet subnets can reach it. If your local machine's public IP is not in the allow-list, all requests will silently drop (curl returns HTTP `000`). Ensure your corporate VPN or proxy (e.g., Zscaler) is active so traffic routes through the permitted IP range, or ask your Azure admin to add your IP.
- **`build_workflow` raises `FileNotFoundError`** — ensure `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_MODEL` are set, or set `ENABLE_AGENT_EMAIL_DRAFT=false` for the draft executor.
- **Checkpoint version mismatch** — delete `./checkpoints/` between schema-changing edits to any `workflow/messages/` submodule or `workflow/queue_envelopes.py`.
- **Azure portal Data Explorer shows `Authorization header doesn't conform to the required format` for `workflow-checkpoints`** — the app may still be writing checkpoints successfully. In Data Explorer settings, change `Enable Entra ID (RBAC)` from `Automatic` to `True` so the portal uses Entra RBAC instead of key-based auth for data requests, then sign in again if prompted.
- **Stale checkpoints between test runs** — checkpoints are keyed by `workflowInstanceId`. If you re-run the workflow with the same ID (e.g., the default in `requests.http`), the framework sees existing checkpoint state and may produce unexpected results. Either change the `@workflowInstanceId` variable in `requests.http` to a new value, or delete `./checkpoints/` between runs.
- **Resume returns `{"status": "already-resumed"}`** — the supplied `checkpointId` was already consumed. Use the latest one from the most recent `hitl_messages[*].checkpointId` in the prior response.
- **Resume returns `{"status": "not-found"}`** — no checkpoint matches `Workflow.name = f"{BASE_WORKFLOW_NAME}-{workflowInstanceId}"`. The `email.received` hop may have failed before the first `request_info` fired; check Functions logs.
- **Service Bus errors in terminal during local HTTP testing** — when `ServiceBusConnection` is blank in `local.settings.json`, the Service Bus trigger logs startup errors. These can be safely ignored when only using the HTTP endpoints (`POST /api/workflow-queue`) to test workflow functionality.
- **Storage Queue auth does not behave as expected** — if both `StorageQueueConnection` and `StorageQueueConnection__queueServiceUri` are present, Azure Functions uses the exact `StorageQueueConnection` value and ignores the identity-based prefix settings.

## References

- [Architecture — `design/architecture.md` §3.4](../../design/architecture.md)
- [MAF — Workflows](https://learn.microsoft.com/en-us/agent-framework/workflows/overview?pivots=programming-language-python)
- [MAF — Human in the Loop](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop?pivots=programming-language-python)
- [MAF — Checkpoints](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints?tabs=py-ckpt-inmemory&pivots=programming-language-python)
- [MAF — Edges (conditional)](https://learn.microsoft.com/en-us/agent-framework/workflows/edges?pivots=programming-language-python)
- [Azure Functions — Service Bus trigger (Python v2)](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-service-bus-trigger?tabs=python-v2)
- [Azure Functions — Azure Queue Storage trigger (Python v2)](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-trigger?tabs=python-v2%2Cisolated-process%2Cnodejs-v4%2Cextensionv5&pivots=programming-language-python)
- [Azure Functions — Azure Queue Storage output binding (Python v2)](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-output?tabs=python-v2%2Cisolated-process%2Cnodejs-v4%2Cextensionv5&pivots=programming-language-python)
- [Azure Functions on Container Apps](https://learn.microsoft.com/en-us/azure/azure-functions/functions-container-apps-hosting)
