"""Prompty-backed loader and renderer for the extraction prompt asset."""

from functools import lru_cache
import os
from pathlib import Path

import prompty
import prompty.parsers  # noqa: F401
from prompty.core import Prompty


_EXTRACTION_PROMPTY_PATH_ENV = "EXTRACTION_PROMPTY_PATH"
_DEFAULT_PROMPTY_PATH = Path(__file__).resolve().parents[2] / "prompts" / "field_extraction.prompty"


def configured_extraction_prompty_path() -> Path:
    """Return the configured extraction prompty path with a repo-local default."""
    configured_path = os.getenv(_EXTRACTION_PROMPTY_PATH_ENV, "").strip()
    if configured_path:
        return Path(configured_path)
    return _DEFAULT_PROMPTY_PATH


def load_extraction_prompty() -> Prompty:
    """Load the extraction prompty from disk via the Prompty runtime."""
    return _load_extraction_prompty(str(configured_extraction_prompty_path()))


@lru_cache(maxsize=8)
def _load_extraction_prompty(prompty_path: str) -> Prompty:
    """Load and cache a Prompty asset by path."""
    return prompty.load(prompty_path)


def prepared_extraction_messages(email_packet: str) -> list[dict[str, str]]:
    """Return the prepared Prompty chat messages for extraction."""
    return list(prompty.prepare(load_extraction_prompty(), {"email_packet": email_packet.strip()}))


def render_extraction_prompt(email_packet: str) -> str:
    """Render the extraction prompty user message via Prompty prepare."""
    messages = prepared_extraction_messages(email_packet)
    return _message_content(messages, "user")


def extraction_instructions() -> str:
    """Return the extraction prompty system instructions."""
    messages = prepared_extraction_messages("")
    return _message_content(messages, "system")


def render_full_extraction_prompt(email_packet: str) -> str:
    """Render the full prepared extraction chat exchange for inspection."""
    rendered_messages: list[str] = []
    for message in prepared_extraction_messages(email_packet):
        role = str(message.get("role", "message")).upper()
        content = str(message.get("content", "")).rstrip()
        rendered_messages.append(f"{role}:\n{content}")
    return "\n\n".join(rendered_messages)


def _message_content(messages: list[dict[str, str]], role: str) -> str:
    """Return the first message content for a role from prepared Prompty output."""
    for message in messages:
        if message.get("role") == role:
            return str(message.get("content", ""))
    raise ValueError(f"missing {role} message in prepared extraction prompty")
