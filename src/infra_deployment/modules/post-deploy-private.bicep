// ============================================================================
// Module: post-deploy-private.bicep
// Purpose: Private-mode post-deployment script that updates the Container App
//          with the ACR image, configures environment variables, and sets
//          Logic App app settings. No git clone or public endpoints required.
// ============================================================================

@description('Base name prefix for all resources')
param baseName string

@description('Location for deployment script resources')
param location string

@description('Resource tags')
param tags object

@description('Container image URL (GHCR)')
param containerImage string

@description('Container App name to update')
param containerAppName string

@description('Logic App name for configuration')
param logicAppName string

@description('Whether to deploy the container image and update the Container App')
param deployContainerApp bool = true

@description('Whether to configure Logic App settings')
param deployLogicApp bool = true

@description('Azure CLI version for the deployment script.')
param azCliVersion string = '2.67.0'

@description('Force re-execution on each deployment')
param forceUpdateTag string = utcNow()

@description('Service Bus namespace name')
param serviceBusNamespaceName string

@description('Cosmos DB endpoint URL')
param cosmosDbEndpoint string

@description('Azure OpenAI endpoint URL')
param openAiEndpoint string

@description('Storage account name')
param storageAccountName string

@description('Key Vault name')
param keyVaultName string

@description('OpenAI model deployment name')
param openAiModelName string

@description('Cosmos DB database name')
param cosmosDbDatabaseName string

@description('Cosmos DB container name')
param cosmosDbContainerName string

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
// ACI requires SMB file share mounting via storage account key.
// The SecurityControl: Ignore tag prevents policy from disabling shared key access.

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

// === Storage Account Contributor role for the script identity ===

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
      { name: 'CONTAINER_IMAGE', value: containerImage }
      { name: 'CONTAINER_APP_NAME', value: containerAppName }
      { name: 'LOGIC_APP_NAME', value: logicAppName }
      { name: 'RESOURCE_GROUP', value: resourceGroup().name }
      { name: 'DEPLOY_CONTAINER_APP', value: string(deployContainerApp) }
      { name: 'DEPLOY_LOGIC_APP', value: string(deployLogicApp) }
      { name: 'SERVICEBUS_NAMESPACE', value: '${serviceBusNamespaceName}.servicebus.windows.net' }
      { name: 'COSMOS_ENDPOINT', value: cosmosDbEndpoint }
      { name: 'OPENAI_ENDPOINT', value: openAiEndpoint }
      { name: 'STORAGE_ACCOUNT_NAME', value: storageAccountName }
      { name: 'KEYVAULT_NAME', value: keyVaultName }
      { name: 'KEYVAULT_DNS_SUFFIX', value: environment().suffixes.keyvaultDns }
      { name: 'STORAGE_DNS_SUFFIX', value: environment().suffixes.storage }
      { name: 'OPENAI_MODEL_NAME', value: openAiModelName }
      { name: 'COSMOS_DATABASE_NAME', value: cosmosDbDatabaseName }
      { name: 'COSMOS_CONTAINER_NAME', value: cosmosDbContainerName }
    ]
    scriptContent: '''
      set -e

      if [ "$DEPLOY_CONTAINER_APP" = "true" ] || [ "$DEPLOY_CONTAINER_APP" = "True" ]; then
        echo "=== Updating Container App with GHCR image ==="
        FULL_IMAGE="${CONTAINER_IMAGE}"
        az containerapp update \
          --name "$CONTAINER_APP_NAME" \
          --resource-group "$RESOURCE_GROUP" \
          --image "$FULL_IMAGE"

        echo "=== Configuring Container App environment variables ==="
        az containerapp update \
          --name "$CONTAINER_APP_NAME" \
          --resource-group "$RESOURCE_GROUP" \
          --set-env-vars \
            SERVICEBUS__FULLYQUALIFIEDNAMESPACE="$SERVICEBUS_NAMESPACE" \
            COSMOS_ENDPOINT="$COSMOS_ENDPOINT" \
            AZURE_OPENAI_ENDPOINT="$OPENAI_ENDPOINT" \
            AZURE_OPENAI_DEPLOYMENT_NAME="$OPENAI_MODEL_NAME" \
            STORAGE_ACCOUNT_NAME="$STORAGE_ACCOUNT_NAME" \
            KEYVAULT_URL="https://${KEYVAULT_NAME}.${KEYVAULT_DNS_SUFFIX}/" \
            COSMOS_DATABASE_NAME="$COSMOS_DATABASE_NAME" \
            COSMOS_CONTAINER_NAME="$COSMOS_CONTAINER_NAME"
      fi

      if [ "$DEPLOY_LOGIC_APP" = "true" ] || [ "$DEPLOY_LOGIC_APP" = "True" ]; then
        echo "=== Configuring Logic App app settings (ARM API) ==="
        az webapp config appsettings set \
          --name "$LOGIC_APP_NAME" \
          --resource-group "$RESOURCE_GROUP" \
          --settings \
            SERVICEBUS_NAMESPACE="${SERVICEBUS_NAMESPACE}" \
            STORAGE_ACCOUNT_NAME="${STORAGE_ACCOUNT_NAME}" \
            BLOB_ENDPOINT="https://${STORAGE_ACCOUNT_NAME}.blob.${STORAGE_DNS_SUFFIX}" \
            COSMOS_ENDPOINT="${COSMOS_ENDPOINT}" \
            KEYVAULT_URL="https://${KEYVAULT_NAME}.${KEYVAULT_DNS_SUFFIX}/"
        echo ""
        echo "NOTE: Logic App workflow zip deploy requires VPN connection."
        echo "Run from a VPN-connected machine:"
        echo "  ./src/logic_app/deploy-workflows.sh --resource-group $RESOURCE_GROUP --logic-app-name $LOGIC_APP_NAME"
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

@description('Deployment script identity principal ID')
output scriptIdentityPrincipalId string = scriptIdentity.properties.principalId
