// ============================================================================
// NExT Accelerator Infrastructure — Main Orchestrator
// Purpose: Composes all modules in dependency order
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

@description('Whether to deploy PostgreSQL Flexible Server (restricted in some regions)')
param deployPostgres bool = true

@description('VNet address space')
param vnetAddressPrefix string = '10.0.0.0/16'

@description('VPN client address pool for P2S connections')
param vpnClientAddressPool string = '172.16.0.0/24'

@description('Entra ID tenant URL for VPN P2S authentication')
param vpnAadTenant string = ''

@description('Entra ID audience (Azure VPN App ID) for VPN P2S authentication')
param vpnAadAudience string = ''

@description('Entra ID issuer URL for VPN P2S authentication')
param vpnAadIssuer string = ''

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

@description('Git branch for setup script download (GitHub Runner VM)')
param setupScriptBranch string = 'main'

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

@description('Whether to run post-deployment application code deployment (ACR build, Container App update, Logic App workflows)')
param deployAppCode bool = true

@description('GitHub repository in owner/repo format for runner registration')
param githubRepo string = ''

@secure()
@description('GitHub runner registration token (1-hour expiry)')
param runnerToken string = ''

@secure()
@description('SSH public key for runner VM admin access')
param sshPublicKey string = ''

@description('Custom DNS server IPs for the VNet. Empty array uses Azure default DNS. Set to DNS Private Resolver inbound IP after resolver is deployed.')
param dnsServerIps array = []

// === Computed Names ===
var resourcePrefix = '${baseName}${uniquePrefix}'

// === Phase 1: Foundation ===

module networking '../modules/networking.bicep' = {
  name: 'networking'
  params: {
    baseName: resourcePrefix
    location: location
    vnetAddressPrefix: vnetAddressPrefix
    vpnClientAddressPool: vpnClientAddressPool
    dnsServers: dnsServerIps
    tags: tags
  }
}

module dnsResolver '../modules/dns-resolver.bicep' = {
  name: 'dns-resolver'
  params: {
    baseName: resourcePrefix
    location: location
    vnetResourceId: networking.outputs.vnetId
    inboundSubnetResourceId: networking.outputs.subnetIds.dnsResolverInbound
    tags: tags
  }
}

module vpnGateway '../modules/vpn-gateway.bicep' = {
  name: 'vpn-gateway'
  params: {
    baseName: resourcePrefix
    location: location
    vnetResourceId: networking.outputs.vnetId
    vpnClientAddressPool: vpnClientAddressPool
    vpnAadTenant: vpnAadTenant
    vpnAadAudience: vpnAadAudience
    vpnAadIssuer: vpnAadIssuer
    tags: tags
  }
}

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
    privateEndpointSubnetId: networking.outputs.subnetIds.privateEndpoints
    privateDnsZoneId: networking.outputs.privateDnsZoneIds.keyVault
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
    privateEndpointSubnetId: networking.outputs.subnetIds.privateEndpoints
    blobDnsZoneId: networking.outputs.privateDnsZoneIds.blob
    queueDnsZoneId: networking.outputs.privateDnsZoneIds.queue
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
    privateEndpointSubnetId: networking.outputs.subnetIds.privateEndpoints
    privateDnsZoneId: networking.outputs.privateDnsZoneIds.serviceBus
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
    privateEndpointSubnetId: networking.outputs.subnetIds.privateEndpoints
    privateDnsZoneId: networking.outputs.privateDnsZoneIds.cosmosDb
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
    delegatedSubnetId: networking.outputs.subnetIds.dataPostgres
    privateDnsZoneId: networking.outputs.privateDnsZoneIds.postgres
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
    privateEndpointSubnetId: networking.outputs.subnetIds.privateEndpoints
    cognitiveServicesDnsZoneId: networking.outputs.privateDnsZoneIds.cognitiveServices
    openAiDnsZoneId: networking.outputs.privateDnsZoneIds.openAi
    managedIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
  }
}

