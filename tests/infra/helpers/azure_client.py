"""Azure SDK client factory for infrastructure tests."""

from azure.identity import DefaultAzureCredential
from azure.mgmt.keyvault import KeyVaultManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.servicebus import ServiceBusManagementClient
from azure.mgmt.cosmosdb import CosmosDBManagementClient
from azure.mgmt.web import WebSiteManagementClient
from azure.mgmt.containerregistry import ContainerRegistryManagementClient
from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.rdbms.postgresql_flexibleservers import PostgreSQLManagementClient


class AzureClientFactory:
    """Factory for lazily creating Azure management clients."""

    def __init__(self, credential: DefaultAzureCredential, subscription_id: str):
        self._credential = credential
        self._subscription_id = subscription_id
        self._cache = {}

    def _get_or_create(self, client_class, **kwargs):
        key = client_class.__name__
        if key not in self._cache:
            self._cache[key] = client_class(
                self._credential, self._subscription_id, **kwargs
            )
        return self._cache[key]

    @property
    def keyvault(self) -> KeyVaultManagementClient:
        return self._get_or_create(KeyVaultManagementClient)

    @property
    def storage(self) -> StorageManagementClient:
        return self._get_or_create(StorageManagementClient)

    @property
    def servicebus(self) -> ServiceBusManagementClient:
        return self._get_or_create(ServiceBusManagementClient)

    @property
    def cosmosdb(self) -> CosmosDBManagementClient:
        return self._get_or_create(CosmosDBManagementClient)

    @property
    def web(self) -> WebSiteManagementClient:
        return self._get_or_create(WebSiteManagementClient)

    @property
    def container_registry(self) -> ContainerRegistryManagementClient:
        return self._get_or_create(ContainerRegistryManagementClient)

    @property
    def cognitive_services(self) -> CognitiveServicesManagementClient:
        return self._get_or_create(CognitiveServicesManagementClient)

    @property
    def network(self) -> NetworkManagementClient:
        return self._get_or_create(NetworkManagementClient)

    @property
    def monitor(self) -> MonitorManagementClient:
        return self._get_or_create(MonitorManagementClient)

    @property
    def postgresql(self) -> PostgreSQLManagementClient:
        return self._get_or_create(PostgreSQLManagementClient)
