using './main.bicep'

param environmentName = readEnvironmentVariable('AZURE_ENV_NAME', 'dev')
param location = readEnvironmentVariable('AZURE_LOCATION', 'swedencentral')
param principalId = readEnvironmentVariable('AZURE_PRINCIPAL_ID')
param existingFoundryResourceName = readEnvironmentVariable('AZURE_OPENAI_RESOURCE', 'proj-ai103-resource')
param realtimeDeploymentName = readEnvironmentVariable('AZURE_OPENAI_REALTIME_DEPLOYMENT', 'gpt-realtime-1.5')
param embeddingDeploymentName = readEnvironmentVariable('AZURE_OPENAI_EMBEDDING_DEPLOYMENT', 'text-embedding-3-large')
param searchSku = readEnvironmentVariable('AZURE_SEARCH_SKU', 'serverless')
param entraClientId = readEnvironmentVariable('ENTRA_CLIENT_ID', '')
param entraClientSecret = readEnvironmentVariable('ENTRA_CLIENT_SECRET', '')
