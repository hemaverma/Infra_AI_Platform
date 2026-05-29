"""Generate reviewed-ground-truth candidates from staged email samples."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experimentation.config import (
    apply_config_environment,
    load_configured_sample_paths,
    load_experimentation_config,
)
from experimentation.evaluation import project_ground_truth_fields
from experimentation.extraction import compare_staged_extractions
from experimentation.paths import (
    CANDIDATE_FILE_NAME,
    REVIEW_EMAIL_FILE_NAME,
)


def prefill_ground_truth_candidates(
    email_sample_paths: list[Path],
    output_root: Path,
    *,
    include_candidate_hints: bool = False,
    prompt_email_format: str = "markdown",
    log_level: str = "INFO",
) -> dict[str, Any]:
    """Generate candidate labels for staged email samples.

    Args:
        email_sample_paths: Staged email sample paths to process.
        output_root: Folder for extraction comparison artifacts.
        include_candidate_hints: Whether to enable deterministic extraction hints.
        prompt_email_format: Extraction prompt input format.
        log_level: Workflow logging verbosity.

    Returns:
        Summary payload describing generated candidate files.
    """
    report = compare_staged_extractions(
        email_sample_paths,
        output_root,
        include_candidate_hints=include_candidate_hints,
        prompt_email_format=prompt_email_format,
        log_level=log_level,
    )

    generated_candidates: list[dict[str, Any]] = []
    for result in report["results"]:
        email_sample_path = Path(result.get("email_sample_path") or result["source_email_sample"])
        candidate_path = email_sample_path.parent / CANDIDATE_FILE_NAME
        review_email_path = _write_review_email(result, email_sample_path.parent)
        candidate_payload = _build_candidate_payload(result, review_email_path)
        candidate_path.write_text(json.dumps(candidate_payload, indent=2) + "\n", encoding="utf-8")
        generated_candidates.append(
            {
                "email_sample_path": str(email_sample_path),
                "candidate_path": str(candidate_path),
                "review_email_path": str(review_email_path) if review_email_path else None,
                "prefill_status": candidate_payload["prefill_status"],
            }
        )

    summary = {
        "sample_count": len(generated_candidates),
        "output_root": str(output_root),
        "generated_candidates": generated_candidates,
    }
    summary_path = output_root / "ground_truth_candidates.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def _build_candidate_payload(
    result: dict[str, Any],
    review_email_path: Path | None,
) -> dict[str, Any]:
    """Build a reviewable candidate payload from one extraction result.

    Args:
        result: One comparison result from the staged extraction runner.
        review_email_path: Local rendered-email artifact path.

    Returns:
        Candidate payload.
    """
    converted_email = result.get("converted_email", {})
    extraction = result.get("extraction")
    email_sample_path_value = result.get("email_sample_path") or result.get("source_email_sample")
    email_sample_path = Path(email_sample_path_value) if email_sample_path_value else None
    payload = {
        "schema_version": "ground_truth_candidate_v1",
        "review_status": "needs_review",
        "prefill_status": "ok" if extraction is not None else "error",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": {
            "workflow_instance_id": converted_email.get("workflowInstanceId", ""),
            "internet_message_id": converted_email.get("internetMessageId", ""),
            "email_sample_path": email_sample_path.name if email_sample_path else None,
            "review_email_path": review_email_path.name if review_email_path else None,
            "sample_dir": result.get("sample_dir"),
            "formatted_email_path": result.get("formatted_email_path"),
            "extraction_path": result.get("extraction_path"),
        },
        "candidate": None,
        "review_notes": [],
    }
    if extraction is None:
        payload["prefill_error"] = result.get("extraction_error")
        return payload

    payload["candidate"] = project_ground_truth_fields(extraction["fields"])
    return payload


def _write_review_email(result: dict[str, Any], destination_dir: Path) -> Path | None:
    """Copy the rendered prompt email next to the candidate for review.

    Args:
        result: One comparison result from the staged extraction runner.
        destination_dir: Folder where the review email artifact should be written.

    Returns:
        Written review email path, or None when the rendered email is unavailable.
    """
    formatted_email_path_value = result.get("formatted_email_path")
    if not formatted_email_path_value:
        return None

    formatted_email_path = Path(formatted_email_path_value)
    if not formatted_email_path.exists():
        return None

    destination_path = destination_dir / REVIEW_EMAIL_FILE_NAME
    destination_path.write_text(formatted_email_path.read_text(encoding="utf-8"), encoding="utf-8")
    return destination_path


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for candidate generation."""
    parser = argparse.ArgumentParser(
        description="Generate reviewed-ground-truth candidates from staged email samples.",
    )
    parser.add_argument(
        "--config",
        help="Optional experimentation YAML config path.",
    )
    parser.add_argument(
        "email_sample_paths",
        nargs="*",
        help="Optional explicit staged email.json paths. Defaults to the manifest's recommended samples.",
    )
    parser.add_argument("--output-dir", help="Directory for extraction comparison artifacts.")
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        type=str.upper,
        help="Set the workflow logger verbosity for this generation run.",
    )
    parser.add_argument(
        "--include-candidate-hints",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Inject deterministic candidate hints into the extraction prompt.",
    )
    parser.add_argument(
        "--prompt-email-format",
        default=None,
        choices=["markdown", "xml"],
        help="Render the extraction email packet as markdown or xml.",
    )
    return parser


def main() -> None:
    """Generate reviewed-ground-truth candidates from staged email samples."""
    args = _build_parser().parse_args()
    config = load_experimentation_config(Path(args.config) if args.config else None)
    apply_config_environment(config)

    email_sample_paths = (
        [Path(path) for path in args.email_sample_paths]
        if args.email_sample_paths
        else load_configured_sample_paths(config)
    )
    if not email_sample_paths:
        raise SystemExit("No staged email samples found for candidate generation")

    output_dir = Path(args.output_dir) if args.output_dir else config.output.prefill_dir
    summary = prefill_ground_truth_candidates(
        email_sample_paths,
        output_dir,
        include_candidate_hints=(
            args.include_candidate_hints
            if args.include_candidate_hints is not None
            else config.experiment.include_candidate_hints
        ),
        prompt_email_format=args.prompt_email_format or config.experiment.prompt_email_format,
        log_level=args.log_level or config.experiment.log_level,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
