#!/usr/bin/env bash
# deploy.sh — Deploys infrastructure to Azure.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Color output (disabled when piped) ---
if [[ -t 1 ]]; then
  RED='\033[0;31m' GREEN='\033[0;32m' YELLOW='\033[0;33m'
  CYAN='\033[0;36m' MAGENTA='\033[0;35m' NC='\033[0m'
else
  RED='' GREEN='' YELLOW='' CYAN='' MAGENTA='' NC=''
fi

info()    { printf "${CYAN}%s${NC}\n" "$1"; }
warn()    { printf "${YELLOW}%s${NC}\n" "$1"; }
success() { printf "${GREEN}%s${NC}\n" "$1"; }
err()     { printf "${RED}ERROR: %s${NC}\n" "$1" >&2; exit 1; }

# ─── Soft-Deleted Resource Handler ────────────────────────────────────────────
# Handles naming conflicts: recovers Key Vaults, purges Cognitive Services,
# and fails-fast with guidance for irrecoverable conflicts.
# Returns 0 on success (all conflicts resolved), exits on irrecoverable blockers.
handle_soft_deleted_resources() {
    local prefix="$1"
    local blockers=()

    # --- Key Vault: attempt recovery (purge-protected, 90-day retention) ---
    local kv_name="${prefix}-kv"
    local deleted_kv
    deleted_kv=$(az keyvault list-deleted \
        --resource-type vault \
        --query "[?name=='${kv_name}'].[name]" -o tsv 2>/dev/null || true)

    if [[ -n "$deleted_kv" ]]; then
        info "Soft-deleted Key Vault '${kv_name}' found. Attempting recovery..."
        if az keyvault recover --name "$kv_name" 2>/dev/null; then
            success "Key Vault '${kv_name}' recovered. Bicep will update it in-place."
        else
            blockers+=("Key Vault '${kv_name}' — cannot recover (may belong to different subscription/RG). 90-day purge protection active.")
        fi
    fi

    # --- PostgreSQL: check global name availability ---
    if [[ "${DEPLOY_POSTGRES:-true}" == "true" ]]; then
        local pg_name="${prefix}-pg"
        local pg_avail
        pg_avail=$(az postgres flexible-server show --name "$pg_name" --resource-group "__nonexistent__" 2>&1 || true)
        if echo "$pg_avail" | grep -q "InvalidParameterValue\|ServerAlreadyExists"; then
            blockers+=("PostgreSQL '${pg_name}' — name globally unavailable (existing server or soft-deleted).")
        fi
        # Also check via name-availability API (REST)
        local name_check
        name_check=$(az rest --method post \
            --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}/providers/Microsoft.DBforPostgreSQL/checkNameAvailability?api-version=2022-12-01" \
            --body "{\"name\": \"${pg_name}\", \"type\": \"Microsoft.DBforPostgreSQL/flexibleServers\"}" \
            --query "nameAvailable" -o tsv 2>/dev/null || echo "true")
        if [[ "$name_check" == "false" ]]; then
            blockers+=("PostgreSQL '${pg_name}' — name not available (globally reserved or soft-deleted).")
        fi
    fi

    # --- Cognitive Services: purge in-place (48-hour retention, no purge protection) ---
    for svc_suffix in oai csafety di; do
        local svc_name="${prefix}-${svc_suffix}"
        local deleted_svc
        deleted_svc=$(az cognitiveservices account list-deleted \
            --query "[?name=='${svc_name}'].[name]" -o tsv 2>/dev/null || true)
        if [[ -n "$deleted_svc" ]]; then
            info "Purging soft-deleted Cognitive Services account '${svc_name}'..."
            az cognitiveservices account purge \
                --name "$svc_name" \
                --resource-group "$RESOURCE_GROUP" \
                --location "$LOCATION" 2>/dev/null || warn "Could not purge '${svc_name}' (may require different location/RG)"
        fi
    done

    # --- AI Hub: purge if soft-deleted (14-day retention, purgeable) ---
    local hub_name="${prefix}-ai-hub"
    local deleted_hub
    deleted_hub=$(az ml workspace list-deleted \
        --query "[?name=='${hub_name}'].[name]" -o tsv 2>/dev/null || true)
    if [[ -n "$deleted_hub" ]]; then
        info "Purging soft-deleted AI Hub '${hub_name}'..."
        az ml workspace purge \
            --name "$hub_name" \
            --resource-group "$RESOURCE_GROUP" 2>/dev/null || warn "Could not purge AI Hub '${hub_name}' (may require different RG)"
    fi

    # --- Fail-fast if irrecoverable blockers found ---
    if ((${#blockers[@]} > 0)); then
        printf "\n${RED}═══ DEPLOYMENT BLOCKED: Resource Naming Conflicts ═══${NC}\n\n"
        printf "The following resources cannot be deployed with prefix '${prefix}':\n\n"
        for blocker in "${blockers[@]}"; do
            printf "  • %s\n" "$blocker"
        done
        printf "\n${YELLOW}Resolution options:${NC}\n"
        printf "  1. Use a different unique prefix:  ./deploy.sh ... --unique-prefix <new-value>\n"
        printf "  2. Wait for auto-purge (90 days for Key Vault, varies for others)\n"
        printf "  3. Manually recover:  az keyvault recover --name ${prefix}-kv\n"
        printf "  4. Contact subscription admin to purge:  az keyvault purge --name ${prefix}-kv\n\n"
        exit 1
    fi

    return 0
}

# ─── Regional Availability Precheck ───────────────────────────────────────────
check_regional_availability() {
    local loc="$1"
    local prefix="$2"
    local failed=0

    info "Running regional availability precheck for '${loc}'..."

    # Resolve display name for location matching (some az commands return display names like "West US 3")
    local display_loc
    display_loc=$(az account list-locations --query "[?name=='${loc}'].displayName | [0]" -o tsv 2>/dev/null || echo "${loc}")

    # 1. Check Cosmos DB provider availability
    if [[ "${DEPLOY_COSMOSDB:-true}" == "true" ]]; then
        local cosmos_check
        cosmos_check=$(az provider show --namespace Microsoft.DocumentDB \
            --query "resourceTypes[?resourceType=='databaseAccounts'].locations[]" \
            -o tsv 2>/dev/null | grep -i "${display_loc}" || true)
        if [[ -z "$cosmos_check" ]]; then
            warn "Cosmos DB may not be available in '${loc}'"
            failed=$((failed + 1))
        else
            success "Cosmos DB: available in ${loc}"
        fi
    fi

    # 2. Check PostgreSQL Flexible Server availability
    if [[ "${DEPLOY_POSTGRES:-true}" == "true" ]]; then
        local pg_check
        pg_check=$(az postgres flexible-server list-skus --location "$loc" \
            --query "[0].name" -o tsv 2>/dev/null || true)
        if [[ -z "$pg_check" ]]; then
            warn "PostgreSQL Flexible Server SKUs not found in '${loc}'"
            failed=$((failed + 1))
        else
            success "PostgreSQL: SKUs available in ${loc}"
        fi
    fi

    # 3. Check Logic App WS1 quota
    if [[ "${DEPLOY_LOGICAPP:-true}" == "true" ]]; then
        local ws1_check
        ws1_check=$(az appservice list-locations --sku WS1 --linux-workers-enabled \
            -o tsv 2>/dev/null | grep -i "${display_loc}" || true)
        if [[ -z "$ws1_check" ]]; then
            warn "Logic App Standard (WS1) may not have quota in '${loc}'"
            failed=$((failed + 1))
        else
            success "Logic App WS1: available in ${loc}"
        fi
    fi

    # 4. Check OpenAI model availability
    if [[ "${DEPLOY_OPENAI:-true}" == "true" ]]; then
        local oai_check
        oai_check=$(az cognitiveservices model list --location "$loc" \
            --query "[?model.name=='${OPENAI_MODEL:-gpt-5}'].model.name" -o tsv 2>/dev/null | head -1 || true)
        if [[ -z "$oai_check" ]]; then
            warn "OpenAI model '${OPENAI_MODEL:-gpt-5}' may not be available in '${loc}'"
            failed=$((failed + 1))
        else
            success "OpenAI: '${OPENAI_MODEL:-gpt-5}' available in ${loc}"
        fi
    fi

    if [[ $failed -gt 0 ]]; then
        warn "Precheck found $failed potential issue(s) in '${loc}'. Deployment may fail for some services."
        warn "Consider using one of: ${ALLOWED_LOCATIONS[*]}"
        # Interactive prompt: let user decide whether to continue
        read -rp "Continue deployment despite warnings? (y/N): " answer
        if [[ ! "$answer" =~ ^[Yy]$ ]]; then
            err "Deployment aborted by user after precheck warnings."
        fi
        info "User chose to continue despite precheck warnings."
        return 0
    fi

    success "Regional precheck passed for '${loc}'"
    return 0
}

# --- Source root .env if present ---
ROOT_ENV="${SCRIPT_DIR}/../../.env"
[[ -f "$ROOT_ENV" ]] && set -a && source "$ROOT_ENV" && set +a

# --- .env parameter overrides (passed to Bicep when non-empty) ---
# These override parameters.json defaults. CLI args take highest priority.
ENV_CONTAINER_IMAGE="${CONTAINER_IMAGE:-}"
ENV_SHARED_MAILBOX="${SHARED_MAILBOX_ADDRESS:-}"
ENV_TEAMS_GROUP_ID="${TEAMS_GROUP_ID:-}"
ENV_TEAMS_CHANNEL_ID="${TEAMS_CHANNEL_ID:-}"
ENV_NOTIFICATION_EMAIL="${NOTIFICATION_RECIPIENT_EMAIL:-}"

# --- Defaults (from environment) ---
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-}"
LOCATION="${REGION:-westus3}"
BASE_NAME=""
SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-}"
WHAT_IF=false
VARIANT="private"
PHASE="all"
LOCAL_BUILD=false
UNIQUE_PREFIX=""
GITHUB_REPO=""

# --- Usage ---
usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Deploys infrastructure to Azure.

Options:
  -r, --resource-group NAME   Resource group (default: from AZURE_RESOURCE_GROUP env var)
  -l, --location REGION       Azure region (default: westus)
  -b, --base-name PREFIX      Resource name prefix (default: next)
  -s, --subscription ID       Subscription ID
  -v, --variant NAME          Deployment variant: 'public' or 'private' (default: private)
  -p, --phase NAME            Deployment phase: 'all', 'network', or 'services' (default: all)
  -u, --unique-prefix NUM     Numeric prefix (1-100) for unique resource names (default: random)
  -w, --what-if               Run in what-if mode (no changes)
  --local-build               Build container image locally with Docker instead of ACR Tasks
  --github-repo OWNER/REPO    GitHub repository (enables Deployment Center for Logic App)
  -h, --help                  Show this help message
EOF
  exit 0
}

