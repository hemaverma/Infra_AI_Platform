#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
#
# deploy-workflows.sh
# Deploy Logic App Standard workflow definitions via zip deployment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"
ZIP_PATH="${SCRIPT_DIR}/workflows.zip"

RESOURCE_GROUP=""
LOGIC_APP_NAME=""
DRY_RUN=false

usage() {
  echo "Usage: ${0##*/} --resource-group <rg> --logic-app-name <name> [--dry-run]"
  echo ""
  echo "Options:"
  echo "  --resource-group   Azure resource group containing the Logic App (required)"
  echo "  --logic-app-name   Name of the Logic App Standard instance (required)"
  echo "  --dry-run          Build zip package without deploying"
  echo "  --help, -h         Show this help message"
  exit 1
}

err() {
  printf "ERROR: %s\n" "$1" >&2
  exit 1
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --resource-group)
        if [[ -z "${2:-}" || "$2" == --* ]]; then
          echo "Error: --resource-group requires an argument" >&2
          usage
        fi
        RESOURCE_GROUP="$2"
        shift 2
        ;;
      --logic-app-name)
        if [[ -z "${2:-}" || "$2" == --* ]]; then
          echo "Error: --logic-app-name requires an argument" >&2
          usage
        fi
        LOGIC_APP_NAME="$2"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --help|-h)
        usage
        ;;
      *)
        echo "Unknown option: $1" >&2
        usage
        ;;
    esac
  done

  if [[ -z "${RESOURCE_GROUP}" ]]; then
    err "--resource-group is required"
  fi
  if [[ -z "${LOGIC_APP_NAME}" ]]; then
    err "--logic-app-name is required"
  fi
}

main() {
  parse_args "$@"

  if ! command -v "az" &>/dev/null; then
    err "'az' command is required but not installed"
  fi

  # Workflow definitions: folder name -> source JSON file
  if ((BASH_VERSINFO[0] < 4)); then
     err "Bash 4+ is required (associative arrays). Install a newer bash or use deploy-workflows.ps1."
  fi
  
  declare -A workflows=(
    ["email-poller"]="logic_app_workflow_main.json"
    ["hitl-approval"]="logic_app_workflow-hitl.json"
  )

  # Clean previous build
  if [[ -d "${BUILD_DIR}" ]]; then
    rm -rf "${BUILD_DIR}"
  fi
  mkdir -p "${BUILD_DIR}"

  # Create workflow folders
  for folder in "${!workflows[@]}"; do
    local source_file="${workflows[${folder}]}"
    local source_path="${SCRIPT_DIR}/${source_file}"
    local wf_dir="${BUILD_DIR}/${folder}"

    mkdir -p "${wf_dir}"

    if [[ ! -f "${source_path}" ]]; then
      err "Workflow source not found: ${source_path}"
    fi

    cp "${source_path}" "${wf_dir}/workflow.json"
    echo "  Packaged: ${folder}/workflow.json"
  done

  # Copy global files
  declare -a global_files=("host.json" "connections.json" "parameters.json")
  for file in "${global_files[@]}"; do
    local file_path="${SCRIPT_DIR}/${file}"
    if [[ ! -f "${file_path}" ]]; then
      err "Required file not found: ${file_path}"
    fi
    cp "${file_path}" "${BUILD_DIR}/"
    echo "  Included: ${file}"
  done

  # Create zip package
  if [[ -f "${ZIP_PATH}" ]]; then
    rm -f "${ZIP_PATH}"
  fi
  (cd "${BUILD_DIR}" && zip -r "${ZIP_PATH}" .)
  echo ""
  echo "  Package created: ${ZIP_PATH}"

  if [[ "${DRY_RUN}" == true ]]; then
    echo ""
    echo "[DryRun] Skipping deployment. Package ready at: ${ZIP_PATH}"
    echo "[DryRun] Contents:"
    find "${BUILD_DIR}" -type f | while read -r f; do
      echo "  ${f#"${BUILD_DIR}"}"
    done
    return
  fi

  # Deploy
  echo ""
  echo "Deploying workflows to ${LOGIC_APP_NAME} in ${RESOURCE_GROUP}..."
  az logicapp deployment source config-zip \
    --name "${LOGIC_APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --src "${ZIP_PATH}"

  echo ""
  echo "Workflows deployed to ${LOGIC_APP_NAME}"
}

main "$@"
