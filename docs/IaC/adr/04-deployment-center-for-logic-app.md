---
title: "Use Deployment Center (Kudu Git) for Logic App Workflow Deployment"
description: "ADR explaining why Logic App Standard workflow definitions are deployed via Deployment Center's internal git pull mechanism instead of zip deploy from CI/CD runners"
ms.date: 2026-06-20
ms.topic: reference
---

# Use Deployment Center (Kudu Git) for Logic App Workflow Deployment

- Status: Accepted (Supersedes [ADR-02](02-logic-app-workflow-deployment.md))
- Deciders: Platform Team
- Date: 2026-06-20

Technical Story: The Logic App's private endpoint blocks all external SCM access, causing zip deploy from GitHub Actions to return 403. Deployment Center's internal Kudu infrastructure pulls source code from GitHub via the app's own outbound path (NAT Gateway), bypassing the private endpoint constraint entirely.

## Context and Problem Statement

ADR-02 documented zip deploy as the deployment mechanism for Logic App Standard workflows. This approach requires the CI/CD runner to reach the Logic App's SCM endpoint. In the private deployment variant, the Logic App has a private endpoint — its SCM endpoint resolves to a private IP accessible only from within the VNet.

The previous solution required a self-hosted runner inside the VNet. With the goal of eliminating self-hosted runner dependencies (see [ADR-06](06-github-hosted-runners.md)), an alternative deployment mechanism is needed that does not require external access to the SCM endpoint.

## Decision Drivers

- Private endpoint blocks SCM access from GitHub-hosted runners (zip deploy returns 403)
- Eliminates self-hosted runner requirement for workflow deployment
- Supports monorepo structure (`src/logic_app/` subfolder deployment)
- Manual sync trigger provides controlled, auditable deployment
- No additional secrets or credentials beyond what Bicep provisions
- NAT Gateway provides outbound connectivity for the app to reach GitHub

## Considered Options

- Option A: Zip deploy from GitHub Actions (ADR-02 approach) — blocked by private endpoint
- Option B: Zip deploy from self-hosted runner — works but requires always-running VM
- Option C: Deployment Center with manual sync (selected)
- Option D: ARM sub-resources for workflows (`Microsoft.Web/sites/workflows`)
- Option E: Azure DevOps with VNet-injected agents

## Decision Outcome

Chosen option: **Option C — Deployment Center with `isManualIntegration: true`**, because it leverages the Logic App's own outbound connectivity (via NAT Gateway) to pull source code from GitHub, completely bypassing the private endpoint constraint without requiring any external runner access.

### Positive Consequences

- Zero external network access required — the app pulls internally via Kudu
- No self-hosted runner needed for Logic App deployment
- Deployment is triggered via `az webapp deployment source sync` from any authenticated context
- Bicep provisions the entire configuration — no manual portal setup
- Works identically for public and private deployment variants

### Negative Consequences

- Linux Kudu does not honor the `project` setting — requires a `.deployment` file with custom command
- Deployment Center webhook is disabled (`isManualIntegration: true`) — sync must be triggered explicitly
- Less visibility into deployment progress compared to GitHub Actions job logs
- Source code must be in a public repository (or GitHub App auth must be configured for private repos)

## Technical Analysis

### How Deployment Center Works with Private Endpoints

The deployment flow:

1. Bicep provisions `Microsoft.Web/sites/sourcecontrols` linking to the GitHub repository
2. Operator (or CI/CD) triggers sync via `az webapp deployment source sync`
3. Logic App's Kudu runtime initiates an outbound HTTPS fetch to `github.com`
4. Outbound traffic routes through the NAT Gateway (attached to `snet-functions`)
5. Kudu clones/pulls the repository and executes the `.deployment` custom command
6. Workflow files are copied to `/home/site/wwwroot/`

```text
┌─────────────────────────────────────────────┐
│  GitHub Actions (GitHub-hosted runner)       │
│  → az webapp deployment source sync         │
└─────────────────┬───────────────────────────┘
                  │ ARM management plane (public)
                  ▼
┌─────────────────────────────────────────────┐
│  Logic App (private endpoint)               │
│  Kudu fetches from github.com               │
│  → outbound via NAT Gateway                 │
│  → executes .deployment command             │
│  → copies src/logic_app/* to wwwroot        │
└─────────────────────────────────────────────┘
```

### Bicep Resource Configuration

```bicep
resource sourceControl 'Microsoft.Web/sites/sourcecontrols@2023-12-01' = {
  parent: logicApp
  name: 'web'
  properties: {
    repoUrl: repoUrl                    // 'https://github.com/{owner}/{repo}'
    branch: 'main'
    isManualIntegration: true           // No webhook — manual sync only
    isGitHubAction: false               // Not using GitHub Actions integration
    isMercurial: false
  }
}
```

### The `.deployment` Custom Command

Linux Kudu does **not** honor the `project` setting in `.deployment`. A custom command is required to deploy from a monorepo subfolder:

