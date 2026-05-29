# Decide Service Bus Queue Topology for NExT Workflows

- Status: Approved
- Deciders: Team
- Date: 2026-05-03

Technical Story: Evaluate how Service Bus messages should be organized for NExT workflows, including whether queue topology should be one queue per subsystem plus event type, one queue per event type, or another routing pattern.

## Context and Problem Statement

NExT uses Azure Service Bus between Logic App workflows and the Azure Function-hosted agent runtime. Azure Service Bus supports both queues and topics. In this design, each message is intended for exactly one consumer, so the relevant choice is queue topology, not topic-and-subscription fan-out topology. The main question is whether queue topology should follow subsystem boundaries plus event types, or event types alone.

## Decision Drivers

- Clear ownership boundaries
- Simple routing and operations
- Flexibility as new events are added
- Low queue sprawl
- Alignment with the current mixed workflow design

## Considered Options

- One queue per subsystem plus event type
- One queue per event type

### Option Meaning

- One queue per subsystem plus event type: create a separate queue for each owning subsystem and event category.
- One queue per event type: create a separate queue for each event type regardless of subsystem. Using the event types from the architecture document.

## Visual Context from the Mixed Design

The proposed mixed-solution workflow in [../design/assets/process-multi-logic-app-2.drawio.png](../design/assets/process-multi-logic-app-2.drawio.png) shows two main messaging boundaries:

- `workflow-queue` carries work into, and back into, the Azure Function-hosted workflow.
- `hitl-queue` carries approval requests into the HITL Logic App workflow.

This architecture uses queues, not topics. The remaining choice is how granular the queue layout should be.

## Decision Outcome

Chosen option: one queue per subsystem plus event type.

This is a point-to-point queue design, not a topic-based fan-out design. Each message has one intended consumer path. Azure Service Bus topics and subscriptions are not used in this architecture because the system does not require one message to be delivered to multiple consumers.

In practice, this means queues are separated by subsystem ownership, and the queue name also reflects the event category being handled. Event type still exists in the message contract, but the primary routing boundary is subsystem plus event type.

### Positive Consequences

- Queue ownership is explicit for each subsystem and event path.
- Monitoring, retry handling, and dead-letter investigation are easier to isolate.
- Routing intent is clearer from queue naming alone.
- The design stays aligned with single-consumer message handling.
- The messaging model stays simple because it uses queues rather than topics and subscriptions.

### Negative Consequences

- The number of queues can grow as subsystems and event types increase.
- Deployment and access-control management become heavier than a flatter queue layout.
- Naming conventions and ownership rules must stay consistent.

## Short Rationale by Option

| Option | Summary |
| --- | --- |
| One queue per subsystem plus event type | Chosen option. Clear ownership and routing, with higher queue-management overhead |
| One queue per event type | Strong per-event isolation, but fragments the workflow and increases overhead |

## Consequences and Follow-Up Considerations

- Define the canonical message envelope including `eventType`, `workflowInstanceId`, `checkpointId`, and payload reference fields.
- Keep routing point-to-point: one message, one consumer.
- Define dead-letter handling, retry policy, and per-queue ownership.
- Define a queue naming convention based on subsystem plus event type, aligned to the event types already used in the architecture document: `email.received`, `approval.requested`, `approval.responded`, and `email-approval.requested`.

## Links

- Related architecture: [../design/architecture.md](../design/architecture.md)
- Mixed solution process: [../design/assets/process-multi-logic-app-2.drawio.png](../design/assets/process-multi-logic-app-2.drawio.png)
