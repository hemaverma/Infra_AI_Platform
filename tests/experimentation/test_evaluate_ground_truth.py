"""Tests for ground-truth evaluation."""

import json
from pathlib import Path

import experimentation.evaluate_ground_truth as evaluation_module
from experimentation.evaluation import project_ground_truth_fields


def test_project_ground_truth_fields_keeps_only_reviewed_subset() -> None:
    """Test projection keeps the reviewed evaluation subset only."""
    projected = project_ground_truth_fields(
        {
            "intent": "create_new",
            "vendor_name": "Vendor A",
            "vendor_ticket_id": "CHG0001",
            "customer_ticket_ids": ["CHG0001", "CHG0001", "CHG0002"],
            "windows": [
                {
                    "start": "2026-05-15T05:01:00",
                    "end": "2026-05-15T11:00:00",
                    "timezone_normalized": "UTC",
                    "kind": "primary",
                    "start_raw": "ignored",
                }
            ],
            "assets": [
                {"type": "circuit", "value": " SYN-NYC-001 "},
                {"type": "site_id", "value": "SITE-1"},
                {"type": "circuit", "value": "SYN-NYC-001"},
            ],
            "impact_category": "outage",
            "notes": ["ignored"],
        }
    )

    assert projected == {
        "intent": "create_new",
        "vendor_name": "Vendor A",
        "vendor_ticket_id": "CHG0001",
        "customer_ticket_ids": ["CHG0001", "CHG0002"],
        "windows": [
            {
                "start": "2026-05-15T05:01:00",
                "end": "2026-05-15T11:00:00",
                "timezone_normalized": "UTC",
                "kind": "primary",
            }
        ],
        "circuit_ids": ["SYN-NYC-001"],
        "impact_category": "outage",
    }


def test_evaluate_ground_truth_summarizes_metrics_and_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Test evaluation aggregates exact-match and list overlap metrics."""
    sample_one_dir = tmp_path / "sample-one"
    sample_two_dir = tmp_path / "sample-two"
    sample_one_dir.mkdir(parents=True, exist_ok=True)
    sample_two_dir.mkdir(parents=True, exist_ok=True)

    sample_one_email = sample_one_dir / "email.json"
    sample_two_email = sample_two_dir / "email.json"
    sample_one_email.write_text("{}\n", encoding="utf-8")
    sample_two_email.write_text("{}\n", encoding="utf-8")

    sample_one_ground_truth = sample_one_dir / "ground_truth.json"
    sample_two_ground_truth = sample_two_dir / "ground_truth.json"
    sample_one_ground_truth.write_text(
        json.dumps(
            {
                "source": {"email_sample_path": "email.json"},
                "candidate": {
                    "intent": "create_new",
                    "vendor_name": "Vendor A",
                    "vendor_ticket_id": "",
                    "customer_ticket_ids": ["CR-0001"],
                    "windows": [
                        {
                            "start": "2026-05-15T05:01:00",
                            "end": "2026-05-15T11:00:00",
                            "timezone_normalized": "UTC",
                            "kind": "primary",
                        }
                    ],
                    "circuit_ids": ["SYN-NYC-001"],
                    "impact_category": "outage",
                },
            }
        ) + "\n",
        encoding="utf-8",
    )
    sample_two_ground_truth.write_text(
        json.dumps(
            {
                "source": {"email_sample_path": "email.json"},
                "candidate": {
                    "intent": "cancel",
                    "vendor_name": "Vendor B",
                    "vendor_ticket_id": "VT-2",
                    "customer_ticket_ids": ["TM-1", "TM-2"],
                    "windows": [],
                    "circuit_ids": ["CKT-1", "CKT-2"],
                    "impact_category": "maintenance",
                },
            }
        ) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        evaluation_module,
        "compare_staged_extractions",
        lambda *args, **kwargs: {
            "experiment": {
                "llm_model": "gpt-test",
                "prompt_email_format": "markdown",
                "candidate_hints_enabled": False,
            },
            "results": [
                {
                    "email_sample_path": str(sample_one_email),
                    "sample_dir": str(tmp_path / "output" / "sample-one"),
                    "extraction_attempt_count": 1,
                    "extraction_error": None,
                    "extraction": {
                        "fields": {
                            "intent": "create_new",
                            "vendor_name": "Vendor A",
                            "vendor_ticket_id": "",
                            "customer_ticket_ids": ["CR-0001"],
                            "windows": [
                                {
                                    "start": "2026-05-15T05:01:00",
                                    "end": "2026-05-15T11:00:00",
                                    "timezone_normalized": "UTC",
                                    "kind": "primary",
                                }
                            ],
                            "assets": [{"type": "circuit", "value": "SYN-NYC-001"}],
                            "impact_category": "outage",
                        }
                    },
                },
                {
                    "email_sample_path": str(sample_two_email),
                    "sample_dir": str(tmp_path / "output" / "sample-two"),
                    "extraction_attempt_count": 1,
                    "extraction_error": None,
                    "extraction": {
                        "fields": {
                            "intent": "cancel",
                            "vendor_name": "Wrong Vendor",
                            "vendor_ticket_id": "",
                            "customer_ticket_ids": ["TM-1"],
                            "windows": [],
                            "assets": [
                                {"type": "circuit", "value": "CKT-1"},
                                {"type": "circuit", "value": "CKT-3"},
                            ],
                            "impact_category": "maintenance",
                        }
                    },
                },
            ]
        },
    )

    evaluation = evaluation_module.evaluate_ground_truth(
        [sample_one_ground_truth, sample_two_ground_truth],
        tmp_path / "output",
    )

    summary = evaluation["summary"]
    assert evaluation["sample_count"] == 2
    assert evaluation["experiment"] == {
        "llm_model": "gpt-test",
        "prompt_email_format": "markdown",
        "candidate_hints_enabled": False,
    }
    assert summary["exact_match_samples"] == 1
    assert summary["field_metrics"]["intent"]["exact_match_rate"] == 1.0
    assert summary["field_metrics"]["vendor_name"]["exact_match_count"] == 1
    assert summary["field_metrics"]["vendor_ticket_id"]["error_counts"]["missing_value"] == 1
    assert summary["field_metrics"]["customer_ticket_ids"]["average_precision"] == 1.0
    assert summary["field_metrics"]["customer_ticket_ids"]["average_recall"] == 0.75
    assert summary["field_metrics"]["circuit_ids"]["average_f1"] < 1.0
    assert {
        (item["field"], item["error_type"], item["count"])
        for item in summary["common_failure_patterns"]
    } >= {
        ("vendor_name", "wrong_value", 1),
        ("vendor_ticket_id", "missing_value", 1),
        ("customer_ticket_ids", "partial_match", 1),
        ("circuit_ids", "partial_match", 1),
    }
    assert Path(evaluation["evaluation_path"]).exists()


def test_compare_set_field_treats_empty_lists_as_perfect_match() -> None:
    """Test empty reviewed and extracted list fields count as a perfect match."""
    result = evaluation_module._compare_set_field([], [])

    assert result == {
        "expected": [],
        "actual": [],
        "exact_match": True,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
        "missing": [],
        "unexpected": [],
        "error_type": "exact_match",
    }
