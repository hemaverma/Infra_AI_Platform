"""Tests for extraction helpers and balanced extraction models."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from prompty.core import Prompty
from pydantic import ValidationError
from workflow.executors.extraction.fallback import build_fallback_extraction
from workflow.executors.extraction.prompt_input import (
    build_candidate_hints,
    build_extraction_prompt_input,
    configured_extraction_prompt_email_format,
)
from workflow.executors.extraction.prompty import (
    configured_extraction_prompty_path,
    extraction_instructions,
    load_extraction_prompty,
    render_extraction_prompt,
    render_full_extraction_prompt,
)
from workflow.extraction_schema import validate_maintenance_email_fields
from workflow.extraction_views import circuit_values, summary_text, ticket_value, window_text
from workflow.messages import AttachmentContent, MaintenanceAsset, MaintenanceEmailFields, MaintenanceWindow, SafeEmail


class TestMaintenanceEmailFieldsModel:
    """Test the balanced extraction model shape."""

    def test_fields_store_balanced_schema_values(self):
        """Test that the model keeps balanced-schema values without legacy aliases."""
        fields = MaintenanceEmailFields(
            schema_version="v1",
            vendor_ticket_id="NCC-24173",
            work_short_description="fiber maintenance",
            work_description="Longer maintenance description.",
            windows=[
                MaintenanceWindow(
                    window_id="window-1",
                    kind="primary",
                    start_raw="2026-05-12 01:00 UTC",
                    end_raw="2026-05-12 03:00 UTC",
                )
            ],
            assets=[MaintenanceAsset(asset_id="asset-1", type="circuit", value="LAX-NYC-OC192-001")],
        )

        assert fields.vendor_ticket_id == "NCC-24173"
        assert fields.work_short_description == "fiber maintenance"
        assert fields.windows[0].start_raw == "2026-05-12 01:00 UTC"
        assert fields.assets[0].value == "LAX-NYC-OC192-001"


class TestExtractionViews:
    """Test shared read-only selectors for balanced extraction fields."""

    def test_shared_selectors_return_expected_values(self):
        """Test ticket, circuit, summary, and window selectors."""
        fields = MaintenanceEmailFields(
            vendor_ticket_id="NCC-24173",
            work_short_description="fiber maintenance",
            work_description="Longer maintenance description.",
            windows=[
                MaintenanceWindow(
                    window_id="window-1",
                    kind="primary",
                    start_raw="2026-05-12 01:00 UTC",
                    end_raw="2026-05-12 03:00 UTC",
                )
            ],
            assets=[MaintenanceAsset(asset_id="asset-1", type="circuit", value="LAX-NYC-OC192-001")],
        )

        assert ticket_value(fields) == "NCC-24173"
        assert circuit_values(fields) == ["LAX-NYC-OC192-001"]
        assert window_text(fields) == "2026-05-12 01:00 UTC to 2026-05-12 03:00 UTC"
        assert summary_text(fields) == "fiber maintenance"


class TestPromptPreparation:
    """Test lightweight prompt preparation helpers."""

    def test_build_candidate_hints_extracts_att_ticket_without_hyphen(self):
        """Test candidate hints recognize CHG-style ids without a hyphen."""
        hints = build_candidate_hints(
            "Vendor Maintenance Notification - Change Request #CHG000000000001",
            "Change Request #: CHG000000000001\nStart Date & Time: 05/19/26 04:01:00 UTC",
            [],
        )

        assert "CHG000000000001" in hints["ticket_candidates"]

    def test_build_candidate_hints_extracts_ticket_circuit_and_window_hints(self):
        """Test candidate hints from subject and body text."""
        hints = build_candidate_hints(
            "Updated maintenance for NCC-24173",
            "Circuit LAX-NYC-OC192-001 will have an outage on 2026-05-12 01:00 UTC.",
            [AttachmentContent(filename="maintenance.csv", content="Circuit ID\nLAX-NYC-OC192-001\n")],
        )

        assert "NCC-24173" in hints["ticket_candidates"]
        assert "LAX-NYC-OC192-001" in hints["circuit_candidates"]
        assert "2026-05-12 01:00 UTC" in hints["window_candidates"]
        assert "maintenance.csv" in hints["attachment_names"]

    def test_build_extraction_prompt_input_appends_csv_rows_when_available(self):
        """Test prompt input building defaults to markdown with CSV content."""
        safe = SafeEmail(
            workflow_instance_id="wf-1",
            internet_message_id="msg-1",
            received_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
            subject="Maintenance for NCC-24173",
            sender="noc@vendor.example",
            body="Please review the attached maintenance schedule.",
            attachments=[
                AttachmentContent(
                    filename="maintenance.csv",
                    content=(
                        "Circuit ID,Start,End\n"
                        "LAX-NYC-OC192-001,2026-05-12 01:00 UTC,2026-05-12 03:00 UTC\n"
                    ),
                )
            ],
            notes={},
        )

        prompt_input = build_extraction_prompt_input(safe)

        assert "## Candidate Hints" not in prompt_input
        assert "# Email Packet" in prompt_input
        assert "## Attachments" in prompt_input
        assert "### maintenance.csv" in prompt_input
        assert "Status: loaded" in prompt_input
        assert "ROW 1 | Circuit ID=LAX-NYC-OC192-001" in prompt_input

    def test_build_extraction_prompt_input_reads_materialized_attachment_content(self):
        """Test prompt input consumes structured attachment payloads instead of file paths."""
        safe = SafeEmail(
            workflow_instance_id="wf-1",
            internet_message_id="msg-1",
            received_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
            subject="Vendor Maintenance Notification - Change Request CR-0001",
            sender="noreply@vendor.example",
            body="Please review the attached maintenance schedule.",
            attachments=[
                AttachmentContent(
                    filename="circuits.csv",
                    content="Circuit ID,Severity\nSYN-NYC-001,Switch to Protect\n",
                )
            ],
            notes={},
        )

        prompt_input = build_extraction_prompt_input(safe)

        assert "### circuits.csv" in prompt_input
        assert "Status: loaded" in prompt_input
        assert "ROW 1 | Circuit ID=SYN-NYC-001" in prompt_input

    def test_build_extraction_prompt_input_can_include_candidate_hints(self):
        """Test prompt input can inject candidate hints into markdown output."""
        safe = SafeEmail(
            workflow_instance_id="wf-1",
            internet_message_id="msg-1",
            received_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
            subject="Maintenance for NCC-24173",
            sender="noc@vendor.example",
            body="Circuit LAX-NYC-OC192-001 will have an outage on 2026-05-12 01:00 UTC.",
            attachments=[],
            notes={},
        )

        prompt_input = build_extraction_prompt_input(safe, include_candidate_hints=True)

        assert "## Candidate Hints" in prompt_input
        assert "NCC-24173" in prompt_input

    def test_build_extraction_prompt_input_can_render_xml_when_requested(self):
        """Test prompt input can still render the legacy XML structure."""
        safe = SafeEmail(
            workflow_instance_id="wf-1",
            internet_message_id="msg-1",
            received_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
            subject="Maintenance for NCC-24173",
            sender="noc@vendor.example",
            body="Circuit LAX-NYC-OC192-001 will have an outage on 2026-05-12 01:00 UTC.",
            attachments=[],
            notes={},
        )

        prompt_input = build_extraction_prompt_input(
            safe,
            include_candidate_hints=True,
            prompt_email_format="xml",
        )

        assert "<email_packet>" in prompt_input
        assert "<candidate_hints>" in prompt_input
        assert "</email_packet>" in prompt_input

    def test_configured_extraction_prompt_email_format_defaults_to_markdown(self, monkeypatch):
        """Test prompt email format defaults to markdown when unset."""
        monkeypatch.delenv("EXTRACTION_PROMPT_EMAIL_FORMAT", raising=False)

        assert configured_extraction_prompt_email_format() == "markdown"

    def test_configured_extraction_prompt_email_format_reads_environment(self, monkeypatch):
        """Test prompt email format can be configured through the environment."""
        monkeypatch.setenv("EXTRACTION_PROMPT_EMAIL_FORMAT", "xml")

        assert configured_extraction_prompt_email_format() == "xml"

    def test_prompty_loader_and_renderer_wrap_email_packet(self):
        """Test the checked-in prompty asset is loaded and rendered by Prompty."""
        prompt = load_extraction_prompty()
        rendered = render_extraction_prompt("<email_packet>example</email_packet>")
        full_rendered = render_full_extraction_prompt("<email_packet>example</email_packet>")

        assert isinstance(prompt, Prompty)
        assert "MaintenanceEmailFields" in extraction_instructions()
        assert "long CHG identifiers belong in customer_ticket_ids" in extraction_instructions()
        assert "Extract maintenance fields from this normalized email packet." in rendered
        assert "<email_packet>example</email_packet>" in rendered
        assert "SYSTEM:" in full_rendered
        assert "USER:" in full_rendered
        assert "<email_packet>example</email_packet>" in full_rendered

    def test_prompty_path_can_be_overridden_by_environment(self, tmp_path: Path, monkeypatch):
        """Test environment-based Prompty path override for local experimentation."""
        prompt_path = tmp_path / "custom.prompty"
        prompt_path.write_text(
            "---\n"
            "name: custom_extractor\n"
            "model:\n"
            "  api: chat\n"
            "template:\n"
            "  type: jinja2\n"
            "  parser: prompty\n"
            "---\n\n"
            "system:\n"
            "Use the custom extraction prompt.\n\n"
            "user:\n"
            "Custom packet:\n{{ email_packet }}\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("EXTRACTION_PROMPTY_PATH", str(prompt_path))

        assert configured_extraction_prompty_path() == prompt_path
        assert "Use the custom extraction prompt." in extraction_instructions()
        assert "Custom packet:" in render_extraction_prompt("<email_packet>custom</email_packet>")


class TestFallbackExtraction:
    """Test the deterministic fallback extraction path."""

    def test_stub_extract_returns_balanced_schema_shape(self):
        """Test fallback extraction from lightweight hints."""
        safe = SafeEmail(
            workflow_instance_id="wf-2",
            internet_message_id="msg-2",
            received_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
            subject="Updated maintenance for NCC-24173",
            sender="noc@vendor.example",
            body="LAX-NYC-OC192-001 outage window 2026-05-12 01:00 UTC.",
            attachments=[],
            notes={},
        )

        fields = build_fallback_extraction(safe)

        assert fields.schema_version == "v1"
        assert fields.vendor_ticket_id == "NCC-24173"
        assert fields.intent == "reschedule"
        assert fields.assets[0].value == "LAX-NYC-OC192-001"

    def test_stub_extract_maps_long_chg_to_customer_ticket_ids(self):
        """Test fallback keeps long CHG values out of vendor_ticket_id."""
        safe = SafeEmail(
            workflow_instance_id="wf-3",
            internet_message_id="msg-3",
            received_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
            subject="Vendor Maintenance Notification - Change Request #CHG000000000001",
            sender="noreply@vendor.example",
            body="Change Request #: CHG000000000001\nStart Date & Time: 05/19/26 04:01:00 UTC.",
            attachments=[],
            notes={},
        )

        fields = build_fallback_extraction(safe)

        assert fields.vendor_ticket_id == ""
        assert fields.customer_ticket_ids == ["CHG000000000001"]


class TestSchemaValidation:
    """Test explicit revalidation against the extraction schema."""

    def test_validate_maintenance_email_fields_accepts_valid_payload(self):
        """Test valid payloads round-trip through explicit schema validation."""
        fields = validate_maintenance_email_fields({
            "vendor_ticket_id": "NCC-24173",
            "intent_confidence": 4,
            "impact_confidence": 2,
        })

        assert fields.vendor_ticket_id == "NCC-24173"
        assert fields.intent_confidence == 4
        assert fields.impact_confidence == 2

    def test_validate_maintenance_email_fields_rejects_out_of_range_confidence(self):
        """Test invalid confidence values fail explicit schema validation."""
        with pytest.raises(ValidationError):
            validate_maintenance_email_fields({
                "intent_confidence": 88,
                "impact_confidence": 20,
            })
