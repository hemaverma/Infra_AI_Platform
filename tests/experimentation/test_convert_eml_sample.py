"""Tests for local .eml to sample fixture conversion."""

import json
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

import experimentation.sample_conversion as sample_conversion
from experimentation.sample_conversion import convert_eml_to_samples


def test_convert_eml_to_samples_strips_message_id_whitespace(tmp_path: Path):
    """Test converted payloads normalize message ids copied from Outlook headers."""
    message = EmailMessage()
    message["From"] = "Transport Vendor Maintenance Engineering <transport_vendor_maintenance@operator.example>"
    message["To"] = "NExT_analysis <NExT_analysis@operator.example>"
    message["Subject"] = "FW: test"
    message["Date"] = format_datetime(datetime(2026, 5, 7, 16, 11, 58, tzinfo=timezone.utc))
    message["Message-ID"] = "\t<outer-message@example.com>"
    message.set_content("plain text")

    eml_path = tmp_path / "message.eml"
    eml_path.write_bytes(message.as_bytes())

    outputs = convert_eml_to_samples(eml_path, tmp_path / "sample")
    email_payload = json.loads(outputs["email_sample"].read_text(encoding="utf-8"))

    assert email_payload["internetMessageId"] == "<outer-message@example.com>"


def test_convert_eml_to_samples_writes_json_and_attachment(tmp_path: Path):
    """Test converting a forwarded .eml file into local communicator sample fixtures."""
    message = EmailMessage()
    message["From"] = "Transport Vendor Maintenance Engineering <transport_vendor_maintenance@operator.example>"
    message["To"] = "NExT_analysis <NExT_analysis@operator.example>"
    message["Subject"] = "FW: Vendor Maintenance Notification - Change Request #CR-0001"
    message["Date"] = format_datetime(datetime(2026, 5, 7, 16, 11, 58, tzinfo=timezone.utc))
    message["Message-ID"] = "<outer-message@example.com>"
    message.set_content(
        "________________________________________\n"
        "From: noreply@vendor.example <noreply@vendor.example>\n"
        "Sent: Thursday, May 7, 2026 11:09:03 AM (UTC-06:00) Central Time (US & Canada)\n"
        "To: Transport Vendor Maintenance Engineering\n"
        "Subject: Vendor Maintenance Notification - Change Request #CR-0001\n\n"
        "[External]\n\n"
        "Change Request #: CR-0001\n"
        "Start Date & Time: 05/19/26 04:01:00 UTC\n"
        "End Date & Time: 05/19/26 10:00:00 UTC\n"
    )
    message.add_attachment(
        b"Circuit ID,Severity\nSYN-NYC-001,Switch to Protect\n",
        maintype="text",
        subtype="csv",
        filename="circuits.csv",
    )

    eml_path = tmp_path / "vendor_notice.eml"
    eml_path.write_bytes(message.as_bytes())

    outputs = convert_eml_to_samples(eml_path, tmp_path / "sample")

    email_payload = json.loads(outputs["email_sample"].read_text(encoding="utf-8"))
    envelope_payload = json.loads(outputs["envelope_sample"].read_text(encoding="utf-8"))

    assert outputs["email_sample"].name == "email.json"
    assert email_payload["senderEmail"] == "noreply@vendor.example"
    assert email_payload["subject"] == "Vendor Maintenance Notification - Change Request #CR-0001"
    assert "Change Request #: CR-0001" in email_payload["body"]
    assert email_payload["attachments"] == ["attachments/circuits.csv"]
    assert (outputs["email_sample"].parent / email_payload["attachments"][0]).exists()
    assert envelope_payload["eventType"] == "email.received"
    assert envelope_payload["internetMessageId"] == "<outer-message@example.com>"


def test_convert_eml_to_samples_extracts_sender_when_parseaddr_rejects_header(
    tmp_path: Path, monkeypatch
):
    """Test sender fallback parsing when parseaddr rejects a forwarded header."""
    message = EmailMessage()
    message["From"] = "Transport Vendor Maintenance Engineering <transport_vendor_maintenance@operator.example>"
    message["To"] = "NExT_analysis <NExT_analysis@operator.example>"
    message["Subject"] = "FW: test"
    message["Date"] = format_datetime(datetime(2026, 5, 7, 16, 11, 58, tzinfo=timezone.utc))
    message.set_content(
        "________________________________________\n"
        "From: noreply@vendor.example <noreply@vendor.example>\n"
        "Sent: Thursday, May 7, 2026 11:09:03 AM (UTC-06:00) Central Time (US & Canada)\n"
        "To: Transport Vendor Maintenance Engineering\n"
        "Subject: test\n\n"
        "body\n"
    )

    monkeypatch.setattr(sample_conversion, "parseaddr", lambda _: ("", ""))

    eml_path = tmp_path / "fallback_sender.eml"
    eml_path.write_bytes(message.as_bytes())

    outputs = convert_eml_to_samples(eml_path, tmp_path / "sample")
    email_payload = json.loads(outputs["email_sample"].read_text(encoding="utf-8"))

    assert email_payload["senderEmail"] == "noreply@vendor.example"


def test_convert_eml_to_samples_prefers_html_body_when_present(tmp_path: Path):
    """Test HTML bodies are preserved when the message includes a text/html part."""
    message = EmailMessage()
    message["From"] = "Vendor <vendor@example.com>"
    message["To"] = "NExT_analysis <NExT_analysis@operator.example>"
    message["Subject"] = "Maintenance Notification"
    message["Date"] = format_datetime(datetime(2026, 5, 7, 16, 11, 58, tzinfo=timezone.utc))
    message["Message-ID"] = "<html-message@example.com>"
    message.set_content("plain body")
    message.add_alternative("<html><body><p>html body</p></body></html>", subtype="html")

    eml_path = tmp_path / "html_notice.eml"
    eml_path.write_bytes(message.as_bytes())

    outputs = convert_eml_to_samples(eml_path, tmp_path / "sample")
    email_payload = json.loads(outputs["email_sample"].read_text(encoding="utf-8"))

    assert email_payload["body"] == "<html><body><p>html body</p></body></html>"
