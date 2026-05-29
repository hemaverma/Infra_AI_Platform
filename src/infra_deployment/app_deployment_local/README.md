---
title: Local Application Deployment Scripts
description: Docker image build and ACR push scripts for local development and emergency deployments outside the CI/CD pipeline
ms.date: 2026-06-18
ms.topic: how-to
---

## Overview

Local Docker image build and push scripts for the private ACR. These scripts are NOT part of the automated CI/CD pipeline — use them for local development or emergency deployments when the self-hosted runner is unavailable.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Docker Desktop | Running with Linux containers |
| VPN Connection | Active connection to the private VNet (private variant only) |
| Azure CLI | Authenticated with `az login` |
| ACR Access | `AcrPush` role on the target Container Registry |

## Scripts

| Script | Purpose |
|--------|---------|
| `build-image.sh` | Docker build + ACR push (bash) |
| `build-image.ps1` | Docker build + ACR push (PowerShell) |

## Usage

```bash
# Bash
bash src/infra_deployment/app_deployment_local/build-image.sh \
  -g <RESOURCE_GROUP> \
  --acr-name <ACR_NAME> \
  --image-name communicator \
  --image-tag latest
```

```powershell
# PowerShell
pwsh -File src/infra_deployment/app_deployment_local/build-image.ps1 `
  -ResourceGroup <RESOURCE_GROUP> `
  -AcrName <ACR_NAME> `
  -ImageName communicator `
  -ImageTag latest
```

## Normal Day-2 Deployment

For routine code deployments, push to `main` — the GitHub Actions workflow
(`deploy-apps.yml`) handles everything automatically via the self-hosted runner.
