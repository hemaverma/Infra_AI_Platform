# workflow/agent.py
"""Generic Azure OpenAI-backed Agent factory for the vendor-email pipeline.

The module is import-safe even when `AZURE_OPENAI_*` env vars are missing —
`OpenAIChatClient` is constructed lazily behind `_client()` (lru_cache).
Executors should gate `agent.run(...)` calls on `*_agent_enabled()`.
"""
# NOTE: Do not add `from __future__ import annotations` (DD-04 — agent_framework's
# response_handler validator inspects raw annotations).

import os
from functools import lru_cache
from typing import Any, cast

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from azure.identity import AzureCliCredential, DefaultAzureCredential


def _credential():
    """Return an Azure credential that works locally (az login) and in prod (managed identity)."""
    auth_mode = os.getenv("AUTH_MODE", "").strip().lower()
    if auth_mode == "apikey":
        raise RuntimeError(
            "AUTH_MODE=apikey is no longer supported. Use Azure identity via "
            "AUTH_MODE=azurecli or the default DefaultAzureCredential flow."
        )
    if auth_mode == "azurecli":
        return AzureCliCredential()
    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


@lru_cache(maxsize=1)
def _client() -> OpenAIChatClient:
    """Build the Azure OpenAI client once per process. Reads AZURE_OPENAI_* env vars."""
    kwargs: dict[str, Any] = {}
    model = os.getenv("AZURE_OPENAI_MODEL", "").strip()
    if model:
        kwargs["model"] = model
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    if endpoint:
        kwargs["azure_endpoint"] = endpoint.rstrip("/")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "").strip()
    if api_version:
        kwargs["api_version"] = api_version
    return OpenAIChatClient(credential=_credential(), **kwargs)


def build_default_agent(name: str, instructions: str, response_format=None) -> Agent:
    """Build a MAF Agent backed by the shared Azure OpenAI client.

    Constructs `Agent(client=..., default_options=...)` directly because
    `OpenAIChatClient` does not expose a `create_agent()` builder in
    agent-framework 1.2.x.
    """
    default_options: dict[str, Any] = {}
    if response_format is not None:
        default_options["response_format"] = response_format
    return Agent(
        client=_client(),
        name=name,
        instructions=instructions,
        default_options=cast(Any, default_options),
    )


def email_draft_agent_enabled() -> bool:
    """Return True when ENABLE_AGENT_EMAIL_DRAFT opts the draft executor into live agent calls."""
    return os.getenv("ENABLE_AGENT_EMAIL_DRAFT", "").lower() in ("true", "1", "yes")


def extraction_agent_enabled() -> bool:
    """Return True when ENABLE_AGENT_EXTRACTION opts the field extractor into live agent calls."""
    return os.getenv("ENABLE_AGENT_EXTRACTION", "true").lower() in ("true", "1", "yes")
