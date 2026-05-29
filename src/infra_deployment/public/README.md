---
title: "NExT IaC Public Deployment Guide"
description: Public deployment variant with no VNet, GHCR images, and single-command deployment completing in 15-20 minutes. Suitable for PoC, development, and experimentation.
ms.date: 2026-06-14
ms.topic: how-to
---

## Overview

In the public deployment all Azure PaaS services use their default public endpoints. Access is controlled through Entra ID RBAC rather than network isolation.

Container images pull from GitHub Container Registry (GHCR), and the entire post-deployment process runs as an ACI deployment script baked into the Bicep template. This design enables a one-click Deploy-to-Azure button and keeps end-to-end deployment under 20 minutes.


### Public Variant Deployment Overview
Full component layout with data flows

The public variant uses the same logical components as private but without network isolation:

![Public Variant Deployment overview](../../../docs/IaC/assets/public-IaC-overview.png)


## Deploy-to-Azure Button

Because post-deployment logic is embedded directly in the Bicep template (via `loadTextContent` and an ACI deployment script), the public variant supports the Deploy-to-Azure button pattern. No external scripts, git clones, or manual follow-up steps are required after the ARM deployment completes. The button triggers `az deployment group create` against the compiled `main.json`, and post-deploy runs automatically as part of the same deployment.

## Public Variant Deployment Workflow (~15-20 minutes)

![Public Deployment Workflow](../../../docs/IaC/assets/public-deployment-workflow.png)

The post-deploy ACI script receives Logic App workflow JSON through environment variables. At Bicep compile time, `loadTextContent` reads the workflow files from the repository and embeds them into the template. At deploy time, the ACI script writes these values to disk with `printf`, zips the directory, and deploys via `az logicapp deployment source config-zip`. No git clone occurs during deployment.

### PowerShell

```powershell
pwsh -File src/infra_deployment/ps-scripts/deploy.ps1 `
  -Phase all `
  -Variant public `
  -ResourceGroup <ResourceGrName> `
  -Location <location>`
  -BaseName next
```

Or directly with Azure CLI:

```powershell
cd src/infra_deployment
az deployment group create `
  --resource-group NExT-Public `
  --template-file public/main.bicep `
  --parameters public/parameters.json
```

### Bash

```bash
bash src/infra_deployment/deploy.sh \
  --variant public \
  --resource-group "<resource_gr_name>" \
  --unique-prefix <prefix> \
  --base-name next \
  --location <location>
```

The deployment runs `az deployment group create` against `public/main.bicep`, which includes the post-deploy ACI module.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Azure CLI | v2.60+ with Bicep extension |
| Azure subscription | With permissions to create resource groups and deploy ARM templates |
| Resource group | Pre-existing or created by the script (e.g., `NExT-Public`) |
| `.env` file | Must contain `postgreSQL_Password` for the PostgreSQL admin credential |
| Bash | Required for deployment scripting via `deploy.sh` |

No VPN client, network configuration, or DNS setup is needed.

## What Gets Deployed

| Resource | Name Pattern | Config |
|----------|-------------|--------|
| Managed Identity | `{prefix}-identity` | User Assigned |
| Key Vault | `{prefix}-kv` | Standard, RBAC, **no purge protection** |
| Storage Account | `{prefix}st` | Standard LRS, public access |
| Service Bus | `{prefix}-servicebus` | Premium, Capacity 1 |
| Cosmos DB | `{prefix}-cosmos` | NoSQL, Serverless |
| Azure OpenAI | `{prefix}-oai` | S0 (conditional) |
| Doc Intelligence | `{prefix}-di` | S0 |
| Content Safety | `{prefix}-csafety` | S0 (conditional) |
| Function App | `{prefix}-func` | B1, Linux, Python 3.11 |
| Logic App | `{prefix}-logic` | WS1, Linux |
| Container Apps | `{prefix}-ca-env` | External ingress |
| PostgreSQL | (conditional) | Burstable B1ms |
| Log Analytics | `{prefix}-law` | PerGB2018 |
| App Insights | `{prefix}-appinsights` | Workspace-based |

Where `{prefix}` = `baseName` + `uniquePrefix` (e.g., `next3`).

## Post-Deployment Process

Post-deployment runs automatically as an ACI deployment script (`post-deploy-public.bicep`) within the Bicep deployment. No manual steps are required.

### How it works

1. **Compile time:** `loadTextContent` reads four files from the repository and embeds them as Bicep variables:
   * `logic_app/logic_app_workflow_main.json`
   * `logic_app/logic_app_workflow-hitl.json`
   * `logic_app/host.json`
   * `logic_app/connections.json`

2. **Deploy time:** These values pass to the ACI script as environment variables.

3. **ACI execution:** The script performs two operations:
   * Updates the Container App image from GHCR (`az containerapp update --image <ghcr-image>`)
   * Builds a Logic App deployment package using `printf` to write embedded JSON to disk, zips the directory, and deploys via `az logicapp deployment source config-zip`

4. **Identity:** A dedicated user-assigned managed identity with Contributor role on the resource group authorizes all ACI operations.

