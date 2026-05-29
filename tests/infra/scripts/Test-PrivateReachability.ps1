#!/usr/bin/env pwsh
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
#Requires -Version 7.0
<#
.SYNOPSIS
    Validates private endpoint reachability for NExT-Private resources.
.DESCRIPTION
    Runs VPN, DNS, TCP, PE status, and ARM health checks for all resources
    in the NExT-Private resource group. Run while connected to P2S VPN.
.PARAMETER ResourceGroup
    Azure resource group name. Default: NExT-Private
.PARAMETER BaseName
    Resource naming prefix. Default: next4
.PARAMETER SkipVpnCheck
    Skip VPN connectivity verification (for CI/VNet-integrated runners).
.EXAMPLE
    ./Test-PrivateReachability.ps1
.EXAMPLE
    ./Test-PrivateReachability.ps1 -ResourceGroup NExT-Private2 -BaseName next5
.EXAMPLE
    ./Test-PrivateReachability.ps1 -SkipVpnCheck
.NOTES
    Requires Azure CLI (az) authenticated and PowerShell 7.x.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ResourceGroup = "NExT-Private",

    [Parameter(Mandatory = $false)]
    [string]$BaseName = "next4",

    [switch]$SkipVpnCheck
)

$ErrorActionPreference = "Continue"

#region Resource Definitions

$endpoints = @(
    @{ Name = "ACR";              FQDN = "${BaseName}acr.azurecr.io";                        Port = 443 }
    @{ Name = "Key Vault";        FQDN = "${BaseName}-kv.vault.azure.net";                   Port = 443 }
    @{ Name = "Service Bus";      FQDN = "${BaseName}-servicebus.servicebus.windows.net";    Port = 443 }
    @{ Name = "OpenAI";           FQDN = "${BaseName}-oai.openai.azure.com";                 Port = 443 }
    @{ Name = "Cosmos DB";        FQDN = "${BaseName}-cosmos.documents.azure.com";           Port = 443 }
    @{ Name = "Storage Blob";     FQDN = "${BaseName}st.blob.core.windows.net";              Port = 443 }
    @{ Name = "Storage Queue";    FQDN = "${BaseName}st.queue.core.windows.net";             Port = 443 }
    @{ Name = "Storage Table";    FQDN = "${BaseName}st.table.core.windows.net";             Port = 443 }
    @{ Name = "Storage File";     FQDN = "${BaseName}st.file.core.windows.net";              Port = 443 }
    @{ Name = "PostgreSQL";       FQDN = "${BaseName}-pg.postgres.database.azure.com";       Port = 5432 }
    @{ Name = "Doc Intelligence"; FQDN = "${BaseName}-di.cognitiveservices.azure.com";       Port = 443 }
    @{ Name = "Content Safety";   FQDN = "${BaseName}-csafety.cognitiveservices.azure.com";  Port = 443 }
)

#endregion Resource Definitions

#region Main Execution

Write-Host "`n============================================" -ForegroundColor Green
Write-Host "  NExT-Private Reachability Validation" -ForegroundColor Green
Write-Host "  Resource Group: $ResourceGroup" -ForegroundColor Green
Write-Host "  Base Name: $BaseName" -ForegroundColor Green
Write-Host "============================================`n" -ForegroundColor Green

# --- Stage 1: VPN ---
if (-not $SkipVpnCheck) {
    Write-Host "=== 1. VPN CONNECTIVITY ===" -ForegroundColor Cyan
    # Cross-platform VPN IP check using .NET APIs
    $vpnIP = $null
    $interfaces = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()
    foreach ($iface in $interfaces) {
        if ($iface.OperationalStatus -ne 'Up') { continue }
        $props = $iface.GetIPProperties()
        foreach ($addr in $props.UnicastAddresses) {
            if ($addr.Address.AddressFamily -eq 'InterNetwork' -and $addr.Address.ToString() -like '172.16.*') {
                $vpnIP = $addr.Address.ToString()
                break
            }
        }
        if ($vpnIP) { break }
    }
    if ($vpnIP) {
        Write-Host "[PASS] VPN connected: $vpnIP" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] No VPN IP (172.16.x.x). Connect Azure VPN Client first." -ForegroundColor Red
    }

    # Cross-platform route check
    $hasRoutes = $false
    if ($IsWindows) {
        $routes = Get-NetRoute -ErrorAction SilentlyContinue | Where-Object { $_.DestinationPrefix -like "10.0.*" }
        $hasRoutes = $null -ne $routes -and $routes.Count -gt 0
    } elseif ($IsLinux) {
        $routeOutput = bash -c "ip route show 10.0.0.0/8 2>/dev/null" 2>$null
        $hasRoutes = -not [string]::IsNullOrWhiteSpace($routeOutput)
    } elseif ($IsMacOS) {
        $routeOutput = bash -c "netstat -rn 2>/dev/null | grep '10\\.'" 2>$null
        $hasRoutes = -not [string]::IsNullOrWhiteSpace($routeOutput)
    }
    if ($hasRoutes) {
        Write-Host "[PASS] Routes to 10.0.0.0/16 present" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] No routes to 10.0.0.0/16 — VPN may not be routing correctly" -ForegroundColor Red
    }
} else {
    Write-Host "=== 1. VPN CONNECTIVITY (SKIPPED) ===" -ForegroundColor Yellow
}

