"""Shared pytest helpers for experimentation tests."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import pytest

from experimentation.config import (
    DataSettings,
    ExperimentationConfig,
    ExperimentSettings,
    ExtractionSettings,
    OutputSettings,
)


@pytest.fixture
def make_experimentation_config(tmp_path: Path) -> Callable[..., ExperimentationConfig]:
    """Build a test experimentation config with simple override points."""

    def factory(
        *,
        prompt_email_format: str = "markdown",
        log_level: str = "INFO",
        include_candidate_hints: bool = False,
        retry_attempts: int = 3,
        retry_delay_seconds: float = 1.0,
        model: str | None = None,
        manifest_path: Path | None = None,
        ground_truth_glob: str = "**/ground_truth.json",
        prefill_dir: Path | None = None,
        runs_dir: Path | None = None,
        search_root: Path | None = None,
        summaries_dir: Path | None = None,
    ) -> ExperimentationConfig:
        return ExperimentationConfig(
            config_path=tmp_path / "experimentation.yaml",
            repo_root=tmp_path,
            experiment=ExperimentSettings(
                prompt_email_format=prompt_email_format,
                log_level=log_level,
                include_candidate_hints=include_candidate_hints,
            ),
            extraction=ExtractionSettings(
                retry_attempts=retry_attempts,
                retry_delay_seconds=retry_delay_seconds,
                model=model,
            ),
            data=DataSettings(
                manifest_path=manifest_path or tmp_path / "manifest.json",
                ground_truth_glob=ground_truth_glob,
            ),
            output=OutputSettings(
                prefill_dir=prefill_dir or tmp_path / "prefill-output",
                runs_dir=runs_dir or tmp_path / "runs-output",
                search_root=search_root or tmp_path / "search-root",
                summaries_dir=summaries_dir or tmp_path / "summaries-output",
            ),
        )

    return factory


@pytest.fixture
def set_cli_args(monkeypatch) -> Callable[..., None]:
    """Set command-line arguments for CLI-oriented tests."""

    def setter(script_name: str, *args: str) -> None:
        monkeypatch.setattr(sys, "argv", [script_name, *args])

    return setter
