# Agent App - Docker Deployment Guide

This guide covers building and deploying the Agent App container to Azure Container Registry (ACR).

## Prerequisites

- **Docker** installed and running
- **Azure CLI** installed and logged in (`az login`)
- **ACR access** - Push permissions to the target registry
- **Azure Functions Core Tools** (for local testing)

## Build and Deploy to ACR

### 1. Set Variables

```bash
# Replace with your ACR name
ACR_NAME="your-acr-name"
IMAGE_NAME="agent-app"
TAG="latest"  # or use version tags like "v1.0.0"

# Full image reference
IMAGE_FULL="${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${TAG}"
```

### 2. Login to ACR

```bash
az acr login --name ${ACR_NAME}
```

### 3. Build Docker Image

From the `src/communicator_app` directory:

```bash
cd src/communicator_app
docker build -t ${IMAGE_FULL} .
```

**Alternative: Build with ACR Tasks** (recommended for CI/CD):

```bash
az acr build \
  --registry ${ACR_NAME} \
  --image ${IMAGE_NAME}:${TAG} \
  --file Dockerfile \
  .
```

### 4. Push Image to ACR

If you built locally:

```bash
docker push ${IMAGE_FULL}
```

> **Note**: ACR Tasks (`az acr build`) automatically pushes the image after building.

### 5. Verify Image in ACR

```bash
az acr repository show --name ${ACR_NAME} --repository ${IMAGE_NAME}
az acr repository show-tags --name ${ACR_NAME} --repository ${IMAGE_NAME}
```

## Local Testing

Test the container locally before deploying:

```bash
# Run container
docker run -p 8080:80 \
  -e AzureWebJobsStorage="UseDevelopmentStorage=true" \
  -e AZURE_COSMOS_ENDPOINT="<your-cosmos-endpoint>" \
  -e AZURE_COSMOS_KEY="<your-cosmos-key>" \
  ${IMAGE_FULL}

# Test health endpoint
curl http://localhost:8080/api/health

# Test readiness endpoint
curl http://localhost:8080/api/readiness
```

## Deploy to Azure

### Option A: Azure Container Apps (Recommended)

```bash
RESOURCE_GROUP="your-resource-group"
CONTAINER_APP_NAME="agent-app"
CONTAINER_APP_ENV="your-environment"

az containerapp create \
  --name ${CONTAINER_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --environment ${CONTAINER_APP_ENV} \
  --image ${IMAGE_FULL} \
  --target-port 80 \
  --ingress external \
  --registry-server ${ACR_NAME}.azurecr.io \
  --cpu 1.0 \
  --memory 2.0Gi
```

### Option B: Azure Functions on Container

```bash
FUNCTION_APP_NAME="your-agent-function-app"
STORAGE_ACCOUNT="your-storage-account"

# Create Function App with container support
az functionapp create \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --storage-account ${STORAGE_ACCOUNT} \
  --deployment-container-image-name ${IMAGE_FULL} \
  --functions-version 4 \
  --os-type Linux
```

### Option C: Azure App Service

```bash
APP_SERVICE_PLAN="your-app-service-plan"
WEB_APP_NAME="your-agent-web-app"

az webapp create \
  --resource-group ${RESOURCE_GROUP} \
  --plan ${APP_SERVICE_PLAN} \
  --name ${WEB_APP_NAME} \
  --deployment-container-image-name ${IMAGE_FULL}
```

## Environment Variables

Configure these environment variables in your Azure service:

```bash
# Required
AzureWebJobsStorage="<connection-string>"
AZURE_CLIENT_ID="<managed-identity-client-id>"
AZURE_TENANT_ID="<tenant-id>"
AZURE_COSMOS_ENDPOINT="<cosmos-db-endpoint>"

# Authentication (choose one method)
# Method 1: Managed Identity (recommended)
AZURE_COSMOS_KEY=""  # Leave empty to use managed identity

# Method 2: Connection String
AZURE_COSMOS_KEY="<cosmos-db-key>"

# Optional
ENABLE_DEBUGPY="0"  # Set to "1" only for debugging
DEBUGPY_PORT="9091"
DEBUGPY_HOST="0.0.0.0"  # For remote debugging
```

### Setting Environment Variables

**Container Apps:**

```bash
az containerapp update \
  --name ${CONTAINER_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --set-env-vars \
    AzureWebJobsStorage="<value>" \
    AZURE_CLIENT_ID="<value>" \
    AZURE_COSMOS_ENDPOINT="<value>"
```

**Function App:**

