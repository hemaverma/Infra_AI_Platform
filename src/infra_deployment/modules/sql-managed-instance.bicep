param baseName string
param location string
param tags object
param delegatedSubnetId string // snet-data-sqlmi

@description('SQL Managed Instance administrator login name.')
param administratorLogin string = 'nextadmin'

@secure()
param administratorLoginPassword string

@description('SQL Managed Instance SKU name.')
@allowed(['GP_Gen5', 'GP_Gen8IH', 'GP_G8IM', 'BC_Gen5', 'BC_Gen8IH', 'BC_Gen8IM'])
param skuName string = 'GP_Gen5'

@description('Number of vCores for the SQL Managed Instance.')
param vCores int = 4

@description('Storage size in GB for the SQL Managed Instance.')
param storageSizeInGB int = 32

module sqlMi 'br/public:avm/res/sql/managed-instance:0.4.1' = {
  name: '${baseName}-sqlmi'
  params: {
    name: '${baseName}-sqlmi'
    location: location
    subnetResourceId: delegatedSubnetId
    skuName: skuName
    vCores: vCores
    storageSizeInGB: storageSizeInGB
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorLoginPassword
    databases: [
      { name: 'next-relational' }
    ]
    tags: tags
  }
}

output sqlMiId string = sqlMi.outputs.resourceId
