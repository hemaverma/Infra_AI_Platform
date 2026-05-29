#!/usr/bin/env bash
# ============================================================================
# DEPRECATED — SUPERSEDED BY GHCR CI/CD
# This script was used to build Docker images locally and push to a PRIVATE ACR.
# The private deployment now uses GHCR + GitHub Actions (self-hosted runner in VNet).
# See: .github/workflows/deploy-apps.yml
#
# Keeping for reference only. Will be removed in a future cleanup.
# ============================================================================
# PRIVATE DEPLOYMENTS ONLY (HISTORICAL)
# This script builds Docker images locally and pushes to a PRIVATE ACR.
# Requires: Docker Desktop installed, VPN connected to private ACR endpoint.
#
# For PUBLIC deployments, use one of:
#   - az acr build (remote, no Docker needed) — used by deploy.sh --variant public
#   - GitHub Actions workflow (docker build on runner) — triggered on push to main
#
# Re-enable for public ONLY if ACR access is later restricted with IP/VNet rules.
# ============================================================================
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
#
# build-image.sh
# Build and push a container image to a private ACR via local Docker.

set -euo pipefail

REGISTRY_NAME="${1:-}"
IMAGE_NAME="${IMAGE_NAME:-communicator}"
TAG="${TAG:-latest}"
DOCKERFILE="${DOCKERFILE:-src/communicator_app/Dockerfile}"
CONTEXT_PATH="${CONTEXT_PATH:-src/communicator_app/}"

main() {
  # ─── Step 1: Verify Docker daemon is running ───
  echo "[1/8] Checking Docker daemon..."
  if ! docker info &>/dev/null; then
    echo "ERROR: Docker daemon is not running. Start Docker Desktop and retry." >&2
    exit 1
  fi
  echo "  Docker is running."

  # ─── Step 2: Verify Azure CLI authentication ───
  echo "[2/8] Checking Azure CLI authentication..."
  if ! az account show -o none 2>/dev/null; then
    echo "ERROR: Not authenticated. Run 'az login' first." >&2
    exit 1
  fi
  echo "  Azure CLI authenticated."

  # ─── Step 3: Resolve resource group ───
  echo "[3/8] Resolving resource group..."
  local resource_group="${AZURE_RESOURCE_GROUP:-}"
  if [[ -z "$resource_group" ]]; then
    echo "ERROR: AZURE_RESOURCE_GROUP environment variable not set." >&2
    exit 1
  fi
  echo "  Resource group: $resource_group"

  # ─── Step 4: Resolve ACR name ───
  echo "[4/8] Resolving ACR registry name..."
  if [[ -z "$REGISTRY_NAME" ]]; then
    REGISTRY_NAME=$(az acr list \
      --resource-group "$resource_group" \
      --query "[0].name" -o tsv 2>/dev/null)
    if [[ -z "$REGISTRY_NAME" ]]; then
      echo "ERROR: No ACR found in resource group '$resource_group'." >&2
      exit 1
    fi
  fi
  local login_server="${REGISTRY_NAME}.azurecr.io"
  echo "  Registry: $login_server"

  # ─── Step 5: DNS resolution check (private endpoint) ───
  echo "[5/8] Verifying private DNS resolution for $login_server..."
  local resolved_ip
  resolved_ip=$(getent hosts "$login_server" 2>/dev/null | awk '{print $1}' | head -1) \
    || resolved_ip=$(dig +short "$login_server" 2>/dev/null | head -1) \
    || resolved_ip=""
  if [[ -z "$resolved_ip" ]]; then
    echo "ERROR: Cannot resolve $login_server. Check DNS and VPN connectivity." >&2
    exit 1
  fi
  if [[ "$resolved_ip" == 10.* ]]; then
    echo "  Resolved to private IP: $resolved_ip"
  else
    echo "WARNING: $login_server resolves to $resolved_ip (not a private IP)." >&2
    echo "  Ensure VPN is connected for private endpoint access." >&2
  fi

  # ─── Step 6: ACR login ───
  echo "[6/8] Logging in to ACR..."
  if ! az acr login --name "$REGISTRY_NAME" 2>/dev/null; then
    echo "  Standard login failed, trying token-based login..."
    local token_json
    token_json=$(az acr login --name "$REGISTRY_NAME" --expose-token -o json 2>/dev/null)
    if [[ -z "$token_json" ]]; then
      echo "ERROR: ACR login failed. Check permissions and connectivity." >&2
      exit 1
    fi
    local access_token
    access_token=$(echo "$token_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['accessToken'])")
    echo "$access_token" | docker login "$login_server" \
      --username "00000000-0000-0000-0000-000000000000" --password-stdin
  fi
  echo "  ACR login successful."

  # ─── Step 7: Docker build ───
  local full_image="${login_server}/${IMAGE_NAME}:${TAG}"
  echo "[7/8] Building image: $full_image"
  docker build -t "$full_image" -f "$DOCKERFILE" "$CONTEXT_PATH"
  echo "  Build successful."

  # ─── Step 8: Docker push ───
  echo "[8/8] Pushing image: $full_image"
  docker push "$full_image"
  echo "  Push successful."

  # ─── Verify tag exists in registry ───
  echo "Verifying tag in registry..."
  local tags
  tags=$(az acr repository show-tags \
    --name "$REGISTRY_NAME" \
    --repository "$IMAGE_NAME" \
    --output tsv 2>/dev/null) || true
  if echo "$tags" | grep -qx "$TAG"; then
    echo "Verified: Tag '$TAG' exists in $login_server/$IMAGE_NAME"
  else
    echo "WARNING: Could not verify tag '$TAG' in repository listing."
  fi

  echo ""
  echo "Done. Image available at: $full_image"
}

main "$@"
