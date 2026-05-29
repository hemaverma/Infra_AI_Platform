param baseName string
param location string
param tags object
param functionsSubnetId string = ''       // snet-functions for VNet integration
param privateEndpointSubnetId string = '' // snet-private-endpoints for inbound PE
param websitesDnsZoneId string = ''       // privatelink.azurewebsites.net
param managedIdentityId string
param managedIdentityClientId string
param keyVaultName string
param storageAccountName string
param serviceBusNamespaceName string
param openAiEndpoint string
param cosmosDbEndpoint string
param appInsightsConnectionString string
param deployStorageQueues bool = true
param contentSafetyEndpoint string = ''
param openAiModelName string
param cosmosDbDatabaseName string = 'vendor-email-response'
param cosmosDbContainerName string = 'workflow-checkpoints'

@description('Linux function app runtime stack version.')
param linuxFxVersion string = 'PYTHON|3.10'

@description('App Service Plan SKU name for the Function App.')
param appServicePlanSku string = 'S1'

module envConfig './env-config.bicep' = {
  name: '${baseName}-env-config-func'
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

module appServicePlan 'br/public:avm/res/web/serverfarm:0.4.1' = {
  name: '${baseName}-func-plan'
  params: {
    name: '${baseName}-func-plan'
    location: location
    skuName: appServicePlanSku
    kind: 'linux'
    reserved: true
    tags: tags
  }
}

module functionApp 'br/public:avm/res/web/site:0.15.1' = {
  name: '${baseName}-func'
  params: {
    name: '${baseName}-func'
    location: location
    kind: 'functionapp,linux'
    serverFarmResourceId: appServicePlan.outputs.resourceId
    managedIdentities: { userAssignedResourceIds: [managedIdentityId] }
    virtualNetworkSubnetId: !empty(functionsSubnetId) ? functionsSubnetId : null
    siteConfig: {
      linuxFxVersion: linuxFxVersion
      ftpsState: 'Disabled'
      vnetRouteAllEnabled: !empty(functionsSubnetId)
    }
    appSettingsKeyValuePairs: union(envConfig.outputs.envVars, {
      FUNCTIONS_WORKER_RUNTIME: 'python'
      AzureWebJobsStorage__accountName: storageAccountName
    })
    privateEndpoints: !empty(privateEndpointSubnetId) ? [
      {
        subnetResourceId: privateEndpointSubnetId
        privateDnsZoneGroup: { privateDnsZoneGroupConfigs: [{ privateDnsZoneResourceId: websitesDnsZoneId }] }
      }
    ] : []
    tags: tags
  }
}

output functionAppId string = functionApp.outputs.resourceId
output functionAppName string = functionApp.outputs.name
output functionAppDefaultHostName string = functionApp.outputs.defaultHostname
