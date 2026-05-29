"""Checkpoint storage wrappers for local workflow persistence.

The upstream Agent Framework `FileCheckpointStorage` currently opens checkpoint
JSON files using the process default text encoding. On Windows that can be a
legacy code page such as cp1252, which breaks checkpoint persistence as soon as
workflow state includes non-ASCII content from vendor emails, LLM drafts, or
HITL payloads.

This module provides a drop-in subclass that forces UTF-8 for all checkpoint
file reads and writes while preserving the framework's JSON + base64-encoded
pickle wire format.
"""

import asyncio
import json
import logging
import os
from typing import Any

from agent_framework import FileCheckpointStorage, WorkflowCheckpoint, WorkflowCheckpointException

logger = logging.getLogger(__name__)


class Utf8FileCheckpointStorage(FileCheckpointStorage):
    """File checkpoint storage that always reads and writes JSON as UTF-8."""

    async def save(self, checkpoint: WorkflowCheckpoint) -> str:
        """Save a checkpoint using UTF-8 text encoding."""
        from agent_framework._workflows._checkpoint_encoding import encode_checkpoint_value

        file_path = self._validate_file_path(checkpoint.checkpoint_id)
        checkpoint_dict = checkpoint.to_dict()
        encoded_checkpoint = encode_checkpoint_value(checkpoint_dict)

        def _write_atomic() -> None:
            tmp_path = file_path.with_suffix(".json.tmp")
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(encoded_checkpoint, handle, indent=2, ensure_ascii=False)
            os.replace(tmp_path, file_path)

        await asyncio.to_thread(_write_atomic)

        logger.info("Saved checkpoint %s to %s", checkpoint.checkpoint_id, file_path)
        return checkpoint.checkpoint_id

    async def load(self, checkpoint_id: str) -> WorkflowCheckpoint:
        """Load a checkpoint using UTF-8 text encoding."""
        file_path = self._validate_file_path(checkpoint_id)

        if not file_path.exists():
            raise WorkflowCheckpointException(f"No checkpoint found with ID {checkpoint_id}")

        def _read() -> dict[str, Any]:
            with open(file_path, encoding="utf-8") as handle:
                return json.load(handle)  # type: ignore[no-any-return]

        encoded_checkpoint = await asyncio.to_thread(_read)

        from agent_framework._workflows._checkpoint_encoding import decode_checkpoint_value

        try:
            decoded_checkpoint_dict = decode_checkpoint_value(
                encoded_checkpoint,
                allowed_types=self._allowed_types,
            )
        except WorkflowCheckpointException:
            raise

        checkpoint = WorkflowCheckpoint.from_dict(decoded_checkpoint_dict)
        logger.info("Loaded checkpoint %s from %s", checkpoint_id, file_path)
        return checkpoint

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        """List checkpoints for one workflow using UTF-8 text encoding."""

        def _list_checkpoints() -> list[WorkflowCheckpoint]:
            checkpoints: list[WorkflowCheckpoint] = []
            for file_path in self.storage_path.glob("*.json"):
                try:
                    with open(file_path, encoding="utf-8") as handle:
                        encoded_checkpoint = json.load(handle)
                        from agent_framework._workflows._checkpoint_encoding import decode_checkpoint_value

                        decoded_checkpoint_dict = decode_checkpoint_value(
                            encoded_checkpoint,
                            allowed_types=self._allowed_types,
                        )
                        checkpoint = WorkflowCheckpoint.from_dict(decoded_checkpoint_dict)
                    if checkpoint.workflow_name == workflow_name:
                        checkpoints.append(checkpoint)
                except Exception as exc:  # noqa: BLE001 - parity with framework storage diagnostics
                    logger.warning("Failed to read checkpoint file %s: %s", file_path, exc)
            return checkpoints

        return await asyncio.to_thread(_list_checkpoints)

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[str]:
        """List checkpoint ids for one workflow using UTF-8 text encoding."""

        def _list_ids() -> list[str]:
            checkpoint_ids: list[str] = []
            for file_path in self.storage_path.glob("*.json"):
                try:
                    with open(file_path, encoding="utf-8") as handle:
                        data = json.load(handle)
                    if data.get("workflow_name") == workflow_name:
                        checkpoint_ids.append(data.get("checkpoint_id", file_path.stem))
                except Exception as exc:  # noqa: BLE001 - parity with framework storage diagnostics
                    logger.warning("Failed to read checkpoint file %s: %s", file_path, exc)
            return checkpoint_ids

        return await asyncio.to_thread(_list_ids)
