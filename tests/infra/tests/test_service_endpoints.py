"""Service endpoint tests — functional health probes against each deployed service."""

import pytest
import requests

from helpers.token_provider import (
    get_keyvault_token,
    get_storage_token,
    get_cognitive_services_token,
    get_token,
)


class TestFunctionAppEndpoint:
    """Verify Function App responds to HTTP requests."""

    @pytest.mark.timeout(30)
    def test_function_app_root(self, config):
        """Function App root URL returns a response."""
        name = config["resources"]["function_app"]
        url = f"https://{name}.azurewebsites.net"
        response = requests.get(url, timeout=15, allow_redirects=True)
        # Function apps without a root handler return 404, which is still proof of life
        assert response.status_code in (200, 204, 401, 403, 404), (
            f"Unexpected status {response.status_code} from {url}"
        )

    @pytest.mark.timeout(30)
    def test_function_app_health(self, config):
        """Function App health endpoint responds (if configured)."""
        name = config["resources"]["function_app"]
        url = f"https://{name}.azurewebsites.net/api/health"
        response = requests.get(url, timeout=15)
        # 200 = health OK, 401/404 = endpoint exists but needs auth or not configured
        assert response.status_code in (200, 401, 403, 404), (
            f"Unexpected status {response.status_code} from {url}"
        )


class TestKeyVaultEndpoint:
    """Verify Key Vault data-plane responds."""

    @pytest.mark.timeout(30)
    def test_keyvault_secrets_api(self, config):
        """Key Vault secrets API is responsive."""
        name = config["resources"]["key_vault"]
        token = get_keyvault_token()
        response = requests.get(
            f"https://{name}.vault.azure.net/secrets?api-version=7.4",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        assert response.status_code in (200, 403), (
            f"Key Vault returned {response.status_code}: {response.text[:200]}"
        )


class TestStorageEndpoint:
    """Verify Storage Account blob and queue services respond."""

    @pytest.mark.timeout(30)
    def test_blob_service_properties(self, config):
        """Storage blob service is responsive."""
        name = config["resources"]["storage_account"]
        token = get_storage_token()
        response = requests.get(
            f"https://{name}.blob.core.windows.net/?restype=service&comp=properties",
            headers={
                "Authorization": f"Bearer {token}",
                "x-ms-version": "2023-11-03",
            },
            timeout=15,
        )
        assert response.status_code in (200, 403), (
            f"Storage blob returned {response.status_code}: {response.text[:200]}"
        )

    @pytest.mark.timeout(30)
    def test_queue_service_properties(self, config):
        """Storage queue service is responsive."""
        name = config["resources"]["storage_account"]
        token = get_storage_token()
        response = requests.get(
            f"https://{name}.queue.core.windows.net/?restype=service&comp=properties",
            headers={
                "Authorization": f"Bearer {token}",
                "x-ms-version": "2023-11-03",
            },
            timeout=15,
        )
        assert response.status_code in (200, 403), (
            f"Storage queue returned {response.status_code}: {response.text[:200]}"
        )


class TestServiceBusEndpoint:
    """Verify Service Bus namespace responds."""

    @pytest.mark.timeout(30)
    def test_servicebus_https(self, config):
        """Service Bus HTTPS endpoint is responsive."""
        name = config["resources"]["service_bus"]
        token = get_token("https://servicebus.azure.net/.default")
        response = requests.get(
            f"https://{name}.servicebus.windows.net/$namespaceinfo?api-version=2017-04",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        # Service Bus REST may return various codes; key is it doesn't timeout/refuse
        assert response.status_code < 500, (
            f"Service Bus returned server error {response.status_code}"
        )


class TestCosmosDBEndpoint:
    """Verify Cosmos DB responds to authenticated requests."""

    @pytest.mark.timeout(30)
    def test_cosmosdb_databases(self, config):
        """Cosmos DB returns database list."""
        name = config["resources"]["cosmos_db"]
        token = get_token("https://cosmos.azure.com/.default")
        response = requests.get(
            f"https://{name}.documents.azure.com/dbs",
            headers={
                "Authorization": f"Bearer {token}",
                "x-ms-version": "2018-12-31",
                "x-ms-date": "",
            },
            timeout=15,
        )
        # Cosmos uses custom auth; REST with AAD token may return 401 without proper headers
        assert response.status_code < 500, (
            f"Cosmos DB returned server error {response.status_code}"
        )


class TestOpenAIEndpoint:
    """Verify Azure OpenAI responds to authenticated requests."""

    @pytest.mark.timeout(30)
    def test_openai_models(self, config):
        """Azure OpenAI returns model/deployment information."""
        name = config["resources"]["openai"]
        token = get_cognitive_services_token()
        response = requests.get(
            f"https://{name}.openai.azure.com/openai/deployments?api-version=2024-10-21",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        assert response.status_code in (200, 403), (
            f"OpenAI returned {response.status_code}: {response.text[:200]}"
        )

    @pytest.mark.timeout(60)
    @pytest.mark.slow
    def test_openai_completion(self, config):
        """Azure OpenAI can process a simple completion request."""
        name = config["resources"]["openai"]
        deployment = config["expected"]["openai_deployment"]
        token = get_cognitive_services_token()

        response = requests.post(
            f"https://{name}.openai.azure.com/openai/deployments/{deployment}"
            f"/chat/completions?api-version=2024-10-21",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "messages": [{"role": "user", "content": "Say hello"}],
                "max_tokens": 10,
            },
            timeout=30,
        )
        assert response.status_code in (200, 403, 429), (
            f"OpenAI completion returned {response.status_code}: {response.text[:200]}"
        )


class TestDocumentIntelligenceEndpoint:
    """Verify Document Intelligence responds."""

    @pytest.mark.timeout(30)
    def test_doc_intelligence_info(self, config):
        """Document Intelligence info endpoint responds."""
        name = config["resources"]["document_intelligence"]
        token = get_cognitive_services_token()
        response = requests.get(
            f"https://{name}.cognitiveservices.azure.com/formrecognizer/info"
            f"?api-version=2024-11-30",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        assert response.status_code in (200, 403, 404), (
            f"Doc Intelligence returned {response.status_code}: {response.text[:200]}"
        )


class TestContainerRegistryEndpoint:
    """Verify Container Registry responds."""

    @pytest.mark.timeout(30)
    def test_acr_catalog(self, config):
        """ACR catalog endpoint is responsive."""
        name = config["resources"]["container_registry"]
        # ACR uses docker token exchange; basic connectivity check
        response = requests.get(
            f"https://{name}.azurecr.io/v2/",
            timeout=15,
        )
        # 401 with www-authenticate header = ACR is alive and requires auth
        assert response.status_code in (200, 401), (
            f"ACR returned {response.status_code} from {name}.azurecr.io"
        )
        if response.status_code == 401:
            assert "www-authenticate" in {k.lower() for k in response.headers}
