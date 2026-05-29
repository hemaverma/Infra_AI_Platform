# NExT Logic App Workflows 

This directory contains Azure Logic App workflow definitions for the NExT (Notification Extraction Tool) Communication System. The workflows handle email ingestion, staging, and human-in-the-loop (HITL) approval processes. 

## Overview

The NExT system uses two coordinated Azure Logic App workflows:

1. **Main Workflow** (`logic_app_workflow_main.json`) - Email ingestion, staging, and queue dispatch
1. **HITL Workflow** (`logic_app_workflow-hitl.json`) - Human-in-the-loop approval via Microsoft Teams

These workflows work together with Azure Functions to process vendor maintenance notifications, extract actionable information, and coordinate with human operators for approvals.  

---

## 1. Main Workflow - Email Ingestion & Staging

File: `logic_app_workflow_main.json`


### Purpose

This workflow monitors a shared mailbox for incoming vendor emails, normalizes the content, stages it in Azure Blob Storage, and dispatches a workflow message to the Azure Service Bus queue for downstream processing by the Azure Function runtime.

### Trigger

- Type: Office 365 connector - Shared Mailbox polling
- Mailbox: `<sample-mailbox>@domain.com`
- Frequency: Every 1 minute
- Folder: Inbox
- Attachments: Included

### Workflow Steps

![Main Workflow](documents/main-workflow.drawio.png)

### Key Actions

1. Generate Metadata
   - Creates unique `workflowInstanceId` with format: `workflow-next-{timestamp}-{guid}`
   - Defines target queue: `workflow-queue`
   - Sets storage container: `email-staging`

1. Get Attachment Names
   - Extracts attachment filenames from trigger payload
   - Handles cases where no attachments exist (empty array)

1. Create Email JSON
   - Builds normalized email payload with fields:
     - `internetMessageId` - Email message identifier
     - `workflowInstanceId` - Unique workflow instance ID
     - `receivedAt` - Email received timestamp
     - `senderEmail` - Sender email address
     - `subject` - Email subject line
     - `body` - Email body content
     - `attachments` - Array of attachment filenames

1. Create Blob (email.json)
   - Uploads normalized email JSON to Blob Storage
   - Path: `email-staging/{workflowInstanceId}/email.json`

1. Upload Attachments
   - Loops through each attachment
   - Converts base64 content to binary
   - Uploads to: `email-staging/{workflowInstanceId}/attachments/{filename}`

1. Build Queue Message
   - Creates workflow event message:

     ```json
     {
       "queueName": "workflow-queue",
       "eventType": "email.received",
       "internetMessageId": "...",
       "workflowInstanceId": "workflow-next-...",
       "storagePrefix": "workflow-next-...",
       "checkpointId": null,
       "receivedAt": "2026-05-15T10:30:00Z"
     }
     ```

1. Put Message on Queue
   - Dispatches message to Azure Storage Queue (`workflow-queue`)
   - Azure Function picks up the message for processing

### Storage Structure

After the workflow completes, the following structure exists in Blob Storage:

```text
email-staging/
  workflow-next-2026-05-15-10-30-00-abc123/
    email.json
    attachments/
      001-maintenance-notice.pdf
      002-circuit-list.xlsx
```

---

## 2. HITL Workflow - Human-in-the-Loop Approval

File: `logic_app_workflow-hitl.json`

### Purpose

This workflow handles human-in-the-loop approval requests by monitoring a dedicated approval queue (`hitl-queue`), presenting approval cards in Microsoft Teams, collecting human responses, and routing the responses back to the main workflow queue.

### Trigger

- Type: Azure Storage Queue threshold trigger
- Queue: `hitl-queue`
- Threshold: 1 message
- Frequency: Every 1 minute

### Workflow Steps

![HITL Workflow](documents/hitl-workflow.drawio.png)

### Key Actions

1. Get Messages from Queue
   - Retrieves 1 message from `hitl-queue`
   - Message contains approval request details

1. Parse Message JSON
   - Extracts JSON from queue message text
   - Schema includes:
     - `queueName` - Target queue for response
     - `eventType` - Type of approval (`command-approval.requested` or `email-approval.requested`)
     - `workflowInstanceId` - Workflow instance identifier
     - `workflowPrefix` - Storage prefix
     - `checkpointId` - Checkpoint identifier for resumption
     - `internetMessageId` - Email message ID
     - `approvalType` - Type of approval needed
     - `adaptiveCardMessage` - Message to display in Teams

1. Delete Message from Queue
   - Removes processed message from `hitl-queue` immediately
   - Uses `MessageId` and `PopReceipt` for deletion

1. Compose Adaptive Card
   - Builds Microsoft Teams Adaptive Card with:
     - Title: "Command Approval Required" or "Email Approval Required"
     - Message body from `adaptiveCardMessage` field
     - Actions: "Approve" and "Reject" buttons

