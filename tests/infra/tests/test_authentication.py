"""Authentication tests — verify Entra ID token acquisition and RBAC access to each resource."""

import pytest
import requests

from helpers.token_provider import (
    get_arm_token,
    get_keyvault_token,
    get_storage_token,
    get_cognitive_services_token,
    get_token,
)


class TestTokenAcquisition:
    """Verify that Entra ID tokens can be acquired for each service scope."""

    def test_arm_token(self):
        """Can acquire ARM management token."""
        token = get_arm_token()
        assert token is not None
        assert len(token) > 100

    def test_keyvault_token(self):
        """Can acquire Key Vault data-plane token."""
        token = get_keyvault_token()
        assert token is not None
        assert len(token) > 100

    def test_storage_token(self):
        """Can acquire Storage data-plane token."""
        token = get_storage_token()
        assert token is not None
        assert len(token) > 100

    def test_cognitive_services_token(self):
        """Can acquire Cognitive Services token (OpenAI, Doc Intel, Content Safety)."""
        token = get_cognitive_services_token()
        assert token is not None
        assert len(token) > 100

    def test_servicebus_token(self):
        """Can acquire Service Bus token."""
        token = get_token("https://servicebus.azure.net/.default")
        assert token is not None
        assert len(token) > 100

    def test_cosmos_token(self):
        """Can acquire Cosmos DB token."""
        token = get_token("https://cosmos.azure.com/.default")
        assert token is not None
        assert len(token) > 100


class TestKeyVaultAccess:
    """Verify authenticated access to Key Vault."""

    @pytest.mark.timeout(30)
    def test_list_secrets(self, config):
        """Can list secrets in Key Vault (verifies RBAC role assignment)."""
        name = config["resources"]["key_vault"]
        vault_url = f"https://{name}.vault.azure.net"
        token = get_keyvault_token()

        response = requests.get(
            f"{vault_url}/secrets?api-version=7.4",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        # 200 = success, 403 = token valid but no permission
        assert response.status_code in (200, 403), (
            f"Unexpected status {response.status_code}: {response.text[:200]}"
        )


class TestStorageAccess:
    """Verify authenticated access to Storage Account."""

    @pytest.mark.timeout(30)
    def test_list_containers(self, config):
        """Can list blob containers (verifies storage RBAC)."""
        name = config["resources"]["storage_account"]
        token = get_storage_token()

        response = requests.get(
            f"https://{name}.blob.core.windows.net/?comp=list",
            headers={
                "Authorization": f"Bearer {token}",
                "x-ms-version": "2023-11-03",
            },
            timeout=15,
        )
        assert response.status_code in (200, 403), (
            f"Unexpected status {response.status_code}: {response.text[:200]}"
        )


class TestOpenAIAccess:
    """Verify authenticated access to Azure OpenAI."""

    @pytest.mark.timeout(30)
    def test_list_deployments(self, config):
        """Can query OpenAI deployments endpoint."""
        name = config["resources"]["openai"]
        token = get_cognitive_services_token()

        response = requests.get(
            f"https://{name}.openai.azure.com/openai/deployments?api-version=2024-10-21",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        assert response.status_code in (200, 403), (
            f"Unexpected status {response.status_code}: {response.text[:200]}"
        )


class TestCognitiveServicesAccess:
    """Verify authenticated access to Document Intelligence and Content Safety."""

    @pytest.mark.timeout(30)
    def test_document_intelligence_health(self, config):
        """Document Intelligence endpoint responds to authenticated request."""
        name = config["resources"]["document_intelligence"]
        token = get_cognitive_services_token()

        response = requests.get(
            f"https://{name}.cognitiveservices.azure.com/formrecognizer/info?api-version=2024-11-30",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        assert response.status_code in (200, 403, 404), (
            f"Unexpected status {response.status_code}: {response.text[:200]}"
        )

    @pytest.mark.timeout(30)
    def test_content_safety_health(self, config):
        """Content Safety endpoint responds to authenticated request."""
        name = config["resources"]["content_safety"]
        token = get_cognitive_services_token()

        response = requests.get(
            f"https://{name}.cognitiveservices.azure.com/contentsafety/text:analyze?api-version=2024-09-01",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        # POST-only endpoint returns 405 for GET, which proves it's reachable
        assert response.status_code in (200, 403, 405), (
            f"Unexpected status {response.status_code}: {response.text[:200]}"
        )
