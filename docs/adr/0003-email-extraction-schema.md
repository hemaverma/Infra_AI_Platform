# Email Extraction Schema

- Status: accepted
- Deciders: team
- Date: 2026-05-01

## Context and Problem Statement

This decision should optimize for three things first:

- intent of the email
- vendor references and affected asset IDs
- related time windows

Lean is the smallest and easiest option. Balanced adds structure for grouped
assets and flat windows without taking on the full operational model. General
is the broadest option and carries the highest prompt and validation burden.

## Decision Drivers

All three options below follow the same baseline rules.

- Keep source extraction separate from downstream CHG planning.
- Preserve raw time text alongside normalized timestamps.
- Keep vendor ticket references and customer-side ticket references separate from
  circuits, sites, aliases, and generic secondary references.
- Allow multiple references and multiple windows.
- Treat attachments as an input surface, not as a separate schema family.
- Keep extraction completeness metadata separate from the core business payload.
- Prefer an internal impact enum that maps deterministically to the VMS target
  enum instead of relying on fuzzy downstream matching.
- If the extractor reports confidence, use a coarse 1-5 scale rather than
  pseudo-probability decimals.

## Considered Options

- Lean
- Balanced
- General

### Option 1: Lean

This is the smallest schema that can still handle most planned maintenance
emails.

It assumes the email describes one source notice with one shared primary window
across all affected assets, plus optional alternate or backup windows.

```json
{
  "schema_version": "1.0",
  "intent": "create|update|cancel|informational|unknown",
  "vendor_name": "Vendor A",
  "vendor_ticket_id": "NCC-24173",
  "customer_ticket_ids": [],
  "work_short_description": "fiber splice repair",
  "work_description": "Splice repair on damaged fiber segment.",
  "other_references": [],
  "assets": [
    {
      "type": "circuit|site_id|alias_id|other",
      "value": "/KRE-/0000006765//XCI/"
    }
  ],
  "primary_window_start": "2026-04-25T04:00:00",
  "primary_window_end": "2026-04-25T08:00:00",
  "primary_window_start_raw": "2026-04-25 04:00:00 UTC",
  "primary_window_end_raw": "2026-04-25 08:00:00 UTC",
  "primary_window_timezone_raw": "UTC",
  "additional_windows": [],
  "notes": []
}
```

### Lean Fields

| Field | Description |
|---|---|
| `schema_version` | Version marker for the extraction contract |
| `intent` | High-level action conveyed by the email |
| `vendor_name` | Vendor name exactly or nearly as stated in the notice |
| `vendor_ticket_id` | Primary vendor maintenance or case reference |
| `customer_ticket_ids` | List of customer-side ticket or change references mentioned in the email |
| `work_short_description` | Brief summary of the planned work |
| `work_description` | Longer plain-language work description |
| `other_references` | Additional identifiers mentioned in the email that are neither the primary vendor ticket nor the primary customer-side tickets |
| `assets[]` | List of affected asset identifiers extracted from the email or attachments |
| `assets[].type` | Identifier type for the asset value |
| `assets[].value` | Raw asset identifier as stated by the vendor |
| `primary_window_start` | Normalized start timestamp for the main window |
| `primary_window_end` | Normalized end timestamp for the main window |
| `primary_window_start_raw` | Raw source text for the start time |
| `primary_window_end_raw` | Raw source text for the end time |
| `primary_window_timezone_raw` | Timezone text exactly as stated in the source |
| `additional_windows` | Other windows mentioned, such as alternates or backups |
| `notes` | Freeform extraction notes that do not fit a structured field |

### Pros

- Small prompt target.
- Easy to inspect in traces.
- Easy to compare against the legacy 15-key output.
- Good fit for vendors that send one ticket, one work scope, and one shared
  maintenance window.
- Low implementation cost.

### Cons

- Intent may be too coarse for some real inbox paths.
- No explicit place for per-asset or per-group windows.
- No explicit grouping when different subsets of assets behave differently.
- Limited support for informational notifications versus vendor inquiries.
- Assumes one operative vendor ticket without much structure for secondary
  references.

### Assumptions

- One email usually describes one maintenance notice.
- All assets in the email share the same main window.
- Extra windows are alternates or backups, not separate scoped windows.
- Attachments mainly contribute more asset IDs, not independent work scopes.

