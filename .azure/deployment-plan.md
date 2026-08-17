---
title: Azure Deployment Plan
description: Validation and execution plan for the ATT NF private network what-if
ms.date: 2026-08-11
ms.topic: deployment
---

## Status

Deployed

Generated: 2026-08-11

## 1. Project Overview

Goal: Run a non-creating Azure Resource Manager what-if for the existing private
network Bicep phase.

Path: Existing infrastructure deployment

## 2. Approved Inputs

| Attribute | Value |
|-----------|-------|
| Classification | Development |
| Scale | Network foundation only |
| Budget | Existing template defaults |
| Subscription |  |
| Resource group | `rg-att-nf-pvt` |
| Location | `westus3` |
| Base name | `attnf` |
| Unique prefix | `1` |
| Variant | `private` |
| Phase | `network` |
| Mode | Deployment approved after successful what-if |

The user approved these inputs in the execution request on 2026-08-11.

## 3. Components Detected

| Component | Type | Technology | Path |
|-----------|------|------------|------|
| Private network phase | Infrastructure | Bicep | `src/infra_deployment/private/phase1-network.bicep` |
| Deployment wrapper | Automation | Bash and Azure CLI | `src/infra_deployment/deploy.sh` |

## 4. Recipe Selection

Selected: Azure CLI with Bicep

The repository already provides the requested phase-aware wrapper and Bicep
entry point. No infrastructure or application code generation is required.

## 5. Architecture Scope

The what-if is limited to the resources declared by the private network phase.
Application deployment is excluded because `--phase network` bypasses the
post-deployment application block.

The wrapper performs preliminary management-plane operations before invoking
what-if. It can set the active Azure CLI subscription, register
`Microsoft.AlertsManagement`, and ensure the resource group exists.

## 6. Provisioning Limit Checklist

| Resource Type | Number to Deploy | Total After Deployment | Limit or Quota | Notes |
|---------------|------------------|------------------------|----------------|-------|
| Virtual network | 1 | 1 | 1000 | Azure CLI regional network usage |
| Public IP address | 2 | 2 | 1000 | NAT and VPN gateway addresses |
| NAT gateway | 1 | 1 | 500 | Azure CLI regional network usage |
| Network security group | 5 baseline | 5 | ARM validation | One per baseline protected subnet |
| Private DNS Resolver | 1 | 1 | ARM validation | Includes inbound endpoint |
| Virtual network gateway | 1 | 1 | ARM validation | P2S VPN gateway |
| User-assigned identity | 1 | 1 | ARM validation | No regional CLI quota exposed |
| Log Analytics workspace | 1 | 1 | ARM validation | No regional CLI quota exposed |
| Application Insights component | 1 | 1 | ARM validation | Workspace based |

Status: All exposed regional limits have sufficient capacity. ARM validation
succeeded for the complete network-phase template.

## 7. Execution Checklist

### Phase 1: Planning

* [x] Analyze the existing deployment wrapper and repository plan
* [x] Confirm the resource group, location, basename, suffix, variant, and phase
* [x] Select the Azure CLI and Bicep recipe
* [x] Record user approval from the explicit execution request
* [x] Inventory network resources and check applicable limits

### Phase 2: Validation

* [x] Verify the Azure CLI account, tenant, subscription, and location
* [x] Compile `phase1-network.bicep`
* [x] Validate wrapper syntax
* [x] Create and confirm the approved target resource group
* [x] Record validation proof
* [x] Set status to `Validated`

### Phase 3: What-if

* [x] Execute the approved wrapper command with `--what-if`
* [x] Record the what-if result

### Phase 4: Deployment

* [x] Receive user approval to deploy the reviewed network resources
* [x] Execute the private network deployment
* [x] Verify the ARM deployment and provisioned resources
* [x] Set status to `Deployed`

## 8. Validation Proof

| Check | Command Run | Result | Timestamp |
|-------|-------------|--------|-----------|
| Azure CLI context | `az account show` | Pass: expected enabled subscription, tenant, and user | 2026-08-11T16:22:20Z |
| Bash syntax | `bash -n src/infra_deployment/deploy.sh` | Pass | 2026-08-11T16:22:20Z |
| Bicep compilation | `az bicep build --file src/infra_deployment/private/phase1-network.bicep --stdout` | Pass | 2026-08-11T16:22:20Z |
| Regional network usage | `az network list-usages --location westus3` | Pass: VNet 0/1000, public IP 0/1000, NAT gateway 0/500 | 2026-08-11T16:22:20Z |
| Required providers | `az provider show` for Network, ManagedIdentity, OperationalInsights, and Insights | Pass: all registered | 2026-08-11T16:22:20Z |
| ARM validation | `az deployment group validate` with filtered phase parameters and approved overrides | Pass: `Succeeded`, no error | 2026-08-11T16:22:20Z |
| ARM what-if | Approved command in section 10 | Pass: planned creates displayed and analysis completed successfully | 2026-08-11T16:43:12Z |
| Non-mutation check | `az resource list` and `az deployment group list` for `rg-att-nf-pvt` | Pass: 0 resources and 0 deployment records | 2026-08-11T16:43:12Z |
| Subscription feature | `az feature register` and `az provider register --wait` | Pass: `AllowBringYourOwnPublicIpAddress` registered | 2026-08-11 |
| Network deployment | `attnf-deploy-20260811-134047` | Pass: ARM deployment succeeded in 27 minutes | 2026-08-11T19:09:29Z |
| Resource verification | `az resource list` for `rg-att-nf-pvt` | Pass: 50 resources, 0 failed provisioning states | 2026-08-11 |

Validated by: azure-validate workflow

Validation timestamp: 2026-08-11T16:22:20Z

## 9. Files

| File | Purpose | Status |
|------|---------|--------|
| `.azure/deployment-plan.md` | Deployment workflow source of truth | Created |
| `src/infra_deployment/deploy.sh` | Existing deployment wrapper | Existing |
| `src/infra_deployment/private/phase1-network.bicep` | Existing network template | Existing |

## 10. Approved Command

```bash
bash src/infra_deployment/deploy.sh --variant private --phase network \
  --resource-group "rg-att-nf-pvt" --location westus3 \
  --base-name attnf --unique-prefix 1 --what-if
```

## 11. Next Step

Connect with the generated Azure VPN client profile, then validate private DNS
resolution before beginning the services phase.

## 12. Wrapper Corrections

The what-if exposed phase-routing defects in the existing wrapper. The wrapper
now filters the shared parameter file to declarations in the selected phase,
omits service-only environment overrides during the network phase, displays
successful Azure CLI output, and skips VPN post-deployment operations during
what-if.

The deployment script now also fails before ARM deployment when
`Microsoft.Network/AllowBringYourOwnPublicIpAddress` is not registered.
