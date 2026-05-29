"""Tests for ground-truth run organization and summarization helpers."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import experimentation.paths as path_module
import experimentation.summarize_ground_truth_runs as summarize_module


def test_build_run_output_dir_uses_canonical_layout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Test the default run folder includes timestamp, model, and format."""
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "gpt-4.1")

    output_dir = path_module.build_run_output_dir(
        "markdown",
        now=datetime(2026, 5, 14, 12, 30, 45, tzinfo=timezone.utc),
        runs_dir=tmp_path / "runs",
    )

    assert output_dir == tmp_path / "runs" / "20260514-123045__gpt-4.1__markdown"


def test_build_run_output_dir_avoids_collisions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Test a numeric suffix is added when the canonical run path already exists."""
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "gpt-4.1")
    runs_dir = tmp_path / "runs"
    existing = runs_dir / "20260514-123045__gpt-4.1__markdown"
    existing.mkdir(parents=True, exist_ok=True)

    output_dir = path_module.build_run_output_dir(
        "markdown",
        now=datetime(2026, 5, 14, 12, 30, 45, tzinfo=timezone.utc),
        runs_dir=runs_dir,
    )

    assert output_dir == runs_dir / "20260514-123045__gpt-4.1__markdown-2"


def test_summarize_ground_truth_runs_writes_summary_csvs(tmp_path: Path) -> None:
    """Test run summarization scans reports and writes the expected CSV tables."""
    output_root = tmp_path / "output"
    run_one_dir = output_root / "ground_truth" / "runs" / "20260514-120000__gpt-5.4__markdown"
    run_two_dir = output_root / "stage1_ground_truth_evaluation_gpt-4.1_20260514-112618"
    run_one_dir.mkdir(parents=True, exist_ok=True)
    run_two_dir.mkdir(parents=True, exist_ok=True)

    run_one_report = {
        "run_id": "20260514-120000__gpt-5.4__markdown",
        "created_at": "2026-05-14T12:00:00Z",
        "sample_count": 5,
        "output_root": str(run_one_dir),
        "comparison_report_path": str(run_one_dir / "comparison_report.json"),
        "evaluation_path": str(run_one_dir / "evaluation_report.json"),
        "experiment": {
            "llm_model": "gpt-5.4",
            "prompt_email_format": "markdown",
            "candidate_hints_enabled": False,
            "log_level": "ERROR",
        },
        "summary": {
            "exact_match_samples": 5,
            "sample_exact_match_rate": 1.0,
            "samples_with_extraction_errors": 0,
            "field_metrics": {
                "intent": {
                    "exact_match_count": 5,
                    "exact_match_rate": 1.0,
                    "error_counts": {"exact_match": 5},
                }
            },
            "common_failure_patterns": [],
        },
        "samples": [],
    }
    run_two_report = {
        "run_id": "stage1_ground_truth_evaluation_gpt-4.1_20260514-112618",
        "created_at": "2026-05-14T11:26:18Z",
        "sample_count": 5,
        "output_root": str(run_two_dir),
        "comparison_report_path": str(run_two_dir / "comparison_report.json"),
        "evaluation_path": str(run_two_dir / "stage1_evaluation_report.json"),
        "experiment": {
            "llm_model": "gpt-4.1",
            "prompt_email_format": "markdown",
            "candidate_hints_enabled": False,
            "log_level": "ERROR",
        },
        "summary": {
            "exact_match_samples": 4,
            "sample_exact_match_rate": 0.8,
            "samples_with_extraction_errors": 0,
            "field_metrics": {
                "circuit_ids": {
                    "exact_match_count": 4,
                    "exact_match_rate": 0.8,
                    "average_precision": 0.93,
                    "average_recall": 1.0,
                    "average_f1": 0.96,
                    "error_counts": {"exact_match": 4, "partial_match": 1},
                }
            },
            "common_failure_patterns": [
                {"field": "circuit_ids", "error_type": "partial_match", "count": 1}
            ],
        },
        "samples": [
            {
                "ground_truth_path": "sample/stage1_ground_truth.json",
                "email_sample_path": "sample/email.json",
                "field_results": {
                    "circuit_ids": {
                        "exact_match": False,
                        "error_type": "partial_match",
                        "expected": ["A", "B"],
                        "actual": ["A", "B", "C"],
                        "missing": [],
                        "unexpected": ["C"],
                    }
                },
            }
        ],
    }
    (run_one_dir / "evaluation_report.json").write_text(
        json.dumps(run_one_report, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_two_dir / "stage1_evaluation_report.json").write_text(
        json.dumps(run_two_report, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = summarize_module.summarize_ground_truth_runs(
        search_root=output_root,
        summaries_dir=tmp_path / "summaries",
    )

    assert summary["report_count"] == 2

    with Path(summary["runs_summary_path"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["run_id"] for row in rows] == [
        "20260514-120000__gpt-5.4__markdown",
        "stage1_ground_truth_evaluation_gpt-4.1_20260514-112618",
    ]

    with Path(summary["field_metrics_path"]).open(encoding="utf-8", newline="") as handle:
        field_rows = list(csv.DictReader(handle))
    assert {row["field_name"] for row in field_rows} == {"intent", "circuit_ids"}

    with Path(summary["field_metrics_wide_path"]).open(encoding="utf-8", newline="") as handle:
        wide_rows = list(csv.DictReader(handle))
    assert [row["run_id"] for row in wide_rows] == [
        "20260514-120000__gpt-5.4__markdown",
        "stage1_ground_truth_evaluation_gpt-4.1_20260514-112618",
    ]
    assert wide_rows[0]["intent__exact_match_rate"] == "1.0"
    assert wide_rows[0]["intent__error_counts_json"] == '{"exact_match": 5}'
    assert wide_rows[1]["circuit_ids__exact_match_rate"] == "0.8"
    assert wide_rows[1]["circuit_ids__average_precision"] == "0.93"
    assert wide_rows[1]["circuit_ids__average_recall"] == "1.0"
    assert wide_rows[1]["circuit_ids__average_f1"] == "0.96"
    assert wide_rows[1]["circuit_ids__error_counts_json"] == '{"exact_match": 4, "partial_match": 1}'

    with Path(summary["sample_diffs_path"]).open(encoding="utf-8", newline="") as handle:
        diff_rows = list(csv.DictReader(handle))
    assert diff_rows == [
        {
            "run_id": "stage1_ground_truth_evaluation_gpt-4.1_20260514-112618",
            "created_at": "2026-05-14T11:26:18Z",
            "ground_truth_path": "sample/stage1_ground_truth.json",
            "email_sample_path": "sample/email.json",
            "field_name": "circuit_ids",
            "error_type": "partial_match",
            "expected_json": '["A", "B"]',
            "actual_json": '["A", "B", "C"]',
            "missing_json": '[]',
            "unexpected_json": '["C"]',
        }
    ]