5. **Storage:** A dedicated storage account (with `allowSharedKeyAccess: true` and a security exception tag) provides the SMB file share that ACI deployment scripts require.

> **Note:** The public post-deploy does not clone the git repository. All application artifacts are embedded at compile time via `loadTextContent`, making the deployment fully self-contained.

## Application Deployment

After infrastructure is deployed:

**Container App** — Updated via GitHub Actions pushing to GHCR:

```bash
# GitHub Actions workflow (deploy-apps.yml) performs:
# 1. Build and push image to GHCR
docker build -t ghcr.io/{owner}/communicator:latest .
docker push ghcr.io/{owner}/communicator:latest

# 2. Update Container App to pull new image
az containerapp update \
  --name next3-ca \
  --resource-group NExT-Public \
  --image ghcr.io/{owner}/communicator:latest
```

**Logic App** — Deployed via config-zip during post-deployment (see [Post-Deployment Process](#post-deployment-process) above):

```bash
az logicapp deployment source config-zip \
  --name <logic_app_name> \
  --resource-group <resource_gr_name> \
  --src /path/to/logicapp.zip
```


## Key Differences from Private Deployment

| Aspect | Public | Private |
|--------|--------|---------|
| Network Isolation | None | Full VNet (10.0.0.0/16) |
| Private Endpoints | None | ~13 endpoints |
| VPN Gateway | Not deployed | VpnGw1AZ + OpenVPN + Entra ID |
| DNS Configuration | Azure default | DNS Private Resolver (10.0.9.4) + 18 zones |
| NSG Rules | None | 4 NSGs with deny-all-other |
| Key Vault Purge Protection | Disabled | Enabled |
| Container Apps Ingress | External | Internal only |
| SQL Managed Instance | Not available | Conditional |
| Deployment Time | ~15-20 min | ~45-60 min |
| Monthly Cost | Lower | Higher (VPN GW, Premium SB, PE charges) |
| Developer Access | Public endpoints + RBAC | VPN required |
| Security Model | Identity-based (RBAC) | Network + Identity (defense in depth) |

## Security Considerations

The public deployment relies solely on identity-based access control:

| Control | Implementation |
|---------|---------------|
| Authentication | Microsoft Entra ID for all service access |
| Authorization | RBAC roles on all resources via Managed Identity |
| Key Management | Key Vault in RBAC mode (no access policies) |
| Data Protection | TLS in transit, encryption at rest |
| Audit | Application Insights + Log Analytics |

> **Warning**: Public endpoints are accessible from the internet. Access is gated by Entra ID authentication and RBAC, but there is no network perimeter. Do not store production data in this variant.

## Design Rationale

| Decision | Rationale | Constraint |
|----------|-----------|------------|
| GHCR for container images | Single registry for all variants; no build step; enables fast PoC | Public registry, no auth needed |
| Post-deploy baked into Bicep | Enables Deploy-to-Azure button (one-click, no follow-up scripts) | Template must be self-contained |
| `loadTextContent` for Logic App | Embeds workflow JSON at compile time; avoids git clone during deploy | Files must exist at `bicep build` time |
| Cosmos DB Serverless | Zero cost at idle; no capacity planning for PoC | Bursty, unpredictable workload |
| Key Vault without purge protection | PoC-friendly; avoids soft-delete lock during iterations | Development convenience (not for production) |
| Container Apps as primary compute | Serverless containers with scale-to-zero; Function App disabled by default | Reduces baseline cost |
| Single User-Assigned MI | Simplifies RBAC surface area | One identity across all services |
| Service Bus Premium | Only tier supporting Private Endpoints across both variants | Shared module constraint |
| PostgreSQL Burstable (B1ms) | Cheapest tier suitable for evaluation workloads | PoC cost optimization |
| AVM throughout | Official Microsoft modules; tested patterns; versioned | Best practice, consistency |

## Contents

| File | Description |
|------|-------------|
| `main.bicep` | Public variant orchestration template |
| `main.json` | Compiled ARM template for Deploy-to-Azure |
| `parameters.json` | Deployment parameters |

## Testing

```powershell
cd tests/infra
# Update config.yaml for public variant
# base_name: "next3"
# deployment_variant: "public"

pytest tests/ -v --tb=short
```

No VPN connection required. Tests run over public endpoints.

## When to Use Each Variant

| Scenario | Recommended Variant |
|----------|-------------------|
| Quick PoC or demo | Public |
| Development and experimentation | Public |
| Customer-facing deployment | Private |
| Compliance requirements (data residency, network controls) | Private |
| Cost-sensitive evaluation | Public |
| Production workloads | Private |

## Comparison with Private Deployment

See [Private Deployment Guide](../private/README.md) for the VNet-isolated variant, or [Infrastructure Architecture](../../../docs/IaC/Infrastructure.md) for the full component reference.

## Related Documentation

* [Infrastructure Deployment Overview](../README.md) for the dual-variant architecture and service inventory
* [Private Deployment Variant](../private/README.md) for the VNet-integrated production variant
* [Infrastructure Architecture](../../../docs/IaC/Infrastructure.md) for the full feature comparison table
