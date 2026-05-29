---
title: Decide Conditional Rejection Graph Structure for the NExT Workflow
description: Decision record for how the NExT workflow branches after command and email approval responses.
author: NExT team
ms.date: 2026-05-11
ms.topic: concept
keywords:
  - adr
  - workflow graph
  - rejection handling
  - agent framework
  - hitl
estimated_reading_time: 6
---

- Status: Approved
- Deciders: Team
- Date: 2026-05-11

Technical Story: Decide how the Azure Function-hosted NExT workflow should
branch after `approval.responded` resumes so valid business rejections stop the
workflow cleanly without changing the Logic App or Service Bus contract.

## Context and Problem Statement

The original communicator workflow graph was effectively linear after both HITL
executors. A rejected command response still fell through to draft generation.
A rejected email review risked reaching the send stage unless later executors
inferred control flow from the payload.

That shape created three problems:

- Rejection was represented as data, not workflow routing.
- The queue contract suggested the transport might need new rejection-specific
  events even though `approval.responded` already carried the required state.
- Invalid approval input could be mistaken for a normal business rejection if
  the workflow normalized unexpected values too loosely.

The team needed a graph structure that keeps the first proof of concept small,
documents the ownership boundary clearly, and preserves room for richer future
graphs.

## Decision Drivers

- Make valid command and email rejections stop the workflow explicitly.
- Preserve the current `approval.responded` Logic App and Service Bus contract.
- Keep Logic App responsible for prompting, not for business branching.
- Distinguish valid business rejection from invalid approval input.
- Keep the first proof of concept small and readable.

## Considered Options

- Shared rejection terminal with conditional edges after both HITL executors.
- Separate terminal executors for command rejection and email rejection.
- Dedicated invalid-approval terminal branch in the workflow graph.
- Host-side branching in `function_app.py` before the workflow resumes.
- No-match dead-end routing where unrecognized approval payloads simply match
  no branch.

## Decision Outcome

Chosen option: use conditional edges after both HITL executors so approved
messages continue on the main path and rejected messages route to one shared
`terminate_rejected` executor.

The selected graph shape is:

```text
validate_normalize
  -> hitl_operations_approval
      -> approved: operations_command -> draft_reply -> hitl_review_draft
      -> rejected: terminate_rejected

hitl_review_draft
  -> approved: send_reply
  -> rejected: terminate_rejected
```

This structure keeps the rejection behavior inside the workflow where the
business decision belongs. Logic App still returns the stable
`approval.responded` message. Azure Function restores the checkpoint and then
applies the branch.

Invalid approval input is not modeled as a business-terminal branch. The
workflow raises an error instead. That preserves the distinction between a
valid human rejection and malformed data.

## Positive Consequences

- The graph now shows rejection as explicit control flow instead of executor
  side effects.
- One shared `terminate_rejected` executor keeps the proof of concept small.
- The current `approval.responded` transport contract remains sufficient for
  both approved and rejected responses.
- Logic App and Azure Function ownership stays clear: Logic App prompts,
  Azure Function decides whether the workflow continues or terminates.

## Negative Consequences

- The shared terminal emits a common terminal shape, so stage-specific
  rejection behavior is intentionally limited in the proof of concept.
- Future designs that need redraft loops, manual-triage artifacts, or
  stage-specific rollback will need additional graph branches.
- Invalid approval payloads now fail loudly, which is correct, but it requires
  operators to treat malformed resume input as an execution issue.

## Rejected Alternatives

### Separate rejection executors

Separate command and email rejection executors were more explicit, but they
added executor surface area without changing the external contract. The team
chose one shared terminal because the current proof of concept only needs to
stop cleanly and record the rejection reason.

### Dedicated invalid-approval terminal branch

Routing malformed approval input to its own terminal branch would have treated
bad data as a normal business outcome. The team rejected that because invalid
payloads should surface as errors, not as valid workflow completions.

### Host-side branching before workflow resume

Branching in `function_app.py` would have coupled transport handling to
workflow-specific business semantics. The team rejected that because the graph
is the correct place to visualize, test, and evolve business routing.

### No-match dead-end routing

Allowing unexpected approval payloads to match no branch would have created a
silent failure mode where a resumed workflow appears stuck. The team rejected
that because the system should fail loudly on malformed approval input.

## Links

- Related architecture: [../design/architecture.md](../design/architecture.md)
- Orchestration decision: [0001-agent-workflow-orchestration-decision.md](0001-agent-workflow-orchestration-decision.md)
- Queue topology decision: [0002-service-bus-queue-topology.md](0002-service-bus-queue-topology.md)
