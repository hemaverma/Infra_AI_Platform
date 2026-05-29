// ============================================================================
// next Accelerator Infrastructure — Phase 2: Services
// Purpose: Deploys all service modules, referencing Phase 1 resources via existing
// ============================================================================
targetScope = 'resourceGroup'

// === Parameters ===

@description('Base name prefix for all resources (e.g., next)')
param baseName string

@description('Single-digit prefix (1-9) prepended to baseName for globally unique resource names')
@minLength(1)
@maxLength(3)
param uniquePrefix string

@description('Azure region for deployment')
param location string = resourceGroup().location

@description('Whether to deploy Azure OpenAI (requires subscription quota approval)')
param deployOpenAi bool = true

@description('Whether to deploy PostgreSQL Flexible Server (restricted in some regions)')
param deployPostgres bool = true

@description('Azure region for AI services (OpenAI, AI Foundry)')
param aiLocation string = 'westus3'

@description('Azure region for Logic App Standard (App Service Plan quota may differ by region)')
param logicAppLocation string = 'westus2'

@description('Fallback region for services restricted in primary location')
param fallbackLocation string = 'westus3'

@description('Azure OpenAI model deployment name')
param openAiDeploymentName string = 'gpt-5.4'

@description('Azure OpenAI model name (e.g., gpt-4o, gpt-5.4)')
param openAiModelName string = 'gpt-5.4'

@description('Azure OpenAI model version')
param openAiModelVersion string = '2026-03-05'

@description('Azure OpenAI model deployment capacity in TPM (thousands).')
param openAiCapacity int = 30

@description('Resource tags applied to all resources')
param tags object = {
  project: 'next'
  environment: 'poc'
}

@description('Whether to deploy the Container App (Container Apps Environment hosting)')
param deployContainerApp bool = true

@description('Whether to deploy Storage Queues (false = use Service Bus as primary transport)')
param deployStorageQueues bool = true

@description('Whether to deploy the Logic App (Standard)')
param deployLogicApp bool = true

@description('Whether to deploy Service Bus namespace')
param deployServiceBus bool = true

@description('Whether to deploy Cosmos DB account')
param deployCosmosDb bool = true

@description('Cosmos DB database name for workflow checkpoints')
param cosmosDbDatabaseName string = 'vendor-email-response'

@description('Cosmos DB container name for workflow checkpoints')
param cosmosDbContainerName string = 'workflow-checkpoints'

@description('Container image for the communicator app (GHCR image URL)')
param containerImage string = 'ghcr.io/hemaverma/communicator:latest'

// === Computed Names ===
var resourcePrefix = '${baseName}${uniquePrefix}'

// === Existing Phase 1 Resources ===

resource existingVnet 'Microsoft.Network/virtualNetworks@2024-05-01' existing = {
  name: '${resourcePrefix}-vnet'
}

resource existingIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: '${resourcePrefix}-id'
}

resource existingLogAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: '${resourcePrefix}-la'
}

resource existingAppInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: '${resourcePrefix}-ai'
}

// === Existing Private DNS Zones (created by Phase 1 networking module) ===

resource privateDnsZoneBlob 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
  name: 'privatelink.blob.core.windows.net'
}

resource privateDnsZoneQueue 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
  name: 'privatelink.queue.core.windows.net'
}

resource privateDnsZoneServiceBus 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
  name: 'privatelink.servicebus.windows.net'
}

resource privateDnsZoneCosmosDb 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
  name: 'privatelink.documents.azure.com'
}

resource privateDnsZoneCognitiveServices 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
  name: 'privatelink.cognitiveservices.azure.com'
}

resource privateDnsZoneOpenAi 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
  name: 'privatelink.openai.azure.com'
}

resource privateDnsZoneKeyVault 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
  name: 'privatelink.vaultcore.azure.net'
}

resource privateDnsZoneWebSites 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
  name: 'privatelink.azurewebsites.net'
}

resource privateDnsZoneAiFoundryApi 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
  name: 'privatelink.api.azureml.ms'
}

resource privateDnsZoneAiFoundryNotebooks 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
  name: 'privatelink.notebooks.azure.net'
}

resource privateDnsZonePostgres 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
  name: 'privatelink.postgres.database.azure.com'
}



// === Phase 2: Security + Storage ===

module keyvault '../modules/keyvault.bicep' = {
  name: 'keyvault'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    privateEndpointSubnetId: '${existingVnet.id}/subnets/snet-private-endpoints'
    privateDnsZoneId: privateDnsZoneKeyVault.id
    managedIdentityPrincipalId: existingIdentity.properties.principalId
    enablePurgeProtection: true
    logAnalyticsWorkspaceId: existingLogAnalytics.id
  }
}

module storage '../modules/storage.bicep' = {
  name: 'storage'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    privateEndpointSubnetId: '${existingVnet.id}/subnets/snet-private-endpoints'
    blobDnsZoneId: privateDnsZoneBlob.id
    queueDnsZoneId: privateDnsZoneQueue.id
    managedIdentityPrincipalId: existingIdentity.properties.principalId
    deployQueues: deployStorageQueues
    logAnalyticsWorkspaceId: existingLogAnalytics.id
  }
}

// === Phase 2: Messaging + Data ===

