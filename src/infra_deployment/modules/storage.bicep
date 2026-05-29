param baseName string
param location string
param tags object
param privateEndpointSubnetId string = ''
param blobDnsZoneId string = ''
param queueDnsZoneId string = ''
param managedIdentityPrincipalId string
param deployQueues bool = true

@description('Log Analytics workspace resource ID for diagnostic settings. Empty = no diagnostics.')
param logAnalyticsWorkspaceId string = ''

@description('Storage account SKU name.')
@allowed(['Standard_LRS', 'Standard_GRS', 'Standard_ZRS', 'Standard_RAGRS', 'Premium_LRS'])
param skuName string = 'Standard_LRS'

@description('Name of the blob container for email staging.')
param emailStagingContainerName string = 'email-staging'

@description('Name of the workflow storage queue.')
param workflowQueueName string = 'workflow-queue'

@description('Name of the human-in-the-loop storage queue.')
param hitlQueueName string = 'hitl-queue'

var privateEndpoints = !empty(privateEndpointSubnetId) ? (deployQueues ? [
  { service: 'blob', subnetResourceId: privateEndpointSubnetId, privateDnsZoneGroup: { privateDnsZoneGroupConfigs: [{ privateDnsZoneResourceId: blobDnsZoneId }] } }
  { service: 'queue', subnetResourceId: privateEndpointSubnetId, privateDnsZoneGroup: { privateDnsZoneGroupConfigs: [{ privateDnsZoneResourceId: queueDnsZoneId }] } }
] : [
  { service: 'blob', subnetResourceId: privateEndpointSubnetId, privateDnsZoneGroup: { privateDnsZoneGroupConfigs: [{ privateDnsZoneResourceId: blobDnsZoneId }] } }
]) : []

module storageAccount 'br/public:avm/res/storage/storage-account:0.14.3' = {
  name: '${baseName}st'
  params: {
    name: toLower(replace('${baseName}st', '-', ''))
    location: location
    skuName: skuName
    kind: 'StorageV2'
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    networkAcls: !empty(privateEndpointSubnetId) ? { defaultAction: 'Deny', bypass: 'AzureServices' } : { defaultAction: 'Allow', bypass: 'AzureServices' }
    blobServices: {
      containers: [
        { name: emailStagingContainerName, publicAccess: 'None' }
      ]
    }
    queueServices: deployQueues ? {
      queues: [
        { name: workflowQueueName }
        { name: hitlQueueName }
      ]
    } : null
    privateEndpoints: privateEndpoints
    roleAssignments: [
      { principalId: managedIdentityPrincipalId, roleDefinitionIdOrName: 'Storage Blob Data Contributor', principalType: 'ServicePrincipal' }
      { principalId: managedIdentityPrincipalId, roleDefinitionIdOrName: 'Storage Queue Data Contributor', principalType: 'ServicePrincipal' }
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
    tags: tags
  }
}

output storageAccountId string = storageAccount.outputs.resourceId
output storageAccountName string = storageAccount.outputs.name