```bash
az functionapp config appsettings set \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --settings \
    AzureWebJobsStorage="<value>" \
    AZURE_CLIENT_ID="<value>" \
    AZURE_COSMOS_ENDPOINT="<value>"
```

## Agent Configuration

The agent app uses configuration files from `src/communicator_app/agent_configs/`. Ensure these are included
in the image or mounted as volumes:

### Option 1: Bake configs into image (default)

Configs are copied during Docker build. Update and rebuild for changes.

### Option 2: Mount configs as volume (dynamic)

```bash
# Container Apps with volume mount
az containerapp create \
  --name ${CONTAINER_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --environment ${CONTAINER_APP_ENV} \
  --image ${IMAGE_FULL} \
  --target-port 80 \
  --ingress external \
  --registry-server ${ACR_NAME}.azurecr.io \
  --cpu 1.0 \
  --memory 2.0Gi \
  --env-vars \
    AGENT_CONFIG_PATH="/mnt/configs" \
  --mount-type AzureFile \
  --mount-source "<file-share-name>" \
  --mount-path "/mnt/configs"
```

### Option 3: Load configs from Azure Storage

Store configs in Azure Blob Storage and load at runtime:

```bash
# Set environment variable pointing to blob storage
az containerapp update \
  --name ${CONTAINER_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --set-env-vars \
    AGENT_CONFIG_STORAGE_URL="https://<storage-account>.blob.core.windows.net/<container>/"
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build and Deploy Agent App

on:
  push:
    branches: [main]
    paths:
      - 'src/communicator_app/**'

env:
  ACR_NAME: your-acr-name
  IMAGE_NAME: agent-app

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Login to ACR
        uses: azure/docker-login@v1
        with:
          login-server: ${{ env.ACR_NAME }}.azurecr.io
          username: ${{ secrets.ACR_USERNAME }}
          password: ${{ secrets.ACR_PASSWORD }}
      
      - name: Build and push
        run: |
          cd src/communicator_app
          docker build -t ${{ env.ACR_NAME }}.azurecr.io/${{ env.IMAGE_NAME }}:${{ github.sha }} .
          docker tag ${{ env.ACR_NAME }}.azurecr.io/${{ env.IMAGE_NAME }}:${{ github.sha }} \
                     ${{ env.ACR_NAME }}.azurecr.io/${{ env.IMAGE_NAME }}:latest
          docker push ${{ env.ACR_NAME }}.azurecr.io/${{ env.IMAGE_NAME }}:${{ github.sha }}
          docker push ${{ env.ACR_NAME }}.azurecr.io/${{ env.IMAGE_NAME }}:latest
      
      - name: Deploy to Container App
        uses: azure/container-apps-deploy-action@v1
        with:
          containerAppName: agent-app
          resourceGroup: ${{ secrets.RESOURCE_GROUP }}
          imageToDeploy: ${{ env.ACR_NAME }}.azurecr.io/${{ env.IMAGE_NAME }}:${{ github.sha }}
```

## Troubleshooting

### Build Issues

**Problem**: agent-framework dependency fails to install

**Solution**: The agent-framework is a pre-release package. Ensure `--pre` flag is used:

```dockerfile
RUN pip install --no-cache-dir --pre -r requirements.txt
```

Or install manually:

```bash
pip install --pre agent-framework==1.0.0b251007
```

**Problem**: SSL certificate errors in corporate network

**Solution**: The `certifi` package is included for SSL compatibility. If issues persist:

```dockerfile
# Add to Dockerfile
RUN pip install --upgrade certifi
ENV REQUESTS_CA_BUNDLE=/usr/local/lib/python3.10/site-packages/certifi/cacert.pem
```

### Runtime Issues

**Problem**: Function app doesn't start

**Solution**: Check logs and verify environment variables

```bash
# Container Apps logs
az containerapp logs show \
  --name ${CONTAINER_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --follow

# Function App logs
az webapp log tail \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP}
```

**Problem**: Agent configuration not found

**Solution**: Verify config files are in the image:

```bash
# Check files in running container
docker exec -it <container-id> ls -la /home/site/wwwroot/communicator_app/agent_configs/

# Or use kubectl for Container Apps
az containerapp exec \
  --name ${CONTAINER_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --command "ls -la /home/site/wwwroot/communicator_app/agent_configs/"
```

### Cosmos DB Connection Issues

**Problem**: Cannot connect to Cosmos DB

**Solution**: Verify connection settings and network access

