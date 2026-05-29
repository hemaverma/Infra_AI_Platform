"""Networking tests — VPN, private endpoints, NSG rules, and VNet configuration."""

import pytest

from helpers.dns_resolver import resolve_hostname, is_private_ip, check_port_open


class TestPrivateEndpointResolution:
    """Verify private endpoints resolve to private IPs when on VPN."""

    @pytest.mark.private_only
    def test_keyvault_resolves_private(self, config):
        """Key Vault resolves to a private IP (10.0.x.x) via VPN."""
        name = config["resources"]["key_vault"]
        ip = resolve_hostname(f"{name}.vault.azure.net")
        assert ip is not None, "Key Vault DNS resolution failed"
        assert is_private_ip(ip), f"Expected private IP, got {ip}"

    @pytest.mark.private_only
    def test_storage_blob_resolves_private(self, config):
        """Storage blob resolves to a private IP via VPN."""
        name = config["resources"]["storage_account"]
        ip = resolve_hostname(f"{name}.blob.core.windows.net")
        assert ip is not None, "Storage blob DNS resolution failed"
        assert is_private_ip(ip), f"Expected private IP, got {ip}"

    @pytest.mark.private_only
    def test_servicebus_resolves_private(self, config):
        """Service Bus resolves to a private IP via VPN."""
        name = config["resources"]["service_bus"]
        ip = resolve_hostname(f"{name}.servicebus.windows.net")
        assert ip is not None, "Service Bus DNS resolution failed"
        assert is_private_ip(ip), f"Expected private IP, got {ip}"

    @pytest.mark.private_only
    def test_cosmosdb_resolves_private(self, config):
        """Cosmos DB resolves to a private IP via VPN."""
        name = config["resources"]["cosmos_db"]
        ip = resolve_hostname(f"{name}.documents.azure.com")
        assert ip is not None, "Cosmos DB DNS resolution failed"
        assert is_private_ip(ip), f"Expected private IP, got {ip}"

    @pytest.mark.private_only
    def test_openai_resolves_private(self, config):
        """Azure OpenAI resolves to a private IP via VPN."""
        name = config["resources"]["openai"]
        ip = resolve_hostname(f"{name}.openai.azure.com")
        assert ip is not None, "OpenAI DNS resolution failed"
        assert is_private_ip(ip), f"Expected private IP, got {ip}"

    @pytest.mark.private_only
    def test_function_app_resolves_private(self, config):
        """Function App resolves to a private IP via VPN."""
        name = config["resources"]["function_app"]
        ip = resolve_hostname(f"{name}.azurewebsites.net")
        assert ip is not None, "Function App DNS resolution failed"
        assert is_private_ip(ip), f"Expected private IP, got {ip}"

    @pytest.mark.private_only
    def test_acr_resolves_private(self, config):
        """Container Registry resolves to a private IP via VPN."""
        name = config["resources"]["container_registry"]
        ip = resolve_hostname(f"{name}.azurecr.io")
        assert ip is not None, "ACR DNS resolution failed"
        assert is_private_ip(ip), f"Expected private IP, got {ip}"


class TestVNetConfiguration:
    """Verify VNet and subnet configuration (private variant only)."""

    @pytest.mark.private_only
    def test_vnet_exists(self, azure_clients, resource_group, config):
        """VNet exists with expected address space."""
        base = config["base_name"]
        vnet = azure_clients.network.virtual_networks.get(
            resource_group, f"{base}-vnet"
        )
        assert vnet is not None
        assert "10.0.0.0/16" in vnet.address_space.address_prefixes

    @pytest.mark.private_only
    def test_gateway_subnet_exists(self, azure_clients, resource_group, config):
        """GatewaySubnet exists for VPN."""
        base = config["base_name"]
        subnet = azure_clients.network.subnets.get(
            resource_group, f"{base}-vnet", "GatewaySubnet"
        )
        assert subnet is not None
        assert "10.0.0.0/27" in subnet.address_prefix

    @pytest.mark.private_only
    def test_functions_subnet_exists(self, azure_clients, resource_group, config):
        """Functions subnet exists with delegation."""
        base = config["base_name"]
        subnet = azure_clients.network.subnets.get(
            resource_group, f"{base}-vnet", "snet-functions"
        )
        assert subnet is not None
        delegations = [d.service_name for d in (subnet.delegations or [])]
        assert "Microsoft.Web/serverFarms" in delegations

    @pytest.mark.private_only
    def test_container_apps_subnet_exists(self, azure_clients, resource_group, config):
        """Container Apps subnet exists."""
        base = config["base_name"]
        subnet = azure_clients.network.subnets.get(
            resource_group, f"{base}-vnet", "snet-container-apps"
        )
        assert subnet is not None

    @pytest.mark.private_only
    def test_private_endpoints_subnet_exists(self, azure_clients, resource_group, config):
        """Private endpoints subnet exists."""
        base = config["base_name"]
        subnet = azure_clients.network.subnets.get(
            resource_group, f"{base}-vnet", "snet-private-endpoints"
        )
        assert subnet is not None


class TestVpnGateway:
    """Verify VPN Gateway configuration (private variant only)."""

    @pytest.mark.private_only
    def test_vpn_gateway_exists(self, azure_clients, resource_group, config):
        """VPN Gateway exists and is provisioned."""
        base = config["base_name"]
        gw = azure_clients.network.virtual_network_gateways.get(
            resource_group, f"{base}-vpn-gw"
        )
        assert gw is not None
        assert gw.provisioning_state == "Succeeded"

    @pytest.mark.private_only
    def test_vpn_gateway_p2s_config(self, azure_clients, resource_group, config):
        """VPN Gateway has P2S configuration with expected client pool."""
        base = config["base_name"]
        gw = azure_clients.network.virtual_network_gateways.get(
            resource_group, f"{base}-vpn-gw"
        )
        p2s = gw.vpn_client_configuration
        assert p2s is not None
        assert "172.16.0.0/24" in (p2s.vpn_client_address_pool.address_prefixes or [])

    @pytest.mark.private_only
    def test_vpn_connectivity(self):
        """VPN client can reach the private subnet (ping private endpoint subnet)."""
        # If we can resolve private IPs, VPN is connected
        # This test assumes the VPN is already connected
        assert check_port_open("10.0.5.1", 443, timeout=5), (
            "VPN connectivity check — if this fails, ensure VPN client is connected"
        )


class TestNsgRules:
    """Verify NSG rules exist for key subnets (private variant only)."""

    @pytest.mark.private_only
    def test_functions_nsg_exists(self, azure_clients, resource_group, config):
        """Functions NSG exists."""
        base = config["base_name"]
        nsg = azure_clients.network.network_security_groups.get(
            resource_group, f"{base}-nsg-functions"
        )
        assert nsg is not None
        rule_names = [r.name for r in (nsg.security_rules or [])]
        assert len(rule_names) > 0, "NSG has no custom rules"

    @pytest.mark.private_only
    def test_private_endpoints_nsg_exists(self, azure_clients, resource_group, config):
        """Private endpoints NSG exists."""
        base = config["base_name"]
        nsg = azure_clients.network.network_security_groups.get(
            resource_group, f"{base}-nsg-private-endpoints"
        )
        assert nsg is not None
        rule_names = [r.name for r in (nsg.security_rules or [])]
        assert len(rule_names) > 0, "NSG has no custom rules"
