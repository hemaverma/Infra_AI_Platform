"""Helpers for persisting JSON-safe workflow state snapshots in checkpoints."""

from typing import Any

from pydantic import BaseModel


def stash_json_state(ctx: Any, key: str, value: Any) -> None:
    """Persist a JSON-safe snapshot for a workflow payload under a stable key."""
    if isinstance(value, BaseModel):
        ctx.set_state(key, value.model_dump(mode="json"))
        return
    ctx.set_state(key, value)
