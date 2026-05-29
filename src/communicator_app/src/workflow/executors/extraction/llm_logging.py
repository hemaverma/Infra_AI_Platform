"""Shared LLM request and response logging helpers for extraction executors."""

import json
import logging
import os
from typing import Any

from pydantic import BaseModel


_LLM_DEBUG_LOGS_ENV = "ENABLE_LLM_DEBUG_LOGS"
_LLM_DEBUG_MAX_CHARS_ENV = "LLM_DEBUG_LOG_MAX_CHARS"
_DEFAULT_MAX_CHARS = 4000
_MIN_MAX_CHARS = 256


def log_llm_request(
    logger,
    operation: str,
    *,
    agent_name: str,
    instructions: str,
    prompt: str,
    response_format: type[Any] | None = None,
    metadata: dict[str, Any] | None = None,
    sections: dict[str, Any] | None = None,
) -> None:
    """Log an LLM request summary and, when enabled, the request payloads."""
    response_format_name = response_format.__name__ if response_format is not None else "none"
    logger.info(
        "%s: invoking llm agent=%s model=%s response_format=%s instructions_chars=%d prompt_chars=%d",
        operation,
        agent_name,
        os.getenv("AZURE_OPENAI_MODEL", ""),
        response_format_name,
        len(instructions),
        len(prompt),
    )
    verbose_level = _verbose_log_level(logger)
    if verbose_level is None:
        return

    if metadata:
        logger.log(verbose_level, "%s: metadata\n%s", operation, _truncate(_to_json_text(metadata)))
    logger.log(verbose_level, "%s: instructions\n%s", operation, _truncate(instructions))
    if sections:
        for title, value in sections.items():
            logger.log(verbose_level, "%s: %s\n%s", operation, title, _truncate(_serialize_for_log(value)))
    logger.log(verbose_level, "%s: prompt\n%s", operation, _truncate(prompt))


def log_llm_response(logger, operation: str, *, response: Any) -> None:
    """Log an LLM response summary and, when enabled, the structured response body."""
    serialized = _serialize_for_log(response)
    logger.info("%s: received llm response chars=%d", operation, len(serialized))
    verbose_level = _verbose_log_level(logger)
    if verbose_level is not None:
        logger.log(verbose_level, "%s: response\n%s", operation, _truncate(serialized))


def _llm_debug_logging_enabled() -> bool:
    """Return True when verbose LLM payload logging is explicitly enabled."""
    return os.getenv(_LLM_DEBUG_LOGS_ENV, "").lower() in ("true", "1", "yes")


def _llm_debug_log_max_chars() -> int:
    """Return the maximum number of characters to emit for verbose LLM logs."""
    raw_value = os.getenv(_LLM_DEBUG_MAX_CHARS_ENV, "").strip()
    if not raw_value:
        return _DEFAULT_MAX_CHARS
    try:
        return max(int(raw_value), _MIN_MAX_CHARS)
    except ValueError:
        return _DEFAULT_MAX_CHARS


def _verbose_log_level(logger) -> int | None:
    """Return the log level to use for verbose LLM payloads, if enabled."""
    if _llm_debug_logging_enabled():
        return logging.INFO
    if logger.isEnabledFor(logging.DEBUG):
        return logging.DEBUG
    return None


def _serialize_for_log(value: Any) -> str:
    """Serialize supported values into readable text for logs."""
    if isinstance(value, BaseModel):
        return _to_json_text(value.model_dump(mode="json"))
    if isinstance(value, (dict, list, tuple)):
        return _to_json_text(value)
    if hasattr(value, "model_dump"):
        try:
            return _to_json_text(value.model_dump(mode="json"))
        except TypeError:
            return _to_json_text(value.model_dump())
    return str(value)


def _to_json_text(value: Any) -> str:
    """Render a Python object as stable JSON for logs."""
    return json.dumps(value, indent=2, sort_keys=True, default=str)


def _truncate(value: str) -> str:
    """Trim long log bodies while preserving size context."""
    max_chars = _llm_debug_log_max_chars()
    if len(value) <= max_chars:
        return value
    omitted_chars = len(value) - max_chars
    return f"{value[:max_chars]}\n... [truncated {omitted_chars} chars]"
