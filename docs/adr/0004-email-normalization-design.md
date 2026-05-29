# Email Normalization Design

- Status: accepted
- Deciders: team
- Date: 2026-05-05

## Context and Problem Statement

The extraction step should use a canonical internal representation and a
deterministic prompt serialization step for the LLM.

That gives two clean boundaries:

- internal format: what the system stores and manipulates
- prompt serialization: how that internal packet is converted into the LLM
  message content

This document compares three practical LLM input format families and records
the selected canonical packet plus the selected prompt serialization strategy.

## Decision Drivers

- Make the email easy for the model to read.
- Preserve prior-thread and attachment context.
- Support small CSV and Excel attachments.
- Keep prompt formats easy to compare and debug.
- Avoid coupling the internal representation to one prompt style.

## Non-Goals

- Defining the extraction output schema.
- Defining downstream CHG planning or market split logic.
- Solving OCR or image-only attachments.

## Considered Options

These are the three practical formats to pass to the LLM.

- Raw Text Bundle
- Simple Structured Text Packet
- Structured JSON Packet

### Format 1: Raw Text Bundle

Pass one long text blob containing:

- current email body
- one or more older thread segments embedded in the body
- attachment text appended after the body

Example:

```text
Subject: Planned Maintenance Notification
From: noreply@cbus.att-mail.com

Current message body...

Older thread segment 1 embedded in the body...

Older thread segment 2 embedded in the body...

Attachment: maintenance.csv
Circuit ID,Alias CID,Start,End
ABC123,9AT4726A,04/20/2026 23:00 CDT,04/21/2026 05:00 CDT
```

Pros:

- Lowest implementation cost
- Fastest way to experiment
- No serialization step beyond concatenation

Cons:

- Weak boundaries between the current message, prior-thread content, and attachments
- Harder for the model to prioritize the right text
- Harder to debug when attachment content dominates the prompt

Best use:

- Early experiments only

### Format 2: Simple Structured Text Packet

Pass a sectioned text packet with clear labels.

Example:

```text
<email_packet>
vendor_key: att
email_subject: Planned Maintenance Notification
email_from: noreply@cbus.att-mail.com
email_sent_at: 2026-04-20T23:15:00-05:00

<current_message_body>
Current vendor-authored content...
</current_message_body>

<prior_thread_content>
Latest prior-thread message segment...

Older prior-thread message segment...
</prior_thread_content>

<attachments>
<attachment filename="maintenance.csv" content_type="text/csv">
ROW 1 | Circuit ID=ABC123 | Alias CID=9AT4726A | Start=04/20/2026 23:00 CDT | End=04/21/2026 05:00 CDT
</attachment>
</attachments>
</email_packet>
```

Pros:

- Easy for the model to scan
- Strong separation between current content, prior-thread content, and attachments
- Good balance of simplicity and structure
- Works well with the current one-string Responses API input pattern

Cons:

- Still relies on the model reading conventions in free text
- Less precise than JSON for structured rows and provenance

Best use:

- Recommended default LLM format

### Format 3: Structured JSON Packet

Pass a richer structured packet, usually JSON or JSON-like text.

This format should read like one delivered email record with separate content
fields for the current message and prior-thread material.

Example:

```json
{
  "vendor_key": "att",
  "email_subject": "Planned Maintenance Notification",
  "email_from": "noreply@cbus.att-mail.com",
  "email_sent_at": "2026-04-20T23:15:00-05:00",
  "current_message_body": "Current vendor-authored content...",
  "prior_thread_content": "Latest prior-thread message segment...\n\nOlder prior-thread message segment...",
  "attachments": [
    {
      "filename": "maintenance.csv",
      "content_type": "text/csv",
      "rows": [
        {
          "Circuit ID": "ABC123",
          "Alias CID": "9AT4726A",
          "Start": "04/20/2026 23:00 CDT",
          "End": "04/21/2026 05:00 CDT"
        }
      ]
    }
  ]
}
```

Pros:

- Strongest structure and provenance
- Better for preserving current content, prior-thread content, and attachments
- Easier to store and inspect in traces
- Better fit when attachment rows need to stay structured

Cons:

- Heavier prompt payload
- More serialization effort
- Less expressive if exact prior-message reconstruction is required

Best use:

- Complex vendors, multi-attachment emails, or debugging-heavy workflows

## Comparison

| Format | Strength | Weakness | Best fit |
|---|---|---|---|
| Raw Text Bundle | Fastest to implement | Weak boundaries and lower reliability | Experiments |
| Simple Structured Text Packet | Best balance | Less precise than full structured data | Default production prompt |
| Structured JSON Packet | Strongest structure | Heavier prompt and serialization cost | Complex cases |

## Selected Canonical Packet

The internal representation should be separate from the prompt format.
The recommended internal model is one canonical packet per email.

Treat the email as one container with these parts:

- `vendor_key`, `email_subject`, `email_from`, and optional `email_sent_at`
- `current_message_body` for the newest visible vendor-authored content
- optional `prior_thread_content` for older thread material embedded in the email body
- `attachments` for real attachments present on the email
- optional `candidate_hints` for deterministic clues found upstream

Keep attachments at the email level. Do not require a link from each attachment
to `current_message_body` or `prior_thread_content`, because they belong to
the delivered email container.

Email-level fields belong to the delivered email and should remain the single
authoritative source for subject, sender, and send time. Do not duplicate
those values inside separate body sections.

