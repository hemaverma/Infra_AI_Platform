---
title: "Use GitHub-Hosted Runners with Deployment Center (Eliminate Self-Hosted Runner Dependency)"
description: "ADR explaining why GitHub-hosted runners are sufficient for all CI/CD operations when combined with Deployment Center for Logic App deployment"
ms.date: 2026-06-20
ms.topic: reference
---

# Use GitHub-Hosted Runners with Deployment Center (Eliminate Self-Hosted Runner Dependency)

- Status: Accepted
- Deciders: Platform Team
- Date: 2026-06-20

Technical Story: The self-hosted runner was originally required because private Logic App deployment needed VNet access to reach the SCM endpoint. With Deployment Center handling Logic App deployment internally (see [ADR-04](04-deployment-center-for-logic-app.md)), and Container App updates operating via the ARM management plane (publicly accessible), no CI/CD operation requires VNet-level network access. GitHub-hosted runners handle all deployment tasks.

## Context and Problem Statement

The private deployment variant previously required a self-hosted runner VM inside the VNet for two reasons:

1. **Logic App deployment**: Zip deploy needs SCM access, which is blocked by the private endpoint
2. **Container App deployment**: Assumed to require VNet access

Analysis revealed that Container App updates via `az containerapp update` operate through the ARM management plane — accessible from any authenticated context, regardless of network position. Combined with Deployment Center eliminating the Logic App SCM requirement, the self-hosted runner has no remaining mandatory use case.

## Decision Drivers

- Zero maintenance: no OS updates, no runner agent updates, no disk space monitoring
- Zero cost: free for public repositories, included minutes for private repositories
- Ephemeral security: each job runs on a fresh VM — no credential persistence
- Deployment Center handles private Logic App deployment without external runner
- ARM management plane is accessible from public internet for Container App updates
- Self-hosted runner Bicep module remains available for edge cases

## Considered Options

- Option A: Self-hosted runner for all deployments (previous approach)
- Option B: GitHub-hosted runners + Deployment Center (selected)
- Option C: Azure DevOps with VNet-injected agents
- Option D: GitHub-hosted runners with Azure VNet gateway (preview, not GA)

## Decision Outcome

Chosen option: **Option B — GitHub-hosted runners for CI/CD + Deployment Center for Logic App**, because no deployment operation requires VNet-level network access when Deployment Center handles Logic App deployment and Container App updates use the ARM management plane.

### Positive Consequences

- $70-150/month VM cost eliminated
- Zero operational overhead: no runner maintenance, no agent updates, no security patching
- Improved security: ephemeral runners leave no persistent credentials or state
- Simplified architecture: no runner subnet, no runner NSG rules, no runner identity
- Faster job startup: no queue waiting for single self-hosted runner availability

### Negative Consequences

- Cannot directly access VNet resources from CI/CD (e.g., for integration testing)
- GitHub-hosted runner minutes have limits on private repositories (2,000 min/month free)
- No persistent cache between runs (cold Docker layer cache each time)

## Technical Analysis

### Why VNet Access Is No Longer Required

| Deployment Task | Previous Requirement | Current Approach | VNet Access Needed? |
|---|---|---|---|
| Container App update | `az containerapp update` | Same — ARM management plane | No |
| Logic App workflows | Zip deploy to SCM endpoint | Deployment Center internal pull | No |
| Deployment sync trigger | N/A | `az webapp deployment source sync` | No (ARM) |
| GHCR image push | `docker push ghcr.io/...` | Same — public GHCR | No |
| Infrastructure (Bicep) | `az deployment group create` | Same — ARM management plane | No |

All operations use either the ARM management plane (publicly accessible with proper authentication) or public registries (GHCR). None require VNet-level network access.

### ARM Management Plane vs Data Plane

```text
┌──────────────────────────────────────────────────┐
│  GitHub-hosted runner (public internet)          │
│                                                  │
│  az containerapp update ──→ ARM (management.azure.com)  ✓ Public
│  az webapp deployment source sync ──→ ARM              ✓ Public
│  az deployment group create ──→ ARM                    ✓ Public
│  docker push ghcr.io/... ──→ GHCR                      ✓ Public
│                                                  │
│  az logicapp deployment source config-zip ──→ SCM      ✗ Private (blocked)
│  (eliminated by Deployment Center)                     │
└──────────────────────────────────────────────────┘
```

The only operation that required VNet access (zip deploy to SCM) is eliminated by Deployment Center.

### Self-Hosted Runner Module (Conditional)

The `github-runner.bicep` module remains in the codebase as a conditional resource:

```bicep
module runner 'modules/github-runner.bicep' = if (!empty(runnerToken)) {
  name: 'github-runner'
  params: {
    baseName: baseName
    location: location
    subnetId: snetReserved.id
    runnerToken: runnerToken
  }
}
```

