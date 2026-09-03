# GPT Realtime Language Lab

[Dansk version](readme_dk.md)

A small learning project for testing `gpt-realtime-1.5` with Danish and English speech and grounded answers from your own PDF, DOCX, and TXT files.

## Architecture

```mermaid
flowchart LR
	user[User] --> browser[Browser client]

	subgraph app[Azure Container Apps]
		static[Static web client]
		api[FastAPI]
	end

	subgraph foundry[Microsoft Foundry]
		realtime[gpt-realtime-1.5]
		embeddings[text-embedding-3-large]
	end

	subgraph knowledge[Knowledge base]
		blob[(Blob Storage)]
		indexer[AI Search indexer]
		index[(Hybrid semantic and vector index)]
	end

	browser -- HTTPS --> static
	browser -- Create session --> api
	api -- Short-lived client secret --> realtime
	browser <-- WebRTC: audio and events --> realtime

	realtime -- search_knowledge_base --> browser
	browser -- Knowledge search --> api
	api -- Hybrid search --> index
	index -- Grounding sources --> api
	api -- Tool result --> browser
	browser -- Function call output --> realtime

	browser -- Upload documents --> api
	api -- PDF, DOCX and TXT --> blob
	api -- Start indexing --> indexer
	blob --> indexer
	indexer -- Chunking and language detection --> embeddings
	embeddings -- 3072-dimensional vectors --> index
```

- The browser connects directly to GPT Realtime through WebRTC using a short-lived client secret from FastAPI.
- FastAPI uses `DefaultAzureCredential`; no Azure API keys are stored in the source code.
- Documents are stored in Blob Storage and chunked/vectorized by Azure AI Search.
- Hybrid semantic/vector search uses `text-embedding-3-large` with 3072 dimensions.
- Azure Container Apps hosts both the API and the static browser client.

`azd up` creates a dedicated Foundry resource in the selected resource group together with deployments for `gpt-realtime-1.5`, `text-embedding-3-large`, and `gpt-4o-mini-transcribe`. Deployment names and model versions can be configured through the azd environment.

## Run locally

Prerequisites:

- Python 3.12
- An Azure CLI login with access to Foundry, Search, and Storage
- The required local data-plane roles

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`, allow microphone access, and select Auto, Dansk, or English.

The knowledge base requires values for `AZURE_SEARCH_ENDPOINT` and `AZURE_STORAGE_ACCOUNT_URL` in `.env`. The storage URL must be the account endpoint without the container name, for example `https://<account>.blob.core.windows.net`; configure the container separately with `AZURE_STORAGE_CONTAINER_NAME`. The realtime functionality can be tested separately.

## Quality checks

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m pytest
```

The manual language and retrieval matrix is available in [docs/manual-test-plan.md](docs/manual-test-plan.md).

## Azure deployment

The project uses azd, Bicep, remote ACR builds, and managed identities. During `azd up`, you are prompted to choose an existing or new resource group for the demo.

```powershell
azd auth login
azd env select realtime-dev
$clientId = azd env get-value ENTRA_CLIENT_ID
az ad app update --id $clientId --enable-id-token-issuance true
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"
azd provision --no-prompt
azd deploy --no-prompt
```

ID token issuance is required by the Container Apps Easy Auth hybrid flow. Container Apps and ACR are deployed in two stages so the `AcrPull` role can propagate between provisioning and image deployment. The Search index, data source, skillset, and indexer are created idempotently by the post-provision hook.

## Security

- Runtime access uses Entra ID and managed identity.
- Local key authentication is disabled for Storage and Search.
- Raw audio is not stored.
- Uploads are limited to PDF, DOCX, and TXT files of up to 20 MB.
- `.env` and `.azure` are ignored by Git.

## Azure RBAC

### Roles provisioned by Bicep

The assignments below are the repeatable source of truth defined in `infra/main.bicep`.

| Principal | Scope | Role | Purpose |
|---|---|---|---|
| Container App user-assigned managed identity | Container Registry | `AcrPull` | Pull the application image |
| Container App user-assigned managed identity | Foundry resource | `Cognitive Services OpenAI User` | Create Realtime sessions and use deployed models |
| Container App user-assigned managed identity | Storage account | `Storage Blob Data Contributor` | List, upload, and delete knowledge documents |
| Container App user-assigned managed identity | Azure AI Search | `Search Index Data Reader` | Query the knowledge index |
| Container App user-assigned managed identity | Azure AI Search | `Search Service Contributor` | Run and inspect the Search indexer |
| Azure AI Search system-assigned managed identity | Storage account | `Storage Blob Data Reader` | Read source documents during indexing |
| Azure AI Search system-assigned managed identity | Foundry resource | `Cognitive Services OpenAI User` | Generate embeddings through the configured model deployment |
| Azure AI Search system-assigned managed identity | Foundry resource | `Cognitive Services User` | Use the AI Services enrichment skillset |
| Deploying user (`principalId`) | Azure AI Search | `Search Service Contributor` | Create and update the index, data source, skillset, and indexer |
| Deploying user (`principalId`) | Azure AI Search | `Search Index Data Reader` | Validate and query the configured index |

Container Apps Easy Auth controls end-user access to the web application separately from these Azure RBAC assignments.

### Required demo environment

For this demo, the expected Azure context is:

- Tenant: `1a8f6d42-be1a-4de7-a668-2857bc39ce8a`
- Subscription: `40bfcd72-ab71-4a15-be1a-be1cff1d2498`
- Resource group: `rg-ai103`

The app uses `DefaultAzureCredential`, so the active Azure CLI session must be logged in to the correct tenant and subscription before starting the realtime session. If the wrong tenant or subscription is active, the backend can start but the realtime session creation will fail with the message: `Could not start the realtime session`.

```powershell
az login --tenant 1a8f6d42-be1a-4de7-a668-2857bc39ce8a
az account set --subscription 40bfcd72-ab71-4a15-be1a-be1cff1d2498
az account show --output table
az group show --name rg-ai103 --subscription 40bfcd72-ab71-4a15-be1a-be1cff1d2498 --output table
```

### RBAC checklist for the demo

Before retrying the app, confirm that the signed-in principal has the required Azure RBAC on the resources in `rg-ai103`, especially the Foundry/OpenAI resource, Azure AI Search, and Storage account used by the demo. The exact assignment names can vary, but the active user must be able to:

- Create and use the realtime/OpenAI session
- Read from the Azure AI Search index
- Read/write the storage account used for knowledge documents
- Access the configured Foundry deployment(s) used by the app

If the app still fails after switching to the correct tenant/subscription, verify the current principal and the role assignments on the target resources in `rg-ai103` before changing code.