# --- Argument parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --resource-group|-r) RESOURCE_GROUP="$2"; shift 2 ;;
    --location|-l)       LOCATION="$2"; shift 2 ;;
    --base-name|-b)      BASE_NAME="$2"; shift 2 ;;
    --subscription|-s)   SUBSCRIPTION_ID="$2"; shift 2 ;;
    --variant|-v)        VARIANT="$2"; shift 2 ;;
    --phase|-p)          PHASE="$2"; shift 2 ;;
    --unique-prefix|-u)  UNIQUE_PREFIX="$2"; shift 2 ;;
    --what-if|-w)        WHAT_IF=true; shift ;;
    --local-build)       LOCAL_BUILD=true; shift ;;
    --github-repo)       GITHUB_REPO="$2"; shift 2 ;;
    --help|-h)           usage ;;
    *)                   err "Unknown option: $1. Use --help for usage." ;;
  esac
done

# --- Input validation ---
validate_base_name() {
    local name="$1"
    if [[ -n "$name" && ! "$name" =~ ^[a-z][a-z0-9-]{1,10}$ ]]; then
        err "Invalid base name '$name'. Must be 2-11 lowercase alphanumeric chars or hyphens, starting with a letter."
    fi
}

validate_unique_prefix() {
    local prefix="$1"
    if [[ -n "$prefix" ]]; then
        if [[ ! "$prefix" =~ ^[0-9]{1,3}$ ]] || (( prefix < 1 || prefix > 100 )); then
            err "Invalid unique prefix '$prefix'. Must be a number 1-100."
        fi
    fi
}

