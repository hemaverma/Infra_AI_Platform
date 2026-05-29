// ============================================================================
// Module: observability.bicep
// Purpose: Log Analytics Workspace + Application Insights
// ============================================================================

@description('Base name prefix for all resources')
param baseName string

@description('Azure region for deployment')
param location string

@description('Resource tags')
param tags object

@description('Log Analytics data retention in days.')
param dataRetentionDays int = 30

// === Log Analytics Workspace ===

module logAnalytics 'br/public:avm/res/operational-insights/workspace:0.9.1' = {
  name: '${baseName}-la'
  params: {
    name: '${baseName}-la'
    location: location
    skuName: 'PerGB2018'
    dataRetention: dataRetentionDays
    tags: tags
  }
}

// === Application Insights ===

module appInsights 'br/public:avm/res/insights/component:0.4.2' = {
  name: '${baseName}-ai'
  params: {
    name: '${baseName}-ai'
    location: location
    workspaceResourceId: logAnalytics.outputs.resourceId
    kind: 'web'
    tags: tags
  }
}

// === Outputs ===

@description('Resource ID of the Log Analytics Workspace')
output logAnalyticsWorkspaceId string = logAnalytics.outputs.resourceId

@description('Application Insights instrumentation key')
output appInsightsInstrumentationKey string = appInsights.outputs.instrumentationKey

@description('Application Insights connection string')
output appInsightsConnectionString string = appInsights.outputs.connectionString

@description('Resource ID of Application Insights')
output appInsightsId string = appInsights.outputs.resourceId
