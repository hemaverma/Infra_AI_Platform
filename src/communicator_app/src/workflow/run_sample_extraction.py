"""Run the communicator extraction flow against local JSON samples."""

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from workflow.executors.extract import FieldExtractionExecutor
from workflow.executors.extraction.prompt_input import (
    build_extraction_prompt_input,
    configured_extraction_prompt_email_format,
    extraction_candidate_hints_enabled,
)
from workflow.executors.extraction.prompty import render_full_extraction_prompt
from workflow.executors.preprocess import _clean_email_body
from workflow.messages import AttachmentContent, ExtractedFields, SafeEmail

_SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
_LOCAL_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "local.settings.json"
_DEFAULT_EMAIL_SAMPLE = _SAMPLES_DIR / "email.json"
_DEFAULT_ENVELOPE_SAMPLE = _SAMPLES_DIR / "workflow_queue_email_received.json"
_DEFAULT_LOG_LEVEL = "INFO"


class _RecordingContext:
    def __init__(self) -> None:
        self.messages: list[ExtractedFields] = []

    async def send_message(self, message: ExtractedFields) -> None:
        self.messages.append(message)


def load_local_settings_values(local_settings_path: Path = _LOCAL_SETTINGS_PATH) -> None:
    """Load Azure Functions local settings into the process environment.

    Existing environment variables win so shell-exported values still take precedence.
    """
    if not local_settings_path.exists():
        return

    payload = json.loads(local_settings_path.read_text(encoding="utf-8"))
    values = payload.get("Values", {})
    for key, value in values.items():
        if key.startswith("_comment"):
            continue
        os.environ.setdefault(key, str(value))


def configure_sample_logging(log_level: str = _DEFAULT_LOG_LEVEL) -> None:
    """Enable readable console logging for local prompt and extraction debugging."""
    resolved_level = getattr(logging, log_level.upper(), logging.INFO)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("workflow").setLevel(resolved_level)


def _load_sample_attachments(
    attachment_values: list[Any],
    email_sample_path: Path,
) -> list[AttachmentContent]:
    """Materialize only CSV attachments so sample runs match preprocess behavior."""
    attachments: list[AttachmentContent] = []
    sample_dir = email_sample_path.parent
    for value in attachment_values:
        if isinstance(value, dict):
            attachment = AttachmentContent.model_validate(value)
            if attachment.filename.strip().lower().endswith(".csv"):
                attachments.append(attachment)
            continue

        reference = str(value)
        if not Path(reference).name.lower().endswith(".csv"):
            continue

        candidate_paths = [Path(reference)]
        if not Path(reference).is_absolute():
            candidate_paths.extend([
                sample_dir / reference,
                _SAMPLES_DIR / reference,
                _SAMPLES_DIR / Path(reference).name,
            ])

        resolved = next((path for path in candidate_paths if path.exists() and path.is_file()), None)
        attachments.append(AttachmentContent(
            filename=Path(reference).name,
            content=resolved.read_text(encoding="utf-8-sig", errors="replace") if resolved else "",
        ))
    return attachments


def load_sample_safe_email(
    email_sample_path: Path = _DEFAULT_EMAIL_SAMPLE,
    envelope_sample_path: Path | None = _DEFAULT_ENVELOPE_SAMPLE,
) -> SafeEmail:
    """Build a preprocessed SafeEmail from local JSON samples."""
    email_payload = json.loads(email_sample_path.read_text(encoding="utf-8"))
    envelope_payload = {}
    if envelope_sample_path is not None:
        envelope_payload = json.loads(envelope_sample_path.read_text(encoding="utf-8"))

    received_at = envelope_payload.get("receivedAt") or email_payload.get("receivedAt")
    if not received_at:
        raise ValueError("sample payload must include receivedAt")

    return SafeEmail(
        workflow_instance_id=(
            envelope_payload.get("workflowInstanceId")
            or email_payload.get("workflowInstanceId")
            or "sample-workflow"
        ),
        internet_message_id=(
            envelope_payload.get("internetMessageId")
            or email_payload.get("internetMessageId")
            or "sample-message"
        ),
        received_at=datetime.fromisoformat(received_at.replace("Z", "+00:00")),
        storage_prefix=envelope_payload.get("storagePrefix", ""),
        subject=email_payload.get("subject", ""),
        sender=email_payload.get("senderEmail", ""),
        body=_clean_email_body(email_payload.get("body", "")),
        attachments=_load_sample_attachments(list(email_payload.get("attachments", []) or []), email_sample_path),
        notes={
            "storage_prefix": envelope_payload.get("storagePrefix", ""),
            "email_sample_path": str(email_sample_path),
        },
    )


async def run_extraction(safe_email: SafeEmail) -> ExtractedFields:
    """Run the extraction executor against a SafeEmail sample."""
    context = _RecordingContext()
    executor = FieldExtractionExecutor()
    await executor.extract(safe_email, cast(Any, context))
    if not context.messages:
        raise RuntimeError("extraction executor produced no output")
    return context.messages[-1]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run communicator extraction against local JSON samples.")
    parser.add_argument(
        "--email-sample",
        default=str(_DEFAULT_EMAIL_SAMPLE),
        help="Path to a staged email JSON file.",
    )
    parser.add_argument(
        "--envelope-sample",
        default=str(_DEFAULT_ENVELOPE_SAMPLE),
        help="Path to a workflow_queue_email_received JSON file.",
    )
    parser.add_argument(
        "--prompt-only",
        action="store_true",
        help="Print the rendered extraction prompt instead of running the executor.",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("SAMPLE_LOG_LEVEL", _DEFAULT_LOG_LEVEL),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        type=str.upper,
        help="Set the workflow logger verbosity for this sample run.",
    )
    parser.add_argument(
        "--include-candidate-hints",
        action="store_true",
        default=extraction_candidate_hints_enabled(),
        help="Inject deterministic candidate hints into the extraction prompt.",
    )
    parser.add_argument(
        "--prompt-email-format",
        default=configured_extraction_prompt_email_format(),
        choices=["markdown", "xml"],
        help="Render the extraction email packet as markdown or xml.",
    )
    return parser


def main() -> None:
    """Run the JSON-sample extraction helper from the command line."""
    load_local_settings_values()
    args = _build_parser().parse_args()
    configure_sample_logging(args.log_level)
    os.environ["ENABLE_EXTRACTION_CANDIDATE_HINTS"] = "true" if args.include_candidate_hints else "false"
    os.environ["EXTRACTION_PROMPT_EMAIL_FORMAT"] = args.prompt_email_format
    envelope_sample = None if args.envelope_sample.lower() in ("", "none") else Path(args.envelope_sample)
    safe_email = load_sample_safe_email(Path(args.email_sample), envelope_sample)

    if args.prompt_only:
        print(
            render_full_extraction_prompt(
                build_extraction_prompt_input(
                    safe_email,
                    include_candidate_hints=args.include_candidate_hints,
                    prompt_email_format=args.prompt_email_format,
                )
            )
        )
        return

    result = asyncio.run(run_extraction(safe_email))
    print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