### Option 2: Balanced

This is the middle ground.

It keeps the schema compact, but adds the missing structure needed for cases
where different asset subsets or different windows appear in the same email.

```json
{
  "schema_version": "1.0",
  "intent": "create_new|reschedule|add_assets|remove_assets|cancel|informational|inquiry|unknown",
  "intent_confidence": 4,
  "intent_reasoning": "Subject and body describe an updated maintenance notice with a changed schedule.",
  "vendor_name": "Vendor A",
  "vendor_ticket_id": "NCC-24173",
  "customer_ticket_ids": ["CR-0001"],
  "work_short_description": "fiber splice repair",
  "work_description": "Splice repair on damaged fiber segment.",
  "other_references": [],
  "windows": [
    {
      "window_id": "window-1",
      "kind": "primary|alternate|backup|rescheduled",
      "start": "2026-04-25T04:00:00",
      "end": "2026-04-25T08:00:00",
      "start_raw": "2026-04-25 04:00:00 UTC",
      "end_raw": "2026-04-25 08:00:00 UTC",
      "timezone_raw": "UTC"
    }
  ],
  "assets": [
    {
      "asset_id": "asset-1",
      "type": "circuit|site_id|alias_id|other",
      "value": "/KRE-/0000006765//XCI/"
    }
  ],
  "scopes": [
    {
      "scope_id": "scope-1",
      "asset_refs": ["asset-1"],
      "window_refs": ["window-1"],
      "location_hints": ["Denver"]
    }
  ],
  "impact_category": "outage|degradation_no_impact_due_to_redundancy|degradation_reduced_capacity|no_impact|regulatory_impact|unknown",
  "impact_confidence": 4,
  "impact_reasoning": "The email explicitly states a potential outage window for the affected service.",
  "impact_raw_text": "Up to 60-minute outage possible",
  "notes": []
}
```

### Balanced Fields

| Field | Description |
|---|---|
| `schema_version` | Version marker for the extraction contract |
| `intent` | More specific action conveyed by the email |
| `intent_confidence` | Coarse 1-5 confidence score for the intent classification |
| `intent_reasoning` | Short explanation for why the extractor chose the intent |
| `vendor_name` | Vendor name exactly or nearly as stated in the notice |
| `vendor_ticket_id` | Primary vendor maintenance or case reference |
| `customer_ticket_ids` | List of customer-side ticket or change references mentioned in the email |
| `work_short_description` | Brief summary of the planned work |
| `work_description` | Longer plain-language work description |
| `other_references` | Additional identifiers mentioned in the email that may matter downstream but are not the primary vendor or customer-side tickets |
| `windows[]` | All explicit maintenance windows found in the email |
| `windows[].window_id` | Stable local identifier used to reference a window elsewhere in the payload |
| `windows[].kind` | Relationship of the window to the notice, such as primary or backup |
| `windows[].start` | Normalized start timestamp for the window |
| `windows[].end` | Normalized end timestamp for the window |
| `windows[].start_raw` | Raw source text for the start time |
| `windows[].end_raw` | Raw source text for the end time |
| `windows[].timezone_raw` | Timezone text exactly as stated in the source |
| `assets[]` | List of affected asset identifiers extracted from the email or attachments |
| `assets[].asset_id` | Stable local identifier used to reference an asset elsewhere in the payload |
| `assets[].type` | Identifier type for the asset value |
| `assets[].value` | Raw asset identifier as stated by the vendor |
| `scopes[]` | Groupings that connect subsets of assets to specific windows or locations |
| `scopes[].scope_id` | Stable local identifier for the grouped scope |
| `scopes[].asset_refs` | References to the assets that belong to the scope |
| `scopes[].window_refs` | References to the windows that apply to the scope |
| `scopes[].location_hints` | Freeform location text associated with the scope |
| `impact_category` | Normalized service-impact classification designed to map directly to the VMS impact enum, with `unknown` reserved for manual review |
| `impact_confidence` | Coarse 1-5 confidence score for the impact classification |
| `impact_reasoning` | Short explanation for why the extractor chose the impact |
| `impact_raw_text` | Raw source text describing expected service impact |
| `notes` | Freeform extraction notes that do not fit a structured field |

### Pros