validate_base_name "$BASE_NAME"
validate_unique_prefix "$UNIQUE_PREFIX"

# --- Prerequisites ---
info "Checking prerequisites..."
command -v az &>/dev/null || err "'az' CLI is required but not found in PATH"
az account show &>/dev/null || err "Not logged in to Azure. Run 'az login' first."

if [[ "$LOCAL_BUILD" == "true" ]]; then
    command -v docker &>/dev/null || err "Docker is required for --local-build but not found in PATH."
    docker info &>/dev/null || err "Docker daemon is not running. Start Docker."
fi

# Validate func CLI for Function App publish (public variant)
if [[ "$VARIANT" == "public" ]]; then
    command -v func &>/dev/null || warn "'func' CLI not found. Function App publish will be skipped."
fi

[[ "$VARIANT" != "public" && "$VARIANT" != "private" ]] && err "Variant must be 'public' or 'private'"
[[ "$PHASE" != "all" && "$PHASE" != "network" && "$PHASE" != "services" ]] && \
    err "Phase must be 'all', 'network', or 'services'"

if [[ "$VARIANT" == "private" && "$PHASE" != "services" ]]; then
    NETWORK_FEATURE_STATE=$(az feature show \
        --namespace Microsoft.Network \
        --name AllowBringYourOwnPublicIpAddress \
        --query properties.state -o tsv 2>/dev/null || echo "NotRegistered")
    if [[ "$NETWORK_FEATURE_STATE" != "Registered" ]]; then
        err "Microsoft.Network/AllowBringYourOwnPublicIpAddress must be registered. Run: az feature register --namespace Microsoft.Network --name AllowBringYourOwnPublicIpAddress && az provider register --namespace Microsoft.Network --wait"
    fi
