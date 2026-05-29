"""Typed workflow payloads for experimentation helpers.

These types document the small JSON-serializable contracts shared across the
experimentation package without changing the runtime behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypedDict

SourceType = Literal["eml", "staged_email_json"]


class PreparedSample(TypedDict):
    """Prepared staged-sample input for a comparison run."""

    source_type: SourceType
    source_path: Path
    email_sample_path: Path
    envelope_sample_path: Path | None
    sample_dir: Path


class ExtractionErrorPayload(TypedDict):
    """Serialized extraction failure details."""

    error_type: str
    message: str
    transient: str
    attempt_count: str
    max_attempts: str


class ComparisonExperiment(TypedDict):
    """Settings that define one extraction comparison run."""

    llm_model: str | None
    prompt_email_format: str
    candidate_hints_enabled: bool
    log_level: str
    extraction_retry_attempts: int
    extraction_retry_delay_seconds: float


class ComparisonResult(TypedDict):
    """Serialized result for one compared sample."""

    source_type: SourceType
    source_path: str
    source_eml: str | None
    source_email_sample: str | None
    sample_dir: str
    email_sample_path: str
    envelope_sample_path: str | None
    extraction_attempt_count: int
    formatted_email_path: str
    extraction_path: str | None
    extraction_error_path: str | None
    converted_email: dict[str, Any]
    converted_envelope: dict[str, Any]
    extraction: dict[str, Any] | None
    extraction_error: ExtractionErrorPayload | None


class ComparisonReport(TypedDict):
    """Aggregate extraction comparison report."""

    email_count: int
    source_glob: str | None
    experiment: ComparisonExperiment
    results: list[ComparisonResult]


class EvaluationTarget(TypedDict):
    """Reviewed target paired with its staged email sample."""

    ground_truth_path: Path
    email_sample_path: Path
    candidate: dict[str, Any]


class FieldComparison(TypedDict, total=False):
    """Comparison payload for one reviewed field."""

    expected: Any
    actual: Any
    exact_match: bool
    error_type: str
    precision: float
    recall: float
    f1: float
    missing: list[Any]
    unexpected: list[Any]


class EvaluationSampleResult(TypedDict):
    """Evaluation result for one ground-truth sample."""

    ground_truth_path: str
    email_sample_path: str
    sample_dir: str | None
    status: str
    extraction_attempt_count: int
    expected: dict[str, Any]
    actual: dict[str, Any] | None
    field_results: dict[str, FieldComparison]
    sample_exact_match: bool
    extraction_error: ExtractionErrorPayload | None


class FailurePattern(TypedDict):
    """Frequent field-level error pattern."""

    field: str
    error_type: str
    count: int


class EvaluationSummary(TypedDict):
    """Aggregate evaluation metrics across reviewed samples."""

    exact_match_samples: int
    sample_exact_match_rate: float
    samples_with_extraction_errors: int
    field_metrics: dict[str, Any]
    common_failure_patterns: list[FailurePattern]


class EvaluationReport(TypedDict):
    """Serialized evaluation report."""

    run_id: str
    created_at: str
    sample_count: int
    output_root: str
    comparison_report_path: str
    experiment: dict[str, Any]
    summary: EvaluationSummary
    samples: list[EvaluationSampleResult]
    evaluation_path: str
