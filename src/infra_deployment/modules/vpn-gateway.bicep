// ============================================================================
// Module: vpn-gateway.bicep
// Purpose: VPN Gateway with P2S OpenVPN + Entra ID authentication
// Separated from networking.bicep to prevent cascading failures
// ============================================================================

@description('Base name prefix for all resources')
param baseName string

@description('Azure region for deployment')
param location string

@description('Resource ID of the Virtual Network')
param vnetResourceId string

@description('VPN client address pool for P2S connections')
param vpnClientAddressPool string = '172.16.0.0/24'

@description('Entra ID tenant URL for VPN P2S authentication')
param vpnAadTenant string = ''

@description('Entra ID audience (Azure VPN App ID) for VPN P2S authentication')
param vpnAadAudience string = ''

@description('Entra ID issuer URL for VPN P2S authentication')
param vpnAadIssuer string = ''

@description('Resource tags')
param tags object

@description('VPN Gateway SKU name.')
@allowed(['VpnGw1AZ', 'VpnGw2AZ', 'VpnGw3AZ', 'VpnGw4AZ', 'VpnGw5AZ'])
param skuName string = 'VpnGw1AZ'

// === Computed ===
var enableVpnP2s = !empty(vpnAadTenant) && !empty(vpnAadAudience) && !empty(vpnAadIssuer)

// === VPN Gateway Public IP ===

module vpnPublicIp 'br/public:avm/res/network/public-ip-address:0.8.0' = {
  name: '${baseName}-vpn-pip'
  params: {
    name: '${baseName}-vpn-pip'
    location: location
    publicIPAllocationMethod: 'Static'
    skuName: 'Standard'
    zones: [1, 2, 3]
    tags: tags
  }
}

// === VPN Gateway ===

module vpnGateway 'br/public:avm/res/network/virtual-network-gateway:0.11.0' = {
  name: '${baseName}-vpn-gw'
  params: {
    name: '${baseName}-vpn-gw'
    location: location
    gatewayType: 'Vpn'
    vpnType: 'RouteBased'
    skuName: skuName
    virtualNetworkResourceId: vnetResourceId
    existingPrimaryPublicIPResourceId: vpnPublicIp.outputs.resourceId
    clusterSettings: {
      clusterMode: 'activePassiveNoBgp'
    }
    vpnClientAddressPoolPrefix: enableVpnP2s ? vpnClientAddressPool : ''
    vpnClientAadConfiguration: enableVpnP2s ? {
      aadTenant: vpnAadTenant
      aadAudience: vpnAadAudience
      aadIssuer: vpnAadIssuer
      vpnAuthenticationTypes: ['AAD']
      vpnClientProtocols: ['OpenVPN']
    } : null
    tags: tags
  }
}

// === Outputs ===

@description('Resource ID of the VPN Gateway')
output vpnGatewayId string = vpnGateway.outputs.resourceId

@description('Name of the VPN Gateway')
output vpnGatewayName string = vpnGateway.outputs.name
