// ============================================================================
// Shared Environment Configuration
// Purpose: Single source of truth for application environment variables.
// Consumed by function-app.bicep and container-apps.bicep.
// ============================================================================

@description('User-assigned managed identity client ID')
param managedIdentityClientId string

@description('Azure OpenAI endpoint URL')
param openAiEndpoint string

@description('Azure OpenAI deployment/model name')
param openAiModelName string

@description('Cosmos DB endpoint URL')
param cosmosDbEndpoint string

@description('Cosmos DB database name')
param cosmosDbDatabaseName string

@description('Cosmos DB container name')
param cosmosDbContainerName string

@description('Key Vault name')
param keyVaultName string

@description('Application Insights connection string')
param appInsightsConnectionString string

@description('Storage account name')
param storageAccountName string

@description('Service Bus namespace name')
param serviceBusNamespaceName string

@description('Whether Storage Queue transport is active')
param deployStorageQueues bool

@description('Azure Content Safety endpoint URL')
param contentSafetyEndpoint string = ''

@description('Azure OpenAI API version for SDK calls')
param openAiApiVersion string = '2024-12-01-preview'

output envVars object = {
  // Core identity
  AZURE_CLIENT_ID: managedIdentityClientId
  // Queue transport
  WorkflowQueueName: 'workflow-queue'
  HitlQueueName: 'hitl-queue'
  ENABLE_STORAGE_QUEUE_TRIGGERS: deployStorageQueues ? 'true' : 'false'
  StorageQueueConnection__queueServiceUri: 'https://${storageAccountName}.queue.${environment().suffixes.storage}'
  StorageQueueConnection__credential: 'managedidentity'
  StorageQueueConnection__clientId: managedIdentityClientId
  // Service Bus
  ServiceBusConnection__fullyQualifiedNamespace: '${serviceBusNamespaceName}.servicebus.windows.net'
  ENABLE_SERVICEBUS_TRIGGERS: deployStorageQueues ? 'false' : 'true'
  // Azure OpenAI
  AZURE_OPENAI_ENDPOINT: openAiEndpoint
  AZURE_OPENAI_MODEL: openAiModelName
  AZURE_OPENAI_API_VERSION: openAiApiVersion
  // Blob storage
  EMAIL_BLOB_ACCOUNT_URL: 'https://${storageAccountName}.blob.${environment().suffixes.storage}'
  EMAIL_BLOB_CONTAINER: 'email-staging'
  EMAIL_ALLOWED_ATTACHMENT_EXTENSIONS: 'csv'
  // Cosmos DB (checkpoints)
  VENDOR_CHECKPOINT_PROVIDER: 'cosmos'
  AZURE_COSMOS_ENDPOINT: cosmosDbEndpoint
  AZURE_COSMOS_DATABASE_NAME: cosmosDbDatabaseName
  AZURE_COSMOS_CONTAINER_NAME: cosmosDbContainerName
  // Key Vault
  AZURE_KEY_VAULT_NAME: keyVaultName
  // Observability
  APPLICATIONINSIGHTS_CONNECTION_STRING: appInsightsConnectionString
  // Content Safety
  AZURE_CONTENT_SAFETY_ENDPOINT: contentSafetyEndpoint
  // Feature flags (production defaults)
  ENABLE_AGENT_EXTRACTION: 'true'
  ENABLE_AGENT_EMAIL_DRAFT: 'true'
  ENABLE_HTTP_TEST_TRIGGERS: 'false'
  ENFORCE_WORKFLOW_IDEMPOTENCY: 'true'
  // LLM debug/extraction settings
  ENABLE_LLM_DEBUG_LOGS: 'false'
  LLM_DEBUG_LOG_MAX_CHARS: '4000'
  ENABLE_EXTRACTION_CANDIDATE_HINTS: 'false'
  EXTRACTION_PROMPT_EMAIL_FORMAT: 'markdown'
}
