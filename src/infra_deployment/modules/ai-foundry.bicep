param baseName string
param location string
param tags object
param privateEndpointSubnetId string = ''
param mlDnsZoneId string = '' // privatelink.api.azureml.ms
param notebooksDnsZoneId string = '' // privatelink.notebooks.azure.net
param storageAccountId string
param keyVaultId string
param appInsightsId string
param openAiAccountId string

@description('Content Safety account endpoint')
param contentSafetyEndpoint string = ''

@description('Content Safety account resource ID')
param contentSafetyResourceId string = ''

@description('Document Intelligence account endpoint')
param docIntelligenceEndpoint string = ''

@description('Document Intelligence account resource ID')
param docIntelligenceResourceId string = ''

var hubConnections = concat(
  [
    {
      name: 'aoai-connection'
      category: 'AzureOpenAI'
      target: openAiAccountId
      connectionProperties: {
        authType: 'AAD'
      }
      metadata: {
        ApiType: 'Azure'
        ResourceId: openAiAccountId
      }
    }
  ],
  !empty(contentSafetyEndpoint) ? [
    {
      name: 'content-safety'
      category: 'CognitiveService'
      target: contentSafetyEndpoint
      metadata: {
        ApiType: 'Azure'
        ResourceId: contentSafetyResourceId
      }
    }
  ] : [],
  !empty(docIntelligenceEndpoint) ? [
    {
      name: 'document-intelligence'
      category: 'CognitiveService'
      target: docIntelligenceEndpoint
      metadata: {
        ApiType: 'Azure'
        ResourceId: docIntelligenceResourceId
      }
    }
  ] : []
)

module aiHub 'br/public:avm/res/machine-learning-services/workspace:0.13.2' = {
  name: '${baseName}-ai-hub'
  params: {
    name: '${baseName}-ai-hub'
    location: location
    kind: 'Hub'
    sku: 'Basic'
    associatedStorageAccountResourceId: storageAccountId
    associatedKeyVaultResourceId: keyVaultId
    associatedApplicationInsightsResourceId: appInsightsId
    connections: hubConnections
    privateEndpoints: !empty(privateEndpointSubnetId) ? [
      {
        subnetResourceId: privateEndpointSubnetId
        privateDnsZoneGroup: {
          privateDnsZoneGroupConfigs: [
            { privateDnsZoneResourceId: mlDnsZoneId }
            { privateDnsZoneResourceId: notebooksDnsZoneId }
          ]
        }
      }
    ] : []
    tags: tags
  }
}

module aiProject 'br/public:avm/res/machine-learning-services/workspace:0.13.2' = {
  name: '${baseName}-ai-project'
  params: {
    name: '${baseName}-ai-project'
    location: location
    kind: 'Project'
    sku: 'Basic'
    hubResourceId: aiHub.outputs.resourceId
    managedIdentities: {
      systemAssigned: true
    }
    // Private endpoints must be on the Hub, not the Project workspace
    tags: tags
  }
}

output aiHubId string = aiHub.outputs.resourceId
output aiProjectId string = aiProject.outputs.resourceId

@description('Principal ID of the AI Project managed identity')
output aiProjectPrincipalId string = aiProject.outputs.?systemAssignedMIPrincipalId ?? ''
