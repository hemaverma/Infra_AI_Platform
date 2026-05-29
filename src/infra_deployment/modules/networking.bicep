// ============================================================================
// Module: networking.bicep
// Purpose: VNet with 8 subnets, NSGs, 16 Private DNS Zones
// ============================================================================

@description('Base name prefix for all resources')
param baseName string

@description('Azure region for deployment')
param location string

@description('VNet address space')
param vnetAddressPrefix string = '10.0.0.0/16'

@description('VPN client address pool (used in NSG rules to allow VPN client access)')
param vpnClientAddressPool string = '172.16.0.0/24'

@description('Resource tags')
param tags object

@description('Deploy the ACR agent pool subnet (for regions that support agent pools)')
param enableAgentPoolSubnet bool = false

@description('Custom DNS server IPs for the VNet (e.g., DNS Private Resolver inbound IP)')
param dnsServers array = []

@description('Subnet CIDR address prefixes for each subnet in the VNet. Override to avoid address conflicts with peered networks.')
param subnetCidrs object = {
  gateway: '10.0.0.0/27'
  functions: '10.0.1.0/26'
  containerApps: '10.0.2.0/23'
  dataPostgres: '10.0.4.0/28'
  dataSqlmi: '10.0.4.32/27'
  privateEndpoints: '10.0.5.0/24'
  monitor: '10.0.6.0/28'
  reserved: '10.0.7.0/24'
  dnsResolver: '10.0.9.0/28'
  agentPool: '10.0.7.0/28'
}

var privateDnsZoneNames = [
  #disable-next-line no-hardcoded-env-urls
  'privatelink.blob.core.windows.net'
  #disable-next-line no-hardcoded-env-urls
  'privatelink.queue.core.windows.net'
  #disable-next-line no-hardcoded-env-urls
  'privatelink.table.core.windows.net'
  #disable-next-line no-hardcoded-env-urls
  'privatelink.file.core.windows.net'
  'privatelink.servicebus.windows.net'
  'privatelink.documents.azure.com'
  'privatelink.cognitiveservices.azure.com'
  'privatelink.openai.azure.com'
  'privatelink.vaultcore.azure.net'
  'privatelink.azurewebsites.net'
  'privatelink.api.azureml.ms'
  'privatelink.notebooks.azure.net'
  'privatelink.monitor.azure.com'
  'privatelink.oms.opinsights.azure.com'
  'privatelink.ods.opinsights.azure.com'
  'privatelink.agentsvc.azure-automation.net'
  'privatelink.postgres.database.azure.com'
]

// === NSGs ===