```ini
[config]
command = bash -c "shopt -s dotglob && rm -rf /home/site/wwwroot/* && cp -r src/logic_app/* /home/site/wwwroot/"
```

This command:
1. Enables dotglob to include hidden files (e.g., `.funcignore`)
2. Clears the existing wwwroot content
3. Copies the `src/logic_app/` subfolder contents to wwwroot

### Prerequisites Chain

Deployment Center requires all three conditions:

| Prerequisite | Resource | Purpose |
|---|---|---|
| NAT Gateway on `snet-functions` | `{baseName}-natgw` | Provides outbound SNAT for GitHub fetch |
| NSG rule `Allow-Outbound-HTTPS-To-Internet` | Priority 200 | Permits HTTPS to github.com |
| `vnetRouteAllEnabled: true` | Logic App site config | Routes all traffic through VNet (including outbound) |

Without any of these, the Kudu fetch fails with a network timeout.

### Sync Trigger

Deployment is triggered manually (not via webhook):

```bash
az webapp deployment source sync \
  --name "${logicAppName}" \
  --resource-group "${resourceGroup}"
```

This can be called from:
- GitHub Actions workflow (GitHub-hosted runner — ARM management plane is public)
- Developer CLI (any authenticated Azure session)
- Automation scripts

### Deployed File Structure

After sync, `/home/site/wwwroot/` contains:

```text
/home/site/wwwroot/
├── host.json                    # Runtime configuration (extension bundle)
├── connections.json             # Managed API connection references
├── parameters.json              # Environment-specific parameters
├── email-poller/
│   └── workflow.json            # Email ingestion workflow definition
└── hitl-approval/
    └── workflow.json            # HITL approval workflow definition
```

## Pros and Cons of the Options

### Option A: Zip Deploy from GitHub Actions (ADR-02)

- Good, because it integrates natively with GitHub Actions
- Good, because deployment logs are visible in the workflow run
- Bad, because private endpoint returns 403 for external SCM access
- Bad, because it requires either a self-hosted runner or public SCM exposure

### Option B: Zip Deploy from Self-Hosted Runner

- Good, because it has VNet access to reach the private SCM endpoint
- Bad, because it requires an always-running VM ($70-150/month)
- Bad, because runner maintenance (OS updates, agent updates) adds operational overhead
- Bad, because runner availability becomes a deployment dependency

### Option D: ARM Sub-Resources

- Good, because everything is managed via Bicep
- Bad, because Microsoft does not recommend this for Logic App Standard
- Bad, because managed API connections do not serialize cleanly into ARM
- Bad, because workflow changes are tied to infrastructure deployment cadence

### Option E: Azure DevOps with VNet-Injected Agents

- Good, because VNet-injected agents have native network access
- Bad, because source code lives in GitHub — introduces a second CI system
- Bad, because additional credential management across platforms
- Bad, because team must maintain expertise in two CI/CD systems

## Implementation Reference

### Logic App Module (`src/infra_deployment/modules/logic-app.bicep`)

Deployment Center configuration:

```bicep
resource sourceControl 'Microsoft.Web/sites/sourcecontrols@2023-12-01' = {
  parent: logicApp
  name: 'web'
  properties: {
    repoUrl: repoUrl
    branch: 'main'
    isManualIntegration: true
    isGitHubAction: false
    isMercurial: false
  }
}
```

VNet route-all setting:

```bicep
siteConfig: {
  vnetRouteAllEnabled: true
  // ... other settings
}
```

### Deployment File (`.deployment`)

```ini
[config]
command = bash -c "shopt -s dotglob && rm -rf /home/site/wwwroot/* && cp -r src/logic_app/* /home/site/wwwroot/"
```

### Workflow Source (`src/logic_app/`)

```text
src/logic_app/
├── host.json
├── connections.json
├── parameters.json
├── email-poller/
│   └── workflow.json
└── hitl-approval/
    └── workflow.json
```

## Summary for Solution Architects

| Aspect | Previous (ADR-02) | Current (ADR-04) |
|---|---|---|
| Deployment mechanism | `az logicapp deployment source config-zip` | Deployment Center (`sourcecontrols` resource) |
| Runner requirement | Self-hosted (VNet access) | None (app pulls internally) |
| Network path | Runner → private SCM endpoint | App → NAT Gateway → github.com |
| Auth | OIDC workload identity | Bicep-provisioned source control link |
| Trigger | Push to `src/logic_app/**` path | `az webapp deployment source sync` |
| Monorepo support | Build script creates zip | `.deployment` custom command |
| Cost | $70-150/month (runner VM) | $0 incremental |

## Links

- Supersedes: [ADR-02 — Logic App Workflow Deployment via Zip Deploy](02-logic-app-workflow-deployment.md)
- Related: [ADR-05 — NAT Gateway over Azure Firewall](05-nat-gateway-over-firewall.md)
- Related: [ADR-06 — GitHub-Hosted Runners](06-github-hosted-runners.md)
