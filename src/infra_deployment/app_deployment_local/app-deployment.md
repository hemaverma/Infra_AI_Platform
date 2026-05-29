---
title: Application Deployment to Private Infrastructure
description: Step-by-step guide for deploying the Communicator Container App and Logic App workflows into the private VNet-isolated Next-Private3 environment.
author: NExT Team
ms.date: 2026-06-08
ms.topic: how-to
---

## Prerequisites

Before deploying application workloads, verify the following:

- Private infrastructure deployment to `Next-Private3` (westus3) has completed successfully
- **Deployer VM workflow**: No VPN required — the VM operates inside the VNet
- **Local docker push to private ACR**: VPN connection IS required (all private endpoints are VNet-only)
- Azure CLI is authenticated with sufficient permissions (`Contributor` + `AcrPush` on the resource group)
- Docker is available locally (optional — ACR Tasks handles remote builds)

### Resource naming reference

| Resource | Name |
|----------|------|
| Resource Group | `Next-Private3` |
| Container Registry | `next17acr` |
| Container App Environment | `next17-cae` |
| Container App | `next17-communicator` |
| Logic App | `next17-logic` |
| Storage Account | `next17st` |
| Service Bus Namespace | `next17-sb` |
| Cosmos DB Account | `next17-cosmos` |
| OpenAI Service | `next17-openai` |
| Key Vault | `next17-kv` |

---

## Step 1 — Build and push the container image

The ACR is Premium SKU with public access disabled. Image builds execute remotely via ACR Tasks, which run inside the VNet.

```powershell
# Option A: Use the build script (auto-selects agent pool vs bypass strategy)
.\infra_deployment\build-image.ps1 `
  -ResourceGroup Next-Private3 `
  -AcrName next17acr

# Option B: Direct ACR build command
az acr build `
  --registry next17acr `
  --image communicator:latest `
  --file src/communicator_app/Dockerfile `
  src/communicator_app/
```

Verify the image is available:

```powershell
az acr repository show-tags --name next17acr --repository communicator --output table
```

---

## Step 2 — Update the Container App with the real image

The infrastructure deployment provisions the Container App with a placeholder image (`containerapps-helloworld`). Replace it with the actual communicator image:

```powershell
az containerapp update `
  --name next17-communicator `
  --resource-group Next-Private3 `
  --image next17acr.azurecr.io/communicator:latest
```

---

## Step 3 — Configure Container App environment variables

Set the connection parameters the communicator app requires. All services authenticate via managed identity — no connection strings with secrets are needed:

```powershell
az containerapp update `
  --name next17-communicator `
  --resource-group Next-Private3 `
  --set-env-vars `
    SERVICEBUS__FULLYQUALIFIEDNAMESPACE=next17-sb.servicebus.windows.net `
    COSMOS_ENDPOINT=https://next17-cosmos.documents.azure.com:443/ `
    COSMOS_DATABASE_NAME=vendor-email-response `
    COSMOS_CONTAINER_NAME=workflow-checkpoints `
    AZURE_OPENAI_ENDPOINT=https://next17-openai.openai.azure.com/ `
    AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5 `
    STORAGE_ACCOUNT_NAME=next17st `
    KEYVAULT_URL=https://next17-kv.vault.azure.net/
```

---

## Step 4 — Deploy Logic App workflows

The Logic App hosts two workflows that coordinate email ingestion and human-in-the-loop approval:

| Workflow | Source file | Purpose |
|----------|-------------|---------|
| `email-poller` | `src/logic_app/logic_app_workflow_main.json` | Polls shared mailbox, stages emails in Blob Storage, enqueues to Service Bus |
| `hitl-approval` | `src/logic_app/logic_app_workflow-hitl.json` | Sends Teams Adaptive Cards for operator approval, routes responses back |

Deploy using the existing script:

```bash
bash src/logic_app/deploy-workflows.sh \
  --resource-group Next-Private3 \
  --logic-app-name next17-logic
