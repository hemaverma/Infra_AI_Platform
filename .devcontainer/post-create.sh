#!/usr/bin/env bash
set -euo pipefail

echo "=== Installing Python dependencies ==="
pip install --pre -r requirements.txt
pip install -r requirements-dev.txt
pip install --pre -r src/communicator_app/requirements.txt

echo "=== Installing cspell (spell checker) ==="
npm install -g cspell

echo "=== Installing Azure Functions Core Tools v4 ==="
curl -sL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /tmp/microsoft.gpg
sudo mv /tmp/microsoft.gpg /etc/apt/trusted.gpg.d/microsoft.gpg
echo "deb [arch=amd64] https://packages.microsoft.com/debian/$(lsb_release -rs | cut -d'.' -f1)/prod $(lsb_release -cs) main" | \
    sudo tee /etc/apt/sources.list.d/azure-functions.list
sudo apt-get update && sudo apt-get install -y azure-functions-core-tools-4

echo "=== Installing go-task ==="
sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d -b /usr/local/bin

echo "=== Installing Azurite ==="
npm install -g azurite

echo "=== Creating Azurite data directory ==="
mkdir -p /workspace/.azurite

echo "=== Setup complete ==="
echo "NOTE: Connect to Azure VPN on your host machine for private endpoint access."
