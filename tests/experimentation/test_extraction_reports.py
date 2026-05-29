"""Tests for staged extraction comparison artifacts."""

import json
from pathlib import Path

import experimentation.extraction as extraction_module

_SAMPLE_EMAIL_PAYLOAD = {
    "internetMessageId": "<sample@example.com>",
    "workflowInstanceId": "wf-sample",
    "receivedAt": "2026-05-07T16:11:58Z",
    "senderEmail": "noreply@example.com",
    "subject": "Sample",
    "body": "Body",
    "attachments": [],
}
_SAMPLE_ENVELOPE_PAYLOAD = {
    "workflowInstanceId": "wf-sample",
    "internetMessageId": "<sample@example.com>",
    "storagePrefix": "inbound/wf-sample/",
    "receivedAt": "2026-05-07T16:11:58Z",
}
_SAMPLE_EXTRACTION_FIELDS = {
    "vendor_ticket_id": "CHG000000000001",
    "assets": [{"value": "SYN-NYC-001"}],
    "windows": [{"start_raw": "05/19/26 04:01:00 UTC"}],
}


class _FakeExtracted:
    """Minimal extracted payload stub for extraction artifact tests."""

    def __init__(self, fields: dict | None = None):
        self._fields = fields or _SAMPLE_EXTRACTION_FIELDS

    def model_dump(self, mode: str = "json") -> dict:
        return {"fields": self._fields}


def _make_workflow_runner(*, failures: list[Exception] | None = None, fields: dict | None = None):
    """Build a fake workflow runner with optional failure attempts."""
    failure_sequence = list(failures or [])

    class FakeWorkflowRunner:
        run_calls = 0

        @staticmethod
        def load_local_settings_values() -> None:
            return None

        @staticmethod
        def configure_sample_logging(log_level: str) -> None:
            return None

        @staticmethod
        def load_sample_safe_email(email_path: Path, envelope_path: Path | None) -> dict[str, Path | None]:
            return {"email_path": email_path, "envelope_path": envelope_path}

        @staticmethod
        def build_extraction_prompt_input(
            safe_email,
            include_candidate_hints: bool = False,
            prompt_email_format: str = "markdown",
        ) -> str:
            return "<email_packet>formatted sample</email_packet>"

        @staticmethod
        async def run_extraction(safe_email):
            FakeWorkflowRunner.run_calls += 1
            if FakeWorkflowRunner.run_calls <= len(failure_sequence):
                raise failure_sequence[FakeWorkflowRunner.run_calls - 1]
            return _FakeExtracted(fields)

    return FakeWorkflowRunner


def _write_staged_sample(sample_dir: Path) -> Path:
    """Write a staged email sample and its queue envelope."""
    sample_dir.mkdir(parents=True, exist_ok=True)
    email_path = sample_dir / "email.json"
    envelope_path = sample_dir / "workflow_queue_email_received.json"
    email_path.write_text(json.dumps(_SAMPLE_EMAIL_PAYLOAD) + "\n", encoding="utf-8")
    envelope_path.write_text(json.dumps(_SAMPLE_ENVELOPE_PAYLOAD) + "\n", encoding="utf-8")
    return email_path


def test_compare_staged_extractions_writes_report(tmp_path: Path, monkeypatch) -> None:
    """Test staged email.json inputs are compared and reported."""
    email_path = _write_staged_sample(tmp_path / "seed-sample")
    workflow_runner = _make_workflow_runner()
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "gpt-test")

    report = extraction_module.compare_staged_extractions(
        [email_path],
        tmp_path / "output",
        workflow_runner_loader=lambda: workflow_runner(),
    )

    assert report["email_count"] == 1
    assert report["experiment"] == {
        "llm_model": "gpt-test",
        "prompt_email_format": "markdown",
        "candidate_hints_enabled": False,
        "log_level": "INFO",
        "extraction_retry_attempts": 3,
        "extraction_retry_delay_seconds": 1.0,
    }
    assert report["results"][0]["source_type"] == "staged_email_json"
    assert report["results"][0]["source_email_sample"] == str(email_path)
    assert report["results"][0]["extraction"]["fields"]["vendor_ticket_id"] == "CHG000000000001"
    assert workflow_runner.run_calls == 1
    assert (tmp_path / "output" / "seed-sample" / "formatted_email.txt").exists()
    assert (tmp_path / "output" / "seed-sample" / "comparison.json").exists()
    assert (tmp_path / "output" / "comparison_report.json").exists()


def test_compare_staged_extractions_retries_transient_failures(tmp_path: Path) -> None:
    """Test staged extraction retries transient failures before succeeding."""
    email_path = _write_staged_sample(tmp_path / "seed-sample")

    class APIConnectionError(Exception):
        """Fake transient connection error."""

    sleep_calls: list[float] = []
    workflow_runner = _make_workflow_runner(
        failures=[APIConnectionError("Connection error."), APIConnectionError("Connection error.")]
    )

    report = extraction_module.compare_staged_extractions(
        [email_path],
        tmp_path / "output",
        extraction_retry_attempts=3,
        extraction_retry_delay_seconds=0.5,
        workflow_runner_loader=lambda: workflow_runner(),
        sleep_func=sleep_calls.append,
    )

    assert report["results"][0]["extraction"]["fields"]["vendor_ticket_id"] == "CHG000000000001"
    assert report["results"][0]["extraction_attempt_count"] == 3
    assert workflow_runner.run_calls == 3
    assert sleep_calls == [0.5, 1.0]


def test_compare_staged_extractions_records_attempt_metadata_on_failure(tmp_path: Path) -> None:
    """Test failed staged extraction writes retry attempt metadata to the error artifact."""
    email_path = _write_staged_sample(tmp_path / "seed-sample")

    class APIConnectionError(Exception):
        """Fake transient connection error."""

    sleep_calls: list[float] = []
    workflow_runner = _make_workflow_runner(
        failures=[
            APIConnectionError("Connection error."),
            APIConnectionError("Connection error."),
            APIConnectionError("Connection error."),
        ]
    )

    report = extraction_module.compare_staged_extractions(
        [email_path],
        tmp_path / "output",
        extraction_retry_attempts=3,
        extraction_retry_delay_seconds=0.5,
        workflow_runner_loader=lambda: workflow_runner(),
        sleep_func=sleep_calls.append,
    )

    result = report["results"][0]
    error_payload = json.loads(Path(result["extraction_error_path"]).read_text(encoding="utf-8"))

    assert result["extraction"] is None
    assert result["extraction_attempt_count"] == 3
    assert error_payload["error_type"] == "APIConnectionError"
    assert error_payload["transient"] == "true"
    assert error_payload["attempt_count"] == "3"
    assert error_payload["max_attempts"] == "3"
    assert workflow_runner.run_calls == 3
    assert sleep_calls == [0.5, 1.0]
