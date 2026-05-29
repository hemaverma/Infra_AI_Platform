---
title: "Use NAT Gateway Instead of Azure Firewall for Outbound Connectivity"
description: "ADR explaining why NAT Gateway was chosen over Azure Firewall for providing outbound internet connectivity from the private VNet"
ms.date: 2026-06-20
ms.topic: reference
---

# Use NAT Gateway Instead of Azure Firewall for Outbound Connectivity

- Status: Accepted
- Deciders: Platform Team
- Date: 2026-06-20

Technical Story: The private VNet workloads need outbound internet access for GHCR image pulls, GitHub source fetches (Deployment Center), and cloud-init operations. NAT Gateway provides this connectivity at 3.5% the cost of Azure Firewall Standard while meeting the platform's security requirements.

## Context and Problem Statement

The private deployment variant uses NSG deny-all-other rules to block unauthorized outbound traffic. Three subnets require controlled outbound internet access:

| Subnet | Outbound Requirement |
|---|---|
| `snet-container-apps` | GHCR image pull (`ghcr.io`, `*.githubusercontent.com`) |
| `snet-functions` | GitHub source fetch for Deployment Center (`github.com`) |
| `snet-reserved` | Cloud-init, runner agent registration (if deployed) |

The platform needs an outbound connectivity mechanism that balances security, cost, and operational simplicity for an accelerator/PoC-stage platform.

## Decision Drivers

- Cost: $32/month (NAT) vs $912/month (Firewall Standard) — 28x difference
- Operational simplicity: no firewall rules to manage, no route tables to maintain
- Sufficient security: NSG rules restrict outbound to HTTPS (port 443) only
- Platform stage: accelerator/PoC — not yet subject to enterprise compliance FQDN filtering
- Upgrade path: Azure Firewall can be added later if compliance requires FQDN filtering

## Considered Options

- Option A: Azure Firewall Standard (full FQDN filtering, TLS inspection)
- Option B: Azure Firewall Basic (limited throughput, basic filtering)
- Option C: NAT Gateway Standard SKU (selected)
- Option D: No outbound mechanism (all private endpoints)

## Decision Outcome

Chosen option: **Option C — NAT Gateway Standard SKU**, because it provides the required outbound SNAT connectivity at minimal cost while NSG rules provide adequate traffic restriction for the platform's current security posture.

### Positive Consequences

- Monthly cost of $32 vs $912 (Firewall Standard) — saves $880/month
- Zero operational overhead: no rule management, no threat intelligence feeds, no route tables
- Simple architecture: NAT Gateway attaches directly to subnets, no UDR required
- Static outbound IP: useful for allowlisting with external services
- Scales automatically: 64K SNAT ports per IP, expandable to 16 IPs

### Negative Consequences

- No FQDN filtering: cannot restrict outbound to specific domains (only port-level via NSG)
- No TLS inspection: cannot inspect encrypted traffic content
- No threat intelligence: no automatic blocking of known-bad destinations
- May require migration to Azure Firewall if enterprise compliance mandates FQDN filtering

## Technical Analysis

### NAT Gateway Configuration

| Property | Value |
|---|---|
| Name | `{baseName}-natgw` |
| SKU | Standard |
| Public IPs | 1 (`{baseName}-natgw-pip`) |
| Idle timeout | 4 minutes |
| SNAT ports per IP | 64,512 |
| Max public IPs | 16 (1,032,192 total SNAT ports) |
| Availability zones | Zone-redundant |

### Subnet Attachments

```text
snet-container-apps ──→ {baseName}-natgw
snet-functions      ──→ {baseName}-natgw
snet-reserved       ──→ {baseName}-natgw
```

Subnets NOT attached (no outbound needed):

- `snet-private-endpoints` — only inbound traffic via private endpoints
- `AzureBastionSubnet` — Bastion has its own public IP

### Security Posture with NAT Gateway

The security boundary is enforced by NSG rules, not the NAT Gateway:

```text
Priority  Name                              Direction  Action  Protocol  Destination
200       Allow-Outbound-HTTPS-To-Internet  Outbound   Allow   TCP       Internet:443
1000      DenyAllOtherOutbound              Outbound   Deny    *         *
```

This combination provides:
- **Allowed**: HTTPS (TCP 443) to any internet destination
- **Denied**: HTTP, SSH, DNS over non-standard ports, all other protocols
- **Denied**: All traffic not matching an explicit allow rule

### Cost Comparison

