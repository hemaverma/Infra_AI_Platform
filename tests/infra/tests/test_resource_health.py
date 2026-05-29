"""Resource health tests — verify Azure resources exist and are in a healthy provisioning state."""

import pytest


class TestResourceProvisioning:
    """Verify all expected resources exist and are successfully provisioned."""

    def test_managed_identity_exists(self, resource_client, resource_group, config, subscription_id):
        """Managed Identity resource exists."""
        name = config["resources"]["managed_identity"]
        resource = resource_client.resources.get_by_id(
            f"/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{name}",
            api_version="2023-01-31",
        )
        assert resource is not None
        assert resource.name == name

    def test_keyvault_provisioned(self, azure_clients, resource_group, config):
        """Key Vault is provisioned successfully."""
        name = config["resources"]["key_vault"]
        vault = azure_clients.keyvault.vaults.get(resource_group, name)
        assert vault is not None
        assert vault.properties.provisioning_state == "Succeeded"

    def test_storage_account_provisioned(self, azure_clients, resource_group, config):
        """Storage Account is provisioned successfully."""
        name = config["resources"]["storage_account"]
        account = azure_clients.storage.storage_accounts.get_properties(
            resource_group, name
        )
        assert account is not None
        assert account.provisioning_state == "Succeeded"

    def test_servicebus_provisioned(self, azure_clients, resource_group, config):
        """Service Bus namespace is provisioned."""
        name = config["resources"]["service_bus"]
        namespace = azure_clients.servicebus.namespaces.get(resource_group, name)
        assert namespace is not None
        assert namespace.provisioning_state == "Succeeded"

    def test_cosmosdb_provisioned(self, azure_clients, resource_group, config):
        """Cosmos DB account is provisioned."""
        name = config["resources"]["cosmos_db"]
        account = azure_clients.cosmosdb.database_accounts.get(resource_group, name)
        assert account is not None
        assert account.provisioning_state == "Succeeded"

    def test_postgresql_provisioned(self, azure_clients, resource_group, config):
        """PostgreSQL Flexible Server is provisioned."""
        name = config["resources"]["postgresql"]
        server = azure_clients.postgresql.servers.get(resource_group, name)
        assert server is not None
        assert server.state == "Ready"

    def test_openai_provisioned(self, azure_clients, resource_group, config):
        """Azure OpenAI account is provisioned."""
        name = config["resources"]["openai"]
        account = azure_clients.cognitive_services.accounts.get(resource_group, name)
        assert account is not None
        assert account.properties.provisioning_state == "Succeeded"

    def test_document_intelligence_provisioned(self, azure_clients, resource_group, config):
        """Document Intelligence account is provisioned."""
        name = config["resources"]["document_intelligence"]
        account = azure_clients.cognitive_services.accounts.get(resource_group, name)
        assert account is not None
        assert account.properties.provisioning_state == "Succeeded"

    def test_content_safety_provisioned(self, azure_clients, resource_group, config):
        """Content Safety account is provisioned."""
        name = config["resources"]["content_safety"]
        account = azure_clients.cognitive_services.accounts.get(resource_group, name)
        assert account is not None
        assert account.properties.provisioning_state == "Succeeded"

    def test_function_app_provisioned(self, azure_clients, resource_group, config):
        """Function App is provisioned and running."""
        name = config["resources"]["function_app"]
        app = azure_clients.web.web_apps.get(resource_group, name)
        assert app is not None
        assert app.state == "Running"

    def test_logic_app_provisioned(self, azure_clients, resource_group, config):
        """Logic App is provisioned and running."""
        name = config["resources"]["logic_app"]
        app = azure_clients.web.web_apps.get(resource_group, name)
        assert app is not None
        assert app.state == "Running"

    def test_acr_provisioned(self, azure_clients, resource_group, config):
        """Container Registry is provisioned."""
        name = config["resources"]["container_registry"]
        registry = azure_clients.container_registry.registries.get(
            resource_group, name
        )
        assert registry is not None
        assert registry.provisioning_state == "Succeeded"


class TestResourceConfiguration:
    """Verify resource configurations match expected values."""

    def test_cosmosdb_database_exists(self, azure_clients, resource_group, config):
        """Cosmos DB database exists with expected name."""
        account_name = config["resources"]["cosmos_db"]
        db_name = config["expected"]["cosmos_database"]
        db = azure_clients.cosmosdb.sql_resources.get_sql_database(
            resource_group, account_name, db_name
        )
        assert db is not None

    def test_cosmosdb_container_exists(self, azure_clients, resource_group, config):
        """Cosmos DB container exists with expected name."""
        account_name = config["resources"]["cosmos_db"]
        db_name = config["expected"]["cosmos_database"]
        container_name = config["expected"]["cosmos_container"]
        container = azure_clients.cosmosdb.sql_resources.get_sql_container(
            resource_group, account_name, db_name, container_name
        )
        assert container is not None

    def test_servicebus_queues_exist(self, azure_clients, resource_group, config):
        """Service Bus queues exist."""
        namespace = config["resources"]["service_bus"]
        expected_queues = config["expected"]["service_bus_queues"]
        queues = list(azure_clients.servicebus.queues.list_by_namespace(
            resource_group, namespace
        ))
        queue_names = [q.name for q in queues]
        for expected in expected_queues:
            assert expected in queue_names, f"Queue '{expected}' not found in {queue_names}"

    def test_storage_container_exists(self, azure_clients, resource_group, config):
        """Storage blob container exists."""
        account_name = config["resources"]["storage_account"]
        container_name = config["expected"]["storage_container"]
        container = azure_clients.storage.blob_containers.get(
            resource_group, account_name, container_name
        )
        assert container is not None

    def test_openai_deployment_exists(self, azure_clients, resource_group, config):
        """Azure OpenAI model deployment exists."""
        account_name = config["resources"]["openai"]
        deployment_name = config["expected"]["openai_deployment"]
        deployment = azure_clients.cognitive_services.deployments.get(
            resource_group, account_name, deployment_name
        )
        assert deployment is not None
        assert deployment.properties.provisioning_state == "Succeeded"

    def test_function_app_runtime(self, azure_clients, resource_group, config):
        """Function App uses expected Python runtime."""
        name = config["resources"]["function_app"]
        app_settings = azure_clients.web.web_apps.list_application_settings(
            resource_group, name
        )
        settings = app_settings.properties
        assert settings.get("FUNCTIONS_WORKER_RUNTIME") == config["expected"]["function_app_runtime"]
