"""Shared YAML configuration helpers for experimentation workflows."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from experimentation.paths import (
    COMPONENT_ROOT,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_PREFILL_OUTPUT_ROOT,
    OUTPUT_ROOT,
    REPO_ROOT,
    RUNS_DIR,
    SUMMARIES_DIR,
)

DEFAULT_CONFIG_PATH = COMPONENT_ROOT / "config" / "experimentation.yaml"
DEFAULT_GROUND_TRUTH_GLOB = "src/experimentation/data/blob_seed_samples/**/ground_truth.json"


@dataclass(frozen=True)
class ExperimentSettings:
    """Shared experiment execution settings."""

    prompt_email_format: str = "markdown"
    log_level: str = "INFO"
    include_candidate_hints: bool = False


@dataclass(frozen=True)
class ExtractionSettings:
    """Extraction runtime settings."""

    retry_attempts: int = 3
    retry_delay_seconds: float = 1.0
    model: str | None = None


@dataclass(frozen=True)
class DataSettings:
    """Dataset discovery settings."""

    manifest_path: Path = DEFAULT_MANIFEST_PATH
    ground_truth_glob: str = DEFAULT_GROUND_TRUTH_GLOB


@dataclass(frozen=True)
class OutputSettings:
    """Output directory settings."""

    prefill_dir: Path = DEFAULT_PREFILL_OUTPUT_ROOT
    runs_dir: Path = RUNS_DIR
    search_root: Path = OUTPUT_ROOT
    summaries_dir: Path = SUMMARIES_DIR


@dataclass(frozen=True)
class ExperimentationConfig:
    """Resolved experimentation workflow configuration."""

    config_path: Path
    repo_root: Path
    experiment: ExperimentSettings
    extraction: ExtractionSettings
    data: DataSettings
    output: OutputSettings


def validate_experimentation_config(config: ExperimentationConfig) -> dict[str, Any]:
    """Validate the resolved experimentation config and report discovered inputs.

    Args:
        config: Resolved experimentation config.

    Returns:
        A machine-readable validation summary.

    Raises:
        FileNotFoundError: If referenced input files do not exist.
        ValueError: If the configured manifest or discovered payloads are invalid.
    """
    sample_paths = load_configured_sample_paths(config)
    ground_truth_paths = discover_configured_ground_truth_paths(config)

    return {
        "config_path": str(config.config_path),
        "repo_root": str(config.repo_root),
        "experiment": {
            "prompt_email_format": config.experiment.prompt_email_format,
            "log_level": config.experiment.log_level,
            "include_candidate_hints": config.experiment.include_candidate_hints,
        },
        "extraction": {
            "retry_attempts": config.extraction.retry_attempts,
            "retry_delay_seconds": config.extraction.retry_delay_seconds,
            "model": config.extraction.model,
        },
        "data": {
            "manifest_path": str(config.data.manifest_path),
            "recommended_sample_count": len(sample_paths),
            "ground_truth_glob": config.data.ground_truth_glob,
            "ground_truth_count": len(ground_truth_paths),
        },
        "output": {
            "prefill_dir": str(config.output.prefill_dir),
            "runs_dir": str(config.output.runs_dir),
            "search_root": str(config.output.search_root),
            "summaries_dir": str(config.output.summaries_dir),
        },
    }


def load_experimentation_config(
    config_path: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
) -> ExperimentationConfig:
    """Load the experimentation YAML config file.

    Args:
        config_path: Optional explicit config file path.
        repo_root: Repository root for resolving repo-relative paths.

    Returns:
        Resolved experimentation config.

    Raises:
        FileNotFoundError: If an explicit config path does not exist.
        ValueError: If the YAML payload is not a mapping.
    """
    resolved_config_path = config_path or DEFAULT_CONFIG_PATH
    if not resolved_config_path.exists():
        if config_path is not None:
            raise FileNotFoundError(f"experimentation config not found: {resolved_config_path}")
        payload: dict[str, Any] = {}
    else:
        payload = _load_config_payload(resolved_config_path)

    experiment_payload = _read_section(payload, "experiment")
    extraction_payload = _read_section(payload, "extraction")
    data_payload = _read_section(payload, "data")
    output_payload = _read_section(payload, "output")

    return ExperimentationConfig(
        config_path=resolved_config_path,
        repo_root=repo_root,
        experiment=ExperimentSettings(
            prompt_email_format=_read_str(experiment_payload, "prompt_email_format", "markdown"),
            log_level=_read_str(experiment_payload, "log_level", "INFO").upper(),
            include_candidate_hints=_read_bool(experiment_payload, "include_candidate_hints", False),
        ),
        extraction=ExtractionSettings(
            retry_attempts=_read_int(extraction_payload, "retry_attempts", 3),
            retry_delay_seconds=_read_float(extraction_payload, "retry_delay_seconds", 1.0),
            model=_read_optional_str(extraction_payload, "model"),
        ),
        data=DataSettings(
            manifest_path=_resolve_repo_path(
                _read_str(data_payload, "manifest_path", str(DEFAULT_MANIFEST_PATH.relative_to(REPO_ROOT))),
                repo_root=repo_root,
            ),
            ground_truth_glob=_read_str(data_payload, "ground_truth_glob", DEFAULT_GROUND_TRUTH_GLOB),
        ),
        output=OutputSettings(
            prefill_dir=_resolve_repo_path(
                _read_str(output_payload, "prefill_dir", str(DEFAULT_PREFILL_OUTPUT_ROOT.relative_to(REPO_ROOT))),
                repo_root=repo_root,
            ),
            runs_dir=_resolve_repo_path(
                _read_str(output_payload, "runs_dir", str(RUNS_DIR.relative_to(REPO_ROOT))),
                repo_root=repo_root,
            ),
            search_root=_resolve_repo_path(
                _read_str(output_payload, "search_root", str(OUTPUT_ROOT.relative_to(REPO_ROOT))),
                repo_root=repo_root,
            ),
            summaries_dir=_resolve_repo_path(
                _read_str(output_payload, "summaries_dir", str(SUMMARIES_DIR.relative_to(REPO_ROOT))),
                repo_root=repo_root,
            ),
        ),
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for config validation."""
    parser = argparse.ArgumentParser(
        description="Validate experimentation YAML config and report resolved inputs.",
    )
    parser.add_argument(
        "--config",
        help="Optional experimentation YAML config path.",
    )
    return parser


