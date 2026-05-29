"""Convert raw .eml files into local communicator sample fixtures."""

import argparse
import json
import os
import re
from datetime import timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

_COMPONENT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUTPUT_ROOT = _COMPONENT_ROOT / "output" / "converted_samples"
_FORWARDED_HEADER_PATTERN = re.compile(
    r"[-_]{10,}\s*\n"
    r"From:\s*(?P<from>.+?)\n"
    r"Sent:\s*(?P<sent>.+?)\n"
    r"To:\s*(?P<to>.+?)\n"
    r"(?:Cc:\s*(?P<cc>.+?)\n)?"
    r"Subject:\s*(?P<subject>.+?)\n",
    re.DOTALL,
)
_EMAIL_IN_BRACKETS_PATTERN = re.compile(r"<\s*(?P<email>[^<>\s]+@[^<>\s]+)\s*>")
_EMAIL_ADDRESS_PATTERN = re.compile(r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def convert_eml_to_samples(eml_path: Path, output_dir: Path) -> dict[str, Path]:
    """Create local sample JSON files and extracted attachments from an .eml file.

    Args:
        eml_path: Path to the source .eml message.
        output_dir: Folder where staged sample artifacts should be written.

    Returns:
        Mapping of artifact labels to their output paths.
    """
    message = _load_message(eml_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    attachments_dir = output_dir / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)

    plain_body = _extract_body_part(message, "text/plain")
    html_body = _extract_body_part(message, "text/html")
    forwarded = _extract_forwarded_email(plain_body)
    subject = forwarded.get("subject") or _strip_forward_prefix(message.get("Subject", ""))
    sender_header = forwarded.get("from") or message.get("From", "")
    sender_email = _normalize_sender_email(sender_header)
    received_at = _normalize_datetime(message.get("Date"))
    internet_message_id = (message.get("Message-ID") or f"<{eml_path.stem}@sample.local>").strip()
    workflow_instance_id = f"sample-{_slugify(eml_path.stem)}"
    attachment_paths = _write_attachments(message, attachments_dir)
    body = html_body.strip() or forwarded.get("body") or plain_body.strip()

    email_payload = {
        "internetMessageId": internet_message_id,
        "workflowInstanceId": workflow_instance_id,
        "receivedAt": received_at,
        "senderEmail": sender_email,
        "subject": subject,
        "body": body,
        "attachments": [path.relative_to(output_dir).as_posix() for path in attachment_paths],
    }
    envelope_payload = {
        "queueName": os.environ.get("WORKFLOW_QUEUE_NAME", "workflow-queue"),
        "eventType": "email.received",
        "workflowInstanceId": workflow_instance_id,
        "internetMessageId": internet_message_id,
        "storagePrefix": f"inbound/{workflow_instance_id}/",
        "checkpointId": None,
        "receivedAt": received_at,
    }

    email_path = output_dir / "email.json"
    envelope_path = output_dir / "workflow_queue_email_received.json"
    email_path.write_text(json.dumps(email_payload, indent=2) + "\n", encoding="utf-8")
    envelope_path.write_text(json.dumps(envelope_payload, indent=2) + "\n", encoding="utf-8")

    return {
        "email_sample": email_path,
        "envelope_sample": envelope_path,
        "attachments_dir": attachments_dir,
    }


def default_output_dir_for_eml(eml_path: Path) -> Path:
    """Return the default output folder for a converted sample email."""
    return _DEFAULT_OUTPUT_ROOT / _slugify(eml_path.stem)


def _load_message(eml_path: Path) -> EmailMessage:
    """Parse an .eml file into an EmailMessage object.

    Args:
        eml_path: Path to the source .eml file.

    Returns:
        Parsed email message.
    """
    with eml_path.open("rb") as handle:
        return BytesParser(policy=policy.default).parse(handle)


def _extract_body_part(message: EmailMessage, content_type: str) -> str:
    """Return the first non-attachment body part that matches the requested content type.

    Args:
        message: Parsed email message.
        content_type: MIME content type to extract.

    Returns:
        Extracted body text, or an empty string if no matching part exists.
    """
    for part in message.walk():
        disposition = (part.get_content_disposition() or "").lower()
        if part.get_content_type() == content_type and disposition != "attachment":
            content = part.get_content()
            if isinstance(content, str):
                return content.strip()

            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or "utf-8"
            if isinstance(payload, bytes):
                return payload.decode(charset, errors="replace").strip()

            return str(payload or "").strip()
    return ""


def _extract_forwarded_email(body: str) -> dict[str, str]:
    """Extract forwarded-email metadata from a plain-text wrapper body.

    Args:
        body: Plain-text email body.

    Returns:
        Dictionary containing forwarded metadata when the wrapper is found.
    """
    match = _FORWARDED_HEADER_PATTERN.search(body)
    if not match:
        return {}

    inner_body = body[match.end():].strip()
    inner_body = re.sub(r"\[External\]\s*", "", inner_body).strip()
    return {
        "from": match.group("from").strip(),
        "sent": match.group("sent").strip(),
        "subject": match.group("subject").strip(),
        "body": inner_body,
    }


def _normalize_sender_email(sender_header: str) -> str:
    """Normalize a sender header into a plain email address.

    Args:
        sender_header: Raw sender header string.

    Returns:
        Best-effort sender email address.
    """
    parsed_email = parseaddr(sender_header)[1].strip()
    if parsed_email:
        return parsed_email

    bracket_match = _EMAIL_IN_BRACKETS_PATTERN.search(sender_header)
    if bracket_match:
        return bracket_match.group("email")

    email_match = _EMAIL_ADDRESS_PATTERN.search(sender_header)
    if email_match:
        return email_match.group(0)

    return sender_header.strip()


def _write_attachments(message: EmailMessage, attachments_dir: Path) -> list[Path]:
    """Write message attachments to disk.

    Args:
        message: Parsed email message.
        attachments_dir: Destination directory for extracted attachments.

    Returns:
        Absolute paths to the written attachment files.
    """
    written_paths: list[Path] = []
    for index, part in enumerate(message.iter_attachments(), start=1):
        filename = part.get_filename() or f"attachment_{index}"
        target = attachments_dir / filename
        payload = part.get_payload(decode=True)
        if isinstance(payload, bytes):
            target.write_bytes(payload)
        else:
            target.write_bytes(str(payload or "").encode("utf-8"))
        written_paths.append(target.resolve())
    return written_paths


def _normalize_datetime(value: str | None) -> str:
    """Normalize an RFC 2822 timestamp into UTC ISO 8601.

    Args:
        value: Raw email date header value.

    Returns:
        UTC timestamp string with a trailing Z.
    """
    if not value:
        return "1970-01-01T00:00:00Z"
    parsed = parsedate_to_datetime(value)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _slugify(value: str) -> str:
    """Normalize a string into a filesystem-safe slug.

    Args:
        value: Input string.

    Returns:
        Lowercase slug containing only letters, numbers, and hyphens.
    """
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "sample"


def _strip_forward_prefix(subject: str) -> str:
    """Remove a leading forward prefix from a subject line.

    Args:
        subject: Raw subject line.

    Returns:
        Subject without a leading FW/FWD prefix.
    """
    return re.sub(r"^(?:fw|fwd):\s*", "", subject, flags=re.IGNORECASE)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert a raw .eml file into communicator sample fixtures.")
    parser.add_argument("eml_path", help="Path to the source .eml file.")
    parser.add_argument(
        "--output-dir",
        help=(
            "Directory to write sample fixtures into. "
            "Defaults to experimentation/output/converted_samples/<eml-stem>/"
        ),
    )
    return parser


def main() -> None:
    """Convert a source .eml file into local communicator sample fixtures."""
    args = _build_parser().parse_args()
    eml_path = Path(args.eml_path)
    output_dir = Path(args.output_dir) if args.output_dir else default_output_dir_for_eml(eml_path)
    outputs = convert_eml_to_samples(eml_path, output_dir)
    print(json.dumps({key: str(value) for key, value in outputs.items()}, indent=2))


if __name__ == "__main__":
    main()
