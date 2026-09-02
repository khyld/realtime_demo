targetScope = 'resourceGroup'

@minLength(1)
@maxLength(20)
param environmentName string

param location string = resourceGroup().location

param principalId string

param foundryResourceName string = ''

param realtimeDeploymentName string = 'gpt-realtime-1.5'

param realtimeModelVersion string = '2026-02-23'

param embeddingDeploymentName string = 'text-embedding-3-large'

param embeddingModelVersion string = '1'

param transcriptionDeploymentName string = 'gpt-4o-mini-transcribe'

param transcriptionModelVersion string = '2025-12-15'

param searchSku string = 'serverless'

@secure()
param entraClientSecret string = ''

param entraClientId string = ''

var resourceToken = toLower(uniqueString(subscription().id, resourceGroup().id, environmentName))
var normalizedEnvironment = toLower(replace(environmentName, '_', '-'))
var resolvedFoundryResourceName = empty(foundryResourceName) ? 'aifd-${normalizedEnvironment}-${take(resourceToken, 8)}' : foundryResourceName
var tags = {
  environment: environmentName
  application: 'bilingual-realtime-lab'
  'azd-env-name': environmentName
}

resource runtimeIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-realtime-${normalizedEnvironment}'
  location: location
  tags: tags
}

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: resolvedFoundryResourceName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: resolvedFoundryResourceName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource realtimeDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundry
  name: realtimeDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 1
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-realtime-1.5'
      version: realtimeModelVersion
    }
    raiPolicyName: 'Microsoft.Default'
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundry
  name: embeddingDeploymentName
  sku: {
    name: 'Standard'
    capacity: 120
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-large'
      version: embeddingModelVersion
    }
    raiPolicyName: 'Microsoft.Default'
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

resource transcriptionDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundry
  name: transcriptionDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 1
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o-mini-transcribe'
      version: transcriptionModelVersion
    }
    raiPolicyName: 'Microsoft.Default'
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2025-01-01' = {
  name: 'strt${resourceToken}'
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowCrossTenantReplication: false
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-01-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

resource knowledgeContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-01-01' = {
  parent: blobService
  name: 'knowledge'
  properties: {
    publicAccess: 'None'
  }
}

resource search 'Microsoft.Search/searchServices@2026-03-01-preview' = {
  name: 'srch-${normalizedEnvironment}-sl-${take(resourceToken, 6)}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: searchSku
  }
  properties: {
    disableLocalAuth: true
    hostingMode: 'Default'
    publicNetworkAccess: 'enabled'
    semanticSearch: 'free'
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'crrt${resourceToken}'
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    dataEndpointEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource containerEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: 'cae-realtime-${normalizedEnvironment}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'none'
    }
    zoneRedundant: false
  }
}

