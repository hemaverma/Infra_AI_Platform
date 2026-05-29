# NExT Communication System

[![Open in GitHub Codespaces](https://img.shields.io/static/v1?style=for-the-badge&label=GitHub+Codespaces&message=Open&color=brightgreen&logo=github)](https://codespaces.new/hemaverma/infra-ai-platform?ref=feature/devcontainer)
[![Open in Dev Container](https://img.shields.io/static/v1?style=for-the-badge&label=Dev+Container&message=Open&color=blue&logo=visualstudiocode)](https://vscode.dev/redirect?url=vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=https://github.com/hemaverma/infra-ai-platform)

(TODO: remove dev branch reference before merge)

NExT is a Python-based communication workflow project for processing vendor maintenance notifications, extracting structured information, and coordinating human-in-the-loop approvals.

## Repository Structure

- `docs/` contains architecture notes and ADRs.
- `src/` contains application and experimentation code.
- `tests/` contains automated tests.
- `Taskfile.yml` defines common development commands.

## Development Setup

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fhemaverma%2FInfra_AI_Platform%2Fmain%2Fsrc%2Finfra_deployment%2Fpublic%2Fmain.json)



Create and activate the virtual environment before running project commands.

### GitHub Codespaces / Dev Container

The fastest way to start is the prebuilt dev container, which works in both
GitHub Codespaces and a local VS Code Dev Container. It pins Python 3.10,
installs the Azure CLI, Azure Functions Core Tools, and GitHub CLI, and runs
`.devcontainer/postCreate.sh` to build `.venv` and install every requirements
file automatically.

- **One-click Codespaces:** click the **GitHub Codespaces** badge above. After
  the container builds, the environment is ready — no manual `task env:create`
  needed.
- **Local Dev Container:** clone the repository, open it in VS Code, and choose
  **Reopen in Container** (requires Docker and the Dev Containers extension).
- **Secrets:** set `AZURE_OPENAI_*` and Cosmos DB credentials as Codespaces
  secrets (Settings → Secrets and variables → Codespaces). They are injected as
  environment variables from `postCreateCommand` onward. Do not commit a `.env`
  file with credentials.

> **Note:** `task app:start` currently uses a Windows-only Python path
> (`.venv/Scripts/python.exe`) and does not yet run inside the Linux container.
> Verify or adjust it before relying on `func start` in Codespaces.

### PowerShell (Windows)

```powershell
task env:create
.\.venv\Scripts\Activate.ps1
task deps:install
```

> **Note:** The `task` CLI (`go-task`) is included in `requirements-dev.txt` as
> `go-task-bin`. After activating the virtual environment, run
> `pip install -r requirements-dev.txt` to make the `task` command available
> locally.

## Common Commands

```powershell
task test:quick
task lint:all
```

## Components

| Component | Location | Purpose |
|-----------|----------|----------|
| Communicator App | [`src/communicator_app/`](src/communicator_app/README.md) | Azure Functions app implementing the agent workflow — envelope dispatch, LLM field extraction, HITL pauses, and email drafting. Contains manual testing instructions via HTTP endpoints. |
| Experimentation | `src/experimentation/` | Experimentation utilities. |

## Documentation

- [Executive Summary](docs/IaC/executive-summary.md): Platform features and cost decisions
- Architecture overview: [docs/design/architecture.md](docs/design/architecture.md)
- [Infrastructure Architecture](docs/IaC/Infrastructure.md): Full technical architecture
- [Private Deployment Guide](src/infra_deployment/private/README.md): End-to-end private deployment walkthrough
- ADRs: [docs/adr](docs/adr)
- Copilot instructions: [.github/copilot-instructions.md](.github/copilot-instructions.md)

## Notes

- Python 3.10 is the primary target version.
- Development tasks assume the repository virtual environment is active.

## Deployment

### Prerequisites

| Tool | Version | Windows | macOS / Linux |
|------|---------|---------|---------------|
| Azure CLI | 2.60+ | `winget install Microsoft.AzureCLI` | `curl -sL https://aka.ms/InstallAzureCLIDeb \| sudo bash` (Ubuntu/Debian) or `brew install azure-cli` (macOS) |
| Bicep CLI | Latest (bundled with az) | `az bicep install` | `az bicep install` |
| Azure Functions Core Tools | 4.x | `winget install Microsoft.Azure.FunctionsCoreTools` | `brew tap azure/functions && brew install azure-functions-core-tools@4` (macOS) or [Linux install guide](https://learn.microsoft.com/azure/azure-functions/functions-run-local#install-the-azure-functions-core-tools) |
| PowerShell | 7+ | `winget install Microsoft.PowerShell` | `sudo apt-get install -y powershell` (Ubuntu/Debian) or `brew install powershell/tap/powershell` (macOS) |

### One-Click Deployment

Click the **Deploy to Azure** button at the top of this README to deploy all infrastructure through the Azure Portal.

### CLI Deployment

**PowerShell (Windows)**

```powershell
task deploy:env:setup    # Validate prerequisites
task deploy:validate     # Validate Bicep templates
task deploy:whatif        # Preview changes
task deploy:infra        # Deploy infrastructure
task deploy:apps         # Deploy application code (requires VPN)
```

**Bash (macOS / Linux)**

```bash
task deploy:env:setup    # Validate prerequisites
task deploy:validate     # Validate Bicep templates
task deploy:whatif        # Preview changes
task deploy:infra        # Deploy infrastructure
task deploy:apps         # Deploy application code (requires VPN)
```

### Private Network Access

Application code deployment requires VPN connectivity to the private VNet.
Configure P2S VPN before running `task deploy:apps`.
