---
title: "NExT IaC Private Variant Deployment Guide"
description: "Private Variant Deployment Guide for VNet-isolated infrastructure with phased provisioning, VPN-based access, and NAT Gateway outbound connectivity"
ms.date: 2026-06-14
ms.topic: how-to
---

<!-- markdownlint-disable MD025 -->

# Private Variant Deployment Guide (VNet-Isolated)

This guide provides a complete end-to-end walkthrough for deploying the NExT infrastructure in a fully private VNet-isolated configuration.

---

## Overview

The private deployment places all Azure PaaS services behind private endpoints within a VNet. Developer access for debugging is through a Point-to-Site VPN gateway authenticated exclusively via Microsoft Entra ID (OpenVPN/TCP protocol). Deployments use GitHub Actions (Container App via GHCR) and Deployment Center (Logic App via Kudu external git), both leveraging a NAT Gateway for outbound connectivity.


### Private Variant Deployment Overview
Full component layout with data flows

![Private Variant Deployment overview](../../../docs/IaC/assets/private-Iac-overview.png)

### Private Variant Networking Overview
Network Topology: Subnets, private endpoints, DNS zones, DNS resolver

![Private Variant Networking](../../../docs/IaC/assets/private-networking.png)

### Private Variant NSG Rules
NSG Rules: Per-subnet NSG inbound/outbound rules

![Private Variant Networking](../../../docs/IaC/assets/nsg-rules.png)

---

## Contents

This directory consolidates all private-variant deployment artifacts:

