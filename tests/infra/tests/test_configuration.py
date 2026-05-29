"""Configuration tests — verify app settings, role assignments, and dependency wiring."""

import pytest

from azure.identity import DefaultAzureCredential
from azure.mgmt.applicationinsights import ApplicationInsightsManagementClient
from azure.mgmt.authorization import AuthorizationManagementClient


class TestFunctionAppConfiguration:
    """Verify Function App has correct app settings for service dependencies."""

    @pytest.fixture()
    def app_settings(self, azure_clients, resource_group, config):
        """Retrieve Function App application settings."""
        name = config["resources"]["function_app"]
        result = azure_clients.web.web_apps.list_application_settings(
            resource_group, name
        )
        return result.properties

    def test_managed_identity_configured(self, app_settings):
        """AZURE_CLIENT_ID is set (managed identity)."""
        assert "AZURE_CLIENT_ID" in app_settings
        assert len(app_settings["AZURE_CLIENT_ID"]) > 0

    def test_openai_endpoint_configured(self, app_settings):
        """AZURE_OPENAI_ENDPOINT is set."""
        assert "AZURE_OPENAI_ENDPOINT" in app_settings
        assert app_settings["AZURE_OPENAI_ENDPOINT"].startswith("https://")

    def test_openai_model_configured(self, app_settings, config):
        """AZURE_OPENAI_MODEL matches expected deployment."""
        expected = config["expected"]["openai_deployment"]
        assert app_settings.get("AZURE_OPENAI_MODEL") == expected

    def test_cosmos_endpoint_configured(self, app_settings):
        """AZURE_COSMOS_ENDPOINT is set."""
        assert "AZURE_COSMOS_ENDPOINT" in app_settings
        assert "documents.azure.com" in app_settings["AZURE_COSMOS_ENDPOINT"]

    def test_cosmos_database_configured(self, app_settings, config):
        """AZURE_COSMOS_DATABASE_NAME matches expected database."""
        expected = config["expected"]["cosmos_database"]
        assert app_settings.get("AZURE_COSMOS_DATABASE_NAME") == expected

    def test_cosmos_container_configured(self, app_settings, config):
        """AZURE_COSMOS_CONTAINER_NAME matches expected container."""
        expected = config["expected"]["cosmos_container"]
        assert app_settings.get("AZURE_COSMOS_CONTAINER_NAME") == expected

    def test_keyvault_name_configured(self, app_settings, config):
        """AZURE_KEY_VAULT_NAME is set."""
        expected = config["resources"]["key_vault"]
        assert app_settings.get("AZURE_KEY_VAULT_NAME") == expected

    def test_storage_blob_url_configured(self, app_settings, config):
        """EMAIL_BLOB_ACCOUNT_URL is set correctly."""
        name = config["resources"]["storage_account"]
        expected = f"https://{name}.blob.core.windows.net"
        assert app_settings.get("EMAIL_BLOB_ACCOUNT_URL") == expected

    def test_servicebus_connection_configured(self, app_settings, config):
        """Service Bus connection uses managed identity pattern."""
        name = config["resources"]["service_bus"]
        expected = f"{name}.servicebus.windows.net"
        setting = app_settings.get("ServiceBusConnection__fullyQualifiedNamespace", "")
        assert expected in setting

    def test_functions_runtime_python(self, app_settings):
        """Function App runtime is Python."""
        assert app_settings.get("FUNCTIONS_WORKER_RUNTIME") == "python"

    def test_agent_features_enabled(self, app_settings):
        """Agent feature flags are enabled."""
        assert app_settings.get("ENABLE_AGENT_EXTRACTION") == "true"
        assert app_settings.get("ENABLE_AGENT_EMAIL_DRAFT") == "true"

    def test_no_connection_strings(self, app_settings):
        """No plain-text connection strings in app settings (security check)."""
        # Verify no settings contain typical connection string patterns
        sensitive_patterns = [
            "AccountKey=",
            "SharedAccessKey=",
            "Password=",
            "Endpoint=sb://",  # Full SB connection string pattern
        ]
        for key, value in app_settings.items():
            for pattern in sensitive_patterns:
                assert pattern not in str(value), (
                    f"Setting '{key}' contains sensitive pattern '{pattern}'"
                )


class TestRoleAssignments:
    """Verify RBAC role assignments exist for the managed identity."""

    def test_identity_has_role_assignments(self, resource_client, resource_group, config, subscription_id):
        """Managed identity has at least one role assignment in the resource group."""
        credential = DefaultAzureCredential()
        auth_client = AuthorizationManagementClient(credential, subscription_id)

        # Get the managed identity principal ID
        identity_name = config["resources"]["managed_identity"]
        identity = resource_client.resources.get_by_id(
            f"/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{identity_name}",
            api_version="2023-01-31",
        )
        principal_id = identity.properties.get("principalId")
        assert principal_id is not None, "Could not get managed identity principalId"

        # List role assignments for this principal in the resource group
        scope = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        assignments = list(auth_client.role_assignments.list_for_scope(
            scope, filter=f"principalId eq '{principal_id}'"
        ))
        assert len(assignments) > 0, (
            f"No role assignments found for managed identity {identity_name}"
        )


class TestLogAnalyticsConfiguration:
    """Verify Log Analytics workspace is linked to Application Insights."""

    def test_app_insights_workspace_linked(self, azure_clients, resource_group, config):
        """Application Insights is connected to Log Analytics workspace."""
        name = config["resources"]["app_insights"]
        # App Insights is accessed via the monitor client's components
        credential = DefaultAzureCredential()
        # Use resource client subscription
        ai_client = ApplicationInsightsManagementClient(
            credential, azure_clients._subscription_id
        )
        component = ai_client.components.get(resource_group, name)
        assert component is not None
        assert component.workspace_resource_id is not None, (
            "App Insights is not linked to a Log Analytics workspace"
        )
