"""Connectivity tests — DNS resolution and endpoint reachability for all deployed resources."""

import pytest

from helpers.dns_resolver import resolve_hostname, check_port_open


class TestDnsResolution:
    """Verify DNS resolution for all resource endpoints."""

    def test_keyvault_dns(self, config):
        """Key Vault FQDN resolves."""
        name = config["resources"]["key_vault"]
        hostname = f"{name}.vault.azure.net"
        ip = resolve_hostname(hostname)
        assert ip is not None, f"Failed to resolve {hostname}"

    def test_storage_blob_dns(self, config):
        """Storage account blob endpoint resolves."""
        name = config["resources"]["storage_account"]
        hostname = f"{name}.blob.core.windows.net"
        ip = resolve_hostname(hostname)
        assert ip is not None, f"Failed to resolve {hostname}"

    def test_storage_queue_dns(self, config):
        """Storage account queue endpoint resolves."""
        name = config["resources"]["storage_account"]
        hostname = f"{name}.queue.core.windows.net"
        ip = resolve_hostname(hostname)
        assert ip is not None, f"Failed to resolve {hostname}"

    def test_servicebus_dns(self, config):
        """Service Bus namespace resolves."""
        name = config["resources"]["service_bus"]
        hostname = f"{name}.servicebus.windows.net"
        ip = resolve_hostname(hostname)
        assert ip is not None, f"Failed to resolve {hostname}"

    def test_cosmosdb_dns(self, config):
        """Cosmos DB account resolves."""
        name = config["resources"]["cosmos_db"]
        hostname = f"{name}.documents.azure.com"
        ip = resolve_hostname(hostname)
        assert ip is not None, f"Failed to resolve {hostname}"

    def test_postgresql_dns(self, config):
        """PostgreSQL Flexible Server resolves."""
        name = config["resources"]["postgresql"]
        hostname = f"{name}.postgres.database.azure.com"
        ip = resolve_hostname(hostname)
        assert ip is not None, f"Failed to resolve {hostname}"

    def test_openai_dns(self, config):
        """Azure OpenAI endpoint resolves."""
        name = config["resources"]["openai"]
        hostname = f"{name}.openai.azure.com"
        ip = resolve_hostname(hostname)
        assert ip is not None, f"Failed to resolve {hostname}"

    def test_document_intelligence_dns(self, config):
        """Document Intelligence endpoint resolves."""
        name = config["resources"]["document_intelligence"]
        hostname = f"{name}.cognitiveservices.azure.com"
        ip = resolve_hostname(hostname)
        assert ip is not None, f"Failed to resolve {hostname}"

    def test_content_safety_dns(self, config):
        """Content Safety endpoint resolves."""
        name = config["resources"]["content_safety"]
        hostname = f"{name}.cognitiveservices.azure.com"
        ip = resolve_hostname(hostname)
        assert ip is not None, f"Failed to resolve {hostname}"

    def test_function_app_dns(self, config):
        """Function App FQDN resolves."""
        name = config["resources"]["function_app"]
        hostname = f"{name}.azurewebsites.net"
        ip = resolve_hostname(hostname)
        assert ip is not None, f"Failed to resolve {hostname}"

    def test_logic_app_dns(self, config):
        """Logic App FQDN resolves."""
        name = config["resources"]["logic_app"]
        hostname = f"{name}.azurewebsites.net"
        ip = resolve_hostname(hostname)
        assert ip is not None, f"Failed to resolve {hostname}"

    def test_acr_dns(self, config):
        """Container Registry FQDN resolves."""
        name = config["resources"]["container_registry"]
        hostname = f"{name}.azurecr.io"
        ip = resolve_hostname(hostname)
        assert ip is not None, f"Failed to resolve {hostname}"


class TestPortReachability:
    """Verify HTTPS (443) port reachability for deployed endpoints."""

    @pytest.mark.timeout(15)
    def test_keyvault_port(self, config):
        """Key Vault HTTPS port is reachable."""
        name = config["resources"]["key_vault"]
        hostname = f"{name}.vault.azure.net"
        assert check_port_open(hostname, 443), f"Port 443 not reachable on {hostname}"

    @pytest.mark.timeout(15)
    def test_storage_blob_port(self, config):
        """Storage blob HTTPS port is reachable."""
        name = config["resources"]["storage_account"]
        hostname = f"{name}.blob.core.windows.net"
        assert check_port_open(hostname, 443), f"Port 443 not reachable on {hostname}"

    @pytest.mark.timeout(15)
    def test_servicebus_port(self, config):
        """Service Bus HTTPS port is reachable."""
        name = config["resources"]["service_bus"]
        hostname = f"{name}.servicebus.windows.net"
        assert check_port_open(hostname, 443), f"Port 443 not reachable on {hostname}"

    @pytest.mark.timeout(15)
    def test_cosmosdb_port(self, config):
        """Cosmos DB HTTPS port is reachable."""
        name = config["resources"]["cosmos_db"]
        hostname = f"{name}.documents.azure.com"
        assert check_port_open(hostname, 443), f"Port 443 not reachable on {hostname}"

    @pytest.mark.timeout(15)
    def test_postgresql_port(self, config):
        """PostgreSQL port 5432 is reachable."""
        name = config["resources"]["postgresql"]
        hostname = f"{name}.postgres.database.azure.com"
        assert check_port_open(hostname, 5432), f"Port 5432 not reachable on {hostname}"

    @pytest.mark.timeout(15)
    def test_openai_port(self, config):
        """Azure OpenAI HTTPS port is reachable."""
        name = config["resources"]["openai"]
        hostname = f"{name}.openai.azure.com"
        assert check_port_open(hostname, 443), f"Port 443 not reachable on {hostname}"

    @pytest.mark.timeout(15)
    def test_function_app_port(self, config):
        """Function App HTTPS port is reachable."""
        name = config["resources"]["function_app"]
        hostname = f"{name}.azurewebsites.net"
        assert check_port_open(hostname, 443), f"Port 443 not reachable on {hostname}"

    @pytest.mark.timeout(15)
    def test_acr_port(self, config):
        """Container Registry HTTPS port is reachable."""
        name = config["resources"]["container_registry"]
        hostname = f"{name}.azurecr.io"
        assert check_port_open(hostname, 443), f"Port 443 not reachable on {hostname}"