fi
success "Prerequisites OK"

# --- Validate location against allowed regions ---
ALLOWED_LOCATIONS=("westus3" "centralus" "swedencentral" "westeurope")

validate_location() {
    local loc="$1"
    for allowed in "${ALLOWED_LOCATIONS[@]}"; do
        [[ "$loc" == "$allowed" ]] && return 0
    done
    return 1
}

if ! validate_location "$LOCATION"; then
    err "Invalid location '${LOCATION}'. Allowed regions: ${ALLOWED_LOCATIONS[*]}"
fi

# --- Generate baseName if not provided ---
if [[ -z "$BASE_NAME" ]]; then
  BASE_NAME="next"
fi
printf "${MAGENTA}Using baseName: %s${NC}\n" "$BASE_NAME"

# --- Resolve subscription ---
if [[ -z "$SUBSCRIPTION_ID" ]]; then
    SUBSCRIPTION_ID=$(az account show --query id -o tsv 2>/dev/null) \
        || err "No subscription. Set AZURE_SUBSCRIPTION_ID in .env, pass --subscription, or run 'az login'."
    info "Using current az subscription: $SUBSCRIPTION_ID"
fi

# --- Require resource group ---
[[ -z "$RESOURCE_GROUP" ]] && err "Resource group required. Set AZURE_RESOURCE_GROUP in .env or pass --resource-group."

info "Setting subscription to ${SUBSCRIPTION_ID}..."
az account set --subscription "$SUBSCRIPTION_ID" || err "Failed to set subscription"

# Register required resource providers (AVM App Insights deploys smart detection rules)
info "Registering required resource providers..."
az provider register --namespace Microsoft.AlertsManagement --wait 2>/dev/null || true

