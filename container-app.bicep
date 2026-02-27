// azure/container-app.bicep
// Deploys the GitHub Visualizer as an Azure Container App.
//
// Usage:
//   az deployment group create \
//     --resource-group <rg-name> \
//     --template-file azure/container-app.bicep \
//     --parameters \
//         acrName=<your-acr-name> \
//         imageTag=latest \
//         groqApiKey=<secret> \
//         endeeApiKey=<secret>

@description('Azure Container Registry name (without .azurecr.io)')
param acrName string

@description('Docker image tag to deploy')
param imageTag string = 'latest'

@description('Azure region')
param location string = resourceGroup().location

@description('App name — used for all resource names')
param appName string = 'github-visualizer'

@secure()
@description('Groq API key')
param groqApiKey string

@secure()
@description('Endee API key')
param endeeApiKey string

@description('Groq model name')
param groqModel string = 'llama-3.3-70b-versatile'

@description('Endee base URL (leave blank for cloud default)')
param endeeBaseUrl string = ''

// Log Analytics workspace
resource logWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${appName}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// Container Apps Environment
resource containerEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: '${appName}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logWorkspace.properties.customerId
        sharedKey: logWorkspace.listKeys().primarySharedKey
      }
    }
  }
}

// Container App
resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: appName
  location: location
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      registries: [
        {
          server: '${acrName}.azurecr.io'
          username: acrName
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        { name: 'groq-api-key',  value: groqApiKey  }
        { name: 'endee-api-key', value: endeeApiKey }
        {
          name: 'acr-password'
          value: listCredentials(resourceId('Microsoft.ContainerRegistry/registries', acrName), '2023-01-01-preview').passwords[0].value
        }
      ]
    }
    template: {
      containers: [
        {
          name: appName
          image: '${acrName}.azurecr.io/${appName}:${imageTag}'
          resources: {
            cpu:    json('1.0')
            memory: '2Gi'
          }
          env: [
            { name: 'GROQ_API_KEY',  secretRef: 'groq-api-key'  }
            { name: 'ENDEE_API_KEY', secretRef: 'endee-api-key' }
            { name: 'GROQ_MODEL',    value: groqModel            }
            { name: 'ENDEE_BASE_URL',value: endeeBaseUrl         }
            { name: 'WORKERS',       value: '2'                  }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 60
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/readiness', port: 8000 }
              initialDelaySeconds: 60
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-scale'
            http: { metadata: { concurrentRequests: '5' } }
          }
        ]
      }
    }
  }
}

output appUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output appName string = containerApp.name
