# Deployment Variant Comparison

This document describes the differences between the public and private deployment variants and how they affect infrastructure testing.

## Public Variant

The public variant is a fast PoC/development deployment (~15-20 min) with all services accessible via public endpoints.

### Characteristics

- No VNet or private endpoints
- All PaaS services have public network access enabled
- Authentication is still RBAC-based (Entra ID tokens)
- No VPN required for local access
- All tests except `@pytest.mark.private_only` are applicable

### Resource Accessibility from Local Machine

| Resource | Endpoint Pattern | Access Method |
|----------|-----------------|---------------|
| Key Vault | `{name}.vault.azure.net` | Entra ID token |
| Storage | `{name}.blob.core.windows.net` | Entra ID token |
| Service Bus | `{name}.servicebus.windows.net` | Entra ID token |
| Cosmos DB | `{name}.documents.azure.com` | Entra ID token |
| PostgreSQL | `{name}.postgres.database.azure.com:5432` | Password or Entra ID (requires firewall rule) |
| OpenAI | `{name}.openai.azure.com` | Entra ID token |
| Doc Intelligence | `{name}.cognitiveservices.azure.com` | Entra ID token |
| Content Safety | `{name}.cognitiveservices.azure.com` | Entra ID token |
| Function App | `{name}.azurewebsites.net` | HTTPS (no auth for health) |
| Logic App | `{name}.azurewebsites.net` | HTTPS |
| ACR | `{name}.azurecr.io` | Docker token exchange |

## Private Variant

The private variant is a production-grade deployment (~45-60 min) with full VNet isolation.

### Characteristics

- VNet `10.0.0.0/16` with 8 subnets
- 18 private DNS zones for all PaaS services
- 4 NSGs with strict inbound/outbound rules
- P2S VPN Gateway for developer access (Entra ID auth)
- All PaaS services locked behind private endpoints
- `networkAcls.defaultAction: Deny` on all data services

### Resource Accessibility from Local Machine

**Requires active VPN connection** (OpenVPN + Entra ID):

| Resource | DNS Resolution | Access |
|----------|---------------|--------|
| Key Vault | Resolves to 10.0.5.x (PE subnet) | Via VPN only |
| Storage | Resolves to 10.0.5.x | Via VPN only |
| Service Bus | Resolves to 10.0.5.x | Via VPN only |
| Cosmos DB | Resolves to 10.0.5.x | Via VPN only |
| PostgreSQL | Resolves to 10.0.4.x (data subnet) | Via VPN only |
| OpenAI | Resolves to 10.0.5.x | Via VPN only |
| Function App | Resolves to 10.0.5.x | Via VPN only |
| ACR | Resolves to 10.0.5.x | Via VPN only |

### VPN Setup for Local Testing

1. Download VPN client configuration from Azure Portal:
   - Navigate to VPN Gateway → Point-to-site configuration
   - Download VPN client

2. Import into OpenVPN client:
   - Use the Azure VPN Client or OpenVPN client
   - Configure Entra ID authentication

3. Connect and verify:
   ```bash
   # After connecting, verify DNS resolution returns private IPs
   nslookup next-kv.vault.azure.net
   # Should return: 10.0.5.x

   # Verify port connectivity
   Test-NetConnection -ComputerName next-kv.vault.azure.net -Port 443
   ```

## Test Execution Matrix

| Test File | Public | Private (No VPN) | Private (VPN Connected) |
|-----------|--------|-------------------|------------------------|
| `test_connectivity.py` | All pass | DNS tests pass (public resolution), port tests may fail | All pass |
| `test_authentication.py` | All pass | Token tests pass, data-plane calls fail | All pass |
| `test_resource_health.py` | All pass | All pass (uses ARM API) | All pass |
| `test_service_endpoints.py` | All pass | Most fail (blocked by firewall) | All pass |
| `test_networking.py` | Skipped (private_only) | Partially (VNet/NSG via ARM pass) | All pass |
| `test_configuration.py` | All pass | All pass (uses ARM API) | All pass |

## Key Insight

Resource health and configuration tests use the **Azure Resource Manager (ARM) API** which is always accessible regardless of networking variant. Service endpoint and connectivity tests use **data-plane APIs** which require direct network access to the resource endpoints.
