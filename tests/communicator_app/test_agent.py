"""Tests for Azure OpenAI client configuration in workflow.agent."""

import workflow.agent as agent_module


def test_client_uses_api_key_mode(monkeypatch):
    """Test AUTH_MODE=apikey is rejected now that Entra auth is required."""
    monkeypatch.setenv("AUTH_MODE", "apikey")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "gpt-test")

    agent_module._client.cache_clear()
    try:
        agent_module._client()
    except RuntimeError as exc:
        assert "AUTH_MODE=apikey is no longer supported" in str(exc)
    else:
        raise AssertionError("expected AUTH_MODE=apikey to be rejected")
    agent_module._client.cache_clear()


def test_client_uses_credential_mode_by_default(monkeypatch):
    """Test the default path continues to use Azure credentials."""
    captured: dict = {}
    sentinel_credential = object()

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(agent_module, "OpenAIChatClient", FakeClient)
    monkeypatch.setattr(agent_module, "_credential", lambda: sentinel_credential)
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "gpt-test")

    agent_module._client.cache_clear()
    agent_module._client()
    agent_module._client.cache_clear()

    assert captured["credential"] is sentinel_credential
    assert captured["azure_endpoint"] == "https://example.openai.azure.com"
    assert captured["api_version"] == "2025-04-01-preview"
    assert captured["model"] == "gpt-test"
