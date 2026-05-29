"""Extraction orchestration helpers for experimentation workflows."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

from experimentation.models import ComparisonReport, ComparisonResult, PreparedSample
from experimentation.paths import REPO_ROOT

COMMUNICATOR_APP_SRC = REPO_ROOT / "src" / "communicator_app" / "src"
DEFAULT_STAGED_SAMPLE_GLOB = "src/experimentation/data/blob_seed_samples/**/email.json"
DEFAULT_EXTRACTION_RETRY_ATTEMPTS = 3
DEFAULT_EXTRACTION_RETRY_DELAY_SECONDS = 1.0
TRANSIENT_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})
EMAIL_SAMPLE_FILE_NAMES = frozenset({"email.json", "email_staging_fixture.json"})

logger = logging.getLogger(__name__)


class ExtractionRunError(RuntimeError):
    """Wrap an extraction failure together with the total attempts consumed."""

    def __init__(self, original_error: Exception, attempts_used: int) -> None:
        """Store the original exception and the number of attempts consumed."""
        super().__init__(str(original_error))
        self.original_error = original_error
        self.attempts_used = attempts_used


def compare_staged_extractions(
    email_sample_paths: list[Path],
    output_root: Path,
    *,
    include_candidate_hints: bool = False,
    prompt_email_format: str = "markdown",
    log_level: str = "INFO",
    extraction_retry_attempts: int = DEFAULT_EXTRACTION_RETRY_ATTEMPTS,
    extraction_retry_delay_seconds: float = DEFAULT_EXTRACTION_RETRY_DELAY_SECONDS,
    workflow_runner_loader: Callable[[], Any] | None = None,
    sleep_func: Callable[[float], None] = time.sleep,
) -> ComparisonReport:
    """Run the communicator extractor directly against staged email JSON samples."""
    return _compare_prepared_samples(
        _prepare_staged_samples(email_sample_paths, output_root),
        output_root,
        source_glob=DEFAULT_STAGED_SAMPLE_GLOB,
        include_candidate_hints=include_candidate_hints,
        prompt_email_format=prompt_email_format,
        log_level=log_level,
        extraction_retry_attempts=extraction_retry_attempts,
        extraction_retry_delay_seconds=extraction_retry_delay_seconds,
        workflow_runner_loader=workflow_runner_loader or load_workflow_runner,
        sleep_func=sleep_func,
    )


def discover_default_staged_email_paths(repo_root: Path = REPO_ROOT) -> list[Path]:
    """Return the default staged email JSON inputs used for experimentation comparisons."""
    return sorted(path for path in repo_root.glob(DEFAULT_STAGED_SAMPLE_GLOB) if is_email_sample_path(path))


def load_workflow_runner() -> Any:
    """Load the communicator sample extraction runner."""
    if str(COMMUNICATOR_APP_SRC) not in sys.path:
        sys.path.insert(0, str(COMMUNICATOR_APP_SRC))

    import workflow.run_sample_extraction as workflow_runner

    return workflow_runner


def is_email_sample_path(path: Path) -> bool:
    """Return True when a path points at a staged email sample JSON file."""
    return path.suffix.lower() == ".json" and path.name in EMAIL_SAMPLE_FILE_NAMES


def _configure_workflow_runner(
    *,
    log_level: str,
    include_candidate_hints: bool,
    prompt_email_format: str,
    workflow_runner_loader: Callable[[], Any],
) -> Any:
    """Load and configure the communicator sample runner for extraction comparisons."""
    workflow_runner = workflow_runner_loader()
    workflow_runner.load_local_settings_values()
    workflow_runner.configure_sample_logging(log_level)
    os.environ["ENABLE_EXTRACTION_CANDIDATE_HINTS"] = "true" if include_candidate_hints else "false"
    os.environ["EXTRACTION_PROMPT_EMAIL_FORMAT"] = prompt_email_format
    return workflow_runner


def _prepare_staged_samples(email_sample_paths: list[Path], output_root: Path) -> list[PreparedSample]:
    """Return staged-sample records ready for extraction comparison."""
    return [
        {
            "source_type": "staged_email_json",
            "source_path": email_sample_path,
            "email_sample_path": email_sample_path,
            "envelope_sample_path": _discover_envelope_sample_path(email_sample_path),
            "sample_dir": output_root / _slugify(email_sample_path.parent.name),
        }
        for email_sample_path in email_sample_paths
    ]


def _compare_prepared_samples(
    prepared_samples: list[PreparedSample],
    output_root: Path,
    *,
    source_glob: str | None,
    include_candidate_hints: bool,
    prompt_email_format: str,
    log_level: str,
    extraction_retry_attempts: int,
    extraction_retry_delay_seconds: float,
    workflow_runner_loader: Callable[[], Any],
    sleep_func: Callable[[float], None],
) -> ComparisonReport:
    """Run extraction comparison for already-prepared staged-sample records."""
    workflow_runner = _configure_workflow_runner(
        log_level=log_level,
        include_candidate_hints=include_candidate_hints,
        prompt_email_format=prompt_email_format,
        workflow_runner_loader=workflow_runner_loader,
    )
    experiment = _build_experiment_metadata(
        prompt_email_format=prompt_email_format,
        include_candidate_hints=include_candidate_hints,
        log_level=log_level,
        extraction_retry_attempts=extraction_retry_attempts,
        extraction_retry_delay_seconds=extraction_retry_delay_seconds,
    )
    results = [
        _compare_staged_sample(
            workflow_runner,
            email_sample_path=prepared_sample["email_sample_path"],
            envelope_sample_path=prepared_sample["envelope_sample_path"],
            sample_dir=prepared_sample["sample_dir"],
            source_type=prepared_sample["source_type"],
            source_path=prepared_sample["source_path"],
            include_candidate_hints=include_candidate_hints,
            prompt_email_format=prompt_email_format,
            extraction_retry_attempts=extraction_retry_attempts,
            extraction_retry_delay_seconds=extraction_retry_delay_seconds,
            sleep_func=sleep_func,
        )
        for prepared_sample in prepared_samples
    ]
    return _write_report(output_root, results, source_glob=source_glob, experiment=experiment)


def _compare_staged_sample(
    workflow_runner: Any,
    *,
    email_sample_path: Path,
    envelope_sample_path: Path | None,
    sample_dir: Path,
    source_type: str,
    source_path: Path,
    include_candidate_hints: bool,
    prompt_email_format: str,
    extraction_retry_attempts: int,
    extraction_retry_delay_seconds: float,
    sleep_func: Callable[[float], None],
) -> ComparisonResult:
    """Run extraction for one staged sample and write comparison artifacts."""
    sample_dir.mkdir(parents=True, exist_ok=True)
    safe_email = workflow_runner.load_sample_safe_email(email_sample_path, envelope_sample_path)
    formatted_email = workflow_runner.build_extraction_prompt_input(
        safe_email,
        include_candidate_hints=include_candidate_hints,
        prompt_email_format=prompt_email_format,
    )

    converted_payload = json.loads(email_sample_path.read_text(encoding="utf-8"))
    converted_envelope = {}
    if envelope_sample_path is not None and envelope_sample_path.exists():
        converted_envelope = json.loads(envelope_sample_path.read_text(encoding="utf-8"))

    formatted_email_path = sample_dir / "formatted_email.txt"
    extraction_path = sample_dir / "extraction.json"
    extraction_error_path = sample_dir / "extraction_error.json"

    formatted_email_path.write_text(formatted_email + "\n", encoding="utf-8")
    extraction_error: dict[str, str] | None = None
    extraction_attempt_count = 0
    try:
        extracted, extraction_attempt_count = _run_extraction_with_retries(
            workflow_runner,
            safe_email,
            max_attempts=extraction_retry_attempts,
            base_delay_seconds=extraction_retry_delay_seconds,
            sleep_func=sleep_func,
        )
        extracted_payload = extracted.model_dump(mode="json")
        extraction_path.write_text(
            json.dumps(extracted_payload, indent=2) + "\n",
            encoding="utf-8",
        )
        if extraction_error_path.exists():
            extraction_error_path.unlink()
    except ExtractionRunError as exc:
        extracted_payload = None
        original_error = exc.original_error
        extraction_attempt_count = exc.attempts_used
        extraction_error = {
            "error_type": type(original_error).__name__,
            "message": str(original_error),
            "transient": "true" if _is_transient_extraction_error(original_error) else "false",
            "attempt_count": str(extraction_attempt_count),
            "max_attempts": str(max(1, extraction_retry_attempts)),
        }
        extraction_error_path.write_text(
            json.dumps(extraction_error, indent=2) + "\n",
            encoding="utf-8",
        )

    sample_result: ComparisonResult = {
        "source_type": source_type,
        "source_path": str(source_path),
        "source_eml": str(source_path) if source_type == "eml" else None,
        "source_email_sample": str(source_path) if source_type == "staged_email_json" else None,
        "sample_dir": str(sample_dir),
        "email_sample_path": str(email_sample_path),
        "envelope_sample_path": str(envelope_sample_path) if envelope_sample_path is not None else None,
        "extraction_attempt_count": extraction_attempt_count,
        "formatted_email_path": str(formatted_email_path),
        "extraction_path": str(extraction_path) if extracted_payload is not None else None,
        "extraction_error_path": str(extraction_error_path) if extraction_error is not None else None,
        "converted_email": converted_payload,
        "converted_envelope": converted_envelope,
        "extraction": extracted_payload,
        "extraction_error": extraction_error,
    }
    (sample_dir / "comparison.json").write_text(
        json.dumps(sample_result, indent=2) + "\n",
        encoding="utf-8",
    )
    return sample_result


def _discover_envelope_sample_path(email_sample_path: Path) -> Path | None:
    """Return the sibling workflow queue envelope for a staged email sample when present."""
    candidate = email_sample_path.parent / "workflow_queue_email_received.json"
    if candidate.exists():
        return candidate
    return None


def _write_report(
    output_root: Path,
    results: list[ComparisonResult],
    *,
    source_glob: str | None,
    experiment: dict[str, Any],
) -> ComparisonReport:
    """Write the aggregate comparison report and return its payload."""
    output_root.mkdir(parents=True, exist_ok=True)
    report: ComparisonReport = {
        "email_count": len(results),
        "source_glob": source_glob,
        "experiment": experiment,
        "results": results,
    }
    (output_root / "comparison_report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def _build_experiment_metadata(
    *,
    prompt_email_format: str,
    include_candidate_hints: bool,
    log_level: str,
    extraction_retry_attempts: int,
    extraction_retry_delay_seconds: float,
) -> dict[str, Any]:
    """Capture the settings that define one extraction comparison run."""
    return {
        "llm_model": os.getenv("AZURE_OPENAI_MODEL", "").strip() or None,
        "prompt_email_format": prompt_email_format,
        "candidate_hints_enabled": include_candidate_hints,
        "log_level": log_level,
        "extraction_retry_attempts": extraction_retry_attempts,
        "extraction_retry_delay_seconds": extraction_retry_delay_seconds,
    }


def _run_extraction_with_retries(
    workflow_runner: Any,
    safe_email: Any,
    *,
    max_attempts: int,
    base_delay_seconds: float,
    sleep_func: Callable[[float], None],
) -> tuple[Any, int]:
    """Run extraction with bounded retries for transient Azure OpenAI failures."""
    attempts = max(1, max_attempts)
    delay_seconds = max(0.0, base_delay_seconds)

    for attempt in range(1, attempts + 1):
        try:
            return asyncio.run(workflow_runner.run_extraction(safe_email)), attempt
        except Exception as exc:
            should_retry = attempt < attempts and _is_transient_extraction_error(exc)
            if not should_retry:
                raise ExtractionRunError(exc, attempt) from exc
            backoff_seconds = delay_seconds * (2 ** (attempt - 1))
            logger.warning(
                "extraction retry: transient extraction failure on attempt %d/%d (%s: %s); retrying in %.1fs",
                attempt,
                attempts,
                type(exc).__name__,
                exc,
                backoff_seconds,
            )
            sleep_func(backoff_seconds)

    raise RuntimeError("unreachable retry loop exit")


def _is_transient_extraction_error(exc: Exception) -> bool:
    """Return True when an extraction error looks transient and retryable."""
    transient_fragments = (
        "connection error",
        "timed out",
        "timeout",
        "rate limit",
        "too many requests",
        "temporarily unavailable",
        "server error",
        "bad gateway",
        "gateway timeout",
        "service unavailable",
        "connection aborted",
        "connection reset",
        "invalid http request received",
    )

    for current in _iter_exception_chain(exc):
        status_code = getattr(current, "status_code", None)
        if isinstance(status_code, int) and status_code in TRANSIENT_STATUS_CODES:
            return True

        class_name = type(current).__name__.lower()
        if class_name in {
            "apiconnectionerror",
            "apitimeouterror",
            "ratelimiterror",
            "internalservererror",
            "serviceunavailableerror",
        }:
            return True

        message = str(current).lower()
        if any(fragment in message for fragment in transient_fragments):
            return True

    return False


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    """Flatten wrapped exception chains so retry classification sees root causes."""
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    chain: list[BaseException] = []

    while pending:
        current = pending.pop()
        identifier = id(current)
        if identifier in seen:
            continue
        seen.add(identifier)
        chain.append(current)

        cause = getattr(current, "__cause__", None)
        if isinstance(cause, BaseException):
            pending.append(cause)

        context = getattr(current, "__context__", None)
        if isinstance(context, BaseException):
            pending.append(context)

        inner_exception = getattr(current, "inner_exception", None)
        if isinstance(inner_exception, BaseException):
            pending.append(inner_exception)

        for arg in getattr(current, "args", ()):  # agent_framework stores inner exceptions in args
            if isinstance(arg, BaseException):
                pending.append(arg)

    return chain


def _slugify(value: str) -> str:
    """Normalize a string into a filesystem-safe slug."""
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "sample"