```

The script performs the following actions:

1. Creates the workflow folder structure (`email-poller/workflow.json`, `hitl-approval/workflow.json`)
2. Copies `host.json` and `connections.json`
3. Packages everything into `workflows.zip`
4. Deploys via `az logicapp deployment source config-zip`

---

## Step 5 — Configure Logic App application settings

Point the Logic App at the private endpoints for dependent services:

```powershell
az logicapp config appsettings set `
  --name next17-logic `
  --resource-group Next-Private3 `
  --settings `
    SERVICEBUS_NAMESPACE=next17-sb.servicebus.windows.net `
    STORAGE_ACCOUNT_NAME=next17st `
    BLOB_ENDPOINT=https://next17st.blob.core.windows.net `
    COSMOS_ENDPOINT=https://next17-cosmos.documents.azure.com:443/ `
    KEYVAULT_URL=https://next17-kv.vault.azure.net/
```

---

## Step 6 — Verify connectivity

### Container App health check

```powershell
# Check revision status
az containerapp revision list `
  --name next17-communicator `
  --resource-group Next-Private3 `
  --output table
```

Confirm the latest revision shows `Running` with `TrafficWeight: 100`.

### Logic App workflow status

```powershell
az logicapp show `
  --name next17-logic `
  --resource-group Next-Private3 `
  --query "siteConfig.appSettings" -o table
```

Open the Logic App in the Azure portal (via VPN) to confirm both workflows appear and the `email-poller` trigger is active.

### End-to-end smoke test

1. Send a test email to the monitored shared mailbox
2. Verify a blob appears in `next17st` under `email-staging/{workflowInstanceId}/`
3. Confirm a message is enqueued on `workflow-queue` in Service Bus
4. Check the Container App logs for workflow execution

```powershell
az containerapp logs show `
  --name next17-communicator `
  --resource-group Next-Private3 `
  --follow
```

---

## Network topology

All traffic flows through the private VNet — no public internet exposure:

```text
┌─────────────────────────────────────────────────────────────────┐
│  VNet: 10.0.0.0/16 (westus3)                                   │
│                                                                 │
│  ┌──────────────────────┐     ┌──────────────────────────────┐  │
│  │ snet-functions       │     │ snet-container-apps          │  │
│  │ 10.0.1.0/26          │     │ 10.0.2.0/23                  │  │
│  │                      │     │                              │  │
│  │  next17-logic        │     │  next17-communicator         │  │
│  │  (VNet integrated)   │     │  (Internal mode)             │  │
│  └──────────┬───────────┘     └──────────────┬───────────────┘  │
│             │                                │                  │
│             ▼                                ▼                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ snet-private-endpoints (10.0.5.0/24)                     │   │
│  │                                                          │   │
│  │  • next17st.blob       • next17-sb.servicebus            │   │
│  │  • next17-cosmos       • next17-openai.cognitiveservices  │   │
│  │  • next17acr           • next17-kv.vaultcore             │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### ACR build fails with network error

The ACR has public access disabled. Ensure the build uses ACR Tasks (which run inside Azure) rather than local `docker push`. If agent pools are unavailable in the region, the build script falls back to `networkRuleBypassAllowedForTasks`.

### Container App fails to pull image

Verify the managed identity has `AcrPull` role on the registry:

```powershell
az role assignment list `
  --scope /subscriptions/<your_subscription>/resourceGroups/Next-Private3/providers/Microsoft.ContainerRegistry/registries/next17acr `
  --query "[?roleDefinitionName=='AcrPull']" -o table
```

### Logic App zip deploy returns 403

Zip deployment requires the SCM endpoint to be accessible. In the private configuration, this is only reachable via the VPN. Confirm your VPN connection is active before deploying.

### Workflows not appearing after deployment

Allow 1-2 minutes for the Logic App runtime to detect new workflow files. If they still don't appear, restart the Logic App:

```powershell
az logicapp restart --name next17-logic --resource-group Next-Private3
```
