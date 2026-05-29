"""Evaluation helpers for reviewed ground-truth workflows."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from experimentation.models import ComparisonResult, EvaluationSampleResult, EvaluationTarget, FailurePattern

SCALAR_FIELDS = (
    "intent",
    "vendor_name",
    "vendor_ticket_id",
    "impact_category",
)
SET_FIELDS = (
    "customer_ticket_ids",
    "circuit_ids",
)
WINDOWS_FIELD = "windows"


def dedupe_preserve_order(values: list[str]) -> list[str]:
    """Return unique normalized string values while preserving first-seen order.

    Args:
        values: Input string values.

    Returns:
        Ordered unique values.
    """
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_values.append(normalized)
    return unique_values


def project_ground_truth_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Project a full extraction field payload to the reviewed evaluation subset.

    Args:
        fields: Full extraction fields payload.

    Returns:
        Narrow evaluation field payload.
    """
    return {
        "intent": fields.get("intent", ""),
        "vendor_name": fields.get("vendor_name", ""),
        "vendor_ticket_id": fields.get("vendor_ticket_id", ""),
        "customer_ticket_ids": dedupe_preserve_order(fields.get("customer_ticket_ids", [])),
        "windows": [
            {
                "start": window.get("start", ""),
                "end": window.get("end", ""),
                "timezone_normalized": window.get("timezone_normalized", ""),
                "kind": window.get("kind", ""),
            }
            for window in fields.get("windows", [])
        ],
        "circuit_ids": dedupe_preserve_order(
            [
                asset.get("value", "").strip()
                for asset in fields.get("assets", [])
                if asset.get("type") == "circuit" and asset.get("value", "").strip()
            ]
        ),
        "impact_category": fields.get("impact_category", ""),
    }


def load_evaluation_target(ground_truth_path: Path, repo_root: Path) -> EvaluationTarget:
    """Load one reviewed ground-truth file and resolve its email sample path.

    Args:
        ground_truth_path: Path to a reviewed ground-truth JSON file.
        repo_root: Repository root used to resolve relative sample paths.

    Returns:
        Evaluation target payload with resolved email sample path.

    Raises:
        ValueError: If the ground-truth file does not contain a candidate payload.
    """
    payload = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    candidate = payload.get("candidate")
    if not isinstance(candidate, dict):
        raise ValueError(f"ground truth file must include a candidate payload: {ground_truth_path}")

    email_sample_path = _resolve_email_sample_path(
        payload.get("source", {}).get("email_sample_path"),
        ground_truth_path,
        repo_root,
    )

    return {
        "ground_truth_path": ground_truth_path,
        "email_sample_path": email_sample_path,
        "candidate": candidate,
    }


def _resolve_email_sample_path(
    email_sample_path_value: str | None,
    ground_truth_path: Path,
    repo_root: Path,
) -> Path:
    """Resolve evaluation sample paths from sibling-relative, repo-relative, or absolute values."""
    default_path = ground_truth_path.with_name("email.json")
    if not email_sample_path_value:
        return default_path.resolve()

    configured_path = Path(email_sample_path_value)
    if configured_path.is_absolute():
        return configured_path.resolve()

    sibling_path = (ground_truth_path.parent / configured_path).resolve()
    if sibling_path.exists():
        return sibling_path

    return (repo_root / configured_path).resolve()


def evaluate_sample(
    extraction_result: ComparisonResult,
    ground_truth_target: EvaluationTarget,
) -> EvaluationSampleResult:
    """Compare one extraction result against one reviewed ground truth sample."""
    extraction = extraction_result.get("extraction")
    actual = project_ground_truth_fields(extraction["fields"]) if extraction else None
    expected = ground_truth_target["candidate"]

    scalar_results = {
        field_name: compare_scalar_field(expected.get(field_name, ""), (actual or {}).get(field_name, ""))
        for field_name in SCALAR_FIELDS
    }
    set_results = {
        field_name: compare_set_field(expected.get(field_name, []), (actual or {}).get(field_name, []))
        for field_name in SET_FIELDS
    }
    windows_result = compare_set_field(
        [normalize_window(window) for window in expected.get(WINDOWS_FIELD, [])],
        [normalize_window(window) for window in (actual or {}).get(WINDOWS_FIELD, [])],
    )
    field_results = {**scalar_results, **set_results, WINDOWS_FIELD: windows_result}

    return {
        "ground_truth_path": str(ground_truth_target["ground_truth_path"]),
        "email_sample_path": str(ground_truth_target["email_sample_path"]),
        "sample_dir": extraction_result.get("sample_dir"),
        "status": "ok" if extraction is not None else "extraction_error",
        "extraction_attempt_count": extraction_result.get("extraction_attempt_count", 0),
        "expected": expected,
        "actual": actual,
        "field_results": field_results,
        "sample_exact_match": all(result["exact_match"] for result in field_results.values()),
        "extraction_error": extraction_result.get("extraction_error"),
    }


