"""Shared pytest fixtures for infrastructure tests."""

import json
import os
import pytest
import yaml
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient

from helpers.azure_client import AzureClientFactory


def _resolve_base_name(config: dict) -> str:
    """Resolve base_name from deployment parameters.json if not overridden.

    Priority: INFRA_TEST_BASE_NAME env var > config.yaml base_name > parameters.json derivation.
    When base_name in config.yaml is empty or 'auto', derive from parameters.json.
    """
    env_override = os.environ.get("INFRA_TEST_BASE_NAME")
    if env_override:
        return env_override

    if config.get("base_name") and config["base_name"] != "auto":
        return config["base_name"]

    # Derive from deployment parameters.json
    variant = os.environ.get("INFRA_TEST_DEPLOYMENT_VARIANT", config.get("deployment_variant", "private"))
    params_path = Path(__file__).parent.parent.parent / "src" / "infra_deployment" / variant / "parameters.json"
    if params_path.exists():
        with open(params_path) as f:
            params = json.load(f)
        base = params["parameters"]["baseName"]["value"]
        prefix = params["parameters"]["uniquePrefix"]["value"]
        return f"{base}{prefix}"

    return config.get("base_name", "next")


def _load_config() -> dict:
    """Load test configuration from config.yaml with environment overrides."""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Apply environment variable overrides
    env_prefix = "INFRA_TEST_"
    for key in ["base_name", "deployment_variant", "location", "ai_location",
                "timeout_seconds", "retry_count", "retry_delay_seconds"]:
        env_key = f"{env_prefix}{key.upper()}"
        if env_key in os.environ:
            value = os.environ[env_key]
            if key in ("timeout_seconds", "retry_count", "retry_delay_seconds"):
                value = int(value)
            config[key] = value

    # Resolve base_name (auto-derive from parameters.json when set to 'auto')
    config["base_name"] = _resolve_base_name(config)

    # Resolve resource names
    base_name = config["base_name"]
    for resource_key, pattern in config.get("resources", {}).items():
        config["resources"][resource_key] = pattern.format(base_name=base_name)

    return config


@pytest.fixture(scope="session")
def config():
    """Test configuration loaded from config.yaml."""
    return _load_config()


@pytest.fixture(scope="session")
def credential():
    """Azure credential using DefaultAzureCredential."""
    return DefaultAzureCredential()


@pytest.fixture(scope="session")
def subscription_id():
    """Azure subscription ID from environment."""
    sub_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
    if not sub_id:
        pytest.skip("AZURE_SUBSCRIPTION_ID not set")
    return sub_id


@pytest.fixture(scope="session")
def resource_group():
    """Azure resource group name from environment."""
    rg = os.environ.get("AZURE_RESOURCE_GROUP")
    if not rg:
        pytest.skip("AZURE_RESOURCE_GROUP not set")
    return rg


@pytest.fixture(scope="session")
def azure_clients(credential, subscription_id):
    """Factory for creating Azure management clients."""
    return AzureClientFactory(credential, subscription_id)


@pytest.fixture(scope="session")
def resource_client(credential, subscription_id):
    """Azure Resource Management client."""
    return ResourceManagementClient(credential, subscription_id)


@pytest.fixture(scope="session")
def deployment_variant(config):
    """Current deployment variant (public or private)."""
    return config.get("deployment_variant", "public")


@pytest.fixture(scope="session")
def base_name(config):
    """Base name for resource naming."""
    return config["base_name"]


@pytest.fixture(scope="session")
def is_private(deployment_variant):
    """Whether the deployment is the private variant."""
    return deployment_variant == "private"


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "private_only: test requires private variant (VPN connected)")
    config.addinivalue_line("markers", "public_only: test only applies to public variant")
    config.addinivalue_line("markers", "slow: test takes longer than usual")


def pytest_collection_modifyitems(config, items):
    """Skip tests based on deployment variant."""
    variant = os.environ.get("INFRA_TEST_DEPLOYMENT_VARIANT",
                             os.environ.get("DEPLOYMENT_VARIANT", "public"))

    skip_private = pytest.mark.skip(reason="Requires private variant with VPN connection")
    skip_public = pytest.mark.skip(reason="Only applies to public variant")

    for item in items:
        if "private_only" in item.keywords and variant != "private":
            item.add_marker(skip_private)
        if "public_only" in item.keywords and variant != "public":
            item.add_marker(skip_public)