1. Check Event Type - Command Approval Branch
   - Post Adaptive Card to Teams
     - Posts card to specific Teams channel
     - Waits for user to click "Approve" or "Reject"
   - Build Approval Response
     - Creates response message:

       ```json
       {
         "queueName": "workflow-queue",
         "eventType": "approval.responded",
         "workflowInstanceId": "...",
         "workflowPrefix": "...",
         "checkpointId": "...",
         "approvalType": "...",
         "approvalStatus": "Approve" | "Reject"
       }
       ```

   - Put Message on workflow-queue
     - Dispatches response back to main workflow

1. Check Event Type - Email Approval Branch
   - Post Adaptive Card to Teams
     - Same adaptive card posting as command approval
   - Check Email Approved
     - If user clicked "Approve":
       - Send Email via Office 365
       - Sends email to configured recipient with workflow details
     - If user clicked "Reject":
       - No email is sent
   - Build Email Approval Response
     - Creates response message with approval status
   - Put Message on workflow-queue
     - Dispatches response back to main workflow

### Approval Message Flow

![Approval Message Flow](documents/approval-sequence.drawio.png)

---

## Queue Message Schemas

### email.received (Main Workflow → workflow-queue)

Dispatched by the main workflow when a new email is staged and ready for processing.

```json
{
  "queueName": "workflow-queue",
  "eventType": "email.received",
  "internetMessageId": "<message-id@example.com>",
  "workflowInstanceId": "workflow-next-2026-05-15-10-30-00-abc123",
  "storagePrefix": "workflow-next-2026-05-15-10-30-00-abc123",
  "checkpointId": null,
  "receivedAt": "2026-05-15T10:30:00Z"
}
```

### approval.requested (Azure Function → hitl-queue)

Sent by Azure Function when human approval is needed.

```json
{
  "queueName": "hitl-queue",
  "eventType": "command-approval.requested",
  "workflowInstanceId": "workflow-next-2026-05-15-10-30-00-abc123",
  "workflowPrefix": "workflow-next-2026-05-15-10-30-00-abc123",
  "checkpointId": "checkpoint-extract-complete",
  "internetMessageId": "<message-id@example.com>",
  "approvalType": "command",
  "adaptiveCardMessage": "Please approve the following command: CREATE TICKET..."
}
```

### approval.responded (HITL Workflow → workflow-queue)

Returned by HITL workflow after human provides approval decision.

```json
{
  "queueName": "workflow-queue",
  "eventType": "approval.responded",
  "workflowInstanceId": "workflow-next-2026-05-15-10-30-00-abc123",
  "workflowPrefix": "workflow-next-2026-05-15-10-30-00-abc123",
  "checkpointId": "checkpoint-extract-complete",
  "approvalType": "command",
  "approvalStatus": "Approve"
}
```

---

## Integration with Azure Functions

The Logic App workflows integrate with the Azure Function runtime through Azure Storage Queues and Blob Storage:

1. Main Workflow → Azure Function
   - Logic App stages email content in Blob Storage
   - Logic App dispatches `email.received` event to `workflow-queue`
   - Azure Function Service Bus trigger picks up the message
   - Function reads staged content from Blob Storage using `storagePrefix`
   - Function processes email through validation, extraction, and command generation

1. Azure Function → HITL Workflow
   - Function encounters checkpoint requiring human approval
   - Function pushes approval request to `hitl-queue`
   - HITL Logic App picks up message and presents adaptive card in Teams
   - Human operator approves or rejects
   - HITL workflow sends response back to `workflow-queue`

1. HITL Workflow → Azure Function
   - HITL workflow dispatches `approval.responded` to `workflow-queue`
   - Azure Function resumes from checkpoint with approval decision
   - Function continues workflow execution based on approval status

---

## Configuration

Both workflows require the following Azure resources:

### Connections

- `office365-4` - Office 365 connector for shared mailbox access and email sending
- `azureblob-4` - Azure Blob Storage connector for email staging
- `azurequeues-2` - Azure Storage Queues connector for workflow messaging
- `teams` - Microsoft Teams connector for adaptive card posting

### Storage Account

- Account Name: `<storage-account-name>`
- Containers:
  - `email-staging` - Email content and attachment staging
- Queues:
  - `workflow-queue` - Main workflow event queue
  - `hitl-queue` - Human-in-the-loop approval queue

### Microsoft Teams

- Group ID: `<teams-group-id>`
- Channel ID: `<teams-channel-id>`

---

## Deployment

These workflows are deployed as Azure Logic Apps (Standard) with the following characteristics:

- Kind: Stateful
- Region: East US
- Recurrence: 1-minute polling intervals for both triggers
- Runtime: Logic Apps Standard (workflow runtime v4)

To deploy or update these workflows:

