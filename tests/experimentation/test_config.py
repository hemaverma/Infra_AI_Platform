"""Tests for experimentation config loading and discovery."""

import json
from pathlib import Path

import experimentation.config as config_module


def test_load_experimentation_config_reads_yaml_and_resolves_paths(tmp_path: Path) -> None:
    """Test config loading resolves repo-relative paths from YAML."""
    config_path = tmp_path / "experimentation.yaml"
    config_path.write_text(
        "\n".join(
            [
                "version: 1",
                "experiment:",
                "  prompt_email_format: xml",
                "  log_level: warning",
                "  include_candidate_hints: true",
                "extraction:",
                "  retry_attempts: 7",
                "  retry_delay_seconds: 3.5",
                "  model: gpt-config",
                "data:",
                "  manifest_path: configs/manifest.json",
                "  ground_truth_glob: samples/**/ground_truth.json",
                "output:",
                "  prefill_dir: outputs/prefill",
                "  runs_dir: outputs/runs",
                "  search_root: outputs",
                "  summaries_dir: outputs/summaries",
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = config_module.load_experimentation_config(config_path, repo_root=tmp_path)

    assert config.experiment.prompt_email_format == "xml"
    assert config.experiment.log_level == "WARNING"
    assert config.experiment.include_candidate_hints is True
    assert config.extraction.retry_attempts == 7
    assert config.extraction.retry_delay_seconds == 3.5
    assert config.extraction.model == "gpt-config"
    assert config.data.manifest_path == tmp_path / "configs" / "manifest.json"
    assert config.output.prefill_dir == tmp_path / "outputs" / "prefill"
    assert config.output.summaries_dir == tmp_path / "outputs" / "summaries"


def test_apply_config_environment_only_fills_missing_model(
    monkeypatch,
    make_experimentation_config,
) -> None:
    """Test config model is applied only when the runtime environment is unset."""
    config = make_experimentation_config(model="gpt-config")

    monkeypatch.delenv("AZURE_OPENAI_MODEL", raising=False)
    config_module.apply_config_environment(config)
    assert config_module.os.getenv("AZURE_OPENAI_MODEL") == "gpt-config"

    monkeypatch.setenv("AZURE_OPENAI_MODEL", "from-env")
    config_module.apply_config_environment(config)
    assert config_module.os.getenv("AZURE_OPENAI_MODEL") == "from-env"


def test_config_discovery_helpers_use_repo_root(tmp_path: Path, make_experimentation_config) -> None:
    """Test config discovery helpers scan from the configured repo root."""
    manifest_path = tmp_path / "configs" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        '{"recommended_samples": [{"local_path": "samples/a/email.json"}]}\n',
        encoding="utf-8",
    )

    email_path = tmp_path / "samples" / "a" / "email.json"
    email_path.parent.mkdir(parents=True, exist_ok=True)
    email_path.write_text("{}\n", encoding="utf-8")

    ground_truth_path = tmp_path / "samples" / "a" / "ground_truth.json"
    ground_truth_path.write_text("{}\n", encoding="utf-8")

    config = make_experimentation_config(
        manifest_path=manifest_path,
        ground_truth_glob="samples/**/ground_truth.json",
    )

    assert config_module.load_configured_sample_paths(config) == [email_path]
    assert config_module.discover_configured_ground_truth_paths(config) == [ground_truth_path]


def test_validate_experimentation_config_reports_discovery_counts(
    tmp_path: Path,
    make_experimentation_config,
) -> None:
    """Test config validation reports resolved paths and discovery counts."""
    manifest_path = tmp_path / "configs" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        '{"recommended_samples": [{"local_path": "samples/a/email.json"}]}' "\n",
        encoding="utf-8",
    )

    sample_dir = tmp_path / "samples" / "a"
    sample_dir.mkdir(parents=True, exist_ok=True)
    (sample_dir / "email.json").write_text("{}\n", encoding="utf-8")
    (sample_dir / "ground_truth.json").write_text("{}\n", encoding="utf-8")
    config = make_experimentation_config(
        manifest_path=manifest_path,
        ground_truth_glob="samples/**/ground_truth.json",
    )

    summary = config_module.validate_experimentation_config(config)

    assert summary["config_path"] == str(tmp_path / "experimentation.yaml")
    assert summary["data"]["manifest_path"] == str(manifest_path)
    assert summary["data"]["recommended_sample_count"] == 1
    assert summary["data"]["ground_truth_count"] == 1


def test_config_main_prints_validation_summary(
    tmp_path: Path,
    monkeypatch,
    capsys,
    set_cli_args,
) -> None:
    """Test the config CLI prints the validation summary as JSON."""
    load_config = config_module.load_experimentation_config
    config_path = tmp_path / "experimentation.yaml"
    manifest_path = tmp_path / "configs" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        '{"recommended_samples": [{"local_path": "samples/a/email.json"}]}' "\n",
        encoding="utf-8",
    )
    sample_dir = tmp_path / "samples" / "a"
    sample_dir.mkdir(parents=True, exist_ok=True)
    (sample_dir / "email.json").write_text("{}\n", encoding="utf-8")
    (sample_dir / "ground_truth.json").write_text("{}\n", encoding="utf-8")
    config_path.write_text(
        "\n".join(
            [
                "data:",
                "  manifest_path: configs/manifest.json",
                "  ground_truth_glob: samples/**/ground_truth.json",
                "",
            ]
        ),
        encoding="utf-8",
    )

    set_cli_args("config.py", "--config", str(config_path))
    monkeypatch.setattr(
        config_module,
        "load_experimentation_config",
        lambda path=None: load_config(path, repo_root=tmp_path),
    )

    config_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["config_path"] == str(config_path)
    assert payload["data"]["recommended_sample_count"] == 1
    assert payload["data"]["ground_truth_count"] == 1
