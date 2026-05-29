#!/usr/bin/env bash
#
# validate.sh
# Validates all Bicep files in the infra_deployment directory.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Color output (disabled when piped) ---
if [[ -t 1 ]]; then
  RED='\033[0;31m' GREEN='\033[0;32m' CYAN='\033[0;36m' NC='\033[0m'
else
  RED='' GREEN='' CYAN='' NC=''
fi

# --- Prerequisites ---
command -v az &>/dev/null || {
  printf "${RED}ERROR: 'az' CLI is required but not found in PATH${NC}\n" >&2
  exit 1
}

az bicep version &>/dev/null || {
  printf "${RED}ERROR: 'az bicep' is not available. Run 'az bicep install' first.${NC}\n" >&2
  exit 1
}

# --- Collect Bicep files ---
modules_dir="${SCRIPT_DIR}/modules"
files=()
files+=("${SCRIPT_DIR}/public/main.bicep")
files+=("${SCRIPT_DIR}/private/main.bicep")

while IFS= read -r -d '' bicep_file; do
  files+=("$bicep_file")
done < <(find "$modules_dir" -name '*.bicep' -print0 | sort -z)

# --- Validate each file ---
declare -a results_file=()
declare -a results_status=()
pass_count=0
fail_count=0
failed=false

for file in "${files[@]}"; do
  relative_path="${file#"${SCRIPT_DIR}/"}"
  printf "Validating %s..." "$relative_path"

  if az bicep build --file "$file" --stdout > /dev/null 2>&1; then
    printf " ${GREEN}PASS${NC}\n"
    results_file+=("$relative_path")
    results_status+=("PASS")
    (( pass_count++ ))
  else
    printf " ${RED}FAIL${NC}\n"
    results_file+=("$relative_path")
    results_status+=("FAIL")
    (( fail_count++ ))
    failed=true
  fi
done

# --- Summary ---
printf "\n${CYAN}=== Validation Summary ===${NC}\n"
printf "%-50s %s\n" "File" "Status"
printf "%-50s %s\n" "----" "------"

for i in "${!results_file[@]}"; do
  status="${results_status[$i]}"
  if [[ "$status" == "PASS" ]]; then
    printf "%-50s ${GREEN}%s${NC}\n" "${results_file[$i]}" "$status"
  else
    printf "%-50s ${RED}%s${NC}\n" "${results_file[$i]}" "$status"
  fi
done

printf "\nTotal: %d | Passed: %d | Failed: %d\n" \
  "$(( pass_count + fail_count ))" "$pass_count" "$fail_count"

if [[ "$failed" == "true" ]]; then
  printf "${RED}One or more files failed validation.${NC}\n" >&2
  exit 1
fi

printf "${GREEN}All files validated successfully.${NC}\n"