# --- Read tags from parameters.json ---
TAGS=$(python3 -c "
import json, pathlib
p = json.loads(pathlib.Path('${SCRIPT_DIR}/${VARIANT}/parameters.json').read_text())
tags = p['parameters']['tags']['value']
print(' '.join(f'{k}={v}' for k, v in tags.items()))
" 2>/dev/null || echo "environment=poc")

info "Ensuring resource group '${RESOURCE_GROUP}' exists..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" \
  --tags $TAGS --output none

# --- Build deployment arguments ---
DEPLOYMENT_NAME="${BASE_NAME}-deploy-$(date '+%Y%m%d-%H%M%S')"
PARAMETERS_FILE="${SCRIPT_DIR}/${VARIANT}/parameters.json"

# --- Read deploy flags for precheck ---
DEPLOY_COSMOSDB=$(python3 -c "
import json, pathlib
p = json.loads(pathlib.Path('${PARAMETERS_FILE}').read_text())
print(str(p['parameters'].get('deployCosmosDb', {}).get('value', True)).lower())
" 2>/dev/null || echo "true")
DEPLOY_POSTGRES=$(python3 -c "
import json, pathlib
p = json.loads(pathlib.Path('${PARAMETERS_FILE}').read_text())
print(str(p['parameters'].get('deployPostgres', {}).get('value', True)).lower())
" 2>/dev/null || echo "true")
DEPLOY_LOGICAPP=$(python3 -c "
import json, pathlib
p = json.loads(pathlib.Path('${PARAMETERS_FILE}').read_text())
print(str(p['parameters'].get('deployLogicApp', {}).get('value', True)).lower())
" 2>/dev/null || echo "true")
DEPLOY_OPENAI=$(python3 -c "
import json, pathlib
p = json.loads(pathlib.Path('${PARAMETERS_FILE}').read_text())
print(str(p['parameters'].get('deployOpenAi', {}).get('value', True)).lower())
" 2>/dev/null || echo "true")
OPENAI_MODEL=$(python3 -c "
import json, pathlib
p = json.loads(pathlib.Path('${PARAMETERS_FILE}').read_text())
print(p['parameters'].get('openAiModelName', {}).get('value', 'gpt-5'))
" 2>/dev/null || echo "gpt-5")

# --- Phase routing ---
# Use provided unique prefix or generate random (1-100) for unique resource names
if [[ -z "$UNIQUE_PREFIX" ]]; then
    UNIQUE_PREFIX=$(( (RANDOM % 100) + 1 ))
fi

# Pre-flight: handle soft-deleted resource naming conflicts
RESOURCE_PREFIX="${BASE_NAME}${UNIQUE_PREFIX}"
handle_soft_deleted_resources "$RESOURCE_PREFIX"

printf "${MAGENTA}Using uniquePrefix: %s (resourcePrefix: %s)${NC}\n" "$UNIQUE_PREFIX" "$RESOURCE_PREFIX"

# --- Run regional availability precheck ---
check_regional_availability "$LOCATION" "$RESOURCE_PREFIX"

case "$PHASE" in
    network)
        TEMPLATE_FILE="${SCRIPT_DIR}/${VARIANT}/phase1-network.bicep"
        info "Phase 1: Deploying network foundation..."
        ;;
    services)
        if [[ "$VARIANT" == "public" ]]; then
            TEMPLATE_FILE="${SCRIPT_DIR}/public/main.bicep"
            warn "Public variant does not include phase2-services.bicep; using public/main.bicep for services phase."
            info "Public services deployment..."
        else
            TEMPLATE_FILE="${SCRIPT_DIR}/${VARIANT}/phase2-services.bicep"
            # Note: VPN connectivity is NOT required for deployment (infra uses management plane).
            # This check is informational for developers running phase=services locally.
            info "Checking DNS resolution (informational, not blocking)..."
            if host "${RESOURCE_PREFIX}acr.azurecr.io" &>/dev/null; then
                resolved_ip=$(dig +short "${RESOURCE_PREFIX}acr.azurecr.io" | head -1)
                if [[ "$resolved_ip" == 10.* ]]; then
                    success "Private DNS resolving (VPN connected: ${resolved_ip})"
                else
                    info "DNS resolves to public IP (${resolved_ip}). Normal for non-VPN callers."
                fi
            else
                info "Cannot resolve private DNS. Normal for non-VPN callers."
            fi
            info "Phase 2: Deploying services..."
        fi
        ;;
    *)
        TEMPLATE_FILE="${SCRIPT_DIR}/${VARIANT}/main.bicep"
        info "Full deployment (all phases)..."
        ;;
esac

# ARM rejects parameters that are not declared by the selected phase template.
# Filter the shared parameter file for phased deployments.
DEPLOY_PARAMETERS_FILE="$PARAMETERS_FILE"
FILTERED_PARAMETERS_FILE=""
COMPILED_TEMPLATE_FILE=""
if [[ "$PHASE" != "all" ]]; then
    FILTERED_PARAMETERS_FILE=$(mktemp --suffix=.json)
    COMPILED_TEMPLATE_FILE=$(mktemp --suffix=.json)
    trap 'rm -f "$FILTERED_PARAMETERS_FILE" "$COMPILED_TEMPLATE_FILE"' EXIT

    az bicep build --file "$TEMPLATE_FILE" --outfile "$COMPILED_TEMPLATE_FILE"
    python3 - "$PARAMETERS_FILE" "$COMPILED_TEMPLATE_FILE" \
        "$FILTERED_PARAMETERS_FILE" <<'PY'
import json
import pathlib
import sys

source_path = pathlib.Path(sys.argv[1])
template_path = pathlib.Path(sys.argv[2])
output_path = pathlib.Path(sys.argv[3])
template = json.loads(template_path.read_text())
source = json.loads(source_path.read_text())
declared = set(template.get("parameters", {}))
source["parameters"] = {
        name: value
        for name, value in source.get("parameters", {}).items()
        if name in declared
}
output_path.write_text(json.dumps(source))
PY

    DEPLOY_PARAMETERS_FILE="$FILTERED_PARAMETERS_FILE"
fi

if [[ "$WHAT_IF" == "true" ]]; then
  warn "Running what-if analysis..."
  deploy_args=(
    deployment group what-if
    --resource-group "$RESOURCE_GROUP"
    --template-file "$TEMPLATE_FILE"
    --parameters "$DEPLOY_PARAMETERS_FILE"
    --parameters "baseName=$BASE_NAME"
    --parameters "uniquePrefix=${UNIQUE_PREFIX}"
    --parameters "location=${LOCATION}"
  )
else
  success "Starting deployment '${DEPLOYMENT_NAME}'..."
  deploy_args=(
    deployment group create
    --resource-group "$RESOURCE_GROUP"
    --template-file "$TEMPLATE_FILE"
    --parameters "$DEPLOY_PARAMETERS_FILE"
    --parameters "baseName=$BASE_NAME"
    --parameters "uniquePrefix=${UNIQUE_PREFIX}"
    --parameters "location=${LOCATION}"
    --name "$DEPLOYMENT_NAME"
  )
fi

# Append service and Deployment Center parameters only for templates that
# include application services.
if [[ "$PHASE" != "network" && -n "$GITHUB_REPO" ]]; then
  deploy_args+=(--parameters "githubRepo=${GITHUB_REPO}")
  info "Deployment Center will be configured for ${GITHUB_REPO} (manual sync)."
fi

# Append .env-driven operational parameters (override parameters.json defaults)
if [[ "$PHASE" != "network" ]]; then
    [[ -n "$ENV_CONTAINER_IMAGE" ]]    && deploy_args+=(--parameters "containerImage=${ENV_CONTAINER_IMAGE}")
    [[ -n "$ENV_SHARED_MAILBOX" ]]     && deploy_args+=(--parameters "sharedMailboxAddress=${ENV_SHARED_MAILBOX}")
    [[ -n "$ENV_TEAMS_GROUP_ID" ]]     && deploy_args+=(--parameters "teamsGroupId=${ENV_TEAMS_GROUP_ID}")
    [[ -n "$ENV_TEAMS_CHANNEL_ID" ]]   && deploy_args+=(--parameters "teamsChannelId=${ENV_TEAMS_CHANNEL_ID}")
    [[ -n "$ENV_NOTIFICATION_EMAIL" ]] && deploy_args+=(--parameters "notificationRecipientEmail=${ENV_NOTIFICATION_EMAIL}")
fi

# --- Execute deployment ---
run_deployment() {
    local output
    set +e
    output=$(az "${deploy_args[@]}" 2>&1)
    local status=$?
    set -e
    printf '%s\n' "$output"
    return $status
}

deployment_output=""
if ! deployment_output=$(run_deployment); then
    printf '%s\n' "$deployment_output" >&2

    if [[ "$deployment_output" == *"AadAuthOperationCannotBePerformedWhenServerIsNotAccessible"* ]]; then
        warn "Detected transient PostgreSQL Entra admin accessibility issue. Retrying deployment automatically..."

        retry_waits=(120 180 300)
        retry_succeeded=false

        for retry_wait in "${retry_waits[@]}"; do
            info "Waiting ${retry_wait}s before retry..."
            sleep "$retry_wait"

            if deployment_output=$(run_deployment); then
                retry_succeeded=true
                success "Deployment retry succeeded."
                break
            fi

            printf '%s\n' "$deployment_output" >&2
        done

        if [[ "$retry_succeeded" != "true" ]]; then
            err "Deployment failed after transient retry attempts"
        fi
    else
        # Check if failure is isolated to VPN Gateway (non-critical for services)
        failed_types=$(az deployment operation group list \
            --resource-group "$RESOURCE_GROUP" \
            --name "$DEPLOYMENT_NAME" \
            --query "[?properties.provisioningState=='Failed'].properties.targetResource.resourceType" \
            -o tsv 2>/dev/null || echo "")

        # Check if ALL failed resources are VPN Gateway (handles multi-line TSV)
        vpn_only=true
        while IFS= read -r rtype; do
            [[ -z "$rtype" ]] && continue
            if [[ "$rtype" != "Microsoft.Network/virtualNetworkGateways" ]]; then
                vpn_only=false
                break
            fi
        done <<< "$failed_types"

        if [[ -n "$failed_types" && "$vpn_only" == "true" ]]; then
            warn "VPN Gateway failed (transient Azure error). Services deployed successfully."
            warn "Retrying deployment to recover VPN Gateway..."
            if run_deployment >/dev/null 2>&1; then
                success "VPN Gateway retry succeeded."
            else
                warn "VPN Gateway retry also failed. Services are deployed and functional."
                warn "The VPN Gateway can be recovered later with:"
                warn "  az network vnet-gateway update --name ${RESOURCE_PREFIX}-vpn-gw --resource-group $RESOURCE_GROUP --no-wait"
                info "Deployment completed with VPN Gateway in failed state."
            fi
        else
            err "Deployment failed"
        fi
    fi
else
    printf '%s\n' "$deployment_output"
fi

# --- Post-Deployment: Application Code ---
if [[ "$WHAT_IF" != "true" && "$PHASE" != "network" ]]; then
    printf "\n${CYAN}=== Deploying Application Code ===${NC}\n"

    if [[ "$VARIANT" == "private" ]]; then
        # --- Private variant: GHCR image + Logic App workflow deploy ---
        GHCR_OWNER="${GHCR_OWNER:-$(git remote get-url origin 2>/dev/null | sed -n 's#.*github.com[:/]\([^/]*\)/.*#\1#p')}"
        [[ -z "$GHCR_OWNER" ]] && err "Cannot determine GHCR owner. Set GHCR_OWNER env var or ensure git remote 'origin' points to GitHub."
        GHCR_IMAGE="ghcr.io/${GHCR_OWNER}/communicator:latest"

        # Configure GHCR registry credentials on Container App (required for private images)
        CONTAINER_APP_NAME="${RESOURCE_PREFIX}-communicator"
        GHCR_TOKEN="${GITHUB_TOKEN:-}"
        if [[ -n "$GHCR_TOKEN" ]]; then
            info "Configuring GHCR registry credentials on '${CONTAINER_APP_NAME}'..."
            az containerapp registry set --name "$CONTAINER_APP_NAME" \
                --resource-group "$RESOURCE_GROUP" \
                --server ghcr.io \
                --username "${GHCR_OWNER}" \
                --password "${GHCR_TOKEN}" \
                || warn "GHCR registry credential setup failed. Image pull may fail."
        else
            warn "GITHUB_TOKEN not set in .env — GHCR registry auth skipped. Image pull will fail for private packages."
        fi

        # Update Container App with GHCR image (management plane, no VNet needed)
        info "Updating Container App '${CONTAINER_APP_NAME}' with image '${GHCR_IMAGE}'..."
        az containerapp update --name "$CONTAINER_APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --image "$GHCR_IMAGE" \
            || warn "Container App update failed. May need manual image update."

        # Deploy Logic App workflows (fallback — primary path is Deployment Center CI/CD)
        info "Primary Logic App deployment is Deployment Center CI/CD (.github/workflows/deploy-logic-app.yml)."
        info "Requires: deploy.sh was run with --github-repo to provision Deployment Center."
        info "This fallback uses direct SCM zip deploy (requires VNet access)."
        LOGIC_DEPLOY_SCRIPT="${SCRIPT_DIR}/../logic_app/deploy-workflows.sh"
        LOGIC_APP_NAME="${RESOURCE_PREFIX}-logic"
        if [[ -f "$LOGIC_DEPLOY_SCRIPT" ]]; then
            info "Deploying Logic App workflows to '${LOGIC_APP_NAME}'..."
            bash "$LOGIC_DEPLOY_SCRIPT" \
                --resource-group "$RESOURCE_GROUP" \
                --logic-app-name "$LOGIC_APP_NAME" \
                || warn "Logic App workflow deploy failed (SCM may be unreachable outside VNet). Push to main to trigger CI/CD instead."
        else
            warn "Logic App deploy script not found at: $LOGIC_DEPLOY_SCRIPT"
        fi

    else
        # --- Public variant: Deploy via GHCR ---
        GHCR_OWNER="${GHCR_OWNER:-$(git remote get-url origin 2>/dev/null | sed -n 's#.*github.com[:/]\([^/]*\)/.*#\1#p')}"
        [[ -z "$GHCR_OWNER" ]] && err "Cannot determine GHCR owner. Set GHCR_OWNER env var or ensure git remote 'origin' points to GitHub."

        GHCR_IMAGE="ghcr.io/${GHCR_OWNER}/communicator:latest"

        # Build and push locally only when --local-build is set (bootstrap/dev)
        if [[ "$LOCAL_BUILD" == "true" ]]; then
            DOCKERFILE_PATH="${SCRIPT_DIR}/../communicator_app/Dockerfile"
            CONTEXT_PATH="${SCRIPT_DIR}/../communicator_app"
            info "Building communicator image locally for GHCR..."
            docker build -t "$GHCR_IMAGE" -f "$DOCKERFILE_PATH" "$CONTEXT_PATH" \
                || err "Docker build failed"
            info "Pushing communicator image to GHCR..."
            docker push "$GHCR_IMAGE" \
                || err "GHCR push failed. Ensure 'docker login ghcr.io' has been done."
        else
            info "Using CI-built GHCR image: ${GHCR_IMAGE}"
        fi

        # 1. Update Container App with GHCR image
        CONTAINER_APP_NAME="${RESOURCE_PREFIX}-communicator"
        info "Updating Container App '${CONTAINER_APP_NAME}' with image '${GHCR_IMAGE}'..."
        az containerapp update --name "$CONTAINER_APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --image "$GHCR_IMAGE" \
            || warn "Container App update failed. May need manual image update."

        # 2. Deploy Logic App workflows
        LOGIC_DEPLOY_SCRIPT="${SCRIPT_DIR}/../logic_app/deploy-workflows.sh"
        LOGIC_APP_NAME="${RESOURCE_PREFIX}-logic"
        if [[ -f "$LOGIC_DEPLOY_SCRIPT" ]]; then
            info "Deploying Logic App workflows to '${LOGIC_APP_NAME}'..."
            bash "$LOGIC_DEPLOY_SCRIPT" \
                --resource-group "$RESOURCE_GROUP" \
                --logic-app-name "$LOGIC_APP_NAME" \
                || warn "Logic App workflow deploy failed. Run manually: bash src/logic_app/deploy-workflows.sh --resource-group $RESOURCE_GROUP --logic-app-name $LOGIC_APP_NAME"
        else
            warn "Logic App deploy script not found at: $LOGIC_DEPLOY_SCRIPT"
        fi

        # 3. Publish Function App code (if function app exists)
        FUNC_APP_NAME="${RESOURCE_PREFIX}-func"
        if az functionapp show --name "$FUNC_APP_NAME" --resource-group "$RESOURCE_GROUP" --query name -o tsv &>/dev/null; then
            info "Publishing function code to '${FUNC_APP_NAME}'..."
            FUNC_PROJECT_PATH="${SCRIPT_DIR}/../communicator_app/src"
            pushd "$FUNC_PROJECT_PATH" > /dev/null
            func azure functionapp publish "$FUNC_APP_NAME" --python \
                || warn "Function App publish failed. Run manually: cd src/communicator_app/src && func azure functionapp publish $FUNC_APP_NAME --python"
            popd > /dev/null
        fi
    fi

    success "Application code deployment complete."
fi

if [[ "$WHAT_IF" != "true" && "$PHASE" == "network" ]]; then
    printf "\n${GREEN}=== Phase 1 Complete ===${NC}\n"
    info "Generating VPN client profile..."
    VPN_PROFILE_URL=$(az network vnet-gateway vpn-client generate \
        --resource-group "$RESOURCE_GROUP" \
        --name "${RESOURCE_PREFIX}-vpn-gw" \
        --authentication-method EapTls \
        --output tsv 2>/dev/null || echo "")

    if [[ -n "$VPN_PROFILE_URL" ]]; then
        PROFILE_DIR="${SCRIPT_DIR}/private/vpn-client-profile"
        mkdir -p "$PROFILE_DIR"
        curl -sL "$VPN_PROFILE_URL" -o "$PROFILE_DIR/vpn-profile.zip"
        unzip -o "$PROFILE_DIR/vpn-profile.zip" -d "$PROFILE_DIR" || true
        rm -f "$PROFILE_DIR/vpn-profile.zip"
        if [[ -f "$PROFILE_DIR/AzureVPN/azurevpnconfig.xml" ]]; then
            success "VPN profile downloaded to infra_deployment/private/vpn-client-profile/"
            info "Import AzureVPN/azurevpnconfig.xml into Azure VPN Client to connect."
        else
            warn "VPN profile archive downloaded but extraction did not produce AzureVPN/azurevpnconfig.xml."
        fi
    else
        warn "Could not generate VPN profile. VPN Gateway may still be provisioning."
        warn "Retry after VPN Gateway is fully provisioned (~30-45 min)."
    fi

    # Configure VPN client DNS to use private DNS resolver
    info "Configuring VPN client DNS servers..."
    VPN_GW_NAME="${RESOURCE_PREFIX}-vpn-gw"
    if az network vnet-gateway update \
        --name "$VPN_GW_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --set "vpnClientConfiguration.vpnClientAddressPool.customDnsServers=['10.0.9.4']" \
        --no-wait \
        --output none 2>/dev/null; then
        success "VPN client DNS configured to use 10.0.9.4"
        info "Clients must re-download VPN profile and reconnect."
    else
        warn "Failed to configure VPN DNS. Run manually:"
        warn "  az network vnet-gateway update --name $VPN_GW_NAME --resource-group $RESOURCE_GROUP --set \"vpnClientConfiguration.vpnClientAddressPool.customDnsServers=['10.0.9.4']\""
    fi

    warn "Next steps:"
    warn "  1. Connect using Azure VPN Client"
    warn "  2. Run: ./deploy.sh --phase services"
fi

if [[ "$WHAT_IF" == "true" ]]; then
    success "What-if analysis completed successfully."
else
    success "Deployment completed successfully."
fi
