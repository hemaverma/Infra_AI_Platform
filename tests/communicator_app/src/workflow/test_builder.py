"""Tests for workflow graph construction."""

import asyncio
from collections.abc import AsyncIterator

from agent_framework import WorkflowCheckpoint
from agent_framework_azure_cosmos import CosmosCheckpointStorage

import workflow.checkpoint_storage as checkpoint_storage_module
from workflow.builder import build_storage, build_workflow
from workflow.checkpoint_storage import Utf8FileCheckpointStorage


class _FakeCosmosContainer:
    def __init__(self) -> None:
        self.documents: list[dict] = []

    async def upsert_item(self, *, body: dict) -> None:
        self.documents = [
            document for document in self.documents if document["id"] != body["id"]
        ]
        self.documents.append(body)

    def query_items(self, *, query: str, parameters: list[dict], partition_key=None) -> AsyncIterator[dict]:
        if "@checkpoint_id" in {parameter["name"] for parameter in parameters}:
            checkpoint_id = next(
                parameter["value"]
                for parameter in parameters
                if parameter["name"] == "@checkpoint_id"
            )
            items = [
                document for document in self.documents if document.get("checkpoint_id") == checkpoint_id
            ]
        elif "@workflow_name" in {parameter["name"] for parameter in parameters}:
            workflow_name = next(
                parameter["value"]
                for parameter in parameters
                if parameter["name"] == "@workflow_name"
            )
            items = [
                document for document in self.documents if document.get("workflow_name") == workflow_name
            ]
        else:
            items = list(self.documents)

        async def _iterator() -> AsyncIterator[dict]:
            for item in items:
                yield item

        return _iterator()


def _edge_map(workflow, source_id: str) -> dict[str, str | None]:
    edge_map: dict[str, str | None] = {}
    for group in workflow.graph_signature["edge_groups"]:
        for edge in group["edges"]:
            if edge["source"] == source_id:
                edge_map[edge["target"]] = edge["condition"]
    return edge_map


def test_given_workflow_when_build_then_has_explicit_rejection_routes() -> None:
    # Arrange
    storage = build_storage()

    # Act
    workflow = build_workflow(storage, workflow_instance_id="wf-builder")

    # Assert
    assert "terminate_rejected" in workflow.executors
    assert _edge_map(workflow, "hitl_operations_approval") == {
        "operations_command": "_is_approved",
        "terminate_rejected": "_is_rejected",
    }
    assert _edge_map(workflow, "hitl_review_draft") == {
        "send_reply": "_is_approved",
        "terminate_rejected": "_is_rejected",
    }


def test_given_storage_when_build_then_uses_utf8_checkpoint_storage() -> None:
    # Arrange / Act
    storage = build_storage()

    # Assert
    assert isinstance(storage, Utf8FileCheckpointStorage)


def test_utf8_checkpoint_storage_uses_utf8_for_unicode_payloads(tmp_path, monkeypatch) -> None:
    # Arrange
    real_open = open
    encodings: list[str | None] = []

    def _recording_open(*args, **kwargs):
        mode = kwargs.get("mode")
        if mode is None and len(args) > 1:
            mode = args[1]
        if mode is None:
            mode = "r"
        if "b" not in mode:
            encodings.append(kwargs.get("encoding"))
            assert kwargs.get("encoding") == "utf-8"
        return real_open(*args, **kwargs)

    monkeypatch.setattr(checkpoint_storage_module, "open", _recording_open, raising=False)
    storage = Utf8FileCheckpointStorage(tmp_path)
    checkpoint = WorkflowCheckpoint(
        workflow_name="wf-unicode",
        graph_signature_hash="graph-hash",
        state={"draft_body": "Approved ✔"},
    )

    # Act
    checkpoint_id = asyncio.run(storage.save(checkpoint))
    loaded = asyncio.run(storage.load(checkpoint_id))
    listed = asyncio.run(storage.list_checkpoints(workflow_name="wf-unicode"))
    listed_ids = asyncio.run(storage.list_checkpoint_ids(workflow_name="wf-unicode"))

    # Assert
    assert loaded.state["draft_body"] == "Approved ✔"
    assert [item.checkpoint_id for item in listed] == [checkpoint_id]
    assert listed_ids == [checkpoint_id]
    assert encodings == ["utf-8", "utf-8", "utf-8", "utf-8"]


def test_cosmos_checkpoint_storage_round_trips_unicode_payloads() -> None:
    # Arrange
    container = _FakeCosmosContainer()
    storage = CosmosCheckpointStorage(
        container_client=container,
        database_name="vendor-email-response",
        container_name="workflow-checkpoints",
        allowed_checkpoint_types=[],
    )
    checkpoint = WorkflowCheckpoint(
        workflow_name="wf-unicode-cosmos",
        graph_signature_hash="graph-hash",
        state={"draft_body": "Approved\u200cOK"},
    )

    # Act
    checkpoint_id = asyncio.run(storage.save(checkpoint))
    loaded = asyncio.run(storage.load(checkpoint_id))

    # Assert
    assert container.documents[0]["state"]["draft_body"] == "Approved\u200cOK"
    assert loaded.state["draft_body"] == "Approved\u200cOK"
