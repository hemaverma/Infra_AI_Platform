param baseName string
param location string
param tags object
param containerAppsSubnetId string = ''   // snet-container-apps
param managedIdentityId string
param managedIdentityClientId string
param logAnalyticsWorkspaceId string
param openAiEndpoint string
param cosmosDbEndpoint string
param keyVaultName string
param appInsightsConnectionString string
param storageAccountName string
param serviceBusNamespaceName string
param openAiModelName string
param cosmosDbDatabaseName string = 'vendor-email-response'
param cosmosDbContainerName string = 'workflow-checkpoints'
param deployStorageQueues bool = true
param contentSafetyEndpoint string = ''

@description('AI Foundry Project resource ID for application code to reference')
param aiProjectResourceId string = ''

@description('Container image reference (e.g., ghcr.io/owner/communicator:latest)')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('ACR login server for registry authentication (empty string skips registry config)')
param acrLoginServer string = ''

@description('Container CPU cores allocation (e.g., 0.25, 0.5, 1.0, 2.0).')
param containerCpu string = '0.5'

@description('Container memory allocation (e.g., 0.5Gi, 1Gi, 2Gi).')
param containerMemory string = '1Gi'

@description('Target port for container app ingress.')
param ingressTargetPort int = 80

module envConfig './env-config.bicep' = {
  name: '${baseName}-env-config-ca'
  params: {
    managedIdentityClientId: managedIdentityClientId
    openAiEndpoint: openAiEndpoint
    openAiModelName: openAiModelName
    cosmosDbEndpoint: cosmosDbEndpoint
    cosmosDbDatabaseName: cosmosDbDatabaseName
    cosmosDbContainerName: cosmosDbContainerName
    keyVaultName: keyVaultName
    appInsightsConnectionString: appInsightsConnectionString
    storageAccountName: storageAccountName
    serviceBusNamespaceName: serviceBusNamespaceName
    deployStorageQueues: deployStorageQueues
    contentSafetyEndpoint: contentSafetyEndpoint
  }
}

module containerAppEnv 'br/public:avm/res/app/managed-environment:0.8.0' = {
  name: '${baseName}-cae'
  params: {
    name: toLower('${baseName}-cae')
    location: location
    tags: tags
    logAnalyticsWorkspaceResourceId: logAnalyticsWorkspaceId
    internal: !empty(containerAppsSubnetId)
    infrastructureSubnetId: !empty(containerAppsSubnetId) ? containerAppsSubnetId : null
    zoneRedundant: false
  }
}

