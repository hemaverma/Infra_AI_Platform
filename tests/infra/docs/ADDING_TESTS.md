# Adding New Tests

This guide explains how to add new infrastructure tests when new resources are added to the deployment.

## When to Add Tests

Add new tests when:

- A new Bicep module is added to `src/infra_deployment/modules/`
- A new resource is added to an existing module
- New app settings or role assignments are configured
- New private endpoints or networking rules are added

## Step-by-Step Process

### 1. Identify the Resource

Determine from the Bicep module:

- Resource type and name pattern
- Whether it has a public endpoint
- Authentication method (RBAC, keys, connection string)
- Whether it has a private endpoint in the private variant

### 2. Update Configuration

Add the resource name pattern to `config.yaml`:

```yaml
resources:
  new_resource: "{base_name}-newresource"

expected:
  new_resource_setting: expected_value
```

### 3. Add DNS/Connectivity Test

In `test_connectivity.py`:

```python
def test_new_resource_dns(self, config):
    """New resource FQDN resolves."""
    name = config["resources"]["new_resource"]
    hostname = f"{name}.example.azure.com"
    ip = resolve_hostname(hostname)
    assert ip is not None, f"Failed to resolve {hostname}"
```

### 4. Add Resource Health Test

In `test_resource_health.py`:

```python
def test_new_resource_provisioned(self, azure_clients, resource_group, config):
    """New resource is provisioned successfully."""
    name = config["resources"]["new_resource"]
    # Use appropriate management client
    resource = azure_clients.some_client.get(resource_group, name)
    assert resource is not None
    assert resource.provisioning_state == "Succeeded"
```

### 5. Add Service Endpoint Test

In `test_service_endpoints.py`:

```python
@pytest.mark.timeout(30)
def test_new_resource_endpoint(self, config):
    """New resource endpoint responds."""
    name = config["resources"]["new_resource"]
    token = get_appropriate_token()
    response = requests.get(
        f"https://{name}.example.azure.com/health",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    assert response.status_code in (200, 403)
```

### 6. Add Private Endpoint Test (if applicable)

In `test_networking.py`:

```python
@pytest.mark.private_only
def test_new_resource_resolves_private(self, config):
    """New resource resolves to private IP via VPN."""
    name = config["resources"]["new_resource"]
    ip = resolve_hostname(f"{name}.example.azure.com")
    assert is_private_ip(ip), f"Expected private IP, got {ip}"
```

### 7. Add Management Client (if needed)

If a new Azure SDK client is needed, add it to `helpers/azure_client.py`:

```python
from azure.mgmt.newservice import NewServiceManagementClient

@property
def new_service(self) -> NewServiceManagementClient:
    return self._get_or_create(NewServiceManagementClient)
```

And add the package to `requirements.txt`.

## Test Naming Conventions

- DNS tests: `test_{resource}_dns`
- Port tests: `test_{resource}_port`
- Provisioning tests: `test_{resource}_provisioned`
- Configuration tests: `test_{resource}_{setting}_configured`
- Endpoint tests: `test_{resource}_{action}`
- Private tests: `test_{resource}_resolves_private`

## Running Specific Tests During Development

```bash
# Run just the new test
pytest infra_test/tests/test_connectivity.py::TestDnsResolution::test_new_resource_dns -v

# Run with verbose failure output
pytest infra_test/tests/ -v --tb=long -k "new_resource"
```
