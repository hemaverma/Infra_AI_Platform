param baseName string
param location string
param tags object
param delegatedSubnetId string = '' // snet-data-postgres
param privateDnsZoneId string = '' // privatelink.postgres.database.azure.com

@description('Principal ID of the managed identity to configure as Entra admin')
param managedIdentityPrincipalId string

@description('Name of the managed identity (used as Entra admin principal name)')
param managedIdentityName string

@description('PostgreSQL Flexible Server SKU name.')
param skuName string = 'Standard_B1ms'

@description('PostgreSQL Flexible Server compute tier.')
@allowed(['Burstable', 'GeneralPurpose', 'MemoryOptimized'])
param tier string = 'Burstable'

@description('PostgreSQL major version.')
@allowed(['13', '14', '15', '16'])
param version string = '16'

module postgresql 'br/public:avm/res/db-for-postgre-sql/flexible-server:0.14.0' = {
  name: '${baseName}-pg'
  params: {
    name: '${baseName}-pg'
    location: location
    availabilityZone: -1
    skuName: skuName
    tier: tier
    version: version
    highAvailability: 'Disabled'
    #disable-next-line BCP321
    delegatedSubnetResourceId: !empty(delegatedSubnetId) ? delegatedSubnetId : null
    #disable-next-line BCP321
    privateDnsZoneArmResourceId: !empty(privateDnsZoneId) ? privateDnsZoneId : null
    firewallRules: !empty(delegatedSubnetId) ? [] : [
      {
        name: 'AllowAllAzureServicesAndResourcesWithinAzureIps'
        startIpAddress: '0.0.0.0'
        endIpAddress: '0.0.0.0'
      }
    ]
    databases: [
      { name: 'next-db', charset: 'UTF8', collation: 'en_US.utf8' }
    ]
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Disabled'
    }
    administrators: [
      {
        objectId: managedIdentityPrincipalId
        principalName: managedIdentityName
        principalType: 'ServicePrincipal'
      }
    ]
    tags: tags
  }
}

output postgresqlId string = postgresql.outputs.resourceId
