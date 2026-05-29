param baseName string
param location string
param tags object
param privateEndpointSubnetId string = ''
param privateDnsZoneId string = '' // privatelink.vaultcore.azure.net
param managedIdentityPrincipalId string

@description('Enable purge protection (required for production).')
param enablePurgeProtection bool = false

@description('Log Analytics workspace resource ID for diagnostic settings. Empty = no diagnostics.')
param logAnalyticsWorkspaceId string = ''

module keyVault 'br/public:avm/res/key-vault/vault:0.11.1' = {
  name: '${baseName}-kv'
  params: {
    name: toLower('${baseName}-kv')
    location: location
    enableRbacAuthorization: true
    enablePurgeProtection: enablePurgeProtection
    tags: tags
    privateEndpoints: !empty(privateEndpointSubnetId) ? [
      {
        subnetResourceId: privateEndpointSubnetId
        privateDnsZoneGroup: {
          privateDnsZoneGroupConfigs: [
            { privateDnsZoneResourceId: privateDnsZoneId }
          ]
        }
      }
    ] : []
    roleAssignments: [
      {
        principalId: managedIdentityPrincipalId
        roleDefinitionIdOrName: 'Key Vault Secrets User'
        principalType: 'ServicePrincipal'
      }
    ]
    diagnosticSettings: !empty(logAnalyticsWorkspaceId) ? [
      {
        name: 'send-to-law'
        workspaceResourceId: logAnalyticsWorkspaceId
        logCategoriesAndGroups: [
          { categoryGroup: 'allLogs' }
        ]
        metricCategories: [
          { category: 'AllMetrics' }
        ]
      }
    ] : []
  }
}

output keyVaultId string = keyVault.outputs.resourceId
output keyVaultName string = keyVault.outputs.name
output keyVaultUri string = keyVault.outputs.uri
