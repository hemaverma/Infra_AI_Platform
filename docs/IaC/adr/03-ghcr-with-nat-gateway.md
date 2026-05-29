---
title: "Use GHCR with NAT Gateway for All Container Image Deployments"
description: "ADR explaining why all container image deployments use GitHub Container Registry (GHCR) with NAT Gateway for outbound connectivity, eliminating the ACR dependency"
ms.date: 2026-06-20
ms.topic: reference
---

# Use GHCR with NAT Gateway for All Container Image Deployments

- Status: Accepted (Supersedes [ADR-01](01-private-deployment-acr-over-ghcr.md))
- Deciders: Platform Team
- Date: 2026-06-20

Technical Story: The introduction of a NAT Gateway on the private VNet enables outbound HTTPS connectivity to GHCR from within the isolated network. This eliminates the original constraint that required Azure Container Registry (ACR) with a private endpoint for container image pulls in the private deployment variant.

## Context and Problem Statement

ADR-01 established a dual-path architecture: GHCR for public deployments and ACR for private deployments. The reasoning was sound — private VNet workloads had no outbound internet access, making GHCR unreachable.

With the addition of a NAT Gateway to the private VNet (see [ADR-05](05-nat-gateway-over-firewall.md)), subnets now have controlled outbound HTTPS connectivity. This resolves the fundamental constraint that drove the ACR requirement and enables unification on a single registry for all deployment variants.

## Decision Drivers

- Cost optimization: ACR ($5-50/month) can be eliminated entirely
- Operational simplicity: single registry path for all variants, no dual-path CI/CD logic
- Zero-secret architecture: public GHCR packages require no authentication for pulls
- CI/CD unification: single GHCR push path, no conditional registry selection
- NAT Gateway already provisioned for other outbound requirements (GitHub fetch, cloud-init)

## Considered Options

- Option A: Continue ACR for private deployments (status quo from ADR-01)
- Option B: GHCR with NAT Gateway for all deployments (selected)
- Option C: GHCR with Azure Firewall FQDN rules
- Option D: ACR Artifact Cache mirroring GHCR

## Decision Outcome

Chosen option: **Option B — GHCR with NAT Gateway**, because NAT Gateway resolves the outbound connectivity constraint at minimal incremental cost (already provisioned for other workloads), enabling a unified single-registry architecture with zero secret management for image pulls.

### Positive Consequences

- Single registry (GHCR) for all deployment variants — eliminates dual-path logic in CI/CD
- Zero secrets for image pulls (Container App pulls public packages anonymously)
- ACR resource eliminated — removes $5-50/month recurring cost
- CI/CD simplified — no conditional registry determination step
- GitHub-native workflow: build → push to GHCR → deploy reference

### Negative Consequences

- Depends on NAT Gateway for outbound connectivity (single point of failure for SNAT)
- No private endpoint for registry traffic — images traverse the public internet via NAT
- Cannot use Defender for Containers image scanning (GHCR only supports GitHub Advanced Security)

## Technical Analysis

### How NAT Gateway Enables GHCR Access

The NAT Gateway provides SNAT for outbound traffic from three subnets:

| Subnet | Purpose | GHCR Requirement |
|---|---|---|
| `snet-container-apps` | Container App runtime | Image pull from `ghcr.io` |
| `snet-functions` | Logic App / Functions | Not applicable |
| `snet-reserved` | Runner / future workloads | CI/CD operations |

NAT Gateway configuration:

| Property | Value |
|---|---|
| Name | `{baseName}-natgw` |
| SKU | Standard |
| Public IPs | 1 (`{baseName}-natgw-pip`) |
| Idle timeout | 4 minutes |
| SNAT ports | 64K per IP (expandable to 16 IPs) |

### NSG Rules Enabling GHCR Traffic

The NSG attached to container subnets includes:

```text
Priority  Name                              Direction  Action  Destination
200       Allow-Outbound-HTTPS-To-Internet  Outbound   Allow   Internet:443
1000      DenyAllOtherOutbound              Outbound   Deny    *
```

Rule 200 permits HTTPS egress (required for `ghcr.io`, `*.githubusercontent.com`, `pkg-containers.githubusercontent.com`). Rule 1000 denies everything else.

### Container App Configuration

With GHCR as the sole registry, the Container App configuration simplifies:

