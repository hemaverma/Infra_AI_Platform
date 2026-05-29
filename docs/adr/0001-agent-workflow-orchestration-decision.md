# Decide Orchestration Approach for NExT Agent Workflow

- Status: Approved
- Deciders: Team
- Date: 2026-05-03

Technical Story: Evaluate why NExT should use a mixed orchestration model of Microsoft Agent Framework plus Azure Logic App, compared with Logic App only, Durable Functions, or Microsoft Agent Framework only.

## Context and Problem Statement

NExT needs an orchestration model for email ingestion, agent processing, human approval, command execution, and reply drafting. The design must handle Outlook and Teams integration cleanly while keeping the AI workflow maintainable and resumable.

## Decision Drivers

- Separation of integration flow from AI workflow logic
- Reliable HITL pause and resume
- Good fit for Outlook and Teams integration
- Maintainability as the workflow grows
- Clear runtime ownership boundaries

## Considered Options

- Mixed workflow: Azure Logic App plus Microsoft Agent Framework workflow hosted in Azure Function
- Azure Logic App centric orchestration with direct API calls into Azure Function
- Durable Functions-centric orchestration
- Microsoft Agent Framework only

## Decision Outcome

Chosen option: "Mixed workflow: Azure Logic App plus Microsoft Agent Framework workflow hosted in Azure Function".

Logic App owns email-triggered ingress and HITL orchestration. Azure Function hosts the Microsoft Agent Framework workflow for validation, extraction, normalization, command execution, and draft generation. Service Bus separates the stages.

### Positive Consequences

- Logic App can own Outlook triggers, Teams adaptive cards, and approval routing with minimal custom plumbing.
- The agent runtime can focus on interpretation, extraction, normalization, command preparation, and draft generation.
- Service Bus creates durable boundaries between ingestion, agent execution, and HITL workflows.
- The AI workflow stays independent from mailbox and approval channel specifics.

### Negative Consequences

- The architecture spans multiple Azure services and deployment units.
- End-to-end tracing and debugging are more complex than in a single-engine design.
- Queue contracts and checkpoint handling must be explicit.

## Short Rationale by Option

| Option | Summary |
| --- | --- |
| Mixed Logic App + Agent Framework | Best balance of connectors, HITL orchestration, and agent workflow fit |
| Logic App centric + direct API calls | Simpler early on, but more tightly coupled and less flexible |
| Durable Functions-centric | Strong orchestration model, but weaker fit for connector-heavy integration |
| Agent Framework only | Strong AI workflow fit, but weaker fit for channel integration and approvals |

## Links

- Related architecture: [../design/architecture.md](../design/architecture.md)
- Mixed solution process: [../design/assets/process-multi-logic-app-2.drawio.png](../design/assets/process-multi-logic-app-2.drawio.png)
- Logic App centric process: [../design/assets/process-single-logic-app.drawio.png](../design/assets/process-single-logic-app.drawio.png)
- Azure Function centric architecture: [../design/assets/architecture-only-azure-function.drawio.png](../design/assets/architecture-only-azure-function.drawio.png)
- Azure Function centric process: [../design/assets/process-only-azure-function.drawio.png](../design/assets/process-only-azure-function.drawio.png)
