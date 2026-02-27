#!/usr/bin/env bash
# azure/deploy.sh
# Full end-to-end build → push → deploy script.
# Run from the project root: ./azure/deploy.sh
#
# Prerequisites:
#   - Azure CLI (az) installed and logged in: az login
#   - Docker installed and running
#   - jq installed (for JSON parsing)
#
# Required env vars (or edit the defaults below):
#   ACR_NAME        — your Azure Container Registry name (without .azurecr.io)
#   RESOURCE_GROUP  — Azure resource group name
#   GROQ_API_KEY    — Groq secret
#   ENDEE_API_KEY   — Endee secret

set -euo pipefail

# ── Config — edit these or set as env vars ────────────────────────────────────
ACR_NAME="${ACR_NAME:-ghvizacr}"
RESOURCE_GROUP="${RESOURCE_GROUP:-github-visualizer-rg}"
LOCATION="${LOCATION:-eastus}"
APP_NAME="${APP_NAME:-github-visualizer}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo latest)}"
GROQ_MODEL="${GROQ_MODEL:-llama-3.3-70b-versatile}"

# ── Validate required secrets ─────────────────────────────────────────────────
: "${GROQ_API_KEY:?GROQ_API_KEY is required}"
: "${ENDEE_API_KEY:?ENDEE_API_KEY is required}"

echo "========================================"
echo " GitHub Visualizer — Azure Deploy"
echo "========================================"
echo " Resource Group : $RESOURCE_GROUP"
echo " ACR            : $ACR_NAME.azurecr.io"
echo " Image tag      : $IMAGE_TAG"
echo " Location       : $LOCATION"
echo "========================================"

# ── 1. Create resource group if it doesn't exist ──────────────────────────────
echo ""
echo "[1/6] Ensuring resource group '$RESOURCE_GROUP' exists..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# ── 2. Create ACR if it doesn't exist ────────────────────────────────────────
echo "[2/6] Ensuring Container Registry '$ACR_NAME' exists..."
az acr create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACR_NAME" \
  --sku Basic \
  --admin-enabled true \
  --output none 2>/dev/null || echo "  (ACR already exists, skipping)"

# ── 3. Build Docker image ─────────────────────────────────────────────────────
echo "[3/6] Building Docker image (this will take several minutes on first run)..."
docker build \
  --tag "${ACR_NAME}.azurecr.io/${APP_NAME}:${IMAGE_TAG}" \
  --tag "${ACR_NAME}.azurecr.io/${APP_NAME}:latest" \
  .

# ── 4. Push to ACR ────────────────────────────────────────────────────────────
echo "[4/6] Pushing image to ACR..."
az acr login --name "$ACR_NAME"
docker push "${ACR_NAME}.azurecr.io/${APP_NAME}:${IMAGE_TAG}"
docker push "${ACR_NAME}.azurecr.io/${APP_NAME}:latest"

# ── 5. Deploy Bicep template ──────────────────────────────────────────────────
echo "[5/6] Deploying Container App via Bicep..."
DEPLOY_OUTPUT=$(az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file azure/container-app.bicep \
  --parameters \
      acrName="$ACR_NAME" \
      imageTag="$IMAGE_TAG" \
      appName="$APP_NAME" \
      location="$LOCATION" \
      groqApiKey="$GROQ_API_KEY" \
      endeeApiKey="$ENDEE_API_KEY" \
      groqModel="$GROQ_MODEL" \
  --output json)

APP_URL=$(echo "$DEPLOY_OUTPUT" | jq -r '.properties.outputs.appUrl.value')

# ── 6. Smoke test ─────────────────────────────────────────────────────────────
echo "[6/6] Waiting for app to become healthy..."
MAX_WAIT=180
INTERVAL=10
ELAPSED=0
until curl -sf "${APP_URL}/health" > /dev/null 2>&1; do
  if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo "  WARNING: App did not become healthy within ${MAX_WAIT}s"
    echo "  Check logs: az containerapp logs show -n $APP_NAME -g $RESOURCE_GROUP"
    break
  fi
  echo "  Waiting... (${ELAPSED}s elapsed)"
  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))
done

echo ""
echo "========================================"
echo " Deployment complete!"
echo " App URL : $APP_URL"
echo " API docs: ${APP_URL}/docs"
echo "========================================"
echo ""
echo "Quick test:"
echo "  curl -X POST ${APP_URL}/analyze \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"repo_url\": \"https://github.com/tiangolo/fastapi\"}'"