| Solution | Monthly Cost | FQDN Filtering | TLS Inspection | Throughput | Complexity |
|---|---|---|---|---|---|
| NAT Gateway | $32 | No | No | 50 Gbps | Low |
| Azure Firewall Basic | $252 | Yes (limited) | No | 250 Mbps | Medium |
| Azure Firewall Standard | $912 | Yes | Optional | 30 Gbps | High |
| Azure Firewall Premium | $1,462 | Yes | Yes (built-in) | 100 Gbps | High |

Cost breakdown for NAT Gateway:
- NAT Gateway resource: $0.045/hour × 730 hours = $32.85/month
- Public IP (Standard): $3.65/month
- Data processing: $0.045/GB (minimal for image pulls and git fetches)
- **Total estimate: ~$37/month**

### Upgrade Path to Azure Firewall

If the platform moves to production with enterprise compliance requirements (FQDN filtering, TLS inspection, threat intelligence):

1. Deploy Azure Firewall in a dedicated `AzureFirewallSubnet`
2. Create route tables with UDR pointing default route to Firewall private IP
3. Associate route tables with the three subnets
4. Remove NAT Gateway association from subnets (Firewall provides SNAT)
5. Configure application rules for allowed FQDNs

The migration is additive — NAT Gateway removal is the final step after Firewall is validated.

### Why Option D (No Outbound) Is Not Feasible

| Service | Private Endpoint Available? | Notes |
|---|---|---|
| GHCR (`ghcr.io`) | No | GitHub does not offer Azure Private Link |
| GitHub (`github.com`) | No | Required for Deployment Center source fetch |
| Cloud-init endpoints | No | Ubuntu package repos, Azure IMDS |

Without outbound connectivity, the platform cannot pull container images or deploy Logic App workflows.

## Pros and Cons of the Options

### Option A: Azure Firewall Standard

- Good, because it provides FQDN filtering (restrict to `ghcr.io`, `github.com` only)
- Good, because threat intelligence blocks known-bad IPs automatically
- Good, because centralized logging of all outbound traffic
- Bad, because it costs $912/month — disproportionate for an accelerator platform
- Bad, because it requires route tables, UDRs, and firewall rule management
- Bad, because it adds significant deployment complexity (dedicated subnet, policy)

### Option B: Azure Firewall Basic

- Good, because it costs less than Standard ($252/month)
- Good, because it provides basic FQDN filtering
- Bad, because throughput is limited to 250 Mbps
- Bad, because it still costs 8x more than NAT Gateway
- Bad, because it has limited rule capacity and no threat intelligence

### Option D: No Outbound (All Private Endpoints)

- Good, because it provides maximum network isolation
- Bad, because GHCR and GitHub do not support Azure Private Link
- Bad, because it makes the platform inoperable for its core use cases

## Implementation Reference

### Networking Module (`src/infra_deployment/modules/networking.bicep`)

NAT Gateway and public IP resources:

```bicep
resource natGatewayPip 'Microsoft.Network/publicIPAddresses@2024-01-01' = {
  name: '${baseName}-natgw-pip'
  location: location
  sku: { name: 'Standard' }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

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

Subnet association:

```bicep
resource snetContainerApps 'Microsoft.Network/virtualNetworks/subnets@2024-01-01' = {
  // ...
  properties: {
    addressPrefix: '10.0.2.0/23'
    natGateway: { id: natGateway.id }
    // ...
  }
}
```

## Summary for Solution Architects

| Aspect | NAT Gateway (Selected) | Azure Firewall Standard | Azure Firewall Basic |
|---|---|---|---|
| Monthly cost | $32 | $912 | $252 |
| FQDN filtering | No (NSG port-level only) | Yes | Yes (limited) |
| TLS inspection | No | Optional | No |
| Throughput | 50 Gbps | 30 Gbps | 250 Mbps |
| Operational complexity | Low | High | Medium |
| Route tables required | No | Yes (UDR) | Yes (UDR) |
| Logging | NSG flow logs | Firewall diagnostics | Firewall diagnostics |
| Use case fit | Accelerator/PoC | Enterprise production | Small enterprise |
| Upgrade path | Add Firewall later | N/A (already at target) | Upgrade to Standard |

## Links

- Related: [ADR-03 — GHCR with NAT Gateway](03-ghcr-with-nat-gateway.md)
- Related: [ADR-04 — Deployment Center for Logic App](04-deployment-center-for-logic-app.md)
