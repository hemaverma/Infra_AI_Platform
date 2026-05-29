// ============================================================================
// ACR Build Infrastructure — Conditional Agent Pool or Bypass Policy
// Deployed by build-image.ps1/sh which determines enableAgentPool at runtime.
// ============================================================================

@description('Name of existing ACR registry.')
param registryName string

@description('Azure region.')
param location string

@description('Enable agent pool (true) or bypass mode (false). Determined by deploy script.')
param enableAgentPool bool

@description('Conditional. Subnet resource ID for agent pool. Required if enableAgentPool=true.')
param agentPoolSubnetId string = ''

@description('Agent pool tier.')
@allowed(['S1', 'S2', 'S3'])
param agentPoolTier string = 'S1'

@description('Agent pool instance count. Use 0 for scale-to-zero between builds.')
param agentPoolCount int = 1

param agentPoolName string = 'buildpool'
param tags object = {}

// ─── Reference existing registry ───
resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: registryName
}

// ─── Path A: Agent Pool (highest security) ───
resource agentPool 'Microsoft.ContainerRegistry/registries/agentPools@2026-01-01' = if (enableAgentPool) {
  parent: registry
  name: agentPoolName
  location: location
  properties: {
    count: agentPoolCount
    tier: agentPoolTier
    os: 'Linux'
    virtualNetworkSubnetResourceId: agentPoolSubnetId
  }
}

// ─── Path B: Bypass Policy (universal fallback) ───
// networkRuleBypassAllowedForTasks requires 2025-06-01-preview API
// Set via az resource update in the script since Bicep may not support this API version yet.
// This resource ensures networkRuleBypassOptions is set for trusted services.
resource registryBypass 'Microsoft.ContainerRegistry/registries@2023-07-01' = if (!enableAgentPool) {
  name: registryName
  location: location
  properties: {
    networkRuleBypassOptions: 'AzureServices'
  }
  tags: tags
}

// ─── Outputs ───
output buildMode string = enableAgentPool ? 'agentPool' : 'bypass'
output agentPoolResourceId string = enableAgentPool ? agentPool.id : ''
output registryLoginServer string = registry.properties.loginServer
