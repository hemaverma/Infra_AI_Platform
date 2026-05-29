---
title: Extraction Evaluation Plan
description: Simple guidance for evaluating email extraction quality, building ground truth, and using HITL feedback to improve measurement over time.
author: NExT team
ms.date: 2026-05-15
ms.topic: how-to
keywords:
  - evaluation
  - extraction
  - llm
  - hitl
  - ground truth
estimated_reading_time: 5
---

## Purpose

We want a simple way to measure how well the system extracts useful
information from vendor emails.

This plan treats extraction schema outputs as the primary evaluation target.

Stage 1 should focus on extraction schema outputs, because we can evaluate
them directly before we have reliable email-to-VMS mapping data. Once the
production workflow is running, the VMS HITL gate can be used to curate
reviewed ground truth for the source extraction fields that drive downstream
VMS parameters. The target is still extraction quality, not the VMS
parameters themselves.

The immediate goal is to build a repeatable baseline, not to set hard pass or
fail thresholds.

## Stage 1

Stage 1 should be narrow and focus on the highest-value fields in the current
schema.

Recommended Stage 1 fields:

- `intent`
- `vendor_name`
- `vendor_ticket_id`
- `customer_ticket_ids`
- `windows`, especially `start`, `end`, `timezone_normalized`, and `kind`
- `assets`, especially `circuit_ids`
- `impact_category`

Stage 1 should use a manually reviewed dataset, even if the first draft of the
labels is prefilled by an LLM. A human should confirm the final ground truth.

The main outputs of Stage 1 should be:

- Field-level accuracy results for the priority fields
- A small error taxonomy, such as missing value, wrong value, partial match,
  wrong normalization, or hallucinated value
- A short list of the most common failure patterns

## Stage 2

Stage 2 can expand the scope after the team has a baseline.

Recommended Stage 2 additions:

- Broader coverage of schema fields such as `work_short_description`,
  `work_description`, `other_references`, `scopes`, `notes`,
  `intent_reasoning`, and `impact_reasoning`
- Use of reviewed operator HITL outcomes to expand and verify extraction-field
  ground truth
- Breakdown by vendor, attachment type, email format, and complexity
- Ongoing measurement using new reviewed HITL examples

Stage 2 should also compare extraction quality to downstream business impact.
For example, a small wording difference may not matter, while a wrong window or
wrong asset identifier matters a great deal.

## Metrics by Field Type

Different fields need different metrics. One metric is usually not enough.

| Field type | Schema examples | Recommended metrics |
|---|---|---|
| Categorical fields | `intent`, `impact_category`, `windows[].kind`, `assets[].type` | Exact match, accuracy |
| IDs and codes | `vendor_ticket_id`, `customer_ticket_ids`, `assets[].value` | Exact match, normalized exact match, Levenshtein distance |
| Dates and times | `windows[].start`, `windows[].end`, `windows[].timezone_normalized` | Exact match after normalization, absolute time difference |
| Lists or sets | `customer_ticket_ids`, assets, windows | Precision, recall, F1, set overlap |
| Short text | `vendor_name`, `work_short_description` | Exact match where realistic, Levenshtein distance, or vector similarity |
| Long text | `work_description`, reasoning fields, `notes` | Vector similarity, Levenshtein distance, LLM-judge |

For this project, the most useful starting metrics are:

- Exact match for enums and IDs
- Normalized exact match for dates, times, and formatted identifiers
- Precision and recall for list fields
- Absolute time difference for maintenance windows
- Levenshtein distance only as a secondary metric for text fields

Vector similarity can be useful for long text comparisons, but it should not
be the primary metric for operational fields.

## Sampling Guidance

The sample should be chosen to represent the real email population, not only
the easiest cases.

Recommended starting sample sizes:

- Stage 1 pilot: 30 to 50 emails
- Stage 1 baseline: 100 to 150 emails
- Stage 2 expanded baseline: 200 or more emails, especially if the team wants
  vendor-level or format-level breakdowns

Sampling should include a mix of:

- Different vendors
- Different email structures, such as plain text, HTML-heavy, and attachment-heavy
- Different complexity levels, such as simple notices versus long threads
- Different extraction outcomes, including obvious successes and borderline cases

If possible, use stratified sampling rather than pure random sampling. A simple
approach is to intentionally split the sample across a few important buckets,
then sample within each bucket.

Good example buckets:

- Vendor
- Attachment presence
- Presence of tables
- Single-window versus multi-window notices
- Whether the email eventually required meaningful HITL correction

## Ground Truth Strategy

Ground truth for extraction schema outputs will likely need to be created
manually at first.

Recommended approach:

1. Start with a small set of representative emails.
1. Let the LLM prefill a candidate label set if that saves time.
1. Have a human reviewer confirm or correct every field.
1. Record a short note when the field was ambiguous.

If historical VMS command data can be reliably mapped back to source emails,
that data can help cross-check reviewed labels. The more useful long-term
ground-truth source is the reviewed extraction state captured at the VMS HITL
gate, because it verifies the source fields that produced the downstream VMS
parameters. Those HITL-reviewed examples still need to be sampled so they are
representative of the broader email population, not only the easiest or most
frequently corrected cases.

## How HITL Helps

The HITL path is one of the best opportunities to create high-quality ground
truth over time.

When an operator reviews extracted data, proposed commands, or drafted content,
their edits and approvals can be treated as reviewed labels for the source
extraction fields behind the downstream action.

This is useful because it can:

- Reduce the amount of separate annotation work
- Capture realistic edge cases from production-like traffic
- Show which errors actually matter to operators
- Create an ongoing evaluation loop instead of a one-time study

## Recommended Next Step

Start with a Stage 1 pilot of 30 to 50 emails focused on the highest-value
fields, build a simple reviewed ground-truth set, and measure a small number of
clear metrics. After that, use HITL-reviewed or manually curated examples to grow the dataset and expand into Stage 2.