module docIntel '../modules/document-intelligence.bicep' = {
  name: 'document-intelligence'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    privateEndpointSubnetId: networking.outputs.subnetIds.privateEndpoints
    cognitiveServicesDnsZoneId: networking.outputs.privateDnsZoneIds.cognitiveServices
    managedIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
  }
}

module contentSafety '../modules/content-safety.bicep' = {
  name: 'content-safety'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    privateEndpointSubnetId: networking.outputs.subnetIds.privateEndpoints
    cognitiveServicesDnsZoneId: networking.outputs.privateDnsZoneIds.cognitiveServices
    managedIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
  }
}

module aiFoundry '../modules/ai-foundry.bicep' = if (deployOpenAi) {
  name: 'ai-foundry'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    privateEndpointSubnetId: networking.outputs.subnetIds.privateEndpoints
    mlDnsZoneId: networking.outputs.privateDnsZoneIds.aiFoundryApi
    notebooksDnsZoneId: networking.outputs.privateDnsZoneIds.aiFoundryNotebooks
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
    functionsSubnetId: networking.outputs.subnetIds.functions
    privateEndpointSubnetId: networking.outputs.subnetIds.privateEndpoints
    websitesDnsZoneId: networking.outputs.privateDnsZoneIds.webSites
    managedIdentityId: identity.outputs.managedIdentityId
    storageAccountName: storage.outputs.storageAccountName
    #disable-next-line BCP318
    serviceBusNamespaceName: deployServiceBus ? servicebus.outputs.serviceBusNamespaceName : ''
    appInsightsConnectionString: observability.outputs.appInsightsConnectionString
    sharedMailboxAddress: sharedMailboxAddress
    teamsGroupId: teamsGroupId
    teamsChannelId: teamsChannelId
    notificationRecipientEmail: notificationRecipientEmail
    githubRepoUrl: !empty(githubRepo) ? 'https://github.com/${githubRepo}' : ''
    githubBranch: setupScriptBranch
  }
}



module containerApps '../modules/container-apps.bicep' = if (deployContainerApp) {
  name: 'container-apps'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    containerAppsSubnetId: networking.outputs.subnetIds.containerApps
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

// === Phase 6: Post-Deployment Application Code (Private Mode) ===

module postDeploy '../modules/post-deploy-private.bicep' = if (deployAppCode && (deployContainerApp || deployLogicApp)) {
  name: 'post-deploy'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
    containerImage: containerImage
    containerAppName: toLower('${resourcePrefix}-communicator')
    logicAppName: toLower('${resourcePrefix}-logic')
    deployContainerApp: deployContainerApp
    deployLogicApp: deployLogicApp
    #disable-next-line BCP318
    serviceBusNamespaceName: deployServiceBus ? servicebus.outputs.serviceBusNamespaceName : ''
    #disable-next-line BCP318
    cosmosDbEndpoint: deployCosmosDb ? cosmosdb.outputs.cosmosDbEndpoint : ''
    #disable-next-line BCP318
    openAiEndpoint: deployOpenAi ? openai.outputs.openAiEndpoint : ''
    storageAccountName: storage.outputs.storageAccountName
    keyVaultName: keyvault.outputs.keyVaultName
    openAiModelName: openAiModelName
    cosmosDbDatabaseName: cosmosDbDatabaseName
    cosmosDbContainerName: cosmosDbContainerName
  }
  dependsOn: [
    containerApps
    logicApp
  ]
}

// === Phase 7: CI/CD Runner (optional — deploys only when runnerToken is provided) ===

module githubRunner '../modules/github-runner.bicep' = if (!empty(runnerToken)) {
  name: 'github-runner'
  params: {
    location: location
    baseName: resourcePrefix
    subnetId: networking.outputs.subnetIds.reserved
    githubRepo: githubRepo
    runnerToken: runnerToken
    runnerLabels: 'self-hosted,linux,x64,azure-private'
    sshPublicKey: sshPublicKey
    tags: tags
    setupScriptBranch: setupScriptBranch
  }
}