resource web 'Microsoft.App/containerApps@2025-01-01' = {
  name: 'ca-realtime-${normalizedEnvironment}'
  location: location
  tags: union(tags, {
    'azd-service-name': 'web'
  })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${runtimeIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        allowInsecure: false
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          identity: runtimeIdentity.id
          server: registry.properties.loginServer
        }
      ]
      secrets: !empty(entraClientId) && !empty(entraClientSecret) ? [
        {
          name: 'entra-client-secret'
          value: entraClientSecret
        }
      ] : []
    }
    template: {
      containers: [
        {
          name: 'web'
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          env: [
            {
              name: 'AZURE_CLIENT_ID'
              value: runtimeIdentity.properties.clientId
            }
            {
              name: 'AZURE_OPENAI_RESOURCE'
              value: foundry.name
            }
            {
              name: 'AZURE_OPENAI_REALTIME_DEPLOYMENT'
              value: realtimeDeploymentName
            }
            {
              name: 'AZURE_OPENAI_TRANSCRIPTION_DEPLOYMENT'
              value: transcriptionDeploymentName
            }
            {
              name: 'AZURE_SEARCH_ENDPOINT'
              value: 'https://${search.name}.search.windows.net'
            }
            {
              name: 'AZURE_SEARCH_INDEX_NAME'
              value: 'knowledge-chunks'
            }
            {
              name: 'AZURE_SEARCH_INDEXER_NAME'
              value: 'knowledge-indexer'
            }
            {
              name: 'AZURE_STORAGE_ACCOUNT_URL'
              value: 'https://${storage.name}.blob.${environment().suffixes.storage}'
            }
            {
              name: 'AZURE_STORAGE_CONTAINER_NAME'
              value: knowledgeContainer.name
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/api/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 2
        rules: [
          {
            name: 'http-requests'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

resource webAuth 'Microsoft.App/containerApps/authConfigs@2025-01-01' = if (!empty(entraClientId) && !empty(entraClientSecret)) {
  parent: web
  name: 'current'
  properties: {
    globalValidation: {
      redirectToProvider: 'azureactivedirectory'
      unauthenticatedClientAction: 'RedirectToLoginPage'
      excludedPaths: [
        '/api/health'
      ]
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: entraClientId
          clientSecretSettingName: 'entra-client-secret'
          openIdIssuer: '${environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'
        }
      }
    }
    platform: {
      enabled: true
    }
  }
}

var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var openAiUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
var storageBlobContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
var storageBlobReaderRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1')
var cognitiveServicesUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
var searchDataReaderRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '1407120a-92aa-4202-b7e9-c0e197c71c8f')
var searchServiceContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7ca78c08-252a-4471-8644-bb5ff32d4ba0')

resource runtimeAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, runtimeIdentity.id, acrPullRoleId)
  scope: registry
  properties: {
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: acrPullRoleId
  }
}

resource runtimeFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, runtimeIdentity.id, openAiUserRoleId)
  scope: foundry
  properties: {
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: openAiUserRoleId
  }
}

resource searchFoundryOpenAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, search.id, openAiUserRoleId)
  scope: foundry
  properties: {
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: openAiUserRoleId
  }
}

resource searchFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, search.id, cognitiveServicesUserRoleId)
  scope: foundry
  properties: {
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: cognitiveServicesUserRoleId
  }
}

resource runtimeStorageContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, runtimeIdentity.id, storageBlobContributorRoleId)
  scope: storage
  properties: {
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: storageBlobContributorRoleId
  }
}

resource searchStorageReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, search.id, storageBlobReaderRoleId)
  scope: storage
  properties: {
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: storageBlobReaderRoleId
  }
}

resource runtimeSearchReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, runtimeIdentity.id, searchDataReaderRoleId)
  scope: search
  properties: {
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: searchDataReaderRoleId
  }
}

resource runtimeSearchContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, runtimeIdentity.id, searchServiceContributorRoleId)
  scope: search
  properties: {
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: searchServiceContributorRoleId
  }
}

resource deployerSearchContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, principalId, searchServiceContributorRoleId)
  scope: search
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: searchServiceContributorRoleId
  }
}

resource deployerSearchReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, principalId, searchDataReaderRoleId)
  scope: search
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: searchDataReaderRoleId
  }
}

output AZURE_LOCATION string = location
output AZURE_OPENAI_RESOURCE string = foundry.name
output AZURE_OPENAI_REALTIME_DEPLOYMENT string = realtimeDeploymentName
output AZURE_OPENAI_EMBEDDING_DEPLOYMENT string = embeddingDeploymentName
output AZURE_OPENAI_TRANSCRIPTION_DEPLOYMENT string = transcriptionDeploymentName
output AZURE_OPENAI_ENDPOINT string = 'https://${foundry.name}.openai.azure.com'
output AZURE_AI_SERVICES_ENDPOINT string = 'https://${foundry.name}.cognitiveservices.azure.com'
output AZURE_SEARCH_ENDPOINT string = 'https://${search.name}.search.windows.net'
output AZURE_SEARCH_INDEX_NAME string = 'knowledge-chunks'
output AZURE_SEARCH_INDEXER_NAME string = 'knowledge-indexer'
output AZURE_STORAGE_ACCOUNT_ID string = storage.id
output AZURE_STORAGE_ACCOUNT_URL string = 'https://${storage.name}.blob.${environment().suffixes.storage}'
output AZURE_STORAGE_CONTAINER_NAME string = knowledgeContainer.name
output AZURE_CLIENT_ID string = runtimeIdentity.properties.clientId
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.properties.loginServer
output SERVICE_WEB_NAME string = web.name
output SERVICE_WEB_URI string = 'https://${web.properties.configuration.ingress.fqdn}'