```bash
# Test connection from container
docker run --rm -it ${IMAGE_FULL} /bin/bash
python -c "from azure.cosmos import CosmosClient; print('Testing connection...')"

# Check firewall rules
az cosmosdb show \
  --name <cosmos-account> \
  --resource-group ${RESOURCE_GROUP} \
  --query ipRules
```

**Solution**: Enable managed identity for Cosmos DB:

```bash
# Enable system-assigned managed identity
az containerapp identity assign \
  --name ${CONTAINER_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --system-assigned

# Get principal ID
PRINCIPAL_ID=$(az containerapp identity show \
  --name ${CONTAINER_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --query principalId -o tsv)

# Grant Cosmos DB Data Contributor role
az cosmosdb sql role assignment create \
  --account-name <cosmos-account> \
  --resource-group ${RESOURCE_GROUP} \
  --scope "/" \
  --principal-id ${PRINCIPAL_ID} \
  --role-definition-name "Cosmos DB Built-in Data Contributor"
```

### Authentication Issues

**Problem**: Managed identity not working

**Solution**: Ensure identity is enabled and roles are assigned:

```bash
# Check identity status
az containerapp identity show \
  --name ${CONTAINER_APP_NAME} \
  --resource-group ${RESOURCE_GROUP}

# List role assignments
az role assignment list \
  --assignee ${PRINCIPAL_ID} \
  --all
```

## Image Tagging Strategy

Use semantic versioning for production:

```bash
# Development
docker tag ${IMAGE_FULL} ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:dev

# Staging
docker tag ${IMAGE_FULL} ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:staging

# Production releases
docker tag ${IMAGE_FULL} ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:v1.0.0
docker tag ${IMAGE_FULL} ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:v1.0
docker tag ${IMAGE_FULL} ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:v1
docker tag ${IMAGE_FULL} ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:latest

# Push all tags
docker push ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:v1.0.0
docker push ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:v1.0
docker push ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:v1
docker push ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:latest
```

## Multi-Container Deployment

Deploy both communicator_app and mcp_app together:

```bash
# Create Container Apps environment
az containerapp env create \
  --name ${CONTAINER_APP_ENV} \
  --resource-group ${RESOURCE_GROUP} \
  --location eastus

# Deploy agent-app
az containerapp create \
  --name agent-app \
  --resource-group ${RESOURCE_GROUP} \
  --environment ${CONTAINER_APP_ENV} \
  --image ${ACR_NAME}.azurecr.io/agent-app:latest \
  --target-port 80 \
  --ingress external

# Deploy mcp-app
az containerapp create \
  --name mcp-app \
  --resource-group ${RESOURCE_GROUP} \
  --environment ${CONTAINER_APP_ENV} \
  --image ${ACR_NAME}.azurecr.io/mcp-app:latest \
  --target-port 80 \
  --ingress internal

# Configure agent-app to communicate with mcp-app
MCP_FQDN=$(az containerapp show \
  --name mcp-app \
  --resource-group ${RESOURCE_GROUP} \
  --query properties.configuration.ingress.fqdn -o tsv)

az containerapp update \
  --name agent-app \
  --resource-group ${RESOURCE_GROUP} \
  --set-env-vars \
    MCP_SERVER_URL="https://${MCP_FQDN}"
```

## Performance Tuning

### CPU and Memory

Adjust based on workload:

```bash
# Scale up for high-traffic
az containerapp update \
  --name ${CONTAINER_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --cpu 2.0 \
  --memory 4.0Gi

# Auto-scaling rules
az containerapp update \
  --name ${CONTAINER_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --min-replicas 1 \
  --max-replicas 10 \
  --scale-rule-name http-rule \
  --scale-rule-type http \
  --scale-rule-http-concurrency 50
```

## Cleanup

```bash
# Remove local images
docker rmi ${IMAGE_FULL}

# Delete from ACR
az acr repository delete \
  --name ${ACR_NAME} \
  --repository ${IMAGE_NAME} \
  --yes

# Delete Container App
az containerapp delete \
  --name ${CONTAINER_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --yes
```

## References

- [Azure Functions Docker Deployment](https://learn.microsoft.com/azure/azure-functions/functions-create-function-linux-custom-image)
- [Azure Container Registry Best Practices](https://learn.microsoft.com/azure/container-registry/container-registry-best-practices)
- [Azure Container Apps Documentation](https://learn.microsoft.com/azure/container-apps/)
- [Azure Cosmos DB with Managed Identity](https://learn.microsoft.com/azure/cosmos-db/how-to-setup-rbac)
- [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
