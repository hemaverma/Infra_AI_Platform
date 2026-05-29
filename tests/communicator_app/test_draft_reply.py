"""Behavior tests for the draft reply executor."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import workflow.executors.draft_reply as draft_reply_module
from workflow.executors.draft_reply import DraftReplyExecutor
from workflow.messages import CommandResult, DraftReply, MaintenanceEmailFields, MaintenanceWindow


class _RecordingContext:
    def __init__(self) -> None:
        self.messages: list[DraftReply] = []
        self.state: dict[str, object] = {}

    async def send_message(self, message: DraftReply) -> None:
        self.messages.append(message)

    def set_state(self, key: str, value: object) -> None:
        self.state[key] = value


class _FakeAgent:
    def __init__(self, value: object) -> None:
        self.value = value
        self.prompts: list[str] = []

    async def run(self, prompt: str):
        self.prompts.append(prompt)
        return SimpleNamespace(value=self.value)


def _sample_command_result(executed: list[dict]) -> CommandResult:
    return CommandResult(
        workflow_instance_id="wf-draft",
        internet_message_id="msg-draft",
        received_at=datetime(2026, 5, 13, tzinfo=timezone.utc),
        subject="Vendor maintenance notice",
        sender="noc@vendor.example",
        fields=MaintenanceEmailFields(
            vendor_ticket_id="NCC-24173",
            windows=[
                MaintenanceWindow(
                    window_id="window-1",
                    kind="primary",
                    start_raw="2026-05-12 01:00 UTC",
                    end_raw="2026-05-12 03:00 UTC",
                )
            ],
        ),
        command_outputs={"operations": {"approved": True, "executed": executed}},
    )


def test_draft_reply_uses_llm_for_successful_create(monkeypatch):
    """Test successful create outcomes draft through the LLM path when enabled."""
    fake_agent = _FakeAgent(
        {
            "subject": "Re: NCC-24173 | CHG0024173",
            "body": "Acknowledged receipt. Change CHG0024173 has been created.",
        }
    )
    monkeypatch.setattr(draft_reply_module, "email_draft_agent_enabled", lambda: True)

    context = _RecordingContext()
    executor = DraftReplyExecutor()
    executor._agent = fake_agent

    asyncio.run(
        executor.draft(
            _sample_command_result([
                {
                    "op": "create_ticket",
                    "status": "stub-ok",
                    "result": {
                        "chg_number": "CHG0024173",
                        "market_cc_dls": [
                            "atlanta@market-dl.example.com",
                            "macon@market-dl.example.com",
                        ],
                    },
                }
            ]),
            context,
        )
    )

    assert len(context.messages) == 1
    draft = context.messages[0]
    assert fake_agent.prompts
    assert draft.cc_addresses == [
        "atlanta@market-dl.example.com",
        "macon@market-dl.example.com",
    ]
    assert draft.subject == "Re: NCC-24173 | CHG0024173"
    assert draft.body == "Acknowledged receipt. Change CHG0024173 has been created."


def test_draft_reply_uses_fallback_when_llm_disabled(monkeypatch):
    """Test fallback acknowledgment drafting when the LLM path is disabled."""
    monkeypatch.setattr(draft_reply_module, "email_draft_agent_enabled", lambda: False)

    context = _RecordingContext()
    executor = DraftReplyExecutor()

    asyncio.run(
        executor.draft(
            _sample_command_result([
                {
                    "op": "create_ticket",
                    "status": "stub-ok",
                    "result": {
                        "chg_number": "CHG0024173",
                        "market_cc_dls": [
                            "atlanta@market-dl.example.com",
                            "macon@market-dl.example.com",
                        ],
                    },
                }
            ]),
            context,
        )
    )

    assert len(context.messages) == 1
    draft = context.messages[0]
    assert draft.subject == "Re: NCC-24173 | CHG0024173"
    assert "Acknowledged receipt of the maintenance notice for ticket NCC-24173" in draft.body
    assert "2026-05-12 01:00 UTC to 2026-05-12 03:00 UTC" in draft.body
    assert "Downstream CHG CHG0024173 has been created" in draft.body


def test_draft_reply_skips_non_create_or_failed_create_outcomes():
    """Test drafting is skipped unless operations reports a successful create."""
    executor = DraftReplyExecutor()

    update_only_context = _RecordingContext()
    asyncio.run(
        executor.draft(
            _sample_command_result([{"op": "update_ticket", "status": "stub-ok"}]),
            update_only_context,
        )
    )

    failed_create_context = _RecordingContext()
    asyncio.run(
        executor.draft(
            _sample_command_result([{"op": "create_ticket", "status": "failed"}]),
            failed_create_context,
        )
    )

    assert update_only_context.messages == []
    assert failed_create_context.messages == []


def test_draft_reply_skips_create_without_stub_chg_number():
    """Test drafting is skipped when the create outcome lacks the stub CHG number."""
    context = _RecordingContext()
    executor = DraftReplyExecutor()

    asyncio.run(
        executor.draft(
            _sample_command_result([
                {
                    "op": "create_ticket",
                    "status": "stub-ok",
                    "result": {"market_cc_dls": ["atlanta@market-dl.example.com"]},
                }
            ]),
            context,
        )
    )

    assert context.messages == []


def test_draft_reply_uploads_blob_artifact_when_storage_prefix_is_available(monkeypatch):
    """Test draft persistence writes draft-reply.json under the staged prefix."""
    upload_calls: list[tuple[str, str, str]] = []

    monkeypatch.setattr(draft_reply_module, "email_draft_agent_enabled", lambda: False)
    monkeypatch.setattr(
        draft_reply_module,
        "upload_json_artifact",
        lambda storage_prefix, artifact_name, payload: upload_calls.append(
            (storage_prefix, artifact_name, payload.workflow_instance_id)
        ),
    )

    context = _RecordingContext()
    executor = DraftReplyExecutor()
    result = _sample_command_result([
        {
            "op": "create_ticket",
            "status": "stub-ok",
            "result": {
                "chg_number": "CHG0024173",
                "market_cc_dls": ["atlanta@market-dl.example.com"],
            },
        }
    ]).model_copy(update={"storage_prefix": "workflow-123"})

    asyncio.run(executor.draft(result, context))

    assert upload_calls == [("workflow-123", "draft-reply.json", "wf-draft")]
