param baseName string
param location string
param tags object
param privateEndpointSubnetId string = ''
param privateDnsZoneId string = '' // privatelink.servicebus.windows.net
param managedIdentityPrincipalId string

@description('Log Analytics workspace resource ID for diagnostic settings. Empty = no diagnostics.')
param logAnalyticsWorkspaceId string = ''

@description('Service Bus namespace SKU tier.')
@allowed(['Basic', 'Standard', 'Premium'])
param skuName string = 'Premium'

@description('Service Bus namespace messaging units (only applicable for Premium SKU).')
param capacity int = 1

@description('Name of the primary workflow queue.')
param workflowQueueName string = 'workflow-queue'

@description('Name of the human-in-the-loop queue.')
param hitlQueueName string = 'hitl-queue'

module serviceBus 'br/public:avm/res/service-bus/namespace:0.12.0' = {
  name: '${baseName}-servicebus'
  params: {
    name: toLower('${baseName}-servicebus')
    location: location
    skuObject: { name: skuName, capacity: capacity }
    zoneRedundant: false
    queues: [
      { name: workflowQueueName }
      { name: hitlQueueName }
    ]
    privateEndpoints: !empty(privateEndpointSubnetId) ? [
      {
        subnetResourceId: privateEndpointSubnetId
        privateDnsZoneGroup: { privateDnsZoneGroupConfigs: [{ privateDnsZoneResourceId: privateDnsZoneId }] }
      }
    ] : []
    roleAssignments: [
      { principalId: managedIdentityPrincipalId, roleDefinitionIdOrName: 'Azure Service Bus Data Sender', principalType: 'ServicePrincipal' }
      { principalId: managedIdentityPrincipalId, roleDefinitionIdOrName: 'Azure Service Bus Data Receiver', principalType: 'ServicePrincipal' }
    ]
    disableLocalAuth: true
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
    tags: tags
  }
}

output serviceBusNamespaceName string = serviceBus.outputs.name
output serviceBusId string = serviceBus.outputs.resourceId
