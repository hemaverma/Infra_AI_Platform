#!/usr/bin/env pwsh
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
#Requires -Version 7.0
<#
.SYNOPSIS
    Build and push a container image to a private ACR via local Docker.
.DESCRIPTION
    Builds a Docker image locally and pushes it to an Azure Container Registry
    accessible over a private endpoint (VPN required). Validates DNS resolution
    to confirm private connectivity before attempting push.
.PARAMETER TargetLocation
    Azure region where the ACR is deployed.
.PARAMETER RegistryName
    Name of the ACR registry. If omitted, resolved from the resource group.
.PARAMETER ResourceGroup
    Resource group containing the ACR. Falls back to $env:AZURE_RESOURCE_GROUP.
.PARAMETER ImageName
    Image name (without tag). Default: communicator
.PARAMETER Tag
    Image tag. Default: latest
.PARAMETER DockerfilePath
    Path to Dockerfile. Default: src/communicator_app/Dockerfile
.PARAMETER ContextPath
    Docker build context directory. Default: src/communicator_app/
.PARAMETER AgentPoolName
    Name for the agent pool. Default: buildpool
.PARAMETER AgentPoolSubnetId
    Subnet resource ID for agent pool. If empty, bypass mode is used even when agent pool is available.
.PARAMETER LocalBuild
    Build image locally with Docker and push to ACR. Bypasses agent pool and bypass strategies entirely.
.EXAMPLE
    ./build-image.ps1 -ResourceGroup "Next-Private"
.EXAMPLE
    ./build-image.ps1 -RegistryName "myacr" -Tag "v1.2.3"
.NOTES
    Requires: Docker Desktop running, Azure CLI authenticated, VPN connected.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$RegistryName,

    [Parameter(Mandatory = $false)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $false)]
    [string]$ImageName = "communicator",

    [Parameter(Mandatory = $false)]
    [string]$Tag = "latest",

    [Parameter(Mandatory = $false)]
    [string]$DockerfilePath = "src/communicator_app/Dockerfile",

    [Parameter(Mandatory = $false)]
    [string]$ContextPath = "src/communicator_app/"
)

$ErrorActionPreference = 'Stop'

# ─── Step 1: Verify Docker daemon is running ───
Write-Host "[1/8] Checking Docker daemon..." -ForegroundColor Cyan
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker daemon is not running. Start Docker Desktop and retry." -ForegroundColor Red
    exit 1
}
Write-Host "  Docker is running." -ForegroundColor Green

# ─── Step 2: Verify Azure CLI authentication ───
Write-Host "[2/8] Checking Azure CLI authentication..." -ForegroundColor Cyan
az account show -o none 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Not authenticated. Run 'az login' first." -ForegroundColor Red
    exit 1
}
Write-Host "  Azure CLI authenticated." -ForegroundColor Green

# ─── Step 3: Resolve resource group ───
Write-Host "[3/8] Resolving resource group..." -ForegroundColor Cyan
if (-not $ResourceGroup) {
    $ResourceGroup = $env:AZURE_RESOURCE_GROUP
}
if (-not $ResourceGroup) {
    Write-Host "ERROR: ResourceGroup not provided and AZURE_RESOURCE_GROUP not set." -ForegroundColor Red
    exit 1
}
Write-Host "  Resource group: $ResourceGroup" -ForegroundColor Green

# ─── Step 4: Resolve ACR name ───
Write-Host "[4/8] Resolving ACR registry name..." -ForegroundColor Cyan
if (-not $RegistryName) {
    $RegistryName = az acr list --resource-group $ResourceGroup --query "[0].name" -o tsv 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $RegistryName) {
        Write-Host "ERROR: No ACR found in resource group '$ResourceGroup'." -ForegroundColor Red
        exit 1
    }
}
$loginServer = "$RegistryName.azurecr.io"
Write-Host "  Registry: $loginServer" -ForegroundColor Green

# ─── Step 5: DNS resolution check (private endpoint) ───
Write-Host "[5/8] Verifying private DNS resolution for $loginServer..." -ForegroundColor Cyan
try {
    $addresses = [System.Net.Dns]::GetHostAddresses($loginServer)
    $resolvedIp = $addresses[0].ToString()
    if (-not $resolvedIp.StartsWith("10.")) {
        Write-Host "WARNING: $loginServer resolves to $resolvedIp (not a private IP)." -ForegroundColor Yellow
        Write-Host "  Ensure VPN is connected for private endpoint access." -ForegroundColor Yellow
    }
    else {
        Write-Host "  Resolved to private IP: $resolvedIp" -ForegroundColor Green
    }
}
catch {
    Write-Host "ERROR: Cannot resolve $loginServer. Check DNS and VPN connectivity." -ForegroundColor Red
    exit 1
}

# ─── Step 6: ACR login ───
Write-Host "[6/8] Logging in to ACR..." -ForegroundColor Cyan
az acr login --name $RegistryName 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Standard login failed, trying token-based login..." -ForegroundColor Yellow
    $tokenJson = az acr login --name $RegistryName --expose-token -o json 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: ACR login failed. Check permissions and connectivity." -ForegroundColor Red
        exit 1
    }
    $token = ($tokenJson | ConvertFrom-Json)
    $token.accessToken | docker login $loginServer --username "00000000-0000-0000-0000-000000000000" --password-stdin
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Docker login with token failed." -ForegroundColor Red
        exit 1
    }
}
Write-Host "  ACR login successful." -ForegroundColor Green

# ─── Step 7: Docker build ───
$fullImage = "$loginServer/${ImageName}:${Tag}"
Write-Host "[7/8] Building image: $fullImage" -ForegroundColor Cyan
docker build -t $fullImage -f $DockerfilePath $ContextPath
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker build failed." -ForegroundColor Red
    exit 1
}
Write-Host "  Build successful." -ForegroundColor Green

# ─── Step 8: Docker push ───
Write-Host "[8/8] Pushing image: $fullImage" -ForegroundColor Cyan
docker push $fullImage
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker push failed. Verify VPN connectivity and ACR permissions." -ForegroundColor Red
    exit 1
}
Write-Host "  Push successful." -ForegroundColor Green

# ─── Verify tag exists in registry ───
Write-Host "Verifying tag in registry..." -ForegroundColor Cyan
$tags = az acr repository show-tags --name $RegistryName --repository $ImageName --output tsv 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: Could not verify tags. Image may still have been pushed." -ForegroundColor Yellow
}
elseif ($tags -match $Tag) {
    Write-Host "Verified: Tag '$Tag' exists in $loginServer/$ImageName" -ForegroundColor Green
}
else {
    Write-Host "WARNING: Tag '$Tag' not found in repository listing." -ForegroundColor Yellow
}

Write-Host "`nDone. Image available at: $fullImage" -ForegroundColor Green
