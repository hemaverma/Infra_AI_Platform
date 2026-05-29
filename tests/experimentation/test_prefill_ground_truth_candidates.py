"""Tests for ground-truth candidate generation."""

import json
from pathlib import Path

import experimentation.paths as path_module
import experimentation.prefill_ground_truth as candidate_module


def test_build_candidate_payload_keeps_only_ground_truth_fields() -> None:
    """Test candidate generation narrows extraction output to the reviewed subset."""
    result = {
        "source_email_sample": "sample/email.json",
        "sample_dir": "sample",
        "formatted_email_path": "sample/formatted_email.txt",
        "extraction_path": "sample/extraction.json",
        "converted_email": {
            "workflowInstanceId": "wf-sample",
            "internetMessageId": "<sample@example.com>",
        },
        "extraction": {
            "fields": {
                "intent": "create_new",
                "vendor_name": "Vendor A",
                "vendor_ticket_id": "CHG0000001",
                "customer_ticket_ids": ["CHG0000001", "CHG0000001", "CHG0000002"],
                "windows": [
                    {
                        "start": "2026-05-19T04:01:00",
                        "end": "2026-05-19T10:00:00",
                        "timezone_normalized": "UTC",
                        "kind": "primary",
                        "start_raw": "ignored",
                    }
                ],
                "assets": [
                    {"type": "circuit", "value": "SYN-NYC-001"},
                    {"type": "site_id", "value": "SITE-001"},
                    {"type": "circuit", "value": "SYN-NYC-001"},
                ],
                "impact_category": "outage",
                "notes": ["ignored"],
            }
        },
    }

    payload = candidate_module._build_candidate_payload(result, None)

    assert payload["prefill_status"] == "ok"
    assert payload["candidate"] == {
        "intent": "create_new",
        "vendor_name": "Vendor A",
        "vendor_ticket_id": "CHG0000001",
        "customer_ticket_ids": ["CHG0000001", "CHG0000002"],
        "windows": [
            {
                "start": "2026-05-19T04:01:00",
                "end": "2026-05-19T10:00:00",
                "timezone_normalized": "UTC",
                "kind": "primary",
            }
        ],
        "circuit_ids": ["SYN-NYC-001"],
        "impact_category": "outage",
    }


def test_build_candidate_payload_records_extraction_errors() -> None:
    """Test candidate generation preserves extraction failures for later review."""
    result = {
        "source_email_sample": "sample/email.json",
        "sample_dir": "sample",
        "formatted_email_path": "sample/formatted_email.txt",
        "extraction_path": None,
        "converted_email": {
            "workflowInstanceId": "wf-sample",
            "internetMessageId": "<sample@example.com>",
        },
        "extraction": None,
        "extraction_error": {"message": "boom"},
    }

    payload = candidate_module._build_candidate_payload(result, None)

    assert payload["prefill_status"] == "error"
    assert payload["candidate"] is None
    assert payload["prefill_error"] == {"message": "boom"}


def test_load_recommended_sample_paths_reads_manifest(tmp_path: Path) -> None:
    """Test manifest loading returns repo-root-relative staged sample paths."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "recommended_samples": [
                    {"local_path": "src/experimentation/data/blob_seed_samples/foo/email.json"},
                    {"local_path": "src/experimentation/data/blob_seed_samples/bar/email.json"},
                ]
            }
        ) + "\n",
        encoding="utf-8",
    )

    paths = path_module.load_recommended_sample_paths(manifest_path)

    assert paths == [
        path_module.REPO_ROOT / Path("src/experimentation/data/blob_seed_samples/foo/email.json"),
        path_module.REPO_ROOT / Path("src/experimentation/data/blob_seed_samples/bar/email.json"),
    ]


def test_prefill_ground_truth_candidates_writes_review_email_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Test candidate generation copies the rendered email beside the review JSON."""
    sample_dir = tmp_path / "sample"
    sample_dir.mkdir(parents=True, exist_ok=True)
    email_sample_path = sample_dir / "email.json"
    email_sample_path.write_text("{}\n", encoding="utf-8")

    extraction_output_root = tmp_path / "output"
    extraction_sample_dir = extraction_output_root / "sample"
    extraction_sample_dir.mkdir(parents=True, exist_ok=True)
    formatted_email_path = extraction_sample_dir / "formatted_email.txt"
    formatted_email_path.write_text("# Email Packet\n\nBody\n", encoding="utf-8")

    monkeypatch.setattr(
        candidate_module,
        "compare_staged_extractions",
        lambda *args, **kwargs: {
            "results": [
                {
                    "source_email_sample": str(email_sample_path),
                    "sample_dir": str(extraction_sample_dir),
                    "formatted_email_path": str(formatted_email_path),
                    "extraction_path": str(extraction_sample_dir / "extraction.json"),
                    "converted_email": {
                        "workflowInstanceId": "wf-sample",
                        "internetMessageId": "<sample@example.com>",
                    },
                    "extraction": {
                        "fields": {
                            "intent": "informational",
                            "vendor_name": "Vendor",
                            "vendor_ticket_id": "TICKET-1",
                            "customer_ticket_ids": [],
                            "windows": [],
                            "assets": [],
                            "impact_category": "outage",
                        }
                    },
                }
            ]
        },
    )

    summary = candidate_module.prefill_ground_truth_candidates(
        [email_sample_path],
        extraction_output_root,
    )

    review_email_path = sample_dir / path_module.REVIEW_EMAIL_FILE_NAME
    candidate_path = sample_dir / path_module.CANDIDATE_FILE_NAME
    candidate_payload = json.loads(candidate_path.read_text(encoding="utf-8"))

    assert review_email_path.read_text(encoding="utf-8") == "# Email Packet\n\nBody\n"
    assert candidate_payload["source"]["email_sample_path"] == "email.json"
    assert candidate_payload["source"]["review_email_path"] == path_module.REVIEW_EMAIL_FILE_NAME
    assert summary["generated_candidates"][0]["review_email_path"] == str(review_email_path)