1. Use Azure Portal Logic App Designer to import the JSON definitions
1. Configure API connections for Office 365, Storage, and Teams
1. Update storage account references and mailbox addresses as needed
1. Enable and test each workflow independently before connecting to Azure Functions

---

## Monitoring & Troubleshooting

### Main Workflow

- Monitor: Azure Portal → Logic App → Run History
- Key Metrics:
  - Email ingestion rate
  - Blob upload success/failure
  - Queue message dispatch success
- Common Issues:
  - Connection failures to Office 365 or Storage
  - Attachment size limits (chunked transfer mode enabled)
  - Queue message size limits (ensure payload < 64KB)

### HITL Workflow

- Monitor: Azure Portal → Logic App → Run History
- Key Metrics:
  - Approval request processing time
  - Teams card posting success
  - Human response time
- Common Issues:
  - Teams connector authentication expiry
  - Missing or malformed `adaptiveCardMessage` in queue payload
  - Queue message deletion failures (check PopReceipt validity)

---

## Architecture References

For more details on how these workflows fit into the overall NExT system architecture:

- [Architecture Overview](../../docs/design/architecture.md)
- [Service Bus Queue Topology ADR](../../docs/adr/0002-service-bus-queue-topology.md)
- [Email Extraction Schema ADR](../../docs/adr/0003-email-extraction-schema.md)
- [Communicator App README](../communicator_app/README.md)

---

## Related Documentation

