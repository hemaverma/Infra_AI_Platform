"""Path and layout helpers for experimentation workflows."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

COMPONENT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[4]
OUTPUT_ROOT = COMPONENT_ROOT / "output"
DEFAULT_MANIFEST_PATH = COMPONENT_ROOT / "data" / "blob_seed_samples" / "manifest.json"
GROUND_TRUTH_ROOT = OUTPUT_ROOT / "ground_truth"
DEFAULT_PREFILL_OUTPUT_ROOT = GROUND_TRUTH_ROOT / "prefill"
RUNS_DIR = GROUND_TRUTH_ROOT / "runs"
SUMMARIES_DIR = GROUND_TRUTH_ROOT / "summaries"
GROUND_TRUTH_FILE_NAME = "ground_truth.json"
CANDIDATE_FILE_NAME = "ground_truth_candidate.json"
REVIEW_EMAIL_FILE_NAME = "ground_truth_email.txt"
EVALUATION_REPORT_FILE_NAME = "evaluation_report.json"
LEGACY_EVALUATION_REPORT_FILE_NAME = "stage1_evaluation_report.json"
COMMUNICATOR_LOCAL_SETTINGS_PATH = REPO_ROOT / "src" / "communicator_app" / "src" / "local.settings.json"


def discover_ground_truth_paths(repo_root: Path = REPO_ROOT) -> list[Path]:
    """Return reviewed ground-truth files under the seed sample directory.

    Args:
        repo_root: Repository root used to resolve the sample directory.

    Returns:
        Sorted list of reviewed ground-truth file paths.
    """
    sample_root = repo_root / "src" / "experimentation" / "data" / "blob_seed_samples"
    return sorted(sample_root.glob(f"**/{GROUND_TRUTH_FILE_NAME}"))


def load_recommended_sample_paths(manifest_path: Path = DEFAULT_MANIFEST_PATH) -> list[Path]:
    """Load recommended staged email sample paths from the seed manifest.

    Args:
        manifest_path: Path to the seed sample manifest.

    Returns:
        Absolute staged sample paths.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [REPO_ROOT / Path(sample["local_path"]) for sample in manifest.get("recommended_samples", [])]


def resolve_configured_llm_model(
    local_settings_path: Path = COMMUNICATOR_LOCAL_SETTINGS_PATH,
) -> str | None:
    """Return the configured extraction model from the environment or local settings.

    Args:
        local_settings_path: Communicator local settings file.

    Returns:
        Configured model name when available.
    """
    model_name = os.getenv("AZURE_OPENAI_MODEL", "").strip()
    if model_name:
        return model_name

    if not local_settings_path.exists():
        return None

    payload = json.loads(local_settings_path.read_text(encoding="utf-8"))
    configured_model = str(payload.get("Values", {}).get("AZURE_OPENAI_MODEL", "")).strip()
    return configured_model or None


def build_run_output_dir(
    prompt_email_format: str,
    *,
    llm_model: str | None = None,
    now: datetime | None = None,
    runs_dir: Path = RUNS_DIR,
) -> Path:
    """Build a unique canonical output directory for one evaluation run.

    Args:
        prompt_email_format: Render format used for the prompt email packet.
        llm_model: Optional explicit model name. Defaults to the configured model.
        now: Optional current time override for deterministic tests.
        runs_dir: Parent directory that stores individual run folders.

    Returns:
        Unique run output directory path.
    """
    model_name = llm_model or resolve_configured_llm_model() or "unknown-model"
    current_time = now or datetime.now(timezone.utc)
    timestamp = current_time.strftime("%Y%m%d-%H%M%S")
    base_name = (
        f"{timestamp}__{_slugify_run_component(model_name)}"
        f"__{_slugify_run_component(prompt_email_format)}"
    )
    return _ensure_unique_path(runs_dir / base_name)


def discover_evaluation_reports(search_root: Path = OUTPUT_ROOT) -> list[Path]:
    """Discover evaluation reports under the experimentation output tree.

    Args:
        search_root: Output tree to scan.

    Returns:
        Sorted report paths.
    """
    reports = {
        *search_root.glob(f"**/{EVALUATION_REPORT_FILE_NAME}"),
        *search_root.glob(f"**/{LEGACY_EVALUATION_REPORT_FILE_NAME}"),
    }
    return sorted(report_path for report_path in reports if SUMMARIES_DIR not in report_path.parents)


def build_run_id(output_root: Path) -> str:
    """Return the stable identifier for a run directory.

    Args:
        output_root: Output directory for one run.

    Returns:
        Run identifier.
    """
    return output_root.name


def build_run_created_at(now: datetime | None = None) -> str:
    """Return an ISO timestamp for one run record.

    Args:
        now: Optional current time override for deterministic tests.

    Returns:
        UTC ISO timestamp.
    """
    current_time = now or datetime.now(timezone.utc)
    return current_time.isoformat().replace("+00:00", "Z")


def _slugify_run_component(value: str) -> str:
    """Normalize a run-path component while keeping dots and hyphens readable."""
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return normalized or "unknown"


def _ensure_unique_path(path: Path) -> Path:
    """Return a unique path by appending a numeric suffix when needed."""
    if not path.exists():
        return path

    for suffix in range(2, 1000):
        candidate = path.with_name(f"{path.name}-{suffix}")
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"unable to allocate unique run path under {path.parent}")