# --- Stage 2: DNS Resolution ---
Write-Host "`n=== 2. DNS RESOLUTION ===" -ForegroundColor Cyan

# Cross-platform DNS flush
if ($IsWindows) {
    ipconfig /flushdns 2>$null | Out-Null
} elseif ($IsMacOS) {
    bash -c "dscacheutil -flushcache 2>/dev/null; sudo killall -HUP mDNSResponder 2>/dev/null" 2>$null
} elseif ($IsLinux) {
    bash -c "systemd-resolve --flush-caches 2>/dev/null || resolvectl flush-caches 2>/dev/null" 2>$null
}

$dnsResults = foreach ($ep in $endpoints) {
    $ip = $null
    try {
        $addresses = [System.Net.Dns]::GetHostAddresses($ep.FQDN)
        $ip = ($addresses | Where-Object { $_.AddressFamily -eq 'InterNetwork' } | Select-Object -First 1)
        if ($ip) { $ip = $ip.ToString() }
    } catch {
        $ip = $null
    }
    $isPrivate = $ip -and ($ip -match "^10\.")
    $status = if ($isPrivate) { "[PASS]" } elseif ($ip) { "[WARN] Public" } else { "[FAIL]" }
    $color = if ($isPrivate) { "Green" } elseif ($ip) { "Yellow" } else { "Red" }
    Write-Host "$status $($ep.Name): $($ep.FQDN) -> $ip" -ForegroundColor $color
    [PSCustomObject]@{ Resource = $ep.Name; FQDN = $ep.FQDN; IP = $ip; Private = $isPrivate }
}

# --- Stage 3: TCP Connectivity ---
Write-Host "`n=== 3. TCP PORT CONNECTIVITY ===" -ForegroundColor Cyan

$uniqueTests = $endpoints | Group-Object { "$($_.FQDN):$($_.Port)" } | ForEach-Object { $_.Group[0] }
foreach ($ep in $uniqueTests) {
    $connected = $false
    try {
        $tcp = [System.Net.Sockets.TcpClient]::new()
        $connected = $tcp.ConnectAsync($ep.FQDN, $ep.Port).Wait(5000)
        $tcp.Dispose()
    } catch {
        $connected = $false
    }
    $status = if ($connected) { "[PASS]" } else { "[FAIL]" }
    $color = if ($connected) { "Green" } else { "Red" }
    Write-Host "$status $($ep.Name) ($($ep.FQDN):$($ep.Port))" -ForegroundColor $color
}

# --- Stage 4: Private Endpoint Status (ARM) ---
Write-Host "`n=== 4. PRIVATE ENDPOINT STATUS ===" -ForegroundColor Cyan
$peJson = az network private-endpoint list --resource-group $ResourceGroup `
    --query "[].{Name:name, Status:privateLinkServiceConnections[0].privateLinkServiceConnectionState.status, Prov:provisioningState}" `
    -o json 2>$null
if ($peJson) {
    $peList = $peJson | ConvertFrom-Json
    foreach ($pe in $peList) {
        $ok = ($pe.Status -eq "Approved") -and ($pe.Prov -eq "Succeeded")
        $status = if ($ok) { "[PASS]" } else { "[FAIL]" }
        $color = if ($ok) { "Green" } else { "Red" }
        Write-Host "$status $($pe.Name) — Connection: $($pe.Status), Provisioning: $($pe.Prov)" -ForegroundColor $color
    }
} else {
    Write-Host "[FAIL] Could not query private endpoints (check az login)" -ForegroundColor Red
}

# --- Stage 5: Resource Provisioning (ARM) ---
Write-Host "`n=== 5. RESOURCE HEALTH ===" -ForegroundColor Cyan
$armChecks = @(
    @{ Name = "Key Vault";    Cmd = "az keyvault show --name ${BaseName}-kv -g $ResourceGroup --query properties.provisioningState -o tsv" }
    @{ Name = "Storage";      Cmd = "az storage account show --name ${BaseName}st -g $ResourceGroup --query provisioningState -o tsv" }
    @{ Name = "Service Bus";  Cmd = "az servicebus namespace show --name ${BaseName}-servicebus -g $ResourceGroup --query provisioningState -o tsv" }
    @{ Name = "Cosmos DB";    Cmd = "az cosmosdb show --name ${BaseName}-cosmos -g $ResourceGroup --query provisioningState -o tsv" }
    @{ Name = "OpenAI";       Cmd = "az cognitiveservices account show --name ${BaseName}-oai -g $ResourceGroup --query provisioningState -o tsv" }
    @{ Name = "ACR";          Cmd = "az acr show --name ${BaseName}acr -g $ResourceGroup --query provisioningState -o tsv" }
    @{ Name = "PostgreSQL";   Cmd = "az postgres flexible-server show --name ${BaseName}-pg -g $ResourceGroup --query state -o tsv" }
)

foreach ($check in $armChecks) {
    $state = Invoke-Expression $check.Cmd 2>$null
    $ok = $state -in "Succeeded", "Ready"
    $color = if ($ok) { "Green" } elseif ($state) { "Yellow" } else { "Red" }
    $display = if ($state) { $state } else { "NOT FOUND" }
    Write-Host "[$display] $($check.Name)" -ForegroundColor $color
}

Write-Host "`n============================================" -ForegroundColor Green
Write-Host "  VALIDATION COMPLETE" -ForegroundColor Green
Write-Host "============================================`n" -ForegroundColor Green

#endregion Main Execution