def main() -> None:
    """Validate the experimentation config and print a JSON summary."""
    args = _build_parser().parse_args()
    config = load_experimentation_config(Path(args.config) if args.config else None)
    print(json.dumps(validate_experimentation_config(config), indent=2))


def apply_config_environment(config: ExperimentationConfig) -> None:
    """Apply non-secret runtime environment overrides from config.

    Args:
        config: Resolved experimentation config.
    """
    model_name = (config.extraction.model or "").strip()
    if model_name and not os.getenv("AZURE_OPENAI_MODEL", "").strip():
        os.environ["AZURE_OPENAI_MODEL"] = model_name


def discover_configured_ground_truth_paths(config: ExperimentationConfig) -> list[Path]:
    """Discover reviewed ground-truth paths using config-provided globbing."""
    return sorted(config.repo_root.glob(config.data.ground_truth_glob))


def load_configured_sample_paths(config: ExperimentationConfig) -> list[Path]:
    """Load recommended sample paths using the configured manifest path."""
    manifest = json.loads(config.data.manifest_path.read_text(encoding="utf-8"))
    return [
        _resolve_repo_path(str(sample["local_path"]), repo_root=config.repo_root)
        for sample in manifest.get("recommended_samples", [])
    ]


def _load_config_payload(config_path: Path) -> dict[str, Any]:
    """Read and validate the YAML config payload."""
    raw_payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw_payload, dict):
        raise ValueError(f"experimentation config must be a mapping: {config_path}")
    return raw_payload


def _read_section(payload: dict[str, Any], section_name: str) -> dict[str, Any]:
    """Return one mapping section from the config payload."""
    section = payload.get(section_name, {})
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise ValueError(f"config section '{section_name}' must be a mapping")
    return section


def _read_str(section: dict[str, Any], key: str, default: str) -> str:
    """Read a required string-like config value with a default."""
    value = section.get(key, default)
    return str(value).strip() if value is not None else default


def _read_optional_str(section: dict[str, Any], key: str) -> str | None:
    """Read an optional string-like config value."""
    value = section.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _read_bool(section: dict[str, Any], key: str, default: bool) -> bool:
    """Read a boolean config value."""
    value = section.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"config value '{key}' must be a boolean")


def _read_int(section: dict[str, Any], key: str, default: int) -> int:
    """Read an integer config value."""
    value = section.get(key, default)
    return int(value)


def _read_float(section: dict[str, Any], key: str, default: float) -> float:
    """Read a float config value."""
    value = section.get(key, default)
    return float(value)


def _resolve_repo_path(path_value: str, *, repo_root: Path) -> Path:
    """Resolve a repo-relative or absolute path from config."""
    candidate = Path(path_value)
    if candidate.is_absolute():
        return candidate
    return repo_root / candidate


if __name__ == "__main__":
    main()