When `runnerToken` is not provided (default), the module is not deployed. This preserves the option for teams that need a VNet-connected runner for:

- Integration testing against private endpoints
- Manual debugging and operations
- Scenarios where data-plane access is required from CI/CD

### Cost Analysis

| Component | Self-Hosted Runner | GitHub-Hosted |
|---|---|---|
| VM (B2s or D2s_v5) | $70-150/month | $0 |
| Managed disk (128 GB) | $10/month | $0 |
| Runner agent maintenance | Operational overhead | $0 |
| OS patching | Operational overhead | $0 |
| Network (NIC, NSG rules) | Config complexity | $0 |
| **Total** | **$80-160/month + ops** | **$0** |

For private repositories, GitHub Actions provides 2,000 minutes/month free (3,000 for Pro). Additional minutes cost $0.008/min. Typical deployment runs (~5 min each, ~60 runs/month) use approximately 300 minutes — well within free tier.

### Security Comparison

| Aspect | Self-Hosted Runner | GitHub-Hosted Runner |
|---|---|---|
| Runner state | Persistent (reused across jobs) | Ephemeral (fresh VM per job) |
| Credential persistence | Secrets may remain in memory | Cleaned after each job |
| OS updates | Manual responsibility | Managed by GitHub |
| Attack surface | Long-running VM in VNet | No persistent infrastructure |
| Network exposure | NIC in VNet with NSG | No VNet presence |

## Pros and Cons of the Options

### Option A: Self-Hosted Runner for All

- Good, because it provides VNet access for any deployment operation
- Good, because it works for integration testing
- Bad, because it costs $70-150/month for a single runner
- Bad, because runner maintenance adds operational overhead
- Bad, because a single runner creates a queue bottleneck for concurrent workflows
- Bad, because persistent state increases security risk

### Option C: Azure DevOps with VNet-Injected Agents

- Good, because Microsoft-hosted agents can be VNet-injected
- Bad, because source code lives in GitHub — introduces a second CI system
- Bad, because VNet-injected agents are not free (paid Azure DevOps)
- Bad, because team must maintain expertise in two CI/CD platforms

### Option D: GitHub-Hosted with VNet Gateway (Preview)

- Good, because it would provide VNet access from GitHub-hosted runners
- Bad, because the feature is in preview (not GA) and not recommended for production
- Bad, because it adds networking complexity (VNet gateway, peering)
- Bad, because it is unnecessary when Deployment Center eliminates the VNet requirement

## Implementation Reference

### CI/CD Workflow (`.github/workflows/deploy-apps.yml`)

Runner selection (simplified to always use GitHub-hosted):

```yaml
jobs:
  deploy-container-app:
    runs-on: ubuntu-latest
    steps:
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - name: Update Container App
        run: |
          az containerapp update \
            --name "${{ env.CONTAINER_APP_NAME }}" \
            --resource-group "${{ env.RESOURCE_GROUP }}" \
            --image "ghcr.io/${{ github.repository_owner }}/communicator:latest"

  sync-logic-app:
    runs-on: ubuntu-latest
    steps:
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - name: Trigger Deployment Center Sync
        run: |
          az webapp deployment source sync \
            --name "${{ env.LOGIC_APP_NAME }}" \
            --resource-group "${{ env.RESOURCE_GROUP }}"
```

### Conditional Runner Module (`src/infra_deployment/modules/github-runner.bicep`)

Deployed only when `runnerToken` is provided:

```bicep
param runnerToken string = ''

module runner 'modules/github-runner.bicep' = if (!empty(runnerToken)) {
  // ... VM + runner agent installation
}
```

## Summary for Solution Architects

| Aspect | Self-Hosted (Previous) | GitHub-Hosted (Current) |
|---|---|---|
| Monthly cost | $70-150 (VM + disk) | $0 (public) / minutes-based (private) |
| Maintenance | OS patches, agent updates | None (GitHub-managed) |
| VNet access | Yes (NIC in subnet) | No (not needed) |
| Availability | Single VM (bottleneck) | Elastic pool (concurrent jobs) |
| Security posture | Persistent state | Ephemeral (clean per job) |
| Container App deploy | via ARM (works from anywhere) | via ARM (works from anywhere) |
| Logic App deploy | Zip deploy to private SCM | Deployment Center (app pulls internally) |
| Setup complexity | Bicep module + runner token | Zero configuration |

## Links

- Related: [ADR-04 — Deployment Center for Logic App](04-deployment-center-for-logic-app.md)
- Related: [ADR-03 — GHCR with NAT Gateway](03-ghcr-with-nat-gateway.md)
