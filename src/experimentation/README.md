---
title: Experimentation Workflow
description: Lightweight workflow for generating reviewed labels, running extraction evaluations, and comparing model runs.
author: James
ms.date: 2026-05-14
ms.topic: how-to
keywords:
  - experimentation
  - evaluation
  - extraction
  - ground truth
  - yaml config
estimated_reading_time: 5
---

## Experimentation Workflow

This area holds the lightweight extraction evaluation workflow. It is built for a small reviewed sample set, repeatable model comparisons, and simple outputs that are easy to inspect.

## Which doc to use

Use this README for the day-to-day workflow: where files live, which commands to run, and what outputs to expect.

Use `docs/design/extraction_evaluation.md` for the evaluation scope, field priorities, metrics, and the longer-term plan. That document explains why we evaluate this way. This README explains how to run the current workflow in the repository.

## Prerequisites

Before you run the experimentation workflow, make sure these pieces are in place:

- The project virtual environment exists and dependencies are installed.
- The communicator app local settings are configured, because the evaluation scripts reuse the same extraction path and model settings.
- You are authenticated for any cloud-backed extraction dependencies that your local settings expect.

The default model comes from `src/communicator_app/src/local.settings.json` unless you override it with `MODEL=...` when using the task.

## First use

If you are picking this workflow up for the first time, use this short sequence:

1. Make sure the virtual environment, communicator local settings, and required auth are already working.
1. Verify the current config and discovered inputs:

```bash
task experiment:config:validate
```

1. If you are working with the reviewed dataset, start with the normal end-to-end run:

```bash
task experiment:ground-truth:run
```

1. Use `task experiment:ground-truth:prefill` first only when you are creating or refreshing candidate labels before review.

Use the ground-truth tasks when you want repeatable evaluation output against checked-in labels, plus refreshed summary CSVs for comparison across runs.

## Config file

The experimentation workflow now reads defaults from
`src/experimentation/config/experimentation.yaml`.

The config file controls four groups of settings:

- Shared experiment settings such as `prompt_email_format`, `log_level`, and `include_candidate_hints`
- Extraction retry policy and an optional model override
- Dataset discovery paths such as the manifest path and ground-truth glob
- Output locations for prefill output, evaluation runs, and summaries

Paths in the YAML file are resolved relative to the repository root.

Use the checked-in config as the default baseline. Override it with `CONFIG=...`
for tasks when you need a different experiment profile. The underlying CLIs
still accept `--config` when you need to call them directly.

## Main files

- `src/experimentation/src/experimentation/prefill_ground_truth.py` generates candidate labels and a rendered email artifact for review.
- `src/experimentation/src/experimentation/evaluate_ground_truth.py` reruns extraction on reviewed samples and writes a per-run evaluation report.
- `src/experimentation/src/experimentation/summarize_ground_truth_runs.py` scans evaluation reports and writes comparison CSVs.
- `src/experimentation/src/experimentation/config.py` loads and resolves the shared experimentation YAML config.
- `src/experimentation/src/experimentation/paths.py` holds the shared naming, discovery, and run-layout helpers.
- `src/experimentation/src/experimentation/evaluation.py` holds the shared field projection and evaluation helpers.
- `src/experimentation/config/experimentation.yaml` stores the checked-in workflow defaults.

## Directory map

The active experimentation directories are:

- `src/experimentation/data/blob_seed_samples/` for reviewed sample inputs
- `src/experimentation/output/ground_truth/prefill/` for candidate-generation artifacts
- `src/experimentation/output/ground_truth/runs/` for per-run evaluation outputs
- `src/experimentation/output/ground_truth/summaries/` for comparison CSVs

## Sample data

> [!IMPORTANT]
> The `src/experimentation/data/blob_seed_samples/` directory is intentionally
> empty in the public repository. Author your own reviewed samples (each as a
> sample directory described below) before running the prefill or evaluation
> tasks. The harness discovers every sample directory under the configured
> `data_root`; no further configuration is needed once your samples land there.

Reviewed samples live under `src/experimentation/data/blob_seed_samples/`.

Each sample directory can contain these files:

- `email.json`
- `ground_truth.json`
- `ground_truth_candidate.json`
- `ground_truth_email.txt`

## Workflow map

This is the normal ground-truth workflow from config and sample inputs to run
outputs and summary CSVs.

![Ground Truth Workflow](assets/ground-truth-workflow.drawio.png)

## Typical workflow

1. Generate or refresh candidates when you need a new review set.
1. Review the candidate JSON and rendered email, then save the final labels to `ground_truth.json`.
1. Run evaluation to create a timestamped report under `src/experimentation/output/ground_truth/runs/`.
1. Regenerate summary CSVs to compare runs.

In practice, that usually looks like this:

1. Run the prefill task only when you are creating or refreshing candidate labels.
1. Edit the checked-in sample files under `src/experimentation/data/blob_seed_samples/` until the reviewed values in `ground_truth.json` are correct.
1. Run `task experiment:ground-truth:run` to create a new evaluation run and refresh the summary tables.
1. Open `runs_summary.csv`, `field_metrics.csv`, and `sample_diffs.csv` to compare models or investigate failures.

## Commands

Run the full evaluation and summary flow with the checked-in config:

```bash
task experiment:ground-truth:run
```

Generate candidate labels from the configured seed samples:

```bash
task experiment:ground-truth:prefill
```

Run evaluation or summarization separately:

```bash
task experiment:ground-truth:evaluate
task experiment:ground-truth:summarize
```

Validate the current config:

```bash
task experiment:config:validate
```

Run the same flow against another configured deployment:

```bash
MODEL=gpt-4.1 task experiment:ground-truth:run
```

Run the same flow against a different config file:

```bash
CONFIG=path/to/experimentation.yaml task experiment:ground-truth:run
```

> [!IMPORTANT]
> The YAML config should contain workflow defaults, paths, and non-secret model
> selection only. Keep credentials and authentication settings in environment
> variables or local settings.

## Outputs

Evaluation runs are written to `src/experimentation/output/ground_truth/runs/`.

Each evaluation run includes:

- `comparison_report.json` as the aggregate extraction report for the evaluated sample set
- `evaluation_report.json` as the scored run report
- one sample directory per reviewed input with `comparison.json`
- per-sample `formatted_email.txt`
- per-sample `extraction.json` or `extraction_error.json`

Summary CSVs are written to `src/experimentation/output/ground_truth/summaries/`:

- `runs_summary.csv`
- `field_metrics.csv`
- `sample_diffs.csv`

## Complement to the design doc

The two documents are intended to be complementary:

- `docs/design/extraction_evaluation.md` is the design and planning document.
- `src/experimentation/README.md` is the practical operator guide for the current implementation.

If the workflow here changes, update this README first. If the evaluation scope, metrics, or longer-term direction changes, update the design document.
