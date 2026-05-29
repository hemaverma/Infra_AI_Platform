"""Summarize evaluation runs into comparison CSVs."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experimentation.config import load_experimentation_config
from experimentation.paths import OUTPUT_ROOT, SUMMARIES_DIR, discover_evaluation_reports

_RUNS_SUMMARY_FILE_NAME = "runs_summary.csv"
_FIELD_METRICS_FILE_NAME = "field_metrics.csv"
_FIELD_METRICS_WIDE_FILE_NAME = "field_metrics_wide.csv"
_SAMPLE_DIFFS_FILE_NAME = "sample_diffs.csv"
_RUNS_SUMMARY_COLUMNS = [
    "run_id",
    "created_at",
    "llm_model",
    "prompt_email_format",
    "candidate_hints_enabled",
    "log_level",
    "sample_count",
    "exact_match_samples",
    "sample_exact_match_rate",
    "samples_with_extraction_errors",
    "output_root",
    "comparison_report_path",
    "evaluation_path",
]
_FIELD_METRICS_COLUMNS = [
    "run_id",
    "created_at",
    "field_name",
    "exact_match_count",
    "exact_match_rate",
    "average_precision",
    "average_recall",
    "average_f1",
    "error_counts_json",
]
_FIELD_METRICS_WIDE_BASE_COLUMNS = list(_RUNS_SUMMARY_COLUMNS)
_FIELD_METRIC_SUFFIXES = [
    "exact_match_count",
    "exact_match_rate",
    "average_precision",
    "average_recall",
    "average_f1",
    "error_counts_json",
]
_SAMPLE_DIFFS_COLUMNS = [
    "run_id",
    "created_at",
    "ground_truth_path",
    "email_sample_path",
    "field_name",
    "error_type",
    "expected_json",
    "actual_json",
    "missing_json",
    "unexpected_json",
]


def summarize_ground_truth_runs(
    *,
    search_root: Path = OUTPUT_ROOT,
    summaries_dir: Path = SUMMARIES_DIR,
) -> dict[str, Any]:
    """Build comparison CSVs from all discovered evaluation reports."""
    reports = discover_evaluation_reports(search_root)
    report_payloads = [
        (report_path, json.loads(report_path.read_text(encoding="utf-8")))
        for report_path in reports
    ]
    report_payloads.sort(
        key=lambda item: (_resolve_created_at(item[0], item[1]), str(item[0])),
        reverse=True,
    )
    field_metric_wide_columns = _build_field_metric_wide_columns(report_payloads)
    run_rows: list[dict[str, Any]] = []
    field_rows: list[dict[str, Any]] = []
    field_wide_rows: list[dict[str, Any]] = []
    diff_rows: list[dict[str, Any]] = []
    for report_path, payload in report_payloads:
        run_row = _build_run_summary_row(report_path, payload)
        run_rows.append(run_row)
        field_rows.extend(_build_field_metric_rows(report_path, payload))
        field_wide_rows.append(
            _build_field_metric_wide_row(report_path, payload, run_row, field_metric_wide_columns)
        )
        diff_rows.extend(_build_sample_diff_rows(report_path, payload))

    summaries_dir.mkdir(parents=True, exist_ok=True)
    runs_summary_path = summaries_dir / _RUNS_SUMMARY_FILE_NAME
    field_metrics_path = summaries_dir / _FIELD_METRICS_FILE_NAME
    field_metrics_wide_path = summaries_dir / _FIELD_METRICS_WIDE_FILE_NAME
    sample_diffs_path = summaries_dir / _SAMPLE_DIFFS_FILE_NAME
    _write_csv(runs_summary_path, _RUNS_SUMMARY_COLUMNS, run_rows)
    _write_csv(field_metrics_path, _FIELD_METRICS_COLUMNS, field_rows)
    _write_csv(field_metrics_wide_path, field_metric_wide_columns, field_wide_rows)
    _write_csv(sample_diffs_path, _SAMPLE_DIFFS_COLUMNS, diff_rows)
    return {
        "report_count": len(reports),
        "runs_summary_path": str(runs_summary_path),
        "field_metrics_path": str(field_metrics_path),
        "field_metrics_wide_path": str(field_metrics_wide_path),
        "sample_diffs_path": str(sample_diffs_path),
    }


def _build_run_summary_row(report_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Build the run-level summary row for one evaluation report."""
    experiment = payload.get("experiment", {})
    summary = payload.get("summary", {})
    created_at = _resolve_created_at(report_path, payload)
    return {
        "run_id": payload.get("run_id") or report_path.parent.name,
        "created_at": created_at,
        "llm_model": experiment.get("llm_model") or "",
        "prompt_email_format": experiment.get("prompt_email_format") or "",
        "candidate_hints_enabled": experiment.get("candidate_hints_enabled"),
        "log_level": experiment.get("log_level") or "",
        "sample_count": payload.get("sample_count", 0),
        "exact_match_samples": summary.get("exact_match_samples", 0),
        "sample_exact_match_rate": summary.get("sample_exact_match_rate", 0.0),
        "samples_with_extraction_errors": summary.get("samples_with_extraction_errors", 0),
        "output_root": payload.get("output_root") or str(report_path.parent),
        "comparison_report_path": payload.get("comparison_report_path") or "",
        "evaluation_path": payload.get("evaluation_path") or str(report_path),
    }


