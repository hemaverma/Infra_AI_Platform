// ============================================================================
// Module: identity.bicep
// Purpose: User Assigned Managed Identity for RBAC-based PaaS access
// ============================================================================

@description('Base name prefix for all resources')
param baseName string

@description('Azure region for deployment')
param location string

@description('Resource tags')
param tags object

// === Managed Identity ===

module managedIdentity 'br/public:avm/res/managed-identity/user-assigned-identity:0.4.1' = {
  name: '${baseName}-identity'
  params: {
    name: '${baseName}-id'
    location: location
    tags: tags
  }
}

// === Outputs ===

@description('Resource ID of the managed identity')
output managedIdentityId string = managedIdentity.outputs.resourceId

@description('Principal ID of the managed identity')
output managedIdentityPrincipalId string = managedIdentity.outputs.principalId

@description('Client ID of the managed identity')
output managedIdentityClientId string = managedIdentity.outputs.clientId

@description('Name of the managed identity')
output managedIdentityName string = managedIdentity.outputs.name