def compare_scalar_field(expected: str, actual: str) -> dict[str, Any]:
    """Compare one scalar field."""
    normalized_expected = (expected or "").strip()
    normalized_actual = (actual or "").strip()
    return {
        "expected": normalized_expected,
        "actual": normalized_actual,
        "exact_match": normalized_expected == normalized_actual,
        "error_type": _categorize_scalar_error(normalized_expected, normalized_actual),
    }


def compare_set_field(expected: list[Any], actual: list[Any]) -> dict[str, Any]:
    """Compare one unordered list field."""
    expected_values = [_stable_serialize(value) for value in expected]
    actual_values = [_stable_serialize(value) for value in actual]
    expected_set = set(expected_values)
    actual_set = set(actual_values)
    if not expected_set and not actual_set:
        return {
            "expected": expected,
            "actual": actual,
            "exact_match": True,
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "missing": [],
            "unexpected": [],
            "error_type": "exact_match",
        }

    true_positives = len(expected_set & actual_set)
    precision = _safe_divide(true_positives, len(actual_set))
    recall = _safe_divide(true_positives, len(expected_set))
    f1 = _safe_divide(2 * precision * recall, precision + recall) if precision + recall else 0.0
    return {
        "expected": expected,
        "actual": actual,
        "exact_match": expected_set == actual_set,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "missing": [value for value in expected if _stable_serialize(value) in expected_set - actual_set],
        "unexpected": [value for value in actual if _stable_serialize(value) in actual_set - expected_set],
        "error_type": _categorize_set_error(expected_set, actual_set),
    }


def normalize_window(window: dict[str, Any]) -> dict[str, str]:
    """Normalize a maintenance window for stable set comparison."""
    return {
        "start": str(window.get("start", "")).strip(),
        "end": str(window.get("end", "")).strip(),
        "timezone_normalized": str(window.get("timezone_normalized", "")).strip(),
        "kind": str(window.get("kind", "")).strip(),
    }


def summarize_sample_results(sample_results: list[EvaluationSampleResult]) -> dict[str, Any]:
    """Aggregate field metrics and taxonomy counts across evaluated samples."""
    field_names = [*SCALAR_FIELDS, *SET_FIELDS, WINDOWS_FIELD]
    field_summary: dict[str, Any] = {}
    for field_name in field_names:
        comparisons = [sample["field_results"][field_name] for sample in sample_results]
        exact_matches = sum(1 for comparison in comparisons if comparison["exact_match"])
        summary = {
            "exact_match_count": exact_matches,
            "exact_match_rate": _safe_divide(exact_matches, len(comparisons)),
            "error_counts": dict(Counter(comparison["error_type"] for comparison in comparisons)),
        }
        if field_name in {*SET_FIELDS, WINDOWS_FIELD}:
            summary.update(
                {
                    "average_precision": _safe_divide(
                        sum(comparison["precision"] for comparison in comparisons),
                        len(comparisons),
                    ),
                    "average_recall": _safe_divide(
                        sum(comparison["recall"] for comparison in comparisons),
                        len(comparisons),
                    ),
                    "average_f1": _safe_divide(
                        sum(comparison["f1"] for comparison in comparisons),
                        len(comparisons),
                    ),
                }
            )
        field_summary[field_name] = summary

    exact_match_samples = sum(1 for sample in sample_results if sample["sample_exact_match"])
    return {
        "exact_match_samples": exact_match_samples,
        "sample_exact_match_rate": _safe_divide(exact_match_samples, len(sample_results)),
        "samples_with_extraction_errors": sum(1 for sample in sample_results if sample["status"] != "ok"),
        "field_metrics": field_summary,
        "common_failure_patterns": build_failure_patterns(sample_results),
    }


def build_failure_patterns(sample_results: list[EvaluationSampleResult]) -> list[FailurePattern]:
    """Summarize the most common field-level failure patterns."""
    failure_counter: Counter[tuple[str, str]] = Counter()
    for sample in sample_results:
        for field_name, comparison in sample["field_results"].items():
            if comparison["error_type"] == "exact_match":
                continue
            failure_counter[(field_name, comparison["error_type"])] += 1
    return [
        {"field": field_name, "error_type": error_type, "count": count}
        for (field_name, error_type), count in failure_counter.most_common()
    ]


def _stable_serialize(value: Any) -> str:
    """Serialize a value for stable equality comparison."""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _categorize_scalar_error(expected: str, actual: str) -> str:
    """Return the scalar error taxonomy label for one field."""
    if expected == actual:
        return "exact_match"
    if expected and not actual:
        return "missing_value"
    if not expected and actual:
        return "hallucinated_value"
    return "wrong_value"


def _categorize_set_error(expected: set[str], actual: set[str]) -> str:
    """Return the set-field error taxonomy label."""
    if expected == actual:
        return "exact_match"
    if expected and not actual:
        return "missing_value"
    if not expected and actual:
        return "hallucinated_value"
    if expected & actual:
        return "partial_match"
    return "wrong_value"


def _safe_divide(numerator: float, denominator: float) -> float:
    """Return a division result, falling back to zero for empty denominators."""
    if not denominator:
        return 0.0
    return numerator / denominator