module nsgFunctions 'br/public:avm/res/network/network-security-group:0.5.1' = {
  name: '${baseName}-nsg-functions'
  params: {
    name: '${baseName}-nsg-functions'
    location: location
    tags: tags
    securityRules: [
      {
        name: 'Allow-Outbound-HTTPS-To-PrivateEndpoints'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: subnetCidrs.functions
          destinationAddressPrefix: subnetCidrs.privateEndpoints
        }
      }
      {
        name: 'Allow-Outbound-AMQP-To-PrivateEndpoints'
        properties: {
          priority: 110
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '5671'
          sourceAddressPrefix: subnetCidrs.functions
          destinationAddressPrefix: subnetCidrs.privateEndpoints
        }
      }
      {
        name: 'Allow-Outbound-PostgreSQL-To-DataSubnet'
        properties: {
          priority: 120
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '5432'
          sourceAddressPrefix: subnetCidrs.functions
          destinationAddressPrefix: subnetCidrs.dataPostgres
        }
      }
      {
        name: 'Allow-Outbound-HTTPS-To-AzureConnectors'
        properties: {
          priority: 130
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: subnetCidrs.functions
          destinationAddressPrefix: 'AzureConnectors'
        }
      }
      {
        name: 'Allow-Outbound-HTTPS-To-AzureMonitor'
        properties: {
          priority: 140
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: subnetCidrs.functions
          destinationAddressPrefix: 'AzureMonitor'
        }
      }
      {
        name: 'Allow-Outbound-HTTPS-To-Internet'
        properties: {
          priority: 200
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: 'VirtualNetwork'
          destinationAddressPrefix: 'Internet'
        }
      }
      {
        name: 'Deny-All-Other-Outbound'
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

module nsgContainerApps 'br/public:avm/res/network/network-security-group:0.5.1' = {
  name: '${baseName}-nsg-container-apps'
  params: {
    name: '${baseName}-nsg-container-apps'
    location: location
    tags: tags
    securityRules: [
      {
        name: 'Allow-Outbound-HTTPS-To-PrivateEndpoints'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: subnetCidrs.containerApps
          destinationAddressPrefix: subnetCidrs.privateEndpoints
        }
      }
      {
        name: 'Allow-Outbound-PostgreSQL-To-DataSubnet'
        properties: {
          priority: 110
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '5432'
          sourceAddressPrefix: subnetCidrs.containerApps
          destinationAddressPrefix: subnetCidrs.dataPostgres
        }
      }
      {
        name: 'Allow-Outbound-HTTPS-To-AzureMonitor'
        properties: {
          priority: 120
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: subnetCidrs.containerApps
          destinationAddressPrefix: 'AzureMonitor'
        }
      }
      {
        name: 'Allow-Outbound-HTTPS-To-AzureAD'
        properties: {
          priority: 130
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: subnetCidrs.containerApps
          destinationAddressPrefix: 'AzureActiveDirectory'
        }
      }
      {
        name: 'Allow-Outbound-HTTPS-To-MCR'
        properties: {
          priority: 140
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: subnetCidrs.containerApps
          destinationAddressPrefix: 'MicrosoftContainerRegistry'
        }
      }
      {
        name: 'Allow-Outbound-HTTPS-To-Internet'
        properties: {
          priority: 150
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: subnetCidrs.containerApps
          destinationAddressPrefix: 'Internet'
        }
      }
      {
        name: 'Deny-All-Other-Outbound'
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

module nsgPrivateEndpoints 'br/public:avm/res/network/network-security-group:0.5.1' = {
  name: '${baseName}-nsg-private-endpoints'
  params: {
    name: '${baseName}-nsg-private-endpoints'
    location: location
    tags: tags
    securityRules: [
      {
        name: 'Allow-Inbound-HTTPS-From-Functions'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: subnetCidrs.functions
          destinationAddressPrefix: subnetCidrs.privateEndpoints
        }
      }
      {
        name: 'Allow-Inbound-HTTPS-From-ContainerApps'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: subnetCidrs.containerApps
          destinationAddressPrefix: subnetCidrs.privateEndpoints
        }
      }
      {
        name: 'Allow-Inbound-HTTPS-From-VPN'
        properties: {
          priority: 120
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: vpnClientAddressPool
          destinationAddressPrefix: subnetCidrs.privateEndpoints
        }
      }
      {
        name: 'Allow-Inbound-HTTPS-From-Reserved'
        properties: {
          priority: 125
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: subnetCidrs.reserved
          destinationAddressPrefix: subnetCidrs.privateEndpoints
        }
      }
      {
        name: 'Allow-Inbound-AMQP-From-Functions'
        properties: {
          priority: 130
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '5671'
          sourceAddressPrefix: subnetCidrs.functions
          destinationAddressPrefix: subnetCidrs.privateEndpoints
        }
      }
      {
        name: 'Deny-All-Other-Inbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
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

module nsgDataPostgres 'br/public:avm/res/network/network-security-group:0.5.1' = {
  name: '${baseName}-nsg-data-postgres'
  params: {
    name: '${baseName}-nsg-data-postgres'
    location: location
    tags: tags
    securityRules: [
      {
        name: 'Allow-Inbound-PostgreSQL-From-Functions'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '5432'
          sourceAddressPrefix: subnetCidrs.functions
          destinationAddressPrefix: subnetCidrs.dataPostgres
        }
      }
      {
        name: 'Allow-Inbound-PostgreSQL-From-ContainerApps'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '5432'
          sourceAddressPrefix: subnetCidrs.containerApps
          destinationAddressPrefix: subnetCidrs.dataPostgres
        }
      }
      {
        name: 'Allow-Inbound-PostgreSQL-From-VPN'
        properties: {
          priority: 120
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '5432'
          sourceAddressPrefix: vpnClientAddressPool
          destinationAddressPrefix: subnetCidrs.dataPostgres
        }
      }
      {
        name: 'Deny-All-Other-Inbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
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

module nsgReserved 'br/public:avm/res/network/network-security-group:0.5.1' = {
  name: '${baseName}-nsg-reserved'
  params: {
    name: '${baseName}-nsg-reserved'
    location: location
    tags: tags
    securityRules: [
      {
        name: 'Allow-Outbound-HTTPS'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: subnetCidrs.reserved
          destinationAddressPrefix: 'Internet'
        }
      }
      {
        name: 'Allow-Outbound-HTTP'
        properties: {
          priority: 110
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '80'
          sourceAddressPrefix: subnetCidrs.reserved
          destinationAddressPrefix: 'Internet'
        }
      }
      {
        name: 'Allow-Outbound-VNet'
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
        name: 'Deny-All-Other-Outbound'
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

// === NAT Gateway for outbound connectivity (GHCR, cloud-init) ===

resource natGatewayPip 'Microsoft.Network/publicIPAddresses@2023-11-01' = {
  name: '${baseName}-natgw-pip'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
  }
}

resource natGateway 'Microsoft.Network/natGateways@2023-11-01' = {
  name: '${baseName}-natgw'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIpAddresses: [
      {
        id: natGatewayPip.id
      }
    ]
    idleTimeoutInMinutes: 4
  }
}

// === Virtual Network ===

module vnet 'br/public:avm/res/network/virtual-network:0.9.0' = {
  name: '${baseName}-vnet'
  params: {
    name: '${baseName}-vnet'
    location: location
    addressPrefixes: [
      vnetAddressPrefix
    ]
    subnets: [
      {
        name: 'GatewaySubnet'
        addressPrefix: subnetCidrs.gateway
      }
      {
        name: 'snet-functions'
        addressPrefix: subnetCidrs.functions
        networkSecurityGroupResourceId: nsgFunctions.outputs.resourceId
        natGatewayResourceId: natGateway.id
        delegation: 'Microsoft.Web/serverFarms'
      }
      {
        name: 'snet-container-apps'
        addressPrefix: subnetCidrs.containerApps
        networkSecurityGroupResourceId: nsgContainerApps.outputs.resourceId
        natGatewayResourceId: natGateway.id
        delegation: 'Microsoft.App/environments'
      }
      {
        name: 'snet-data-postgres'
        addressPrefix: subnetCidrs.dataPostgres
        networkSecurityGroupResourceId: nsgDataPostgres.outputs.resourceId
        delegation: 'Microsoft.DBforPostgreSQL/flexibleServers'
      }
      {
        name: 'snet-data-sqlmi'
        addressPrefix: subnetCidrs.dataSqlmi
        delegation: 'Microsoft.Sql/managedInstances'
      }
      {
        name: 'snet-private-endpoints'
        addressPrefix: subnetCidrs.privateEndpoints
        networkSecurityGroupResourceId: nsgPrivateEndpoints.outputs.resourceId
      }
      {
        name: 'snet-monitor'
        addressPrefix: subnetCidrs.monitor
      }
      {
        name: 'snet-reserved'
        addressPrefix: subnetCidrs.reserved
        networkSecurityGroupResourceId: nsgReserved.outputs.resourceId
        natGatewayResourceId: natGateway.id
      }
      {
        name: 'snet-dns-resolver-inbound'
        addressPrefix: subnetCidrs.dnsResolver
        delegation: 'Microsoft.Network/dnsResolvers'
      }
    ]
    dnsServers: dnsServers
    tags: tags
  }
}

// === Private DNS Zones ===

module dnsZones 'br/public:avm/res/network/private-dns-zone:0.7.1' = [
  for (zoneName, i) in privateDnsZoneNames: {
    name: '${baseName}-dns-${i}'
    params: {
      name: zoneName
      location: 'global'
      tags: tags
      virtualNetworkLinks: [
        {
          virtualNetworkResourceId: vnet.outputs.resourceId
          registrationEnabled: false
        }
      ]
    }
  }
]

// === ACR Agent Pool Subnet (conditional) ===

resource agentPoolNsg 'Microsoft.Network/networkSecurityGroups@2024-01-01' = if (enableAgentPoolSubnet) {
  name: '${baseName}-nsg-acrpool'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowAzureKeyVault'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: 'AzureKeyVault'
        }
      }
      {
        name: 'AllowStorage'
        properties: {
          priority: 110
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: 'Storage'
        }
      }
      {
        name: 'AllowEventHub'
        properties: {
          priority: 120
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: 'EventHub'
        }
      }
      {
        name: 'AllowAzureActiveDirectory'
        properties: {
          priority: 130
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: 'AzureActiveDirectory'
        }
      }
      {
        name: 'AllowAzureMonitor'
        properties: {
          priority: 140
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRanges: ['443', '12000']
          sourceAddressPrefix: '*'
          destinationAddressPrefix: 'AzureMonitor'
        }
      }
    ]
  }
}

resource existingVnet 'Microsoft.Network/virtualNetworks@2024-01-01' existing = if (enableAgentPoolSubnet) {
  name: '${baseName}-vnet'
}

resource agentPoolSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-01-01' = if (enableAgentPoolSubnet) {
  parent: existingVnet
  name: 'snet-acrpool'
  properties: {
    addressPrefix: subnetCidrs.agentPool
    networkSecurityGroup: {
      id: agentPoolNsg.id
    }
    serviceEndpoints: [
      { service: 'Microsoft.AzureActiveDirectory' }
      { service: 'Microsoft.EventHub' }
      { service: 'Microsoft.KeyVault' }
      { service: 'Microsoft.Storage' }
    ]
  }
  dependsOn: [vnet]
}

// === Outputs ===

@description('Resource ID of the Virtual Network')
output vnetId string = vnet.outputs.resourceId

@description('Name of the Virtual Network')
output vnetName string = vnet.outputs.name

@description('Resource IDs of each subnet')
output subnetIds object = {
  gateway: vnet.outputs.subnetResourceIds[0]
  functions: vnet.outputs.subnetResourceIds[1]
  containerApps: vnet.outputs.subnetResourceIds[2]
  dataPostgres: vnet.outputs.subnetResourceIds[3]
  dataSqlmi: vnet.outputs.subnetResourceIds[4]
  privateEndpoints: vnet.outputs.subnetResourceIds[5]
  monitor: vnet.outputs.subnetResourceIds[6]
  reserved: vnet.outputs.subnetResourceIds[7]
  dnsResolverInbound: vnet.outputs.subnetResourceIds[8]
}

@description('Resource IDs of each Private DNS Zone')
output privateDnsZoneIds object = {
  blob: dnsZones[0].outputs.resourceId
  queue: dnsZones[1].outputs.resourceId
  table: dnsZones[2].outputs.resourceId
  file: dnsZones[3].outputs.resourceId
  serviceBus: dnsZones[4].outputs.resourceId
  cosmosDb: dnsZones[5].outputs.resourceId
  cognitiveServices: dnsZones[6].outputs.resourceId
  openAi: dnsZones[7].outputs.resourceId
  keyVault: dnsZones[8].outputs.resourceId
  webSites: dnsZones[9].outputs.resourceId
  aiFoundryApi: dnsZones[10].outputs.resourceId
  aiFoundryNotebooks: dnsZones[11].outputs.resourceId
  monitor: dnsZones[12].outputs.resourceId
  logAnalytics: dnsZones[13].outputs.resourceId
  ods: dnsZones[14].outputs.resourceId
  automation: dnsZones[15].outputs.resourceId
  postgres: dnsZones[16].outputs.resourceId
}

@description('Resource ID of the ACR agent pool subnet (empty if not deployed)')
output agentPoolSubnetId string = enableAgentPoolSubnet ? agentPoolSubnet.id : ''
