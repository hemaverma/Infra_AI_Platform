// ============================================================================
// NExT Accelerator Infrastructure — Phase 1: Network Foundation
// Purpose: Deploys networking, managed identity, and observability
// ============================================================================
targetScope = 'resourceGroup'

// === Parameters ===

@description('Base name prefix for all resources (e.g., next)')
param baseName string

@description('Numeric prefix (1-100) appended to baseName for globally unique resource names')
@minLength(1)
@maxLength(3)
param uniquePrefix string

@description('Azure region for deployment')
param location string = resourceGroup().location

@description('VNet address space')
param vnetAddressPrefix string = '10.0.0.0/16'

@description('VPN client address pool for P2S connections')
param vpnClientAddressPool string = '172.16.0.0/24'

@description('Entra ID tenant URL for VPN P2S authentication')
param vpnAadTenant string = ''

@description('Entra ID audience (Azure VPN App ID) for VPN P2S authentication')
param vpnAadAudience string = ''

@description('Entra ID issuer URL for VPN P2S authentication')
param vpnAadIssuer string = ''

@description('Resource tags applied to all resources')
param tags object = {
  project: 'NExT'
  environment: 'poc'
}

@description('Custom DNS server IPs for the VNet. Empty array uses Azure default DNS. Set to DNS Private Resolver inbound IP after Phase 1 deploys.')
param dnsServerIps array = []

// === Computed Names ===
var resourcePrefix = '${baseName}${uniquePrefix}'

// === Modules ===

module networking '../modules/networking.bicep' = {
  name: 'networking'
  params: {
    baseName: resourcePrefix
    location: location
    vnetAddressPrefix: vnetAddressPrefix
    vpnClientAddressPool: vpnClientAddressPool
    dnsServers: dnsServerIps
    tags: tags
  }
}

module dnsResolver '../modules/dns-resolver.bicep' = {
  name: 'dns-resolver'
  params: {
    baseName: resourcePrefix
    location: location
    vnetResourceId: networking.outputs.vnetId
    inboundSubnetResourceId: networking.outputs.subnetIds.dnsResolverInbound
    tags: tags
  }
}

module vpnGateway '../modules/vpn-gateway.bicep' = {
  name: 'vpn-gateway'
  params: {
    baseName: resourcePrefix
    location: location
    vnetResourceId: networking.outputs.vnetId
    vpnClientAddressPool: vpnClientAddressPool
    vpnAadTenant: vpnAadTenant
    vpnAadAudience: vpnAadAudience
    vpnAadIssuer: vpnAadIssuer
    tags: tags
  }
}

module identity '../modules/identity.bicep' = {
  name: 'identity'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
  }
}

module observability '../modules/observability.bicep' = {
  name: 'observability'
  params: {
    baseName: resourcePrefix
    location: location
    tags: tags
  }
}

// === Outputs ===

output vnetName string = networking.outputs.vnetName
output managedIdentityPrincipalId string = identity.outputs.managedIdentityPrincipalId
output logAnalyticsWorkspaceId string = observability.outputs.logAnalyticsWorkspaceId
