#!/usr/bin/env bash
set -euo pipefail
# Codespaces-specific setup: private network relay
# Only meaningful in GitHub Codespaces (CODESPACES=true)

if [[ "${CODESPACES:-}" == "true" ]]; then
    echo "=== Codespaces detected: configuring private network relay ==="

    # Option A: Tailscale (recommended for simplicity)
    # Requires TAILSCALE_AUTHKEY secret in Codespaces settings
    if [[ -n "${TAILSCALE_AUTHKEY:-}" ]]; then
        curl -fsSL https://tailscale.com/install.sh | sh
        sudo tailscale up --authkey="$TAILSCALE_AUTHKEY" --accept-routes
        echo "Tailscale connected. Private endpoints accessible via Tailscale network."
    else
        echo "NOTE: Set TAILSCALE_AUTHKEY Codespace secret for private network access."
    fi

    # Option B: Azure Relay Hybrid Connection (alternative)
    if [[ -n "${AZURE_RELAY_CONNECTION_STRING:-}" ]]; then
        echo "Azure Relay configured. Use relay for private endpoint access."
    fi
else
    echo "Local dev container: using host VPN DNS relay (--dns=10.0.6.20)"
fi
