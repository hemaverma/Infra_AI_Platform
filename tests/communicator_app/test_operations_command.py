"""Behavior tests for the stubbed operations command executor."""

import asyncio
from datetime import datetime, timezone

from workflow.executors.operations_command import OperationsCommandExecutor
from workflow.messages import ApprovedOperationsPlan, CommandResult, MaintenanceEmailFields, OperationsRequest


class _RecordingContext:
    def __init__(self) -> None:
        self.messages: list[CommandResult] = []
        self.state: dict[str, object] = {}

    async def send_message(self, message: CommandResult) -> None:
        self.messages.append(message)

    def set_state(self, key: str, value: object) -> None:
        self.state[key] = value


def test_operations_command_carries_stub_create_result_into_command_outputs():
    """Test the stubbed executor preserves create-result metadata for reply drafting."""
    plan = ApprovedOperationsPlan(
        workflow_instance_id="wf-ops",
        internet_message_id="msg-ops",
        received_at=datetime(2026, 5, 13, tzinfo=timezone.utc),
        subject="Vendor maintenance notice",
        sender="noc@vendor.example",
        fields=MaintenanceEmailFields(vendor_ticket_id="NCC-24173"),
        approved_operations=[
            OperationsRequest(
                op="create_ticket",
                payload={"ticket_id": "NCC-24173"},
                metadata={
                    "stub_create_result": {
                        "chg_number": "CHG0024173",
                        "market_cc_dls": ["atlanta@market-dl.example.com"],
                    }
                },
            )
        ],
        approved=True,
    )

    context = _RecordingContext()
    executor = OperationsCommandExecutor()

    asyncio.run(executor.run_commands(plan, context))

    assert len(context.messages) == 1
    executed = context.messages[0].command_outputs["operations"]["executed"]
    assert executed[0]["status"] == "stub-ok"
    assert executed[0]["result"] == {
        "chg_number": "CHG0024173",
        "market_cc_dls": ["atlanta@market-dl.example.com"],
    }