The key deterministic boundary is between the current visible message body and
the older thread content below it. Do not require full reconstruction of each
older message as a separate object.

```json
{
  "vendor_key": "att",
  "email_subject": "Planned Maintenance Notification",
  "email_from": "noreply@cbus.att-mail.com",
  "email_sent_at": "2026-04-20T23:15:00-05:00",
  "current_message_body": "Current vendor-authored content...",
  "prior_thread_content": "Latest prior-thread message segment...\n\nOlder prior-thread message segment...",
  "attachments": [
    {
      "attachment_id": "att-1",
      "filename": "maintenance.csv",
      "content_type": "text/csv",
      "tables": [
        {
          "table_id": "table-1",
          "columns": ["Circuit ID", "Alias CID", "Start", "End"],
          "rows": [
            {
              "row_id": "row-1",
              "values": {
                "Circuit ID": "ABC123",
                "Alias CID": "9AT4726A",
                "Start": "04/20/2026 23:00 CDT",
                "End": "04/21/2026 05:00 CDT"
              }
            }
          ]
        }
      ]
    }
  ],
  "candidate_hints": {
    "ticket_candidates": ["NCC-24173"],
    "circuit_candidates": ["ABC123"]
  }
}
```

Why this shape:

- It maps directly from parsed email inputs.
- It preserves the most important deterministic boundary in the email.
- It avoids duplicate metadata and unclear precedence rules.
- It avoids brittle reconstruction of each older message.
- It preserves row-level attachment structure when available.
- It stays useful even when detailed prior-thread metadata is missing.

Implementation notes:

- `current_message_body` is the core required content for the newest visible
  vendor-authored message.
- `email_sent_at` is optional when it cannot be recovered deterministically.
- `prior_thread_content` contains the remaining older thread material when
  present.
- If a reliable current-versus-prior split cannot be made, keep the full body
  in `current_message_body` and omit `prior_thread_content`.
- `attachments` represents actual attachments present on the email.
- Attachment-to-message linkage is optional and should not be required.

## Candidate Hints

Candidate hints are optional, deterministic clues collected during parsing and
normalization before the LLM step.

They are not extracted facts and they are not authoritative. They exist to help
the prompt body and debugging workflows point the model at likely identifiers
without requiring the LLM to trust them blindly.

Good candidate hints are directly observable from the email inputs, for
example:

- ticket numbers found in the subject, body, or attachment filenames
- circuit identifiers found in the body or attachment rows
- maintenance IDs, order IDs, or market names matched by deterministic rules
- candidate time windows or service dates parsed from clearly labeled fields

The internal packet should remain fully usable even when candidate hints are
empty.

## Prompt Serialization

The canonical packet does not need a separate rendered-format abstraction.
It only needs a deterministic serialization step before the LLM call.

### Simple Structured Text Packet

This is the selected default prompt serialization.

Use this when:

- the email is not structurally complex
- attachments are small
- the goal is the best readability-to-size ratio

Serialize the canonical packet into stable labeled sections with XML-like tags
or similar delimiters so the sections and attachments stay visually
separate.

Render `current_message_body` and `prior_thread_content` as separate
top-level blocks. If the older thread content cannot be split reliably from
the newest visible message, keep the full body in `current_message_body` and omit
`prior_thread_content`.

This serialization works well with the recommended canonical packet and keeps
the prompt compact.

In the current one-string message pattern, this serialized packet becomes the
text content of the user message sent to the LLM.

### Structured JSON Packet

This is the fallback prompt serialization for complex cases.

Use this when:

- the email has meaningful prior-thread content
- attachments contain row-level data that should stay structured
- debugging and provenance matter more than prompt compactness

Render the flat packet fields directly. If the older thread content cannot be
split reliably, keep the full body in `current_message_body` and omit
`prior_thread_content`.

When available, include `email_sent_at` alongside `vendor_key`,
`email_subject`, and `email_from`.

This works well when preserving arrays and objects in the prompt body is worth
the added verbosity.

## Serialization Choices

There are two practical serialization choices for the recommended canonical
packet.

| Canonical packet | Prompt serialization | Recommendation |
|---|---|---|
| Recommended canonical packet | Simple text packet | Selected default |
| Recommended canonical packet | Structured JSON packet | Alternate for complex vendors and attachment-heavy emails |

## CSV and Message Guidance

Regardless of format choice, use these rules.

- Separate `current_message_body` from `prior_thread_content` when deterministic boundaries exist.
- Inline small CSV attachments after normalization.
- Prefer row-oriented text for simple structured text packets.
- Preserve structured rows internally even when serializing them as text.
- Include all relevant older thread material in `prior_thread_content` by default.
- If prompt size becomes a constraint, apply a separate deterministic truncation policy.
- Include attachment manifests even when attachment content is skipped.

## Decision Outcome

Chosen option: "recommended canonical packet with simple structured text packet serialization," because it provides the best balance of readability, deterministic structure, and implementation flexibility.

- internal format: recommended canonical packet with thin email-level metadata, `current_message_body`, and `prior_thread_content`
- prompt serialization: Format 2, the simple structured text packet

That keeps the internal model durable, debuggable, and provenance-friendly
while keeping the prompt compact and readable.

The internal format can be more complex than the serialized prompt body as
long as it is created directly and deterministically from the parsed email
inputs, including the current message body, prior-thread content, attachment
metadata, and normalized attachment rows.

Alternative prompt serialization formats can be created and tested later as needed, and the internal format should accommodate a wide variety.
