<#
.SYNOPSIS
    Deploy Logic App Standard workflow definitions via zip deployment.
.DESCRIPTION
    Packages workflow JSON definitions into the required folder structure
    and deploys them to the specified Logic App Standard instance.
.PARAMETER ResourceGroup
    Azure resource group containing the Logic App.
.PARAMETER LogicAppName
    Name of the Logic App Standard instance.
.PARAMETER DryRun
    When set, builds the zip package but does not deploy.
#>
param(
    [Parameter(Mandatory)]
    [string]$ResourceGroup,

    [Parameter(Mandatory)]
    [string]$LogicAppName,

    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$scriptDir = $PSScriptRoot
$buildDir = Join-Path $scriptDir 'build'
$zipPath = Join-Path $scriptDir 'workflows.zip'

# Workflow definitions: folder name -> source JSON file
$workflows = @{
    'email-poller'   = 'logic_app_workflow_main.json'
    'hitl-approval'  = 'logic_app_workflow-hitl.json'
}

# --- Clean previous build ---
if (Test-Path $buildDir) { Remove-Item $buildDir -Recurse -Force }
New-Item -ItemType Directory -Path $buildDir | Out-Null

# --- Create workflow folders ---
foreach ($entry in $workflows.GetEnumerator()) {
    $wfDir = Join-Path $buildDir $entry.Key
    New-Item -ItemType Directory -Path $wfDir | Out-Null

    $sourcePath = Join-Path $scriptDir $entry.Value
    if (-not (Test-Path $sourcePath)) {
        Write-Error "Workflow source not found: $sourcePath"
    }
    Copy-Item $sourcePath (Join-Path $wfDir 'workflow.json')
    Write-Host "  Packaged: $($entry.Key)/workflow.json"
}

# --- Copy global files ---
$globalFiles = @('host.json', 'connections.json', 'parameters.json')
foreach ($file in $globalFiles) {
    $filePath = Join-Path $scriptDir $file
    if (-not (Test-Path $filePath)) {
        Write-Error "Required file not found: $filePath"
    }
    Copy-Item $filePath $buildDir
    Write-Host "  Included: $file"
}

# --- Create zip package ---
if (Test-Path $zipPath) { Remove-Item $zipPath }
Compress-Archive -Path "$buildDir/*" -DestinationPath $zipPath
Write-Host "`n  Package created: $zipPath"

if ($DryRun) {
    Write-Host "`n[DryRun] Skipping deployment. Package ready at: $zipPath"
    Write-Host "[DryRun] Contents:"
    Get-ChildItem $buildDir -Recurse | ForEach-Object {
        Write-Host "  $($_.FullName.Replace($buildDir, ''))"
    }
    return
}

# --- Deploy ---
Write-Host "`nDeploying workflows to $LogicAppName in $ResourceGroup..."
az logicapp deployment source config-zip `
    --name $LogicAppName `
    --resource-group $ResourceGroup `
    --src $zipPath

if ($LASTEXITCODE -ne 0) {
    Write-Error "Deployment failed with exit code $LASTEXITCODE"
}

Write-Host "`n Workflows deployed to $LogicAppName"