- Handles the core real-world problem of multiple windows or grouped assets.
- Keeps the important pieces first-class: intent, references, assets, windows.
- Adds inspectable confidence and reasoning for both intent and impact.
- Keeps impact categories close enough to the VMS target for deterministic mapping.
- Still much smaller than the full `EmailExtraction` design.
- Supports attachments that provide row-level assets and windows.
- Gives downstream code enough structure to derive market-based CHGs cleanly.

### Cons

- Slightly harder to prompt and validate than the lean option.
- Introduces IDs and references inside the extraction payload.
- Some vendors will produce flat outputs, so `scopes` may often be sparse.
- Secondary references still need a small companion structure if they matter.

### Assumptions

- One email still usually represents one source notice.
- If the email contains multiple groupings, they can be represented as a small
  set of scopes.
- Market split still happens after extraction.
- Contact and reply workflow details can remain outside the core extraction
  contract for now.

### Option 3: General

This follows the broader extraction model while trimming parts that are likely
too heavy for the first production extractor.

The idea is to keep the major sections, but reduce the number of fields and
defer less-critical operational details.

```json
{
  "schema_version": "1.0",
  "vendor_name_as_stated": "Uniti Fiber",
  "vendor_name_normalized": "Uniti Fiber",
  "primary_intent": "create_new_maintenance|reschedule_existing|add_assets_to_existing|cancel_existing|informational_started|informational_completed|informational_incident|inquiry_from_vendor|human_reply|unknown",
  "primary_intent_confidence": 5,
  "primary_intent_reasoning": "Subject and body indicate a new planned maintenance notice with no prior customer-side change reference.",
  "vendor_ticket_id": "NCC-24173",
  "vendor_ticket_id_raw": "NCC-24173",
  "customer_ticket_ids": [],
  "prior_references": [],
  "work_short_description": "fiber splice repair",
  "work_description": "Splice repair on damaged fiber segment.",
  "windows": [
    {
      "window_id": "window-1",
      "kind": "primary|alternate|backup|rescheduled",
      "start": "2026-04-25T04:00:00Z",
      "end": "2026-04-25T08:00:00Z",
      "start_raw": "2026-04-25 04:00:00 UTC",
      "end_raw": "2026-04-25 08:00:00 UTC",
      "timezone_raw": "UTC"
    }
  ],
  "recurrence": null,
  "impact_category": "outage|degradation_no_impact_due_to_redundancy|degradation_reduced_capacity|no_impact|regulatory_impact|unknown",
  "impact_raw_text": "Up to 60-minute outage possible",
  "impact_duration_raw": "Up to 60 minutes",
  "assets": [
    {
      "asset_id": "asset-1",
      "type": "circuit|site_id|alias_id|evc_id|other",
      "value": "/KRE-/0000006765//XCI/",
      "source": "body|attachment|subject"
    }
  ],
  "scopes": [
    {
      "scope_id": "scope-1",
      "asset_refs": ["asset-1"],
      "window_refs": ["window-1"],
      "location_hints": ["Birmingham, AL", "Atlanta, GA"]
    }
  ],
  "attachments_present": true,
  "primary_data_attachment": "maintenance.csv",
  "extraction_status": "complete|partial|ambiguous",
  "overall_confidence": 4,
  "ambiguities": [],
  "warnings": []
}
```

### General Fields

