param baseName string
param location string
param tags object
param privateEndpointSubnetId string = ''
param cognitiveServicesDnsZoneId string = ''
param managedIdentityPrincipalId string

module docIntelligence 'br/public:avm/res/cognitive-services/account:0.10.1' = {
  name: '${baseName}-di'
  params: {
    name: toLower('${baseName}-di')
    location: location
    kind: 'FormRecognizer'
    sku: 'S0'
    customSubDomainName: toLower('${baseName}-di')
    privateEndpoints: !empty(privateEndpointSubnetId) ? [
      {
        subnetResourceId: privateEndpointSubnetId
        privateDnsZoneGroup: {
          privateDnsZoneGroupConfigs: [
            { privateDnsZoneResourceId: cognitiveServicesDnsZoneId }
          ]
        }
      }
    ] : []
    roleAssignments: [
      {
        principalId: managedIdentityPrincipalId
        roleDefinitionIdOrName: 'Cognitive Services User'
        principalType: 'ServicePrincipal'
      }
    ]
    networkAcls: !empty(privateEndpointSubnetId) ? { defaultAction: 'Deny' } : { defaultAction: 'Allow' }
    disableLocalAuth: true
    tags: tags
  }
}

output docIntelligenceEndpoint string = docIntelligence.outputs.endpoint
output docIntelligenceId string = docIntelligence.outputs.resourceId
