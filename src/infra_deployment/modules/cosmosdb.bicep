param baseName string
param location string
param tags object
param privateEndpointSubnetId string = ''
param privateDnsZoneId string = '' // privatelink.documents.azure.com
param managedIdentityPrincipalId string

@description('Cosmos DB database name')
param databaseName string = 'vendor-email-response'

@description('Cosmos DB container name')
param containerName string = 'workflow-checkpoints'

module cosmosDb 'br/public:avm/res/document-db/database-account:0.11.1' = {
  name: '${baseName}-cosmos'
  params: {
    name: toLower('${baseName}-cosmos')
    location: location
    capabilitiesToAdd: ['EnableServerless']
    enableMultipleWriteLocations: false
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    sqlDatabases: [
      {
        name: databaseName
        containers: [
          {
            name: containerName
            paths: ['/workflow_name']
          }
        ]
      }
    ]
    sqlRoleDefinitions: [
      {
        name: 'dataContributor'
        roleName: 'Workflow Data Contributor'
      }
    ]
    sqlRoleAssignmentsPrincipalIds: [
      managedIdentityPrincipalId
    ]
    privateEndpoints: !empty(privateEndpointSubnetId) ? [
      {
        subnetResourceId: privateEndpointSubnetId
        service: 'Sql'
        privateDnsZoneGroup: { privateDnsZoneGroupConfigs: [{ privateDnsZoneResourceId: privateDnsZoneId }] }
      }
    ] : []
    disableLocalAuth: true
    tags: tags
  }
}

output cosmosDbEndpoint string = cosmosDb.outputs.endpoint
output cosmosDbId string = cosmosDb.outputs.resourceId
