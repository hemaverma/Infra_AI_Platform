# Infrastructure Automated Test Plan

## Purpose

This test plan defines the automated verification strategy for validating that deployed Azure resources in the NExT/next Accelerator infrastructure are:

1. **Provisioned** — resources exist and are in a healthy state
2. **Accessible** — endpoints resolve and respond from local developer machines
3. **Authenticated** — Entra ID tokens grant appropriate access
4. **Configured** — app settings, role assignments, and service wiring are correct
5. **Secured** — network isolation works as expected (private variant)

## Scope

### In Scope

- All 17 resource types deployed by `src/infra_deployment/` Bicep modules
- Both **public** and **private** deployment variants
- Local machine accessibility verification
- RBAC and managed identity validation
- Network connectivity (DNS, ports, VPN)

### Out of Scope

- Application-level integration tests (covered in `tests/`)
- Performance/load testing
- Disaster recovery validation
- Cost optimization checks

## Test Categories

### 1. Connectivity Tests (`test_connectivity.py`)

Verifies DNS resolution and TCP port reachability for all resource endpoints.

| Test | Resource | Port | Expected Result |
|------|----------|------|-----------------|
| DNS resolution | All 12 endpoints | N/A | Returns valid IP address |
| HTTPS port check | Key Vault, Storage, Service Bus, Cosmos, OpenAI, Function App, ACR | 443 | TCP connection succeeds |
| PostgreSQL port | PostgreSQL Flexible Server | 5432 | TCP connection succeeds |

**Failure indicates**: DNS misconfiguration, firewall blocking, resource not deployed, or private endpoint without VPN.

### 2. Authentication Tests (`test_authentication.py`)

Verifies Entra ID token acquisition for all service scopes and authenticated data-plane access.

| Test | Scope | Expected Result |
|------|-------|-----------------|
| ARM token | `management.azure.com` | Token acquired |
| Key Vault token | `vault.azure.net` | Token acquired |
| Storage token | `storage.azure.com` | Token acquired |
| Cognitive Services token | `cognitiveservices.azure.com` | Token acquired |
| Service Bus token | `servicebus.azure.net` | Token acquired |
| Cosmos token | `cosmos.azure.com` | Token acquired |
| Key Vault list secrets | Data-plane API | 200 or 403 |
| Storage list containers | Data-plane API | 200 or 403 |
| OpenAI list deployments | Data-plane API | 200 or 403 |

**Failure indicates**: Azure CLI not logged in, tenant mismatch, or service principal lacks permissions.

### 3. Resource Health Tests (`test_resource_health.py`)

Verifies resources exist with correct provisioning state via Azure Management APIs.

| Test | Resource | Check |
|------|----------|-------|
| Managed Identity | `next-id` | Exists |
| Key Vault | `next-kv` | `provisioningState == Succeeded` |
| Storage Account | `nextst` | `provisioningState == Succeeded` |
| Service Bus | `next-servicebus` | `provisioningState == Succeeded` |
| Cosmos DB | `next-cosmos` | `provisioningState == Succeeded` |
| PostgreSQL | `next-pg` | `state == Ready` |
| Azure OpenAI | `next-oai` | `provisioningState == Succeeded` |
| Document Intelligence | `next-di` | `provisioningState == Succeeded` |
| Content Safety | `next-csafety` | `provisioningState == Succeeded` |
| Function App | `next-func` | `state == Running` |
| Logic App | `next-logic` | `state == Running` |
| Container Registry | `nextacr` | `provisioningState == Succeeded` |
| Cosmos DB database | `vendor-email-response` | Exists |
| Cosmos DB container | `workflow-checkpoints` | Exists |
| Service Bus queues | `workflow-queue`, `hitl-queue` | Exist |
| Storage container | `email-staging` | Exists |
| OpenAI deployment | `gpt-5` | `provisioningState == Succeeded` |

**Failure indicates**: Deployment failed, resource deleted, or naming mismatch.

### 4. Service Endpoint Tests (`test_service_endpoints.py`)

Functional health probes validating services respond to authenticated requests.

| Test | Endpoint | Method | Expected |
|------|----------|--------|----------|
| Function App root | `https://next-func.azurewebsites.net` | GET | 200/404 |
| Function App health | `https://next-func.azurewebsites.net/api/health` | GET | 200/404 |
| Key Vault secrets | `.vault.azure.net/secrets` | GET | 200/403 |
| Storage blob properties | `.blob.core.windows.net` | GET | 200/403 |
| Storage queue properties | `.queue.core.windows.net` | GET | 200/403 |
| Service Bus namespace info | `$namespaceinfo` | GET | < 500 |
| Cosmos DB databases | `/dbs` | GET | < 500 |
| OpenAI deployments | `/openai/deployments` | GET | 200/403 |
| OpenAI completion | chat completions | POST | 200/403/429 |
| Document Intelligence info | `/formrecognizer/info` | GET | 200/403/404 |
| ACR catalog | `/v2/` | GET | 200/401 |

