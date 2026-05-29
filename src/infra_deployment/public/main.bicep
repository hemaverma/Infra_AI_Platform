// ============================================================================
// NExT Accelerator Infrastructure — Public Orchestrator (No VNet)
// Purpose: Deploys all services with public access for quick PoC setup
// Used by: Deploy to Azure button, public variant CLI deployments
// ============================================================================
targetScope = 'resourceGroup'

// === Parameters ===

@description('Base name prefix for all resources (e.g., next)')
param baseName string

@description('Optional Numeric prefix (1-100) appended to baseName for globally unique resource names')
@maxLength(3)
param uniquePrefix string =''

@description('Azure region for deployment')
@allowed([
  'westus3'
  'centralus'
  'swedencentral'
  'westeurope'
])
param location string = 'westus3'

@description('Whether to deploy Azure OpenAI (requires subscription quota approval)')
param deployOpenAi bool = true

@description('Whether to deploy PostgreSQL Flexible Server')
param deployPostgres bool = true

@description('Azure region for AI services (OpenAI, AI Foundry). Defaults to main location.')
param aiLocation string = location

@description('Azure region for Logic App Standard (App Service Plan quota may differ by region). Defaults to main location.')
param logicAppLocation string = location

@description('Shared mailbox address for the email-poller workflow')
param sharedMailboxAddress string = ''

@description('Teams group (team) ID for HITL approval notifications')
param teamsGroupId string = ''

@description('Teams channel ID for HITL approval notifications')
param teamsChannelId string = ''

@description('Email recipient for approved email notifications')
param notificationRecipientEmail string = ''

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
  project: 'NExT'
  environment: 'poc'
  team: 'next'
  SecurityControl: 'Ignore'
  'security-exception': 'shared-key-required-for-aci'
}

@description('Whether to deploy the Container App (Container Apps Environment hosting)')
param deployContainerApp bool = true

@description('Whether to deploy Service Bus namespace')
param deployServiceBus bool = true

@description('Whether to deploy Storage Queues (false = use Service Bus as primary transport)')
param deployStorageQueues bool = false

@description('Whether to deploy the Logic App (Standard)')
param deployLogicApp bool = true

@description('Whether to deploy Cosmos DB account')
param deployCosmosDb bool = true

@description('Whether to deploy a standalone Function App (native hosting, alternative to Container Apps)')
param deployFunctionApp bool = false

@description('Cosmos DB database name for workflow checkpoints')
param cosmosDbDatabaseName string = 'vendor-email-response'

@description('Cosmos DB container name for workflow checkpoints')
param cosmosDbContainerName string = 'workflow-checkpoints'

@description('Initial container image for Container App. Must be provided at deployment time (e.g., ghcr.io/org/image:tag or ACR reference).')
param containerImage string



// === Computed Names ===
var resourcePrefix = '${baseName}${uniquePrefix}'

// === Phase 1: Foundation ===

module identity '../modules/identity.bicep' = {
  name: 'identity'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
  }
}

module observability '../modules/observability.bicep' = {
  name: 'observability'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
  }
}

// === Phase 2: Security + Storage ===

module keyvault '../modules/keyvault.bicep' = {
  name: 'keyvault'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    managedIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
    enablePurgeProtection: true
    logAnalyticsWorkspaceId: observability.outputs.logAnalyticsWorkspaceId
  }
}

module storage '../modules/storage.bicep' = {
  name: 'storage'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    managedIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
    deployQueues: deployStorageQueues
    logAnalyticsWorkspaceId: observability.outputs.logAnalyticsWorkspaceId
  }
}

// === Phase 3: Messaging + Data ===

module servicebus '../modules/servicebus.bicep' = if (deployServiceBus) {
  name: 'servicebus'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    managedIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
    logAnalyticsWorkspaceId: observability.outputs.logAnalyticsWorkspaceId
  }
}

module cosmosdb '../modules/cosmosdb.bicep' = if (deployCosmosDb) {
  name: 'cosmosdb'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    managedIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
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
    managedIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
    managedIdentityName: identity.outputs.managedIdentityName
  }
}

// === Phase 4: AI Services ===

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
    managedIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
  }
}

module docIntel '../modules/document-intelligence.bicep' = {
  name: 'document-intelligence'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    managedIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
  }
}

