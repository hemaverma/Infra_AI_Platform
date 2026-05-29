// ============================================================================
// Module: dns-resolver.bicep
// Purpose: Azure DNS Private Resolver with inbound endpoint for VPN DNS
// Uses:    AVM network/dns-resolver module
// ============================================================================

@description('Base name prefix for all resources')
param baseName string

@description('Azure region for deployment')
param location string

@description('Resource ID of the VNet')
param vnetResourceId string

@description('Resource ID of the inbound endpoint subnet')
param inboundSubnetResourceId string

@description('Resource tags')
param tags object = {}

// === DNS Private Resolver (AVM) ===

module dnsResolver 'br/public:avm/res/network/dns-resolver:0.5.0' = {
  name: '${baseName}-dns-resolver'
  params: {
    name: toLower('${baseName}-dns-resolver')
    location: location
    tags: tags
    virtualNetworkResourceId: vnetResourceId
    inboundEndpoints: [
      {
        name: '${baseName}-dns-inbound'
        subnetResourceId: inboundSubnetResourceId
      }
    ]
  }
}

// === Outputs ===

@description('Resource ID of the DNS Private Resolver')
output resolverResourceId string = dnsResolver.outputs.resourceId

@description('Name of the DNS Private Resolver')
output resolverName string = dnsResolver.outputs.name

// TODO: Verify inbound endpoint IP output path against AVM dns-resolver schema at runtime.
// AVM may expose this via dnsResolver.outputs.inboundEndpoints[0].properties.ipConfigurations[0].privateIpAddress
// or a different output structure. The exact path depends on the AVM module version.
@description('Inbound endpoint IP address (Dynamic — assigned by Azure)')
output inboundEndpointIp string = dnsResolver.outputs.resourceId // Placeholder — see TODO above