**Failure indicates**: Service down, networking issue, or configuration error.

### 5. Networking Tests (`test_networking.py`)

Validates private endpoint resolution, VNet configuration, VPN gateway, and NSG rules.

| Test | Variant | Check |
|------|---------|-------|
| Private IP resolution | Private | All PaaS endpoints resolve to 10.0.x.x |
| VNet exists | Private | `10.0.0.0/16` address space |
| GatewaySubnet | Private | `10.0.0.0/27` |
| Functions subnet | Private | Delegated to `Microsoft.Web/serverFarms` |
| Container Apps subnet | Private | Exists |
| Private Endpoints subnet | Private | Exists |
| VPN Gateway | Private | Provisioned, P2S configured |
| VPN client pool | Private | `172.16.0.0/24` |
| Functions NSG | Private | Has custom rules |
| Private Endpoints NSG | Private | Has custom rules |

**Failure indicates**: VNet misconfiguration, missing private endpoints, or VPN not connected.

### 6. Configuration Tests (`test_configuration.py`)

Validates application settings, RBAC role assignments, and observability wiring.

| Test | Check |
|------|-------|
| `AZURE_CLIENT_ID` set | Managed identity configured |
| `AZURE_OPENAI_ENDPOINT` set | OpenAI wired |
| `AZURE_OPENAI_MODEL` correct | Matches deployment |
| `AZURE_COSMOS_ENDPOINT` set | Cosmos wired |
| `AZURE_COSMOS_DATABASE_NAME` correct | Matches database |
| `AZURE_KEY_VAULT_NAME` set | Key Vault wired |
| `EMAIL_BLOB_ACCOUNT_URL` correct | Storage wired |
| Service Bus namespace configured | Managed identity pattern |
| No connection strings | Security validation |
| Role assignments exist | RBAC configured |
| App Insights linked | Observability wired |

**Failure indicates**: Deployment wiring issue, missing role assignments, or security violation.

## Execution Strategy

### Local Development (Public Variant)

```bash
# Prerequisites
az login
export AZURE_SUBSCRIPTION_ID="<sub-id>"
export AZURE_RESOURCE_GROUP="<rg-name>"
export DEPLOYMENT_VARIANT="public"

# Run all tests
pip install -r infra_test/requirements.txt
pytest infra_test/tests/ -v --tb=short
```

### Local Development (Private Variant)

```bash
# Prerequisites: VPN must be connected first
# 1. Download VPN client config from Azure Portal
# 2. Connect via OpenVPN with Entra ID auth
# 3. Verify: nslookup next-kv.vault.azure.net should return 10.0.x.x

az login
export AZURE_SUBSCRIPTION_ID="<sub-id>"
export AZURE_RESOURCE_GROUP="<rg-name>"
export DEPLOYMENT_VARIANT="private"

pytest infra_test/tests/ -v --tb=short
```

### CI/CD Pipeline

Tests can be integrated into Azure DevOps or GitHub Actions pipelines:

```yaml
# Example GitHub Actions step
- name: Run infrastructure tests
  env:
    AZURE_SUBSCRIPTION_ID: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    AZURE_RESOURCE_GROUP: ${{ vars.RESOURCE_GROUP }}
    DEPLOYMENT_VARIANT: public
  run: |
    pip install -r infra_test/requirements.txt
    pytest infra_test/tests/ -v --junitxml=infra_test/reports/results.xml
```

## Test Markers

| Marker | Description |
|--------|-------------|
| `@pytest.mark.private_only` | Runs only when `DEPLOYMENT_VARIANT=private` |
| `@pytest.mark.public_only` | Runs only when `DEPLOYMENT_VARIANT=public` |
| `@pytest.mark.slow` | Tests taking > 30 seconds (e.g., OpenAI completion) |
| `@pytest.mark.timeout(N)` | Per-test timeout in seconds |

## Success Criteria

| Variant | Required Pass Rate | Notes |
|---------|-------------------|-------|
| Public | 100% of non-private tests | All endpoints reachable directly |
| Private | 100% of all tests | Requires active VPN connection |

## Troubleshooting

| Symptom | Likely Cause | Resolution |
|---------|-------------|------------|
| All DNS tests fail | Not connected to network/VPN | Check network; connect VPN for private |
| Auth token tests fail | Not logged in to Azure CLI | Run `az login` |
| Resource health tests return 404 | Resource not deployed | Verify deployment completed |
| Private tests show public IPs | VPN not connected | Connect OpenVPN client |
| 403 on data-plane calls | Missing RBAC roles | Assign required roles to your identity |
| PostgreSQL port test fails | Firewall rule missing | Add your IP to PostgreSQL firewall |