module containerApp 'br/public:avm/res/app/container-app:0.12.1' = {
  name: '${baseName}-ca-communicator'
  params: {
    name: toLower('${baseName}-communicator')
    location: location
    environmentResourceId: containerAppEnv.outputs.resourceId
    managedIdentities: { userAssignedResourceIds: [managedIdentityId] }
    containers: [
      {
        name: 'communicator'
        image: containerImage
        resources: { cpu: containerCpu, memory: containerMemory }
        env: [
          { name: 'AZURE_CLIENT_ID', value: envConfig.outputs.envVars.AZURE_CLIENT_ID }
          { name: 'AZURE_OPENAI_ENDPOINT', value: envConfig.outputs.envVars.AZURE_OPENAI_ENDPOINT }
          { name: 'AZURE_OPENAI_MODEL', value: envConfig.outputs.envVars.AZURE_OPENAI_MODEL }
          { name: 'AZURE_OPENAI_API_VERSION', value: envConfig.outputs.envVars.AZURE_OPENAI_API_VERSION }
          { name: 'AZURE_COSMOS_ENDPOINT', value: envConfig.outputs.envVars.AZURE_COSMOS_ENDPOINT }
          { name: 'AZURE_COSMOS_DATABASE_NAME', value: envConfig.outputs.envVars.AZURE_COSMOS_DATABASE_NAME }
          { name: 'AZURE_COSMOS_CONTAINER_NAME', value: envConfig.outputs.envVars.AZURE_COSMOS_CONTAINER_NAME }
          { name: 'AZURE_KEY_VAULT_NAME', value: envConfig.outputs.envVars.AZURE_KEY_VAULT_NAME }
          { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: envConfig.outputs.envVars.APPLICATIONINSIGHTS_CONNECTION_STRING }
          { name: 'WorkflowQueueName', value: envConfig.outputs.envVars.WorkflowQueueName }
          { name: 'HitlQueueName', value: envConfig.outputs.envVars.HitlQueueName }
          { name: 'ENABLE_STORAGE_QUEUE_TRIGGERS', value: envConfig.outputs.envVars.ENABLE_STORAGE_QUEUE_TRIGGERS }
          { name: 'StorageQueueConnection__queueServiceUri', value: envConfig.outputs.envVars.StorageQueueConnection__queueServiceUri }
          { name: 'StorageQueueConnection__credential', value: envConfig.outputs.envVars.StorageQueueConnection__credential }
          { name: 'StorageQueueConnection__clientId', value: envConfig.outputs.envVars.StorageQueueConnection__clientId }
          { name: 'ServiceBusConnection__fullyQualifiedNamespace', value: envConfig.outputs.envVars.ServiceBusConnection__fullyQualifiedNamespace }
          { name: 'ENABLE_SERVICEBUS_TRIGGERS', value: envConfig.outputs.envVars.ENABLE_SERVICEBUS_TRIGGERS }
          { name: 'EMAIL_BLOB_ACCOUNT_URL', value: envConfig.outputs.envVars.EMAIL_BLOB_ACCOUNT_URL }
          { name: 'EMAIL_BLOB_CONTAINER', value: envConfig.outputs.envVars.EMAIL_BLOB_CONTAINER }
          { name: 'EMAIL_ALLOWED_ATTACHMENT_EXTENSIONS', value: envConfig.outputs.envVars.EMAIL_ALLOWED_ATTACHMENT_EXTENSIONS }
          { name: 'VENDOR_CHECKPOINT_PROVIDER', value: envConfig.outputs.envVars.VENDOR_CHECKPOINT_PROVIDER }
          { name: 'ENABLE_AGENT_EXTRACTION', value: envConfig.outputs.envVars.ENABLE_AGENT_EXTRACTION }
          { name: 'ENABLE_AGENT_EMAIL_DRAFT', value: envConfig.outputs.envVars.ENABLE_AGENT_EMAIL_DRAFT }
          { name: 'ENFORCE_WORKFLOW_IDEMPOTENCY', value: envConfig.outputs.envVars.ENFORCE_WORKFLOW_IDEMPOTENCY }
          { name: 'ENABLE_LLM_DEBUG_LOGS', value: envConfig.outputs.envVars.ENABLE_LLM_DEBUG_LOGS }
          { name: 'LLM_DEBUG_LOG_MAX_CHARS', value: envConfig.outputs.envVars.LLM_DEBUG_LOG_MAX_CHARS }
          { name: 'ENABLE_EXTRACTION_CANDIDATE_HINTS', value: envConfig.outputs.envVars.ENABLE_EXTRACTION_CANDIDATE_HINTS }
          { name: 'EXTRACTION_PROMPT_EMAIL_FORMAT', value: envConfig.outputs.envVars.EXTRACTION_PROMPT_EMAIL_FORMAT }
          { name: 'AI_PROJECT_RESOURCE_ID', value: aiProjectResourceId }
        ]
      }
    ]
    registries: !empty(acrLoginServer) ? [
      {
        server: acrLoginServer
        identity: managedIdentityId
      }
    ] : []
    ingressExternal: false
    ingressTargetPort: ingressTargetPort
    tags: tags
  }
}

output containerAppEnvId string = containerAppEnv.outputs.resourceId
output containerAppFqdn string = containerApp.outputs.fqdn
