---
title: "NExT VPN Setup Guide"
description: ""
ms.date: 2026-06-24
ms.topic: overview
---


# VPN Setup Guide

This guide covers connecting to the NExT private VNet via Point-to-Site (P2S) VPN using Entra ID authentication.

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Azure VPN Client | [Download from Microsoft Store](https://apps.microsoft.com/detail/9NP355QT2SQB) or [direct download](https://aka.ms/azvpnclientdownload) |
| Entra ID Account | Must be in the FDPO tenant (`<your_tenantID>`) |
| VPN Gateway Deployed | Phase 1 (network) deployment must be complete |
| OS | Windows 10/11, macOS, or Linux |

---

## Quick Start

### 1. Install Azure VPN Client

Download and install from the Microsoft Store or the direct link above. The Azure VPN Client supports OpenVPN protocol with Entra ID authentication.

### 2. Import VPN Profile

1. Open **Azure VPN Client**
2. Click the **+** button (bottom left) → **Import**
3. Navigate to this repository's folder:

   ```text
   src/infra_deployment/private/vpn-client-profile/AzureVPN/azurevpnconfig.xml
   ```

4. Click **Save**

### 3. Connect

3. Select the imported connection (named `next-vnet`)
2. Click **Connect**
3. Authenticate with your FDPO Entra ID credentials when prompted
4. Wait for "Connected" status

### 4. Verify Connectivity

Open a terminal and verify DNS resolution returns private IPs (10.0.x.x):

```powershell
# Flush DNS cache first
ipconfig /flushdns

# Verify private endpoint resolution
Resolve-DnsName "next-kv.vault.azure.net"
Resolve-DnsName "nextacr.azurecr.io"
Resolve-DnsName "nextst.blob.core.windows.net"
Resolve-DnsName "next-servicebus.servicebus.windows.net"
```

**Expected**: All hostnames resolve to addresses in the `10.0.5.x` range (private endpoint subnet).

**If you see public IPs**: DNS is not routing through the VPN. See [Troubleshooting](#troubleshooting).

---

## Connection Details

| Property | Value |
|----------|-------|
| VPN Type | OpenVPN (SSL/TLS) |
| Transport | TCP |
| Authentication | Entra ID (AAD) |
| Tenant | `https://login.microsoftonline.com/<your_tenantID>` |
| Audience | `c632b3df-fb67-4d84-bdcf-b95ad541b5c8` |
| Issuer | `https://sts.windows.net/<your_tenantID>/` |
| Client Address Pool | `172.16.0.0/24` |
| VNet Address Space | `10.0.0.0/16` |
| Custom DNS Server | `10.0.9.4` (DNS Private Resolver) |
| Gateway FQDN | `azuregateway-a37b0043-c671-4ccb-b84a-6cf43fced19e-465029442f24.vpn.azure.com` |

---

## Network Routing

When connected, the VPN client routes traffic for these address ranges through the tunnel:

| Range | Purpose |
|-------|---------|
| `10.0.0.0/16` | VNet address space (all subnets and private endpoints) |
| `172.16.0.0/24` | VPN client pool (other connected clients) |

All other traffic (internet, corporate network) continues through your normal routes — this is a **split-tunnel** configuration.

---

## DNS Configuration

The VPN profile configures a custom DNS server (`10.0.9.4` — the DNS Private Resolver inbound endpoint) and registers these DNS suffixes for private link resolution:

| Suffix | Service |
|--------|---------|
| `privatelink.vaultcore.azure.net` | Key Vault |
| `privatelink.azurecr.io` | Container Registry |
| `privatelink.blob.core.windows.net` | Blob Storage |
| `privatelink.servicebus.windows.net` | Service Bus |
| `privatelink.documents.azure.com` | Cosmos DB |
| `privatelink.postgres.database.azure.com` | PostgreSQL |
| `privatelink.openai.azure.com` | Azure OpenAI |
| `privatelink.cognitiveservices.azure.com` | Cognitive Services |
| `privatelink.azurewebsites.net` | Function App / Logic App |
| `privatelink.monitor.azure.com` | Azure Monitor |
| `privatelink.oms.opinsights.azure.com` | Log Analytics |
| `privatelink.ods.opinsights.azure.com` | Log Analytics (ODS) |
| `privatelink.agentsvc.azure-automation.net` | Automation Agent |
| `privatelink.api.azureml.ms` | AI Foundry API |
| `privatelink.notebooks.azure.net` | AI Foundry Notebooks |
| `privatelink.table.core.windows.net` | Table Storage |
| `privatelink.queue.core.windows.net` | Queue Storage |
| `privatelink.file.core.windows.net` | File Storage |

---

## Subnet Layout

| Subnet | CIDR | Purpose |
|--------|------|---------|
| GatewaySubnet | `10.0.0.0/27` | VPN Gateway |
| snet-functions | `10.0.1.0/26` | Function App + Logic App VNet integration |
| snet-container-apps | `10.0.2.0/23` | Container Apps Environment |
| snet-data-postgres | `10.0.4.0/28` | PostgreSQL Flexible Server |
| snet-data-sqlmi | `10.0.4.32/27` | SQL Managed Instance |
| snet-private-endpoints | `10.0.5.0/24` | All private endpoints |
| snet-monitor | `10.0.6.0/28` | Azure Monitor (reserved) |
| snet-reserved | `10.0.7.0/24` | Deployer VM (private variant) |
| snet-dns-resolver-inbound | `10.0.9.0/28` | DNS Private Resolver inbound endpoint |

---

## Troubleshooting

### DNS resolves to public IPs instead of 10.0.x.x

1. Verify VPN is connected (status shows "Connected" in Azure VPN Client)
2. Flush DNS cache:

   ```powershell
   ipconfig /flushdns
   ```

3. Confirm the DNS server is set:

   ```powershell
   Get-DnsClientServerAddress | Where-Object { $_.ServerAddresses -contains "10.0.9.4" }
   ```

4. If DNS server is missing, disconnect and reconnect the VPN

### Connection fails with authentication error

- Verify your account is in the FDPO tenant (`<your_tenantID>`)
- Check that your account has not been blocked or requires MFA re-authentication
- Try signing out and back in to the Azure VPN Client

### Connection drops or times out

- The VPN Gateway SKU is `VpnGw1AZ` (supports up to 250 P2S connections)
- Check if the gateway is in a healthy state:

  ```powershell
  az network vnet-gateway show --name next-vpn-gw --resource-group NExT-Private --query "provisioningState" -o tsv
  ```

### Cannot reach a specific service

1. Verify the private endpoint exists:

   ```powershell
   az network private-endpoint list --resource-group NExT-Private --query "[].{Name:name, NIC:networkInterfaces[0].id}" -o table
   ```

2. Verify the DNS zone has the A record:

   ```powershell
   az network private-dns record-set a list --zone-name privatelink.vaultcore.azure.net --resource-group NExT-Private -o table
   ```

3. Test TCP connectivity:

   ```powershell
   Test-NetConnection -ComputerName "nextkv.vault.azure.net" -Port 443
   ```

### VPN profile is outdated

Re-download the profile from the Azure Portal or CLI:

```powershell
az network vnet-gateway vpn-client generate --name next-vpn-gw --resource-group NExT-Private --processor-architecture Amd64 -o tsv | ForEach-Object { Invoke-WebRequest -Uri $_ -OutFile vpn-profile.zip }
Expand-Archive -Path vpn-profile.zip -DestinationPath src/infra_deployment/private/vpn-client-profile/ -Force
```

---

## Running Infrastructure Tests Over VPN

With VPN connected, run the reachability test suite:

```powershell
cd tests/infra
pip install -r requirements.txt
pytest tests/infra/tests/test_connectivity.py tests/infra/tests/test_networking.py -v
```

These tests validate:

- DNS resolution returns private IPs for all endpoints
- TCP connectivity to private endpoints on expected ports
- Service Bus, Cosmos DB, Key Vault, and Storage are reachable
- NSG rules allow traffic from VPN client pool

---

## Profile File Reference

| File | Purpose |
|------|---------|
| `src/infra_deployment/private/vpn-client-profile/AzureVPN/azurevpnconfig.xml` | Azure VPN Client profile (recommended) |
| `src/infra_deployment/private/vpn-client-profile/Generic/VpnSettings.xml` | Generic OpenVPN settings (for non-Windows clients) |
| `src/infra_deployment/private/vpn-client-profile/Generic/VpnServerRoot.cer_0` | Server root certificate |

---

## Deployment Behavior

VPN Gateway deploys independently from all other infrastructure modules. This separation ensures that VPN provisioning failures do not cascade to service deployments.

### Independent Module Deployment

The VPN Gateway uses its own Bicep module (`src/infra_deployment/modules/vpn-gateway.bicep`) and deploys in parallel with service modules. Services only depend on the VNet and DNS zones (ready in ~5 min), not on VPN Gateway completion (~35 min).

### Automatic Retry on Transient Failure

The deployment script (`deploy.ps1`) detects when VPN Gateway is the only failing resource and retries the deployment once automatically. Transient failures from Azure capacity constraints or timeout during the long provisioning window are handled without manual intervention.

### Recovery After Failed Retry

If the automatic retry also fails, all services remain deployed and fully functional. VPN Gateway can be recovered later independently:

```powershell
az network vnet-gateway update --name <prefix>-vpn-gw --resource-group <rg> --no-wait
```

Alternatively, re-run the network phase:

```powershell
pwsh -File src/infra_deployment/ps-scripts/deploy.ps1 -Phase network -Variant private -ResourceGroup <rg> -Location westus3 -BaseName <prefix>
```

### VPN Failure Does Not Affect Service Access

Private endpoints operate independently of the VPN Gateway. All service-to-service communication (Function App to Cosmos DB, Logic App to Service Bus, Container Apps to Key Vault) uses VNet integration and private endpoints directly.

VPN is required only for developer access to private endpoints from local machines. If VPN Gateway is unavailable, deployed services continue operating normally.