| File | Purpose |
|------|---------|
| `main.bicep` | Private variant orchestrator template |
| `phase1-network.bicep` | Phase 1 network foundation deployment |
| `phase2-services.bicep` | Phase 2 service deployment with private endpoints |
| `parameters.json` | Bicep parameter defaults |
| `vpn-client-profile/` | VPN client configuration files (azurevpnconfig.xml) |

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Azure CLI | v2.60+ with Bicep extension |
| Subscription | `<yoursubscription>` (or any with required providers) |
| Resource Group | `<ResourceGroupName>` in `<location>` |
| Entra ID Tenant | FDPO (`<your_tenantID>`) |
| Azure VPN Enterprise App | `<vpn>` (admin-consented) |
| Azure VPN Client | [Microsoft Store](https://apps.microsoft.com/detail/9NP355QT2SQB) |
| PostgreSQL Password | Set in `.env` as `postgreSQL_Password` |

---

## Private Variant Deployment Workflow

![Private Variant Deployment Workflow](../../../docs/IaC/assets/private-deployment-workflow.png)

### Phase 1: Network Foundation (~5 min) + VPN Gateway (~35 min, parallel)

Deploy VNet, DNS zones, identity, and observability. VPN Gateway deploys as a separate module in parallel:

```bash
bash src/infra_deployment/deploy.sh \
  --phase network \
  --variant private \
  --resource-group <resource-gr-name> \
  --location <location> \
  --base-name next
```

This deploys two modules in parallel:

**Network core** (networking.bicep, ~5 min):

| Resource | Name | Config |
|----------|------|--------|
| Virtual Network | `next-vnet` | 10.0.0.0/16, 8 subnets |
| NSGs (4) | `next-nsg-*` | Per-subnet deny-all-other rules |
| Private DNS Zones | 18 zones | All linked to VNet |
| Managed Identity | `next-identity` | User Assigned |
| Log Analytics | `next-law` | PerGB2018 |
| App Insights | `next-appinsights` | Workspace-based |

**VPN Gateway** (vpn-gateway.bicep, ~35 min):

| Resource | Name | Config |
|----------|------|--------|
| VPN Gateway | `next-vpn-gw` | VpnGw1AZ, OpenVPN/TCP, Entra ID |
| Public IP | `next-vpn-pip` | Standard, Static, Zone-redundant |

> VPN Gateway deploys as a SEPARATE module (`vpn-gateway.bicep`) in parallel with service modules. A VPN Gateway failure does NOT block service deployment. Services can proceed as soon as VNet and DNS zones are ready (~5 min) without waiting for VPN Gateway provisioning (~35 min).
>
> If VPN Gateway encounters a transient failure, `deploy.sh` automatically retries once. If the retry also fails, services remain fully deployed and functional. VPN can be recovered later independently.

### Phase 1b: DNS Private Resolver (Automated)

The DNS Private Resolver and its inbound subnet (`snet-dns-resolver-inbound`, 10.0.9.0/28) are provisioned automatically by `networking.bicep`. After deployment, the resolver receives IP `10.0.9.4` and the VNet custom DNS is configured automatically.

> **Note**: The resolver requires delegation to `Microsoft.Network/dnsResolvers` on its subnet. This is handled by the Bicep module.

### Phase 2: VPN Connection (Not required for infrastructure deployment)

1. Download the VPN client profile (auto-generated after gateway deployment)
2. Import `src/infra_deployment/private/vpn-client-profile/AzureVPN/azurevpnconfig.xml` into Azure VPN Client
3. Connect using your FDPO Entra ID credentials
4. Verify DNS resolution:

```powershell
ipconfig /flushdns
Resolve-DnsName next-kv.vault.azure.net
# Expected: 10.0.5.x (private IP in PE subnet)
```

### Phase 3: Service Deployment

Deploy all PaaS services with private endpoints:

```bash
bash src/infra_deployment/deploy.sh \
  --phase services \
  --variant private \
  --resource-group NExT-Private \
  --location westus3 \
  --base-name next
```

This deploys:

| Resource | Name | Private Endpoint |
|----------|------|-----------------|
| Key Vault | `next-kv` | `privatelink.vaultcore.azure.net` |
| Storage Account | `nextst` | Blob + Queue + Table + File PEs |
| Service Bus | `next-servicebus` | `privatelink.servicebus.windows.net` |
| Cosmos DB | `next-cosmos` | `privatelink.documents.azure.com` |
| Azure OpenAI | `next-oai` | `privatelink.openai.azure.com` |
| Doc Intelligence | `next-di` | `privatelink.cognitiveservices.azure.com` |
| Content Safety | `next-csafety` | `privatelink.cognitiveservices.azure.com` |
| Logic App | `next-logic` | VNet-integrated + PE |
| Container Apps | `next-ca-env` | Internal-only (no public ingress) |
| PostgreSQL Flex | (conditional) | VNet-delegated |

### Phase 4: Application Deployment

**Container App**: Updated via GitHub Actions pushing to GHCR, then updating the Container App:

```bash
# GitHub Actions workflow (deploy-apps.yml) performs:
# 1. Build and push image to GHCR
docker build -t ghcr.io/{owner}/communicator:latest .
docker push ghcr.io/{owner}/communicator:latest

# 2. Update Container App to pull new image
az containerapp update \
  --name next-ca \
  --resource-group NExT-Private \
  --image ghcr.io/{owner}/communicator:latest
```

The Container App pulls from GHCR anonymously. Outbound access is provided by the NAT Gateway attached to `snet-container-apps`.

**Logic App**: Deployed via Azure Deployment Center (Kudu external git):

```bash
# Trigger a sync from the configured GitHub repository
az webapp deployment source sync \
  --name next-logic \
  --resource-group NExT-Private
```

Deployment Center uses Kudu to perform a `git pull` from the configured GitHub repository. Outbound connectivity for the fetch is provided by the NAT Gateway attached to `snet-functions`. See [Logic App Deployment (Deployment Center)](#logic-app-deployment-deployment-center) for full details.

---

## Phased Deployment

### Why phases?

VPN Gateway provisioning takes approximately 35 minutes. Running it in parallel with the networking module isolates its long execution time from the rest of the deployment. If the VPN Gateway fails (quota, region capacity), the networking foundation still succeeds, and VPN Gateway deployment can be retried independently.

Phase 2 modules require the VNet, subnets, and private DNS zones from Phase 1. Services create private endpoints that register DNS records in the zones established during Phase 1. The VPN connection must be active before Phase 2 so the Bicep deployment agent can resolve private DNS names.

### Phase sequence

1. Deploy Phase 1 (network + VPN, parallel execution within the phase)
2. Download VPN client profile and connect
3. Deploy Phase 2 (services with private endpoints)
4. Application deployment (GHCR + Deployment Center)

---

## DNS Resolution Architecture

```text
VPN Client (172.16.0.x)
    │ DNS query: next-kv.vault.azure.net
    ▼
VPN Gateway → VNet Custom DNS (10.0.9.4)
    │
    ▼
DNS Private Resolver (snet-dns-resolver-inbound, 10.0.9.0/28)
    │
    ▼
Private DNS Zone: privatelink.vaultcore.azure.net
    │ A record: next-kv → 10.0.5.x
    ▼
Client resolves to private endpoint IP
```

**Why this is needed**: Azure's wireserver (168.63.129.16) only responds to DNS queries from resources running inside the VNet (VMs, VMSS). P2S VPN clients route through the gateway but cannot reach 168.63.129.16. The DNS Private Resolver provides an in-VNet DNS forwarder at a routable IP (10.0.9.4) that can query the private DNS zones.

---

## Subnet Layout

| Subnet | CIDR | Delegation | Purpose |
|--------|------|-----------|---------|
| GatewaySubnet | 10.0.0.0/27 | (Azure-managed) | VPN Gateway |
| snet-functions | 10.0.1.0/26 | Microsoft.Web/serverFarms | Logic App |
| snet-container-apps | 10.0.2.0/23 | Microsoft.App/environments | Container Apps Environment |
| snet-data-postgres | 10.0.4.0/28 | Microsoft.DBforPostgreSQL | PostgreSQL Flex Server |
| snet-private-endpoints | 10.0.5.0/24 | — | All private endpoints (~13) |
| snet-monitor | 10.0.6.0/28 | — | Monitoring (reserved) |
| snet-reserved | 10.0.7.0/24 | — | Future use |
| snet-dns-resolver-inbound | 10.0.9.0/28 | Microsoft.Network/dnsResolvers | DNS Private Resolver inbound |

---

## VPN Gateway Configuration

| Setting | Value |
|---------|-------|
| Name | `next-vpn-gw` |
| SKU | VpnGw1AZ |
| Type | RouteBased |
| Protocol | OpenVPN (TCP 443) only |
| Authentication | Microsoft Entra ID only |
| Client Pool | 172.16.0.0/24 |
| AAD Tenant | `https://login.microsoftonline.com/<your_tenantID>` |
| AAD Audience | `c632b3df-fb67-4d84-bdcf-b95ad541b5c8` |
| Gateway FQDN | `azuregateway-a37b0043-c671-4ccb-b84a-6cf43fced19e-465029442f24.vpn.azure.com` |

No IKEv2 protocol. No certificate authentication. No root certificates configured.

---

## Infrastructure Testing

Run the test suite to validate all resources are reachable:

```powershell
# Set environment variables
$env:AZURE_SUBSCRIPTION_ID = "<your_subscription>"
$env:AZURE_TENANT_ID = "<your_tenantID>"

# Run tests (requires active VPN connection)
cd tests/infra
pytest tests/ -v --tb=short
```

Test configuration is in `tests/infra/config.yaml`:

```yaml
base_name: "next"
deployment_variant: "private"
location: "<location>"
ai_location: "<location>"
```


VPN Gateway failure isolation is a core design principle. The gateway's 35-minute provisioning time makes it the longest single resource deployment. A transient failure during provisioning does not block service deployment because `deploy.sh` retries automatically on failure, and the gateway module runs in parallel with the service phase prerequisites. If both attempts fail, all services remain fully deployed and functional; the VPN gateway can be recovered independently.

ACI deployment scripts cannot perform the full application deployment in private mode because ACI containers lack VNet DNS integration. They cannot resolve private DNS zone records for private endpoints. For the Container App, GitHub Actions pushes to GHCR and updates the Container App from a GitHub-hosted runner (the Container App pulls the image outbound via NAT Gateway). For the Logic App, Deployment Center (Kudu) performs a `git pull` from GitHub outbound via NAT Gateway, so no runner within the VNet is required.

---

## NAT Gateway

The NAT Gateway provides controlled outbound HTTPS connectivity for VNet-integrated services.

| Setting | Value |
|---------|-------|
| Name | `{baseName}-natgw` |
| SKU | Standard |
| Public IPs | 1 (`{baseName}-natgw-pip`) |
| Attached Subnets | `snet-functions`, `snet-container-apps`, `snet-reserved` |
| Purpose | Outbound HTTPS for Deployment Center (GitHub fetch), GHCR image pull, cloud-init |
| NSG Rule | `Allow-Outbound-HTTPS-To-Internet` (priority 200 on `nsg-functions`) |
| Cost | ~$32/month (vs $912/month for Azure Firewall) |

The NAT Gateway enables:

- **Logic App Deployment Center**: Kudu performs `git pull` from GitHub over HTTPS
- **Container App image pull**: Pull from `ghcr.io` anonymously
- **cloud-init**: Initial package installation on provisioned resources

> **Reference**: See [ADR-05](../../../docs/IaC/adr/05-nat-gateway-for-outbound.md) for the design decision.

---

## Logic App Deployment (Deployment Center)

The Logic App is deployed via Azure Deployment Center using Kudu external git.

| Setting | Value |
|---------|-------|
| Mechanism | Deployment Center (Kudu external git) |
| Bicep resource | `Microsoft.Web/sites/sourcecontrols@2023-12-01` |
| `isManualIntegration` | `true` (no webhook; sync triggered manually) |
| `isGitHubAction` | `false` (Kudu-based, not GitHub Actions) |
| Repository | `https://github.com/{owner}/{repo}` |
| Branch | `main` |
| `.deployment` file | Custom bash command targeting monorepo subfolder |

**Sync trigger:**

```bash
az webapp deployment source sync \
  --name {name} \
  --resource-group {rg}
```

**`.deployment` file** (in repo root):

```ini
[config]
command = bash -c "cp -r src/logic_app/* /home/site/wwwroot/"
```

Prerequisites:

- NAT Gateway on `snet-functions` (provides outbound HTTPS to GitHub)
- NSG rule `Allow-Outbound-HTTPS-To-Internet` at priority 200

> **Reference**: See [ADR-04](../../../docs/IaC/adr/04-deployment-center-for-logic-app.md) for the design decision.

---

## Design Rationale

| Decision | Rationale | Constraint |
|----------|-----------|------------|
| Service Bus Premium | Only tier supporting Private Endpoints | Azure platform constraint |
| GHCR + NAT Gateway | Single container registry for all variants; NAT provides outbound for image pull; ~$32/month | Single registry, no premium tier needed |
| Deployment Center | Kudu pulls from GitHub internally via NAT Gateway; no runner VM needed | No in-VNet runner required |
| NAT Gateway | Controlled outbound for GHCR pull, GitHub fetch, cloud-init. $32/month vs $912 Firewall | Cost-effective outbound without full firewall |
| VPN Gateway isolation | 35-min provision time; failure should not block services | Parallel deployment, auto-retry |
| Dual-auth PostgreSQL | Password now + Entra ID migration path later | Transition flexibility |
| AVM throughout | Official Microsoft modules; tested PE patterns; versioned | Best practice, consistency |
| Phased deployment | VPN verification between network and services | Operational safety |
| Single User-Assigned MI | Simplifies RBAC surface area | One identity across all services |

---

## Comparison with Public Deployment

See [Public Deployment Guide](../public/README.md) for the simplified public variant, or [Infrastructure Architecture](../../../docs/IaC/Infrastructure.md) for the full feature comparison table.
