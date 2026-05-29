param baseName string
param location string
param tags object
param privateEndpointSubnetId string = ''
param cognitiveServicesDnsZoneId string = '' // privatelink.cognitiveservices.azure.com
param openAiDnsZoneId string = '' // privatelink.openai.azure.com
param managedIdentityPrincipalId string
param deploymentName string = 'gpt-4o'
param modelName string = 'gpt-4o'
param modelVersion string = '2024-11-20'

@description('OpenAI model deployment capacity in TPM (thousands).')
param modelCapacity int = 30

module openAi 'br/public:avm/res/cognitive-services/account:0.10.1' = {
  name: '${baseName}-oai'
  params: {
    name: toLower('${baseName}-oai')
    location: location
    kind: 'OpenAI'
    sku: 'S0'
    customSubDomainName: toLower('${baseName}-oai')
    deployments: [
      {
        name: deploymentName
        model: { format: 'OpenAI', name: modelName, version: modelVersion }
        sku: { name: 'GlobalStandard', capacity: modelCapacity }
      }
    ]
    privateEndpoints: !empty(privateEndpointSubnetId) ? [
      {
        subnetResourceId: privateEndpointSubnetId
        privateDnsZoneGroup: {
          privateDnsZoneGroupConfigs: [
            { privateDnsZoneResourceId: cognitiveServicesDnsZoneId }
            { privateDnsZoneResourceId: openAiDnsZoneId }
          ]
        }
      }
    ] : []
    roleAssignments: [
      {
        principalId: managedIdentityPrincipalId
        roleDefinitionIdOrName: 'Cognitive Services OpenAI User'
        principalType: 'ServicePrincipal'
      }
    ]
    networkAcls: !empty(privateEndpointSubnetId) ? { defaultAction: 'Deny' } : { defaultAction: 'Allow' }
    disableLocalAuth: true
    tags: tags
  }
}

output openAiEndpoint string = openAi.outputs.endpoint
output openAiId string = openAi.outputs.resourceId
output openAiName string = openAi.outputs.name
