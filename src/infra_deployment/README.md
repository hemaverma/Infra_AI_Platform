---
title: NExT Infrastructure Deployment
description: Deployment overview for the NExT dual-variant infrastructure covering public and private architectures, service inventory, and pipeline scripts.
ms.date: 2026-06-14
ms.topic: overview
---

## Overview

NExT deploys Azure infrastructure in two variants that share a common module library:

| Variant | Use Case | Networking | Post-Deploy Model |
|---------|----------|------------|-------------------|
| Public | PoC, demos, rapid iteration | No VNet, public endpoints | ACI deployment script baked into Bicep |
| Private | Production, compliance, regulated workloads | Full VNet, Private Endpoints on all services | Deployment Center + NAT Gateway |

Both variants deploy from the same set of 24 Bicep modules under `modules/`. The variant orchestrator (`public/main.bicep` or `private/main.bicep`) selects which modules to invoke and whether networking resources are included.

## Naming Convention

All resources follow the pattern `{baseName}{uniquePrefix}`:

| Parameter | Example | Purpose |
|-----------|---------|---------|
| `baseName` | `next` | Project identifier |
| `uniquePrefix` | `51` | Numeric suffix ensuring global uniqueness |
| Result | `next51` | Used as prefix for all resource names (e.g., `next51-communicator`, `next51-keyvault`) |

Pass these values via `--base-name` and `--unique-prefix` flags in the deployment scripts.

## Quick Start

### Public Variant (single command, ~15-20 min)

```bash
bash src/infra_deployment/deploy.sh \
  --variant public \
  --resource-group "<resource_gr_name>" \
  --unique-prefix <prefix>  \
  --base-name next \
  --location <location>
```

### Private Variant, Phase 1: Network (~35 min with VPN Gateway)

```bash
bash src/infra_deployment/deploy.sh \
  --variant private \
  --phase network \
  --resource-group "<resource_gr_name>" \
  --base-name next \
  --location <location>
```

Connect your VPN client after Phase 1 completes, then proceed to Phase 2.

### Private Variant, Phase 2: Services (requires VPN)

```bash
bash src/infra_deployment/deploy.sh \
  --variant private \
  --phase services \
  --resource-group "<resource_gr_name>" \
  --base-name next \
  --location <location>
```

## Services Inventory

| Service | SKU | Variant | Conditional | Rationale |
|---------|-----|---------|-------------|-----------|
| Container Apps (communicator) | 0.5 vCPU / 1Gi | Both | Yes (default: true) | Primary compute, scale-to-zero |
| Logic App Standard | WS1 | Both | Yes (default: true) | Minimum Standard tier on Linux |
| Function App | S1 | Both | Yes (default: false) | Optional secondary compute |
| Service Bus | Premium (capacity 1) | Both | No | PE requires Premium tier |
| Cosmos DB | Serverless (NoSQL) | Both | No | Zero cost at idle for PoC |
| Azure OpenAI | S0 (GlobalStandard 30 TPM) | Both | Yes (default: true) | AI orchestration backbone |
| ACR | Premium | Private only | No | PE requires Premium; public uses GHCR |
| PostgreSQL | Standard_B1ms (Burstable) | Both | Yes (default: true) | Cheapest tier for evaluation |
| Key Vault | Standard (RBAC mode) | Both | No | Secrets, certificates, app config |
| Storage Account | Standard_LRS | Both | No | Function App backing, artifacts |
| VPN Gateway | VpnGw1AZ | Private only | No | Entra ID authenticated VPN access |

Conditional services are toggled via Bicep parameters (e.g., `deployContainerApps`, `deployOpenAi`).

## Deployment Scripts

| Script | Purpose |
|--------|---------|
| `deploy.sh` | Main orchestrator (bash): arg parsing, provider registration, template routing |
| `validate.sh` | Bicep syntax validation across all template files |
| `app_deployment_local/build-image.sh` | _(deprecated)_ Local Docker build + ACR push — superseded by GHCR CI/CD |

## Directory Structure

| Path | Purpose |
|------|---------|
| `app_deployment_local/` | Local Docker image build scripts (not part of CI/CD) |
| `modules/` | Shared Bicep modules for infrastructure |
| `private/` | Private deployment variant: Bicep templates, parameters, VPN profile |
| `public/` | Public deployment variant resources |

## Module Reference

Shared Bicep modules under `modules/`:

| Module | AVM Registry Reference |
|--------|----------------------|
| identity | `br/public:avm/res/managed-identity/user-assigned-identity:0.4.1` |
| observability | `br/public:avm/res/operational-insights/workspace:0.9.1` |
| observability (App Insights) | `br/public:avm/res/insights/component:0.4.2` |
| keyvault | `br/public:avm/res/key-vault/vault:0.11.1` |
| storage | `br/public:avm/res/storage/storage-account:0.14.3` |
| servicebus | `br/public:avm/res/service-bus/namespace:0.12.0` |
| cosmosdb | `br/public:avm/res/document-db/database-account:0.11.1` |
| postgresql | `br/public:avm/res/db-for-postgre-sql/flexible-server:0.14.0` |
| openai | `br/public:avm/res/cognitive-services/account:0.10.1` |
| ai-foundry | `br/public:avm/res/machine-learning-services/workspace:0.10.1` |
| logic-app | `br/public:avm/res/web/serverfarm:0.4.1` + `br/public:avm/res/web/site:0.15.1` |
| acr | `br/public:avm/res/container-registry/registry:0.6.0` |
| container-apps | `br/public:avm/res/app/container-app:0.12.1` |
| networking (NSG) | `br/public:avm/res/network/network-security-group:0.5.1` |
| vpn-gateway | `br/public:avm/res/network/virtual-network-gateway:0.11.0` |

Additional custom modules (no AVM equivalent): `dns-resolver`, `env-config`, `acr-build-infra`, `github-runner`, `content-safety`, `document-intelligence`, `post-deploy-public`, `post-deploy-private`.

## Post-Deployment

Post-deployment handles application code that cannot be expressed as Bicep resource declarations.

### Public Variant

An ACI deployment script is baked directly into the Bicep template (`post-deploy-public.bicep`). This design enables the Deploy-to-Azure button pattern where the entire deployment is self-contained. The script:

1. Updates the Container App image from GHCR (`ghcr.io/hemaverma/communicator:latest`)
2. Writes Logic App workflow JSON (embedded at compile time via `loadTextContent`) to disk, zips, and deploys via `az logicapp deployment source config-zip`
3. Optionally publishes the Function App

### Private Variant

Two complementary mechanisms handle private post-deployment:

1. **Container App image** (`deploy.sh`): Updates the Container App to pull from GHCR via NAT Gateway outbound.
2. **Logic App workflows** (Deployment Center): Logic App uses Deployment Center (Kudu external git) to pull workflows from GitHub via NAT Gateway outbound. No runner VM required.

## Links

| Resource | Path |
|----------|------|
| Public variant guide | [public/README.md](public/README.md) |
| Private variant guide | [private/README.md](private/README.md) |
| Architecture overview | [../../docs/design/architecture.md](../../docs/design/architecture.md) |
