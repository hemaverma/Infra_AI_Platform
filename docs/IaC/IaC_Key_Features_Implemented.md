---
title: "NExT IaC_Key_Features_Implemented"
description: "High-level overview of the NExT Accelerator Infrastructure platform features, deployment architecture, cost decisions, and security posture."
ms.date: 2026-06-24
ms.topic: overview
---

## Platform Overview

The NExT Accelerator Infrastructure is a production-grade Azure deployment platform supporting two deployment variants (private VNet-isolated and public simplified) for an AI-powered email processing system. The platform deploys 23 Azure resources across 7 deployment phases using Azure Bicep with Azure Verified Modules (AVM).

## Key Features Implemented

### 1. Dual-Variant Deployment Architecture

The **private variant** provides full VNet isolation with 9 subnets, 18 private DNS zones, 4 NSGs, a P2S VPN Gateway (Entra ID auth), and NAT Gateway for controlled outbound traffic.

The **public variant** offers simplified deployment without networking, where all services use public endpoints for rapid development iteration.

### 2. Intelligent Deployment Orchestration

The deployment orchestrator (`deploy.sh`) provides:

- 11 CLI parameters for flexible configuration
- Phased deployment (network then services, or all-in-one)
- `.env`-driven configuration overrides
- Pre-flight checks: soft-deleted resource recovery (Key Vault auto-recover), regional availability validation
- Resilience: VPN Gateway failure isolation (parallel deploy + auto-retry), PostgreSQL Entra ID retry (exponential backoff, 10-min total)

### 3. Zero-Runner CI/CD Pipeline

- Two GitHub Actions workflows on GitHub-hosted runners (zero infrastructure cost)
- OIDC federated credentials (no long-lived secrets)
- Container App: GHCR push + `az containerapp update` via ARM management plane
- Logic App: Deployment Center with Kudu external git sync via NAT Gateway
- No self-hosted runner required ([ADR-06](adr/06-github-hosted-runners.md))

### 4. Cost-Optimized Network Security

| Component | Selected | Alternative | Monthly Savings |
|-----------|----------|-------------|-----------------|
| Outbound connectivity | NAT Gateway ($32/mo) | Azure Firewall ($912/mo) | ~$880 |
| Container registry | GHCR (free) | ACR Premium ($480/mo) | ~$480 |
| CI/CD runner | GitHub-hosted (included) | Self-hosted VM ($104/mo) | ~$104 |
| **Total estimated savings** | | | **~$1,500/mo** |

### 5. AI Services Integration

- Azure OpenAI (GPT model deployment with private endpoint)
- Document Intelligence (form/document extraction)
- Content Safety (content moderation)
- AI Foundry Hub + Project (ML workspace integration)

### 6. Data Platform

- PostgreSQL Flexible Server (VNet-delegated, Entra ID auth)
- Cosmos DB (NoSQL document store with private endpoint)
- Azure Service Bus Premium (message queuing with private endpoint)
- Azure Storage Account (blob + queue with private endpoints)

### 7. Application Hosting

- Container Apps Environment (internal-only, no public ingress)
- Logic App Standard (VNet-integrated, Deployment Center)
- User-Assigned Managed Identity (single identity across all services)

### 8. Observability

- Log Analytics Workspace (centralized logging)
- Application Insights (distributed tracing, APM)
- Diagnostic settings on all applicable resources

### 9. Security Posture

- Zero public endpoints in private variant (all PaaS behind private endpoints)
- Entra ID authentication for VPN, PostgreSQL, and managed identity access
- Key Vault with purge protection (90-day retention)
- NSG deny-all-other rules with explicit allow lists
- No long-lived secrets in CI/CD (OIDC federated credentials)

## Architecture Decision Records

| # | Decision | Status | Impact |
|---|----------|--------|--------|
| ADR-01 | ACR over GHCR for private | Superseded by ADR-03 | Historical context |
| ADR-02 | Logic App workflow deployment methods | Superseded by ADR-04 | Historical context |
| ADR-03 | GHCR + NAT Gateway for all variants | Active | Eliminates $480/month ACR cost |
| ADR-04 | Deployment Center for Logic App | Active | Eliminates VNet runner dependency |
| ADR-05 | NAT Gateway over Azure Firewall | Active | Saves $880/month |
| ADR-06 | GitHub-hosted runners (eliminate self-hosted) | Active | Saves $104/month, zero maintenance |

## Related Documentation

- [Infrastructure Architecture](Infrastructure.md): Full technical architecture and resource inventory
- [Private Deployment Guide](../../src/infra_deployment/private/README.md): End-to-end private deployment walkthrough
- [Public Deployment Guide](../../src/infra_deployment/public/README.md): Simplified public variant
- [GitHub Actions Setup](github-actions-setup.md): CI/CD configuration
