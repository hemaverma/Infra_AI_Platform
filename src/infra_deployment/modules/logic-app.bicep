// AVM-based Logic App deployment
// Note: WS1 (Workflow Standard) plan for Linux Logic App Standard
param baseName string
param location string
param tags object
param functionsSubnetId string = ''       // snet-functions (shared with Function App)
param privateEndpointSubnetId string = ''
param websitesDnsZoneId string = ''
param managedIdentityId string
param storageAccountName string
param serviceBusNamespaceName string
param appInsightsConnectionString string
param blobConnectionName string = ''
param blobConnectionRuntimeUrl string = ''
param office365ConnectionName string = ''
param office365ConnectionRuntimeUrl string = ''
param teamsConnectionName string = ''
param teamsConnectionRuntimeUrl string = ''

@description('Shared mailbox address for the email-poller workflow to monitor')
param sharedMailboxAddress string = ''

@description('Teams group (team) ID for HITL approval notifications')
param teamsGroupId string = ''

@description('Teams channel ID for HITL approval notifications')
param teamsChannelId string = ''

@description('Email recipient for approved email notifications')
param notificationRecipientEmail string = ''

@description('GitHub repository URL for Deployment Center (e.g. https://github.com/owner/repo)')
param githubRepoUrl string = ''

@description('Branch to deploy from')
param githubBranch string = 'main'

@description('Subdirectory in the repo containing Logic App files')
param projectPath string = 'src/logic_app'

module logicAppPlan 'br/public:avm/res/web/serverfarm:0.4.1' = {
  name: '${baseName}-logic-plan'
  params: {
    name: '${baseName}-logic-plan'
    location: location
    kind: 'linux'
    reserved: true
    skuName: 'WS1'
    skuCapacity: 1
    tags: tags
  }
}

module logicApp 'br/public:avm/res/web/site:0.15.1' = {
  name: '${baseName}-logic'
  params: {
    name: '${baseName}-logic'
    location: location
    kind: 'functionapp,workflowapp,linux'
    serverFarmResourceId: logicAppPlan.outputs.resourceId
    managedIdentities: { userAssignedResourceIds: [managedIdentityId] }
    virtualNetworkSubnetId: !empty(functionsSubnetId) ? functionsSubnetId : null
    siteConfig: {
      vnetRouteAllEnabled: !empty(functionsSubnetId)
      ftpsState: 'Disabled'
    }
    appSettingsKeyValuePairs: {
      FUNCTIONS_WORKER_RUNTIME: 'node'
      FUNCTIONS_EXTENSION_VERSION: '~4'
      AzureWebJobsStorage__accountName: storageAccountName
      ServiceBusConnection__fullyQualifiedNamespace: '${serviceBusNamespaceName}.servicebus.windows.net'
      APPLICATIONINSIGHTS_CONNECTION_STRING: appInsightsConnectionString
      WORKFLOWS_SUBSCRIPTION_ID: subscription().subscriptionId
      WORKFLOWS_LOCATION_NAME: location
      WORKFLOWS_RESOURCE_GROUP_NAME: resourceGroup().name
      BLOB_CONNECTION_NAME: blobConnectionName
      BLOB_CONNECTION_RUNTIME_URL: blobConnectionRuntimeUrl
      OFFICE365_CONNECTION_NAME: office365ConnectionName
      OFFICE365_CONNECTION_RUNTIME_URL: office365ConnectionRuntimeUrl
      TEAMS_CONNECTION_NAME: teamsConnectionName
      TEAMS_CONNECTION_RUNTIME_URL: teamsConnectionRuntimeUrl
      SHARED_MAILBOX_ADDRESS: sharedMailboxAddress
      TEAMS_GROUP_ID: teamsGroupId
      TEAMS_CHANNEL_ID: teamsChannelId
      NOTIFICATION_RECIPIENT_EMAIL: notificationRecipientEmail
      PROJECT: !empty(githubRepoUrl) ? projectPath : ''
      SCM_DO_BUILD_DURING_DEPLOYMENT: !empty(githubRepoUrl) ? '1' : ''
    }
    privateEndpoints: !empty(privateEndpointSubnetId) ? [
      {
        subnetResourceId: privateEndpointSubnetId
        privateDnsZoneGroup: { privateDnsZoneGroupConfigs: [{ privateDnsZoneResourceId: websitesDnsZoneId }] }
      }
    ] : []
    tags: tags
  }
}

// Deployment Center — Azure internal infra monitors GitHub and deploys via internal network
resource logicAppSite 'Microsoft.Web/sites@2023-12-01' existing = {
  name: '${baseName}-logic'
}

resource deploymentCenter 'Microsoft.Web/sites/sourcecontrols@2023-12-01' = if (!empty(githubRepoUrl)) {
  name: 'web'
  parent: logicAppSite
  dependsOn: [logicApp]
  properties: {
    repoUrl: githubRepoUrl
    branch: githubBranch
    isManualIntegration: true
    isMercurial: false
    isGitHubAction: false
    deploymentRollbackEnabled: false
  }
}

output logicAppId string = logicApp.outputs.resourceId
output logicAppName string = logicApp.outputs.name