```bicep
// No registry credentials needed — anonymous pull from public package
registries: []

template: {
  containers: [
    {
      name: 'communicator'
      image: 'ghcr.io/{owner}/communicator:latest'
    }
  ]
}
```

The `acrLoginServer` parameter is passed as empty string `''`, bypassing all registry credential logic.

### Cost Comparison

| Component | ADR-01 (ACR) | ADR-03 (GHCR + NAT) |
|---|---|---|
| ACR Basic | $5/month | $0 (eliminated) |
| ACR Premium (geo-replication) | $50/month | $0 (eliminated) |
| NAT Gateway | N/A | $32/month (shared with other workloads) |
| Managed identity for AcrPull | Config overhead | N/A |
| **Net cost** | $5-50/month + identity config | $0 incremental (NAT already provisioned) |

NAT Gateway cost is attributed to [ADR-05](05-nat-gateway-over-firewall.md) since it serves multiple purposes beyond GHCR access.

### Why This Was Not Possible Before

ADR-01 correctly identified that GHCR cannot serve private VNet workloads **without outbound connectivity**. The constraint was:

> NSG rule `DenyAllOtherOutbound` blocks all GHCR traffic

NAT Gateway resolves this by providing controlled SNAT while NSG rules restrict traffic to HTTPS only. The security boundary shifts from "no outbound at all" to "outbound HTTPS only via NAT with static IP."

## Pros and Cons of the Options

### Option A: Continue ACR for Private (Status Quo)

- Good, because traffic stays entirely within Azure backbone
- Good, because Defender for Containers provides image scanning
- Bad, because it maintains dual-path CI/CD complexity
- Bad, because it requires managed identity configuration for AcrPull
- Bad, because ACR adds recurring cost with no unique benefit once NAT exists

### Option C: GHCR with Azure Firewall FQDN Rules

- Good, because it provides FQDN-level filtering for GHCR domains
- Bad, because Azure Firewall costs $912/month — disproportionate
- Bad, because NAT Gateway already provides the outbound connectivity needed
- Bad, because the filtering adds operational complexity with minimal security gain

### Option D: ACR Artifact Cache

- Good, because images are cached locally after first pull
- Bad, because it requires ACR Premium ($50/month)
- Bad, because it adds operational complexity (cache invalidation, mirror sync)
- Bad, because GHCR is already fast enough for image pulls via NAT

## Implementation Reference

### Networking Module (`src/infra_deployment/modules/networking.bicep`)

NAT Gateway resource with subnet association:

```bicep
resource natGateway 'Microsoft.Network/natGateways@2024-01-01' = {
  name: '${baseName}-natgw'
  location: location
  sku: { name: 'Standard' }
  properties: {
    idleTimeoutInMinutes: 4
    publicIpAddresses: [{ id: natGatewayPip.id }]
  }
}
```

### Container Apps Module (`src/infra_deployment/modules/container-apps.bicep`)

Registry configuration when using GHCR (no credentials):

```bicep
registries: !empty(acrLoginServer) ? [
  { server: acrLoginServer, identity: managedIdentityId }
] : []  // GHCR path: anonymous pull, no registry config needed
```

### CI/CD Workflow (`.github/workflows/deploy-apps.yml`)

Single GHCR push path:

```yaml
- name: Push to GHCR
  run: |
    echo "${{ secrets.GITHUB_TOKEN }}" | docker login ghcr.io -u ${{ github.actor }} --password-stdin
    docker push ghcr.io/${{ github.repository_owner }}/communicator:latest
```

## Summary for Solution Architects

| Aspect | Previous (ADR-01) | Current (ADR-03) |
|---|---|---|
| Registry | GHCR (public) / ACR (private) | GHCR for all variants |
| Auth mechanism | Anonymous (public) / Managed identity (private) | Anonymous for all |
| Runner | GitHub-hosted (public) / Self-hosted (private) | GitHub-hosted for all |
| Network requirement | Public internet / Private endpoint | NAT Gateway outbound |
| Secret management | None / Managed identity config | None |
| Cost | $0 / $5-50/month ACR | $0 incremental |
| CI/CD complexity | Dual-path registry logic | Single path |
| Image scanning | N/A / Defender for Containers | GitHub Advanced Security |

## Links

- Supersedes: [ADR-01 — ACR vs GHCR for Private Deployment](01-private-deployment-acr-over-ghcr.md)
- Related: [ADR-05 — NAT Gateway over Azure Firewall](05-nat-gateway-over-firewall.md)