module contentSafety '../modules/content-safety.bicep' = {
  name: 'content-safety'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    managedIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
  }
}

module aiFoundry '../modules/ai-foundry.bicep' = if (deployOpenAi) {
  name: 'ai-foundry'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    keyVaultId: keyvault.outputs.keyVaultId
    storageAccountId: storage.outputs.storageAccountId
    appInsightsId: observability.outputs.appInsightsId
    #disable-next-line BCP318
    openAiAccountId: deployOpenAi ? openai.outputs.openAiId : ''
  }
}

// === Phase 5: Compute ===

module logicApp '../modules/logic-app.bicep' = if (deployLogicApp) {
  name: 'logic-app'
  params: {
    baseName: resourcePrefix
    location: logicAppLocation
    tags: tags
    managedIdentityId: identity.outputs.managedIdentityId
    storageAccountName: storage.outputs.storageAccountName
    #disable-next-line BCP318
    serviceBusNamespaceName: deployServiceBus ? servicebus.outputs.serviceBusNamespaceName : ''
    appInsightsConnectionString: observability.outputs.appInsightsConnectionString
    sharedMailboxAddress: sharedMailboxAddress
    teamsGroupId: teamsGroupId
    teamsChannelId: teamsChannelId
    notificationRecipientEmail: notificationRecipientEmail
  }
}



module containerApps '../modules/container-apps.bicep' = if (deployContainerApp) {
  name: 'container-apps'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    managedIdentityId: identity.outputs.managedIdentityId
    managedIdentityClientId: identity.outputs.managedIdentityClientId
    keyVaultName: keyvault.outputs.keyVaultName
    #disable-next-line BCP318
    openAiEndpoint: deployOpenAi ? openai.outputs.openAiEndpoint : ''
    #disable-next-line BCP318
    cosmosDbEndpoint: deployCosmosDb ? cosmosdb.outputs.cosmosDbEndpoint : ''
    appInsightsConnectionString: observability.outputs.appInsightsConnectionString
    logAnalyticsWorkspaceId: observability.outputs.logAnalyticsWorkspaceId
    storageAccountName: storage.outputs.storageAccountName
    #disable-next-line BCP318
    serviceBusNamespaceName: deployServiceBus ? servicebus.outputs.serviceBusNamespaceName : ''
    openAiModelName: openAiModelName
    cosmosDbDatabaseName: cosmosDbDatabaseName
    cosmosDbContainerName: cosmosDbContainerName
    deployStorageQueues: deployStorageQueues
    contentSafetyEndpoint: contentSafety.outputs.contentSafetyEndpoint
    containerImage: containerImage
    acrLoginServer: ''
  }
}

module functionApp '../modules/function-app.bicep' = if (deployFunctionApp) {
  name: 'function-app'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    managedIdentityId: identity.outputs.managedIdentityId
    managedIdentityClientId: identity.outputs.managedIdentityClientId
    keyVaultName: keyvault.outputs.keyVaultName
    storageAccountName: storage.outputs.storageAccountName
    #disable-next-line BCP318
    serviceBusNamespaceName: deployServiceBus ? servicebus.outputs.serviceBusNamespaceName : ''
    #disable-next-line BCP318
    openAiEndpoint: deployOpenAi ? openai.outputs.openAiEndpoint : ''
    #disable-next-line BCP318
    cosmosDbEndpoint: deployCosmosDb ? cosmosdb.outputs.cosmosDbEndpoint : ''
    appInsightsConnectionString: observability.outputs.appInsightsConnectionString
    openAiModelName: openAiModelName
    cosmosDbDatabaseName: cosmosDbDatabaseName
    cosmosDbContainerName: cosmosDbContainerName
    deployStorageQueues: deployStorageQueues
    contentSafetyEndpoint: contentSafety.outputs.contentSafetyEndpoint
  }
}

// === Phase 6: Post-Deployment Application Code ===

module postDeploy '../modules/post-deploy-public.bicep' = {
  name: 'post-deploy'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    containerAppName: toLower('${resourcePrefix}-communicator')
    logicAppName: toLower('${resourcePrefix}-logic')
    deployContainerApp: deployContainerApp
    deployLogicApp: deployLogicApp
    ghcrImage: containerImage
  }
  dependsOn: [
    containerApps
    logicApp
  ]
}
