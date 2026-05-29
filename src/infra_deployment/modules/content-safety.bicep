param baseName string
param location string
param tags object
param privateEndpointSubnetId string = ''
param cognitiveServicesDnsZoneId string = ''
param managedIdentityPrincipalId string

module contentSafety 'br/public:avm/res/cognitive-services/account:0.10.1' = {
  name: '${baseName}-csafety'
  params: {
    name: toLower('${baseName}-csafety')
    location: location
    kind: 'ContentSafety'
    sku: 'S0'
    customSubDomainName: toLower('${baseName}-csafety')
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

output contentSafetyEndpoint string = contentSafety.outputs.endpoint
output contentSafetyId string = contentSafety.outputs.resourceId