module servicebus '../modules/servicebus.bicep' = if (deployServiceBus) {
  name: 'servicebus'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    privateEndpointSubnetId: '${existingVnet.id}/subnets/snet-private-endpoints'
    privateDnsZoneId: privateDnsZoneServiceBus.id
    managedIdentityPrincipalId: existingIdentity.properties.principalId
    logAnalyticsWorkspaceId: existingLogAnalytics.id
  }
}

module cosmosdb '../modules/cosmosdb.bicep' = if (deployCosmosDb) {
  name: 'cosmosdb'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    privateEndpointSubnetId: '${existingVnet.id}/subnets/snet-private-endpoints'
    privateDnsZoneId: privateDnsZoneCosmosDb.id
    managedIdentityPrincipalId: existingIdentity.properties.principalId
    databaseName: cosmosDbDatabaseName
    containerName: cosmosDbContainerName
  }
}

module postgresql '../modules/postgresql.bicep' = if (deployPostgres) {
  name: 'postgresql'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    delegatedSubnetId: '${existingVnet.id}/subnets/snet-data-postgres'
    privateDnsZoneId: privateDnsZonePostgres.id
    managedIdentityPrincipalId: existingIdentity.properties.principalId
    managedIdentityName: existingIdentity.name
  }
}

// === Phase 2: AI Services ===

module openai '../modules/openai.bicep' = if (deployOpenAi) {
  name: 'openai'
  params: {
    baseName: resourcePrefix
    location: aiLocation
    tags: tags
    deploymentName: openAiDeploymentName
    modelName: openAiModelName
    modelVersion: openAiModelVersion
    modelCapacity: openAiCapacity
    privateEndpointSubnetId: '${existingVnet.id}/subnets/snet-private-endpoints'
    cognitiveServicesDnsZoneId: privateDnsZoneCognitiveServices.id
    openAiDnsZoneId: privateDnsZoneOpenAi.id
    managedIdentityPrincipalId: existingIdentity.properties.principalId
  }
}

module docIntel '../modules/document-intelligence.bicep' = {
  name: 'document-intelligence'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    privateEndpointSubnetId: '${existingVnet.id}/subnets/snet-private-endpoints'
    cognitiveServicesDnsZoneId: privateDnsZoneCognitiveServices.id
    managedIdentityPrincipalId: existingIdentity.properties.principalId
  }
}

module contentSafety '../modules/content-safety.bicep' = {
  name: 'content-safety'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    privateEndpointSubnetId: '${existingVnet.id}/subnets/snet-private-endpoints'
    cognitiveServicesDnsZoneId: privateDnsZoneCognitiveServices.id
    managedIdentityPrincipalId: existingIdentity.properties.principalId
  }
}

module aiFoundry '../modules/ai-foundry.bicep' = if (deployOpenAi) {
  name: 'ai-foundry'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    privateEndpointSubnetId: '${existingVnet.id}/subnets/snet-private-endpoints'
    mlDnsZoneId: privateDnsZoneAiFoundryApi.id
    notebooksDnsZoneId: privateDnsZoneAiFoundryNotebooks.id
    keyVaultId: keyvault.outputs.keyVaultId
    storageAccountId: storage.outputs.storageAccountId
    appInsightsId: existingAppInsights.id
    openAiAccountId: deployOpenAi ? openai.outputs.openAiId : ''
  }
}

// === Phase 2: Compute ===

module logicApp '../modules/logic-app.bicep' = if (deployLogicApp) {
  name: 'logic-app'
  params: {
    baseName: resourcePrefix
    location: logicAppLocation
    tags: tags
    functionsSubnetId: '${existingVnet.id}/subnets/snet-functions'
    privateEndpointSubnetId: '${existingVnet.id}/subnets/snet-private-endpoints'
    websitesDnsZoneId: privateDnsZoneWebSites.id
    managedIdentityId: existingIdentity.id
    storageAccountName: storage.outputs.storageAccountName
    serviceBusNamespaceName: deployServiceBus ? servicebus.outputs.serviceBusNamespaceName : ''
    appInsightsConnectionString: existingAppInsights.properties.ConnectionString
  }
}



module containerApps '../modules/container-apps.bicep' = if (deployContainerApp) {
  name: 'container-apps'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    containerAppsSubnetId: '${existingVnet.id}/subnets/snet-container-apps'
    managedIdentityId: existingIdentity.id
    managedIdentityClientId: existingIdentity.properties.clientId
    keyVaultName: keyvault.outputs.keyVaultName
    openAiEndpoint: deployOpenAi ? openai.outputs.openAiEndpoint : ''
    cosmosDbEndpoint: deployCosmosDb ? cosmosdb.outputs.cosmosDbEndpoint : ''
    appInsightsConnectionString: existingAppInsights.properties.ConnectionString
    logAnalyticsWorkspaceId: existingLogAnalytics.id
    storageAccountName: storage.outputs.storageAccountName
    serviceBusNamespaceName: deployServiceBus ? servicebus.outputs.serviceBusNamespaceName : ''
    openAiModelName: openAiModelName
    cosmosDbDatabaseName: cosmosDbDatabaseName
    cosmosDbContainerName: cosmosDbContainerName
    deployStorageQueues: deployStorageQueues
    containerImage: containerImage
    acrLoginServer: ''
    aiProjectResourceId: deployOpenAi ? aiFoundry.outputs.aiProjectId : ''
  }
}
