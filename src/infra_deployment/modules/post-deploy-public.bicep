// ============================================================================
// Module: post-deploy-public.bicep
// Purpose: Public-mode post-deployment script that updates the Container App
//          with a GHCR image and deploys Logic App workflows using embedded
//          JSON (no git clone required). Enables stateless, repeatable deploys.
// ============================================================================

@description('Base name prefix for all resources.')
param baseName string

@description('Location for deployment script resources.')
param location string

@description('Resource tags.')
param tags object

@description('Container App name to update.')
param containerAppName string

@description('Logic App name for workflow deployment.')
param logicAppName string

@description('Whether to deploy the container image and update the Container App.')
param deployContainerApp bool = true

@description('Whether to deploy Logic App workflows.')
param deployLogicApp bool = true

@description('GHCR image reference for public mode.')
param ghcrImage string

@description('Azure CLI version for the deployment script.')
param azCliVersion string = '2.67.0'

@description('Force re-execution on each deployment.')
param forceUpdateTag string = utcNow()

// === Embedded Workflow JSON (loaded at compile time) ===

var workflowMainJson = loadTextContent('../../logic_app/logic_app_workflow_main.json')
var workflowHitlJson = loadTextContent('../../logic_app/logic_app_workflow-hitl.json')
var hostJson = loadTextContent('../../logic_app/host.json')
var connectionsJson = loadTextContent('../../logic_app/connections.json')

// === Deployment Script Identity ===

resource scriptIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${baseName}-script-id'
  location: location
  tags: tags
}

// === Role Assignment: Contributor on resource group ===

var contributorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'b24988ac-6180-42a0-ab88-20f7382dd24c'
)

resource scriptRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, scriptIdentity.id, 'b24988ac-6180-42a0-ab88-20f7382dd24c')
  properties: {
    roleDefinitionId: contributorRoleId
    principalId: scriptIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// === Dedicated Storage Account for Deployment Scripts ===
// ACI (underlying deployment scripts) requires SMB file share mounting via storage account key.
// The MCAPSGovDeployPolicies Modify policy sets allowSharedKeyAccess=false on all storage accounts
// UNLESS the resource or resource group has tag 'SecurityControl: Ignore'.

resource scriptStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: toLower(replace('${baseName}-dsst', '-', ''))
  location: location
  tags: union(tags, {
    SecurityControl: 'Ignore'
    'security-exception': 'shared-key-required-for-aci'
  })
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    allowSharedKeyAccess: true
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

// === Storage Account Contributor role for the script identity on the dedicated storage ===

var storageAccountContributorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '17d1049b-9a84-46fb-8f53-869881c3d3ab'
)

resource scriptStorageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(scriptStorage.id, scriptIdentity.id, '17d1049b-9a84-46fb-8f53-869881c3d3ab')
  scope: scriptStorage
  properties: {
    roleDefinitionId: storageAccountContributorRoleId
    principalId: scriptIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// === Post-Deployment Script ===

resource postDeployScript 'Microsoft.Resources/deploymentScripts@2023-08-01' = {
  name: '${baseName}-post-deploy'
  location: location
  tags: tags
  kind: 'AzureCLI'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${scriptIdentity.id}': {}
    }
  }
  properties: {
    azCliVersion: azCliVersion
    forceUpdateTag: forceUpdateTag
    timeout: 'PT30M'
    retentionInterval: 'PT1H'
    cleanupPreference: 'Always'
    storageAccountSettings: {
      storageAccountName: scriptStorage.name
      storageAccountKey: scriptStorage.listKeys().keys[0].value
    }
    environmentVariables: [
      { name: 'CONTAINER_APP_NAME', value: containerAppName }
      { name: 'LOGIC_APP_NAME', value: logicAppName }
      { name: 'RESOURCE_GROUP', value: resourceGroup().name }
      { name: 'GHCR_IMAGE', value: ghcrImage }
      { name: 'DEPLOY_CONTAINER_APP', value: string(deployContainerApp) }
      { name: 'DEPLOY_LOGIC_APP', value: string(deployLogicApp) }
      { name: 'WORKFLOW_MAIN_JSON', value: workflowMainJson }
      { name: 'WORKFLOW_HITL_JSON', value: workflowHitlJson }
      { name: 'HOST_JSON', value: hostJson }
      { name: 'CONNECTIONS_JSON', value: connectionsJson }
    ]
    scriptContent: '''
      set -e

      if [ "$DEPLOY_CONTAINER_APP" = "true" ] || [ "$DEPLOY_CONTAINER_APP" = "True" ]; then
        echo "=== Updating Container App with GHCR image ==="
        az containerapp update \
          --name "$CONTAINER_APP_NAME" \
          --resource-group "$RESOURCE_GROUP" \
          --image "$GHCR_IMAGE"
        echo "Container App updated."
      fi

      if [ "$DEPLOY_LOGIC_APP" = "true" ] || [ "$DEPLOY_LOGIC_APP" = "True" ]; then
        echo "=== Deploying Logic App workflows (embedded JSON, no git) ==="
        az extension add --name logic --yes 2>/dev/null || true
        tdnf install -y zip 2>/dev/null || apk add --no-cache zip 2>/dev/null || apt-get update -qq && apt-get install -y -qq zip 2>/dev/null || true

        mkdir -p /tmp/build/email-poller /tmp/build/hitl-approval
        printf '%s' "$WORKFLOW_MAIN_JSON" > /tmp/build/email-poller/workflow.json
        printf '%s' "$WORKFLOW_HITL_JSON" > /tmp/build/hitl-approval/workflow.json
        printf '%s' "$HOST_JSON" > /tmp/build/host.json
        printf '%s' "$CONNECTIONS_JSON" > /tmp/build/connections.json

        cd /tmp/build
        zip -r /tmp/workflows.zip .
        az logicapp deployment source config-zip \
          --name "$LOGIC_APP_NAME" \
          --resource-group "$RESOURCE_GROUP" \
          --src /tmp/workflows.zip
        echo "Logic App workflows deployed."
      fi

      echo "=== Post-deployment complete ==="
    '''
  }
  dependsOn: [
    scriptRoleAssignment
    scriptStorageRoleAssignment
  ]
}

// === Outputs ===

@description('Principal ID of the deployment script managed identity.')
output scriptIdentityPrincipalId string = scriptIdentity.properties.principalId
