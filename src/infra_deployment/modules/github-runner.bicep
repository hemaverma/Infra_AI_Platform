// ============================================================================
// Module: github-runner.bicep
// Purpose: Provisions a self-hosted GitHub Actions runner VM inside the
//          snet-reserved subnet for private-network CI/CD deployments.
// Uses:    AVM compute/virtual-machine + network/network-security-group modules
// ============================================================================

@description('Base name prefix for all resources')
param baseName string

@description('Location for all resources')
param location string = resourceGroup().location

@description('Resource ID of the runner subnet (snet-reserved)')
param subnetId string

@description('GitHub repository (owner/repo format)')
param githubRepo string

@description('Git branch for setup script download. Used to construct the raw GitHub URL for the runner setup script.')
param setupScriptBranch string = 'main'

@description('GitHub runner registration token (short-lived, generated at deploy time)')
@secure()
param runnerToken string

@description('Runner labels for workflow routing')
param runnerLabels string = 'self-hosted,linux,x64,azure-private'

@description('VM size for the runner')
param vmSize string = 'Standard_D2s_v5'

@description('SSH public key for admin access')
@secure()
param sshPublicKey string

@description('Admin username for the runner VM')
param adminUsername string = 'azureuser'

@description('Tags for all resources')
param tags object = {}

var runnerName = '${baseName}-runner'

// === NSG (AVM) — allow outbound 443 (GitHub endpoints) ===

module runnerNsg 'br/public:avm/res/network/network-security-group:0.5.1' = {
  name: '${runnerName}-nsg'
  params: {
    name: toLower('${runnerName}-nsg')
    location: location
    tags: tags
    securityRules: [
      {
        name: 'AllowHttpsOutbound'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: 'Internet'
        }
      }
      {
        name: 'AllowVnetOutbound'
        properties: {
          priority: 200
          direction: 'Outbound'
          access: 'Allow'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          destinationAddressPrefix: 'VirtualNetwork'
        }
      }
      {
        name: 'DenyAllOtherOutbound'
        properties: {
          priority: 4096
          direction: 'Outbound'
          access: 'Deny'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

// === Runner VM (AVM) — Ubuntu 22.04, system-assigned MI, custom script ===

module runnerVm 'br/public:avm/res/compute/virtual-machine:0.11.0' = {
  name: runnerName
  params: {
    name: toLower(runnerName)
    location: location
    tags: union(tags, { Role: 'GitHubRunner' })
    vmSize: vmSize
    osType: 'Linux'
    zone: 0
    imageReference: {
      publisher: 'Canonical'
      offer: '0001-com-ubuntu-server-jammy'
      sku: '22_04-lts-gen2'
      version: 'latest'
    }
    osDisk: {
      diskSizeGB: 128
      managedDisk: {
        storageAccountType: 'Premium_LRS'
      }
    }
    adminUsername: adminUsername
    disablePasswordAuthentication: true
    publicKeys: [
      {
        keyData: sshPublicKey
        path: '/home/${adminUsername}/.ssh/authorized_keys'
      }
    ]
    customData: loadTextContent('../private/cloud-init-runner.yml')
    nicConfigurations: [
      {
        nicSuffix: '-nic'
        ipConfigurations: [
          {
            name: 'ipconfig1'
            subnetResourceId: subnetId
            privateIPAllocationMethod: 'Dynamic'
          }
        ]
        networkSecurityGroupResourceId: runnerNsg.outputs.resourceId
      }
    ]
    managedIdentities: {
      systemAssigned: true
    }
    encryptionAtHost: false
    extensionCustomScriptConfig: {
      enabled: true
      fileData: []
      protectedSettings: {
        commandToExecute: 'bash /opt/setup-runner.sh "${runnerToken}" "${githubRepo}" "${runnerLabels}" "${runnerName}"'
        fileUris: [
          'https://raw.githubusercontent.com/${githubRepo}/${setupScriptBranch}/src/infra_deployment/private/setup-runner.sh'
        ]
      }
    }
  }
}

// === RG-scoped role assignments (separate — AVM scopes to VM, not RG) ===

// TODO: Verify `systemAssignedMIPrincipalId` is the exact AVM compute/virtual-machine output name.
// If the AVM module uses a different output (e.g., `systemAssignedPrincipalId`), update accordingly.

resource contributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, '${baseName}-runner', 'b24988ac-6180-42a0-ab88-20f7382dd24c')
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'b24988ac-6180-42a0-ab88-20f7382dd24c'
    )
    principalId: runnerVm.outputs.systemAssignedMIPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource storageBlobDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, '${baseName}-runner', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe' // Storage Blob Data Contributor
    )
    principalId: runnerVm.outputs.systemAssignedMIPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// === Outputs ===

output runnerPrincipalId string = runnerVm.outputs.systemAssignedMIPrincipalId
output runnerName string = runnerVm.outputs.name
