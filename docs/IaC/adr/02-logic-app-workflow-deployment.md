---
title: "Deploy Logic App Standard Workflows via Zip Deploy in GitHub Actions"
description: "ADR explaining why Logic App Standard workflow definitions are deployed as application code via zip deploy in the unified deploy-apps.yml workflow"
ms.date: 2026-06-12
ms.topic: reference
---

# Deploy Logic App Standard Workflows via Zip Deploy in GitHub Actions

- Status: Superseded by [ADR-04](04-deployment-center-for-logic-app.md)
- Deciders: Platform Team
- Date: 2026-06-12

Technical Story: A code reviewer questioned why Logic App workflow deployment lives inside the `deploy-apps.yml` GitHub Actions workflow rather than being handled by Bicep/ARM or a separate deployment mechanism. This ADR documents the architectural reasoning.

## Context and Problem Statement

The platform uses Logic App Standard (single-tenant) for email ingestion and HITL approval workflows. A PR reviewer raised the concern: "Why are we using GitHub workflows to deploy Logic App? This should be infrastructure, not application deployment."

The core question is whether Logic App workflow definitions should be deployed as infrastructure (via Bicep/ARM) or as application code (via zip deploy in CI/CD), and whether this deployment belongs in the unified `deploy-apps.yml` workflow.

## Decision Drivers

- Logic App Standard stores workflows as files on the app filesystem (unlike Consumption tier which uses ARM resources)
- Microsoft recommends zip deploy for Logic App Standard workflow code
- Private deployment variant requires VNet connectivity to reach the Logic App SCM endpoint
- Workflow definitions change on application release cadence, not infrastructure cadence
- Runner and OIDC credentials are already configured in `deploy-apps.yml`
- A previously separate `deploy-logic-app.yml` caused double-deployment issues

## Considered Options

- Option A: Deploy workflow definitions via Bicep/ARM sub-resources (`Microsoft.Web/sites/workflows`)
- Option B: Maintain a separate `deploy-logic-app.yml` GitHub Actions workflow
- Option C: Deploy via Azure DevOps pipeline
- Option D: Deploy manually via Azure Portal designer or VS Code extension
- Option E: Deploy workflow code via zip deploy in `deploy-apps.yml` (current approach)

## Decision Outcome

Chosen option: **Option E — Deploy workflow code via zip deploy in `deploy-apps.yml`**, because Logic App Standard workflows are application code (not ARM resources), Microsoft recommends zip deploy for this tier, and co-locating with the container deployment job reuses the same runner, credentials, and trigger configuration.

### Positive Consequences

- Single workflow file manages all application code deployment (container image + Logic App workflows)
- Reuses the self-hosted runner that already has VNet connectivity for private deployments
- Reuses OIDC federated credentials already configured for the environment
- `skip_logic_app` input provides independent control when only container changes are needed
- Follows Microsoft's recommended deployment pattern for Logic App Standard

### Negative Consequences

- Workflow file has two deployment jobs (increased complexity over a single-purpose file)
- Reviewers unfamiliar with Logic App Standard may confuse workflow code with infrastructure

## Technical Analysis

### Logic App Standard vs Consumption: A Critical Distinction

The reviewer's concern likely stems from experience with Logic App Consumption, where workflows ARE ARM resources. Logic App Standard operates fundamentally differently:

| Aspect | Logic App Consumption | Logic App Standard |
|---|---|---|
| Workflow storage | ARM resource (`Microsoft.Logic/workflows`) | File on app filesystem (`workflow.json`) |
| Deployment | Bicep/ARM deploys everything | Bicep creates host; zip deploy pushes workflows |
| Multiple workflows | One workflow per resource | Multiple workflows per app (folder-per-workflow) |
| Hosting | Serverless multi-tenant | Dedicated App Service Plan (WS1/WS2/WS3) |
| VNet support | Not natively supported | Full VNet integration + private endpoints |
| Runtime | Shared multi-tenant | Single-tenant (same runtime as Azure Functions) |

### Infrastructure vs Application Code Separation

**Infrastructure layer** (Bicep — `modules/logic-app.bicep`):

Creates the Logic App Standard hosting environment:

- App Service Plan (SKU `WS1`, Linux)
- Web Site (kind `functionapp,workflowapp,linux`)
- App settings (connection strings, identity config, storage references)
- VNet integration (private variant)
- Private endpoint restricting SCM/Kudu access (private variant)

This creates an **empty** Logic App. No workflows exist after infrastructure deployment.

**Application code layer** (`deploy-workflows.sh`):

Deploys the actual workflow definitions via `az logicapp deployment source config-zip`:

```text
build/
  host.json                    # Runtime configuration (extension bundle)
  connections.json             # Managed API connection references
  email-poller/
    workflow.json              # Email ingestion workflow definition
  hitl-approval/
    workflow.json              # HITL approval workflow definition
```

This is a second, separate deployment step that requires the infrastructure to already exist — identical to deploying function code into an existing Azure Functions app.

### Private vs Public Deployment Paths

#### Public Variant

- GitHub-hosted runner (`ubuntu-latest`) calls `deploy-workflows.sh`
- Logic App SCM endpoint is publicly accessible
- No special network connectivity required

#### Private Variant

