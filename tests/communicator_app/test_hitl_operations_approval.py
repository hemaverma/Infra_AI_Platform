"""Behavior tests for the stubbed operations approval proposal step."""

from datetime import datetime, timezone

import pytest
from workflow.executors.hitl_operations_approval import (
    _coerce_approval_response,
    _propose_operations,
)
from workflow.messages import (
    HitlRequest,
    MaintenanceAsset,
    MaintenanceEmailFields,
    NormalizedFields,
)


class _RecordingContext:
    def __init__(self) -> None:
        self.requests: list[HitlRequest] = []
        self.state: dict[str, object] = {}

    async def request_info(self, request_data: HitlRequest, response_type: type[dict]) -> None:
        del response_type
        self.requests.append(request_data)

    def set_state(self, key: str, value: object) -> None:
        self.state[key] = value


def test_propose_operations_uses_fixed_mock_chg_number():
    """Test stubbed create metadata uses fixed mock CHG and market CC values."""
    normalized = NormalizedFields(
        workflow_instance_id="wf-approval",
        internet_message_id="msg-approval",
        received_at=datetime(2026, 5, 13, tzinfo=timezone.utc),
        subject="Vendor maintenance notice",
        sender="noc@vendor.example",
        fields=MaintenanceEmailFields(
            vendor_ticket_id="NCC-24173",
            assets=[MaintenanceAsset(asset_id="asset-1", type="circuit", value="LAX-NYC-OC192-001")],
        ),
        affected_sites=["ATLANTA"],
    )

    operations = _propose_operations(normalized)

    assert len(operations) == 1
    assert operations[0].metadata["stub_create_result"]["chg_number"] == "CHG0000001"
    assert operations[0].metadata["stub_create_result"]["market_cc_dls"] == [
        "market-dl-stub@example.com"
    ]


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"approval_status": "Approve"}, True),
        ({"approval_status": "Reject"}, False),
        ({"approved": "Approve"}, True),
        ({"approved": "Reject"}, False),
    ],
)
def test_coerce_approval_response_accepts_approve_reject_aliases(response, expected):
    """Test alias approval values are accepted defensively by the executor helper."""
    assert _coerce_approval_response(response) is expected
