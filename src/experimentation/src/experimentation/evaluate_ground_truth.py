"""Evaluate extraction quality against reviewed ground truth."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from experimentation import evaluation as evaluation_helpers
from experimentation.config import (
    apply_config_environment,
    discover_configured_ground_truth_paths,
    load_experimentation_config,
)
from experimentation.extraction import compare_staged_extractions
from experimentation.paths import (
    EVALUATION_REPORT_FILE_NAME,
    REPO_ROOT,
    build_run_created_at,
    build_run_id,
    build_run_output_dir,
)

_REPO_ROOT = REPO_ROOT
_compare_set_field = evaluation_helpers.compare_set_field
_evaluate_sample = evaluation_helpers.evaluate_sample
_load_evaluation_target = evaluation_helpers.load_evaluation_target
_normalize_window = evaluation_helpers.normalize_window
_summarize_sample_results = evaluation_helpers.summarize_sample_results
project_ground_truth_fields = evaluation_helpers.project_ground_truth_fields


def evaluate_ground_truth(
    ground_truth_paths: list[Path],
    output_root: Path,
    *,
    include_candidate_hints: bool = False,
    prompt_email_format: str = "markdown",
    log_level: str = "INFO",
    created_at: str | None = None,
) -> dict[str, object]:
    """Evaluate reviewed ground truth against fresh extraction output.

    Args:
        ground_truth_paths: Reviewed ground-truth files to evaluate.
        output_root: Directory where comparison and evaluation artifacts are written.
        include_candidate_hints: Whether to enable deterministic extraction hints.
        prompt_email_format: Extraction prompt input format.
        log_level: Workflow logging verbosity.
        created_at: Optional run creation timestamp.

    Returns:
        Aggregate evaluation payload.
    """
    evaluation_targets = [_load_evaluation_target(path, _REPO_ROOT) for path in ground_truth_paths]
    report = compare_staged_extractions(
        [target["email_sample_path"] for target in evaluation_targets],
        output_root,
        include_candidate_hints=include_candidate_hints,
        prompt_email_format=prompt_email_format,
        log_level=log_level,
    )

    ground_truth_by_email_path = {
        str(target["email_sample_path"].resolve()): target for target in evaluation_targets
    }
    sample_results: list[dict[str, object]] = []
    for extraction_result in report["results"]:
        email_sample_path = Path(extraction_result["email_sample_path"]).resolve()
        ground_truth_target = ground_truth_by_email_path[str(email_sample_path)]
        sample_results.append(_evaluate_sample(extraction_result, ground_truth_target))

    output_root.mkdir(parents=True, exist_ok=True)
    evaluation = {
        "run_id": build_run_id(output_root),
        "created_at": created_at or build_run_created_at(),
        "sample_count": len(sample_results),
        "output_root": str(output_root),
        "comparison_report_path": str(output_root / "comparison_report.json"),
        "experiment": report.get("experiment", {}),
        "summary": _summarize_sample_results(sample_results),
        "samples": sample_results,
    }
    evaluation_path = output_root / EVALUATION_REPORT_FILE_NAME
    evaluation_path.write_text(json.dumps(evaluation, indent=2) + "\n", encoding="utf-8")
    evaluation["evaluation_path"] = str(evaluation_path)
    return evaluation


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for evaluation."""
    parser = argparse.ArgumentParser(
        description="Evaluate reviewed ground truth against fresh staged extraction output.",
    )
    parser.add_argument(
        "--config",
        help="Optional experimentation YAML config path.",
    )
    parser.add_argument(
        "ground_truth_paths",
        nargs="*",
        help="Optional explicit ground truth paths. Defaults to the seed sample set.",
    )
    parser.add_argument("--output-dir", help="Directory for extraction comparison and evaluation artifacts.")
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        type=str.upper,
        help="Set the workflow logger verbosity for this evaluation run.",
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
    """Run the ground-truth evaluation helper from the command line."""
    args = _build_parser().parse_args()
    config = load_experimentation_config(Path(args.config) if args.config else None)
    apply_config_environment(config)

    ground_truth_paths = (
        [Path(path) for path in args.ground_truth_paths]
        if args.ground_truth_paths
        else discover_configured_ground_truth_paths(config)
    )
    if not ground_truth_paths:
        raise SystemExit("No reviewed ground-truth files found")

    prompt_email_format = args.prompt_email_format or config.experiment.prompt_email_format
    output_root = (
        Path(args.output_dir)
        if args.output_dir
        else build_run_output_dir(prompt_email_format, runs_dir=config.output.runs_dir)
    )
    evaluation = evaluate_ground_truth(
        ground_truth_paths,
        output_root,
        include_candidate_hints=(
            args.include_candidate_hints
            if args.include_candidate_hints is not None
            else config.experiment.include_candidate_hints
        ),
        prompt_email_format=prompt_email_format,
        log_level=args.log_level or config.experiment.log_level,
        created_at=build_run_created_at(datetime.now(timezone.utc)),
    )
    print(json.dumps(evaluation["summary"], indent=2))


if __name__ == "__main__":
    main()
