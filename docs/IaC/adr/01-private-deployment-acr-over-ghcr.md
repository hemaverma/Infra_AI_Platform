# Use Azure Container Registry (ACR) Vs. GHCR for container Image deployment in a Private Vnet

- Status: Superseded by [ADR-03](03-ghcr-with-nat-gateway.md)
- Deciders: Platform Team
- Date: 2026-06-12

Technical Story: Evaluate whether the private (VNet-isolated) deployment variant can pull container images from GitHub Container Registry (GHCR) to simplify the CI/CD pipeline to a single registry, or whether Azure Container Registry (ACR) with a private endpoint remains necessary.

## Context and Problem Statement

The NExT platform supports two deployment variants: **public** and **private**. The public variant uses GHCR as the container registry. The private variant deploys into a fully isolated VNet with no public internet egress, using ACR with a private endpoint.

The question arose whether we can unify on GHCR for both variants, eliminating the dual-path registry logic in CI/CD and removing the ACR dependency from private deployments.

## Decision Drivers

- Network isolation requirements for private deployments (no public egress)
- Secret management overhead (PAT rotation vs managed identity)
- Cost implications of each approach
- Security posture and attack surface minimization
- CI/CD pipeline complexity

## Considered Options

- Option A: Use GHCR for both public and private deployments
- Option B: Use GHCR with Azure Firewall FQDN allowlisting for private deployments
- Option C: Use ACR Artifact Cache to mirror GHCR into ACR for private deployments
- Option D: Keep current dual-path architecture (GHCR for public, ACR for private)

## Decision Outcome

Chosen option: **Option D — Keep dual-path architecture (GHCR for public, ACR for private)**, because GHCR fundamentally cannot serve private VNet workloads without compromising the security posture that defines the private deployment variant.

### Positive Consequences

- Zero secrets to manage for container pulls (ACR uses managed identity with `AcrPull` role)
- All image pull traffic stays within the private network via ACR's private endpoint
- Self-hosted runner (already inside the VNet) pushes directly to ACR without needing public egress
- No dependency on external service availability (GitHub) for production deployments

### Negative Consequences

- Two code paths in `deploy-apps.yml` for registry selection (acceptable complexity)
- ACR has a recurring cost (~$5/mo Basic, ~$50/mo Premium for geo-replication)

## Technical Analysis

### Why GHCR Cannot Serve Private Deployments

| Constraint | GHCR Limitation |
|---|---|
| Network reachability | Requires HTTPS egress to `ghcr.io`, `*.githubusercontent.com`, `pkg-containers.githubusercontent.com` |
| Private endpoint | Not available — GHCR is GitHub-hosted with no Azure Private Link integration |
| Authentication | PAT-based only; no managed identity, no service principal, no Azure RBAC |
| IP allowlisting | GitHub IP ranges are dynamic and explicitly documented as unstable for allowlisting |
| NSG compatibility | The private VNet's `DenyAllOtherOutbound` rule blocks all GHCR traffic |

### Why ACR Works for Private Deployments

| Requirement | ACR Capability |
|---|---|
| Private network access | Private endpoint in `snet-private-endpoints` subnet with `privatelink.azurecr.io` DNS zone |
| Authentication | User-assigned managed identity with `AcrPull` role — no secrets |
| Image push from CI | Self-hosted runner inside VNet uses `az acr login` (token-based, no PAT) |
| Remote builds | ACR Tasks can build images inside Azure without exposing source externally |
| Image scanning | Microsoft Defender for Containers integration |

### Option B Rejection: Azure Firewall + GHCR

Adding Azure Firewall with FQDN-based rules to allow GHCR traffic was rejected because:

- Azure Firewall Standard costs ~$876/month — disproportionate to the problem
- Allowing `*.githubusercontent.com` is overly broad and increases attack surface
- Still requires PAT management for Container Apps registry credentials
- Defeats the purpose of a private deployment by intentionally poking holes in network isolation

### Option C Rejection: ACR Artifact Cache

ACR Artifact Cache (pull-through proxy that mirrors GHCR into ACR) was rejected because:

- Adds operational complexity with no clear benefit (we do not need GHCR as canonical source)
- Requires ACR Premium SKU (~$50/month)
- Introduces a dependency on GHCR availability during cache misses
- The self-hosted runner can push directly to ACR, making the proxy unnecessary

## Architecture Diagram

<!-- Image planned but not created; this ADR is superseded by ADR-03 -->

## Implementation Reference

The dual-path logic lives in `.github/workflows/deploy-apps.yml`:

```yaml
- name: Determine registry
  run: |
    if [[ "${{ vars.DEPLOYMENT_VARIANT }}" == "private" ]]; then
      ACR_NAME=$(az acr list -g "$RG" --query "[0].name" -o tsv)
      echo "login_server=${ACR_NAME}.azurecr.io" >> "$GITHUB_OUTPUT"
    else
      echo "login_server=ghcr.io" >> "$GITHUB_OUTPUT"
    fi
```

Container Apps Bicep module (`modules/container-apps.bicep`):

```bicep
registries: !empty(acrLoginServer) ? [
  {
    server: acrLoginServer
    identity: managedIdentityId  // No secrets — managed identity
  }
] : []  // Public variant: anonymous pull from GHCR
```

## Summary for Solution Architects

| Aspect | Public Variant | Private Variant |
|---|---|---|
| Registry | GHCR (`ghcr.io`) | ACR (private endpoint) |
| Auth mechanism | Anonymous pull (public package) | Managed identity (`AcrPull` role) |
| Runner | `ubuntu-latest` (GitHub-hosted) | Self-hosted runner inside VNet |
| Network requirement | Public internet | All traffic stays in VNet |
| Secret management | None (public image + `GITHUB_TOKEN` in CI) | None (managed identity) |
| Cost | Free | ACR SKU cost ($5-50/month) |
| Image push | `docker/login-action` + `GITHUB_TOKEN` | `az acr login` from self-hosted runner |

The dual-path approach is the correct architecture. Attempting to unify on GHCR for private deployments would require either compromising network isolation or introducing disproportionate cost and complexity.