- [Azure Logic Apps Documentation](https://learn.microsoft.com/en-us/azure/logic-apps/)
- [Adaptive Cards Schema](https://adaptivecards.io/schemas/adaptive-card.json)
- [Office 365 Connector Reference](https://learn.microsoft.com/en-us/connectors/office365/)
- [Azure Storage Queues Connector](https://learn.microsoft.com/en-us/connectors/azurequeues/)

---

## Deployment Guide

Logic App deployment follows a 3-phase lifecycle:

| Phase | Frequency | Automation |
|-------|-----------|------------|
| 1. Infrastructure (Bicep) | Once per environment | Fully automated via `az deployment group create` |
| 2. Connection Authorization | Once per environment (manual gate) | Portal-based; cannot be automated |
| 3. Workflow Deployment | Every code change | Automated via `deploy-workflows.ps1` |

### Architecture

The Logic App runs as a **Standard (WS1 Linux)** instance using the bundle-based (non-.NET) runtime with Node.js. Key characteristics:

- **SKU**: WorkflowStandard WS1 (Linux)
- **Runtime**: Azure Functions Extension Bundle v4
- **Connection Model**: Managed API connections (Office 365, Blob, Teams) + Service Provider (Service Bus built-in)
- **Authentication**: User Assigned Managed Identity for all connections
- **Parameterization**: All connection details use `@appsetting()` references (no hardcoded values)

### Phase 2: Connection Authorization (Manual — One-Time)

After infrastructure deployment creates the Logic App and its managed API connections, you must authorize each connection in the Azure Portal. This cannot be automated because Microsoft requires interactive OAuth consent.

#### Prerequisites

- Logic App deployed via Bicep (Phase 1 complete)
- User Assigned Managed Identity exists and has required RBAC roles:
  - Storage Blob Data Contributor (on storage account)
  - Service Bus Data Sender / Receiver (on Service Bus namespace)
  - Appropriate Office 365 / Teams permissions

#### Steps

1. Navigate to the Logic App in Azure Portal
2. Go to **Workflows** → **Connections** → **API Connections**
3. For each connection (azureblob, office365, teams):
   a. Click the connection name
   b. Click **Edit API connection**
   c. Under **Authentication**, select **Managed Identity**
   d. Choose the User Assigned Managed Identity (`next-identity`)
   e. Click **Authorize** — this triggers OAuth consent
   f. Click **Save**
4. Verify each connection shows status: **Connected**

#### Validation

```powershell
# Check connection status via CLI
az resource show \
  --resource-group next \
  --resource-type Microsoft.Web/connections \
  --name azureblob \
  --query "properties.statuses[0].status" -o tsv
# Expected: Connected
```

> **Note**: If a connection shows "Error" status after authorization, delete and recreate it via the Portal. The Bicep module will re-provision the connection shell on next deployment, and you re-authorize.

#### When Re-Authorization Is Needed

- After rotating managed identity credentials
- After changing the identity assignment on the Logic App
- After deleting and recreating the Logic App resource
- After re-deploying infrastructure with identity changes

### Phase 3: Workflow Deployment (Repeatable)

Workflow deployment uses zip-based deployment via `deploy-workflows.ps1`. This is the repeatable step — run it every time workflow definitions change.

#### Quick Start

```powershell
# Deploy workflows to the Logic App
./deploy-workflows.ps1 -ResourceGroup next -LogicAppName next-logic-app

# Dry run (build zip without deploying)
./deploy-workflows.ps1 -ResourceGroup next -LogicAppName next-logic-app -DryRun
```

#### What the Script Does

1. Creates a clean `build/` directory
2. For each workflow (`email-poller`, `hitl-approval`):
   - Creates a folder named after the workflow
   - Copies the source JSON as `workflow.json` inside that folder
3. Copies global files: `host.json`, `connections.json`
4. Compresses everything into `workflows.zip`
5. Deploys via `az logicapp deployment source config-zip`

#### Package Structure

```text
workflows.zip
├── host.json
├── connections.json
├── email-poller/
│   └── workflow.json     (from logic_app_workflow_main.json)
└── hitl-approval/
    └── workflow.json     (from logic_app_workflow-hitl.json)
```

#### Important Notes

- Zip deploy is **full replacement** — all workflows in the zip become the deployed state
- Workflows NOT in the zip will be removed from the Logic App
- The `connections.json` in the zip references `@appsetting()` values; actual secrets come from Logic App app settings (configured in Bicep)
- No restart required — workflows activate immediately after deployment

### Alternative Deployment Methods

| Method | Suitable For | Pros | Cons |
|--------|-------------|------|------|
| **Zip Deploy (current)** | CI/CD, repeatable deploys | Fast, atomic, scriptable, supports -DryRun | Full replacement only; no partial updates |
| **Azure DevOps Logic App Extension** | ADO pipelines | Visual designer export/import, connection handling | Tied to ADO; heavier setup |
| **GitHub Actions (azure/logicapps-deploy)** | GitHub-based CI/CD | First-class GitHub integration | Limited to zip deploy under the hood |
| **ARM/Bicep inline** | Infrastructure-as-code purists | Single deployment unit | Workflow JSON embedded in Bicep is unwieldy |
| **Portal Designer** | Ad-hoc prototyping | Visual, immediate feedback | No version control; drift risk |
| **VS Code Extension** | Local development | Design + deploy from IDE | Manual process; not CI/CD friendly |

#### Why Zip Deploy Was Chosen

1. **Decoupled lifecycle**: Infrastructure (Bicep) and workflows (JSON) deploy independently
2. **Version control**: Workflow definitions live in Git alongside application code
3. **CI/CD ready**: Single PowerShell command integrates into any pipeline
4. **Dry-run support**: `-DryRun` flag for safe validation before deployment
5. **Full replacement semantics**: Ensures deployed state matches repository state exactly

#### CI/CD Pipeline Template (GitHub Actions)

```yaml
name: Deploy Logic App Workflows
on:
  push:
    branches: [main]
    paths: ['src/logic_app/**']

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - name: Deploy workflows
        run: |
          pwsh src/logic_app/deploy-workflows.ps1 \
            -ResourceGroup next \
            -LogicAppName next-logic-app
```

### Troubleshooting

| Issue | Cause | Resolution |
|-------|-------|------------|
| Workflows don't appear after deploy | Zip missing `host.json` or folder structure wrong | Run with `-DryRun` and inspect `build/` directory |
| Connection shows "Error" status | OAuth consent expired or identity changed | Re-authorize in Portal (Phase 2 steps) |
| "Resource not found" on deploy | Logic App name or RG incorrect | Verify `az logicapp list -g next` returns the app |
| Workflow triggers but fails at first action | `@appsetting()` reference missing | Check Logic App Configuration for required app settings |
| Service Bus trigger not firing | Built-in connector namespace missing | Verify `ServiceBusConnection__fullyQualifiedNamespace` in app settings |
| 409 Conflict on zip deploy | Concurrent deployment in progress | Wait 60 seconds and retry |

#### Required App Settings

These app settings must exist on the Logic App (configured via Bicep in `logic-app.bicep`):

| Setting | Purpose |
|---------|---------|
| `BLOB_CONNECTION_RUNTIME_URL` | Managed API runtime URL for Blob connection |
| `BLOB_CONNECTION_NAME` | Name of the Blob API connection resource |
| `OFFICE365_CONNECTION_RUNTIME_URL` | Managed API runtime URL for Office 365 |
| `OFFICE365_CONNECTION_NAME` | Name of the Office 365 API connection resource |
| `TEAMS_CONNECTION_RUNTIME_URL` | Managed API runtime URL for Teams |
| `TEAMS_CONNECTION_NAME` | Name of the Teams API connection resource |
| `ServiceBusConnection__fullyQualifiedNamespace` | Service Bus fully qualified namespace (managed identity auth) |
| `WORKFLOWS_SUBSCRIPTION_ID` | Azure subscription ID |
| `WORKFLOWS_RESOURCE_GROUP_NAME` | Resource group name |
| `WORKFLOWS_LOCATION_NAME` | Azure region |