| Field | Description |
|---|---|
| `schema_version` | Version marker for the extraction contract |
| `vendor_name_as_stated` | Vendor name as written in the source email |
| `vendor_name_normalized` | Canonical vendor name used for downstream consistency |
| `primary_intent` | Detailed workflow intent inferred from the email |
| `primary_intent_confidence` | Coarse 1-5 confidence score for the intent classification |
| `primary_intent_reasoning` | Short explanation for why the extractor chose the intent |
| `vendor_ticket_id` | Parsed vendor maintenance or case reference |
| `vendor_ticket_id_raw` | Raw source text for the vendor reference |
| `customer_ticket_ids` | List of customer-side ticket or change references mentioned in the email |
| `prior_references` | Older related identifiers mentioned in the thread |
| `work_short_description` | Brief summary of the planned work |
| `work_description` | Longer plain-language work description |
| `windows[]` | All explicit maintenance windows found in the email |
| `windows[].window_id` | Stable local identifier used to reference a window elsewhere in the payload |
| `windows[].kind` | Relationship of the window to the notice, such as primary or rescheduled |
| `windows[].start` | Normalized start timestamp for the window |
| `windows[].end` | Normalized end timestamp for the window |
| `windows[].start_raw` | Raw source text for the start time |
| `windows[].end_raw` | Raw source text for the end time |
| `windows[].timezone_raw` | Timezone text exactly as stated in the source |
| `recurrence` | Recurrence details if the notice describes a repeating schedule |
| `impact_category` | Normalized service-impact classification designed to map directly to the VMS impact enum, with `unknown` reserved for manual review |
| `impact_raw_text` | Raw source text describing expected service impact |
| `impact_duration_raw` | Raw duration text associated with the impact statement |
| `assets[]` | List of affected asset identifiers extracted from the email or attachments |
| `assets[].asset_id` | Stable local identifier used to reference an asset elsewhere in the payload |
| `assets[].type` | Identifier type for the asset value |
| `assets[].value` | Raw asset identifier as stated by the vendor |
| `assets[].source` | Where the asset was found, such as the subject, body, or an attachment |
| `scopes[]` | Groupings that connect subsets of assets to specific windows or locations |
| `scopes[].scope_id` | Stable local identifier for the grouped scope |
| `scopes[].asset_refs` | References to the assets that belong to the scope |
| `scopes[].window_refs` | References to the windows that apply to the scope |
| `scopes[].location_hints` | Freeform location text associated with the scope |
| `attachments_present` | Indicates whether the email included attachments |
| `primary_data_attachment` | Attachment most likely to carry the main asset or timing data |
| `extraction_status` | Overall completeness state of the extraction |
| `overall_confidence` | Coarse confidence score for the full payload |
| `ambiguities` | Known uncertainties that may require review |
| `warnings` | Non-blocking issues noticed during extraction |

### Pros

- Covers most production concerns without going all the way to the full schema.
- Intent handling is much closer to the real inbox workflow.
- Gives room for attachment provenance and ambiguity capture.
- Easier to grow into the broader operational model later.
- Keeps extraction completeness in metadata rather than mixing it into the
  business payload.

### Cons

- Heavier prompt target.
- More fields to validate and maintain.
- Higher risk of partial outputs if the prompt or attachment parsing is weak.

### Assumptions

- The team wants one broader extraction contract for dashboards, review, and
  downstream services.
- The extractor can reliably classify a wider set of intents.
- It is acceptable to store some operationally useful metadata that is not
  strictly required for first-pass CHG creation.

## Impact Compatibility

The design should treat impact as a normalized internal enum that is almost the
same as the VMS target enum, plus one fallback value: `unknown`.

That gives the extractor one stable vocabulary while still allowing a
deterministic compatibility layer.

The two degradation values are not duplicates.

- `degradation_no_impact_due_to_redundancy` means a planned hit or degraded
  path exists, but redundancy is expected to prevent observable customer impact.
- `degradation_reduced_capacity` means service remains up, but usable capacity,
  resiliency, or path diversity is reduced during the work.

| Internal impact category | Downstream change-management value | Notes |
|---|---|---|
| `outage` | `Outage` | Full or likely service interruption |
| `degradation_no_impact_due_to_redundancy` | `Degradation - No Impact due to Redundancy` | Redundancy absorbs the planned hit |
| `degradation_reduced_capacity` | `Degradation - Reduced Capacity` | Service remains up with reduced capacity or resiliency |
| `no_impact` | `No Impact` | Explicitly non-service affecting |
| `regulatory_impact` | `Regulatory Impact` | Reserved for regulatory or compliance-impacting work |
| `unknown` | no direct mapping | Requires manual review or explicit compatibility-layer fallback |

## Comparison

| Option | Best trait | Main weakness | Good fit |
|---|---|---|---|
| Lean | Lowest complexity | Too coarse for grouped scopes and richer intent handling | Fastest path off the legacy schema |
| Balanced | Best tradeoff | Slightly more modeling overhead | Production-focused middle ground |
| General | Broadest coverage | Heavier prompt and validation burden | Multi-consumer long-term contract |

## Decision Outcome

No option is selected yet, because the evaluation remains open.
