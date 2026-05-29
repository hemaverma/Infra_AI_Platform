"""Entra ID token acquisition utilities for infrastructure tests."""

from azure.identity import DefaultAzureCredential


_credential = None


def get_credential() -> DefaultAzureCredential:
    """Get or create a shared DefaultAzureCredential instance."""
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential


def get_token(scope: str) -> str:
    """Acquire an Entra ID access token for the given scope.

    Common scopes:
    - https://management.azure.com/.default (ARM)
    - https://vault.azure.net/.default (Key Vault)
    - https://storage.azure.com/.default (Storage)
    - https://servicebus.azure.net/.default (Service Bus)
    - https://cosmos.azure.com/.default (Cosmos DB)
    - https://cognitiveservices.azure.com/.default (Cognitive Services / OpenAI)
    """
    credential = get_credential()
    token = credential.get_token(scope)
    return token.token


def get_arm_token() -> str:
    """Get token for Azure Resource Manager."""
    return get_token("https://management.azure.com/.default")


def get_keyvault_token() -> str:
    """Get token for Azure Key Vault."""
    return get_token("https://vault.azure.net/.default")


def get_storage_token() -> str:
    """Get token for Azure Storage."""
    return get_token("https://storage.azure.com/.default")


def get_cognitive_services_token() -> str:
    """Get token for Cognitive Services (OpenAI, Doc Intelligence, Content Safety)."""
    return get_token("https://cognitiveservices.azure.com/.default")