- Self-hosted runner inside the VNet calls `deploy-workflows.sh`
- Logic App has a private endpoint; SCM resolves to a private IP via `privatelink.azurewebsites.net`
- NSG rule `DenyAllOtherOutbound` blocks all public egress
- Deployment MUST execute from within the VNet

```yaml
runs-on: ${{ vars.RUNNER_LABEL || 'ubuntu-latest' }}
```

The `RUNNER_LABEL` variable selects the VNet-connected self-hosted runner for private deployments.

### Why a Unified Workflow File

The previously separate `deploy-logic-app.yml` was deleted because:

1. **Double-trigger problem** — Both workflows triggered on `push` to `src/logic_app/**`, causing duplicate deployments
2. **Same runner requirement** — Private deployments need the VNet-connected runner; duplicating runner config adds maintenance burden
3. **Same credentials** — OIDC federated credentials are scoped to the environment; duplicating this across workflows adds secret management overhead
4. **Atomic releases** — Logic App workflows reference Service Bus queues and endpoints that the Container App consumes; deploying together ensures consistency

## Architecture Diagram

<!-- Image planned but not created; this ADR is superseded by ADR-04 -->

## Pros and Cons of the Options

### Option A: Bicep/ARM Sub-Resources

Deploy workflows as `Microsoft.Web/sites/workflows` sub-resources in Bicep.

- Good, because it consolidates everything into a single IaC deployment
- Bad, because Microsoft does not recommend this for Standard tier
- Bad, because managed API connections (Office 365, Teams) do not serialize cleanly into ARM sub-resources
- Bad, because workflow definitions change frequently (app cadence) while infrastructure changes rarely
- Bad, because it couples application release to infrastructure deployment pipeline

### Option B: Separate `deploy-logic-app.yml` Workflow

Maintain a dedicated GitHub Actions workflow for Logic App deployment.

- Good, because it provides clear separation of concerns at the workflow level
- Bad, because it caused double deployments on the same path trigger (proven failure)
- Bad, because it duplicates runner selection, OIDC config, and environment setup
- Bad, because it cannot share skip/gate logic with the container deployment

### Option C: Azure DevOps Pipeline

Deploy Logic App workflows from an Azure DevOps pipeline.

- Good, because ADO integrates natively with Azure
- Bad, because source code lives in GitHub; cross-platform CI adds complexity with no benefit
- Bad, because it introduces a second CI system to maintain

### Option D: Portal Designer or VS Code Extension

Edit workflows manually via Azure Portal or deploy via VS Code.

- Good, because it provides a visual editing experience
- Bad, because there is no version control, no CI/CD, no reproducibility
- Bad, because portal edits are not auditable or reviewable
- Bad, because private deployments require VPN connectivity from the developer machine

### Option E: Zip Deploy in `deploy-apps.yml` (Selected)

Deploy workflow code via `az logicapp deployment source config-zip` in the unified workflow.

- Good, because it follows Microsoft's recommended pattern for Logic App Standard
- Good, because it reuses existing runner, credentials, and environment configuration
- Good, because `skip_logic_app` input provides independent control
- Good, because path filters ensure deployment only triggers on workflow code changes
- Bad, because the workflow file has two deployment concerns (container + Logic App)

## Implementation Reference

The deployment job in `.github/workflows/deploy-apps.yml`:

```yaml
deploy-logic-app-workflows:
  name: Deploy Logic App Workflows
  runs-on: ${{ vars.RUNNER_LABEL || 'ubuntu-latest' }}
  if: ${{ !inputs.skip_logic_app }}
  environment: ${{ inputs.environment || 'dev' }}
  steps:
    - uses: actions/checkout@v4
    - uses: azure/login@v2
      with:
        client-id: ${{ secrets.AZURE_CLIENT_ID }}
        tenant-id: ${{ secrets.AZURE_TENANT_ID }}
        subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    - run: |
        ./src/logic_app/deploy-workflows.sh \
          --resource-group "${{ env.RESOURCE_GROUP }}" \
          --logic-app-name "${{ env.LOGIC_APP_NAME }}"
```

The deployment script (`src/logic_app/deploy-workflows.sh`):

1. Maps source workflow JSONs to folder structure (`logic_app_workflow_main.json` → `email-poller/workflow.json`)
2. Copies `host.json` and `connections.json` to build root
3. Creates zip package
4. Deploys via `az logicapp deployment source config-zip`

## Summary for Solution Architects

| Aspect | Public Variant | Private Variant |
|---|---|---|
| Deployment mechanism | `az logicapp deployment source config-zip` | Same |
| Runner | `ubuntu-latest` (GitHub-hosted) | Self-hosted runner inside VNet |
| Network requirement | Public internet | SCM accessible only via private endpoint |
| Auth | OIDC workload identity federation | Same |
| Skip control | `skip_logic_app: true` input | Same |
| What Bicep does | Creates empty Logic App host | Same + VNet integration + private endpoint |
| What zip deploy does | Pushes workflow JSON files to app filesystem | Same |

## Links

- Related: [ADR-01: ACR over GHCR for Private Deployments](01-private-deployment-acr-over-ghcr.md)
- Upstream: `docs/adr/0001-agent-workflow-orchestration-decision.md` (chose Logic App Standard for email/HITL)
- Microsoft reference: [Deploy Standard logic app workflows](https://learn.microsoft.com/en-us/azure/logic-apps/deploy-single-tenant-logic-apps-private-storage-account)