def _build_field_metric_rows(report_path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Build per-field metric rows for one evaluation report."""
    run_id = payload.get("run_id") or Path(payload.get("output_root", "unknown")).name
    created_at = _resolve_created_at(report_path, payload)
    rows: list[dict[str, Any]] = []
    for field_name, metrics in payload.get("summary", {}).get("field_metrics", {}).items():
        rows.append(
            {
                "run_id": run_id,
                "created_at": created_at,
                "field_name": field_name,
                "exact_match_count": metrics.get("exact_match_count", 0),
                "exact_match_rate": metrics.get("exact_match_rate", 0.0),
                "average_precision": metrics.get("average_precision", ""),
                "average_recall": metrics.get("average_recall", ""),
                "average_f1": metrics.get("average_f1", ""),
                "error_counts_json": json.dumps(metrics.get("error_counts", {}), sort_keys=True),
            }
        )
    return rows


def _build_field_metric_wide_columns(
    report_payloads: list[tuple[Path, dict[str, Any]]],
) -> list[str]:
    """Build the wide CSV header from all discovered per-field metric names."""
    field_names = sorted(
        {
            field_name
            for _, payload in report_payloads
            for field_name in payload.get("summary", {}).get("field_metrics", {})
        }
    )
    return [
        *_FIELD_METRICS_WIDE_BASE_COLUMNS,
        *[
            f"{field_name}__{suffix}"
            for field_name in field_names
            for suffix in _FIELD_METRIC_SUFFIXES
        ],
    ]


def _build_field_metric_wide_row(
    report_path: Path,
    payload: dict[str, Any],
    run_row: dict[str, Any],
    columns: list[str],
) -> dict[str, Any]:
    """Build one row per run with flattened per-field metric columns."""
    row = {column: "" for column in columns}
    row.update(run_row)
    for field_name, metrics in payload.get("summary", {}).get("field_metrics", {}).items():
        row[f"{field_name}__exact_match_count"] = metrics.get("exact_match_count", 0)
        row[f"{field_name}__exact_match_rate"] = metrics.get("exact_match_rate", 0.0)
        row[f"{field_name}__average_precision"] = metrics.get("average_precision", "")
        row[f"{field_name}__average_recall"] = metrics.get("average_recall", "")
        row[f"{field_name}__average_f1"] = metrics.get("average_f1", "")
        row[f"{field_name}__error_counts_json"] = json.dumps(
            metrics.get("error_counts", {}),
            sort_keys=True,
        )
    return row


def _build_sample_diff_rows(report_path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Build one row per non-exact sample field comparison."""
    run_id = payload.get("run_id") or Path(payload.get("output_root", "unknown")).name
    created_at = _resolve_created_at(report_path, payload)
    rows: list[dict[str, Any]] = []
    for sample in payload.get("samples", []):
        for field_name, comparison in sample.get("field_results", {}).items():
            if comparison.get("exact_match"):
                continue
            rows.append(
                {
                    "run_id": run_id,
                    "created_at": created_at,
                    "ground_truth_path": sample.get("ground_truth_path", ""),
                    "email_sample_path": sample.get("email_sample_path", ""),
                    "field_name": field_name,
                    "error_type": comparison.get("error_type", ""),
                    "expected_json": json.dumps(comparison.get("expected"), sort_keys=True),
                    "actual_json": json.dumps(comparison.get("actual"), sort_keys=True),
                    "missing_json": json.dumps(comparison.get("missing", []), sort_keys=True),
                    "unexpected_json": json.dumps(comparison.get("unexpected", []), sort_keys=True),
                }
            )
    return rows


def _write_csv(file_path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    """Write rows to a CSV file with a fixed header."""
    with file_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _resolve_created_at(report_path: Path, payload: dict[str, Any]) -> str:
    """Return the run timestamp from the payload or the report file metadata."""
    created_at = str(payload.get("created_at") or "").strip()
    if created_at:
        return created_at

    return datetime.fromtimestamp(report_path.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for run summarization."""
    parser = argparse.ArgumentParser(description="Summarize evaluation reports into comparison CSVs.")
    parser.add_argument("--config", help="Optional experimentation YAML config path.")
    parser.add_argument("--search-root", help="Root directory to scan for evaluation report files.")
    parser.add_argument("--summaries-dir", help="Directory where summary CSV files should be written.")
    return parser


def main() -> None:
    """Run the evaluation summarizer from the command line."""
    args = _build_parser().parse_args()
    config = load_experimentation_config(Path(args.config) if args.config else None)
    summary = summarize_ground_truth_runs(
        search_root=Path(args.search_root) if args.search_root else config.output.search_root,
        summaries_dir=Path(args.summaries_dir) if args.summaries_dir else config.output.summaries_dir,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
