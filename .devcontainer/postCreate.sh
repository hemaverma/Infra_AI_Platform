#!/usr/bin/env bash
set -euo pipefail

# The dev container is already an isolated environment, so dependencies are
# installed directly into the container's Python rather than a virtualenv.
# (A workspace-folder .venv would be shadowed by the bind-mounted host .venv,
# whose symlinks point at host paths that do not exist inside the container.)

echo "[postCreate] Upgrading pip..."
python -m pip install --upgrade pip

echo "[postCreate] Installing dev + project + component requirements..."
python -m pip install -r requirements-dev.txt
python -m pip install -r requirements.txt
# --pre: communicator_app pins a pre-release lower bound
# (agent-framework-azure-cosmos>=1.0.0b260429), which pip will not resolve
# without pre-releases enabled.
python -m pip install --pre -r src/communicator_app/requirements.txt
python -m pip install -r src/experimentation/requirements.txt

echo "[postCreate] Done. Run 'task test:quick' to verify."
