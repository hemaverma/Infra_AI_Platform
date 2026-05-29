# Infrastructure Validation Test Suite

Automated tests to verify deployed Azure resources exist, are configured correctly, and are accessible from local developer machines.

## Overview

This test suite validates the NExT/next Accelerator Azure infrastructure deployed via the Bicep modules in `src/infra_deployment/`. Tests cover both the **public** (PoC) and **private** (production) deployment variants.

## Test Categories

| Category | Description | Script |
|----------|-------------|--------|
| **Connectivity** | DNS resolution, endpoint reachability, port checks | `tests/test_connectivity.py` |
| **Authentication** | Entra ID token acquisition, RBAC role verification | `tests/test_authentication.py` |
| **Resource Health** | Azure resource provisioning state and configuration | `tests/test_resource_health.py` |
| **Service Endpoints** | Functional health probes against each service | `tests/test_service_endpoints.py` |
| **Networking** | VPN connectivity, private endpoint resolution, NSG validation | `tests/test_networking.py` |
| **Configuration** | App settings, role assignments, and dependency wiring | `tests/test_configuration.py` |

## Prerequisites

### Software

- Python 3.10+
- Azure CLI (`az`) logged in with appropriate permissions
- `psql` client (for PostgreSQL tests)
- OpenVPN client (for private variant tests only)

### Azure Permissions

The test runner requires at minimum:

- `Reader` on the resource group
- `Key Vault Secrets User` on the Key Vault (for secret list test)
- `Storage Blob Data Reader` on the storage account
- Network access (public variant or VPN connected for private)

### Environment Setup

```bash
# Install dependencies
pip install -r tests/infra/requirements.txt

# Set required environment variables
export AZURE_SUBSCRIPTION_ID="<subscription-id>"
export AZURE_RESOURCE_GROUP="<resource-group-name>"
export AZURE_BASE_NAME="next"  # default base name for resources
export DEPLOYMENT_VARIANT="public"  # or "private"
```

## Running Tests

```bash
# Run all tests
pytest tests/infra/tests/ -v

# Run a specific category
pytest tests/infra/tests/test_connectivity.py -v

# Run only public-variant tests (skip VPN-required tests)
pytest tests/infra/tests/ -v -m "not private_only"

# Run with resource group override
AZURE_RESOURCE_GROUP=my-rg pytest tests/infra/tests/ -v

# Generate HTML report
pytest tests/infra/tests/ -v --html=tests/infra/reports/report.html --self-contained-html
```

## Configuration

Test behavior is controlled via `config.yaml`:

```yaml
base_name: next
deployment_variant: public  # public | private
timeout_seconds: 30
retry_count: 3
```

Override any value with environment variables prefixed `INFRA_TEST_`:

```bash
export INFRA_TEST_BASE_NAME=next
export INFRA_TEST_DEPLOYMENT_VARIANT=private
```

## Test Architecture

```
tests/infra/
├── README.md              # This file
├── requirements.txt       # Python dependencies
├── config.yaml            # Test configuration
├── conftest.py            # Shared pytest fixtures
├── helpers/
│   ├── __init__.py
│   ├── azure_client.py    # Azure SDK client factory
│   ├── dns_resolver.py    # DNS resolution utilities
│   └── token_provider.py  # Entra ID token acquisition
├── tests/
│   ├── __init__.py
│   ├── test_connectivity.py
│   ├── test_authentication.py
│   ├── test_resource_health.py
│   ├── test_service_endpoints.py
│   ├── test_networking.py
│   └── test_configuration.py
└── reports/               # Generated test reports (gitignored)
```

## Deployment Variant Behavior

### Public Variant

All resources have public endpoints. Tests connect directly over the internet using Entra ID tokens for authentication.

### Private Variant

All PaaS services are behind private endpoints. Tests require:

1. Active P2S VPN connection (OpenVPN, Entra ID auth)
2. DNS resolution through Azure Private DNS zones
3. VPN client IP in the `172.16.0.0/24` pool

Tests marked `@pytest.mark.private_only` are skipped when `DEPLOYMENT_VARIANT=public`.

## Tested Resources

| Resource | Name Pattern | Public Access | Private Access |
|----------|-------------|---------------|----------------|
| Managed Identity | `{base}-id` | N/A | N/A |
| Log Analytics | `{base}-la` | Yes | Yes |
| App Insights | `{base}-ai` | Yes | Yes |
| Key Vault | `{base}-kv` | Yes | VPN required |
| Storage Account | `{base}st` | Yes | VPN required |
| Service Bus | `{base}-servicebus` | Yes | VPN required |
| Cosmos DB | `{base}-cosmos` | Yes | VPN required |
| PostgreSQL | `{base}-pg` | Firewall rule | VPN required |
| Azure OpenAI | `{base}-oai` | Yes | VPN required |
| Document Intelligence | `{base}-di` | Yes | VPN required |
| Content Safety | `{base}-csafety` | Yes | VPN required |
| Function App | `{base}-func` | Yes | VPN required |
| Logic App | `{base}-logic` | Yes | VPN required |
| Container App | `{base}-communicator` | Internal only | VPN required |
| Container Registry | `{base}acr` | Yes | VPN required |
| VPN Gateway | `{base}-vpn-gw` | N/A (private only) | Gateway endpoint |
