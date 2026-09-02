# Start guide for the project

This file is a quick reference for starting the application locally and for understanding the project setup.

## Daily startup

Open PowerShell and run:

```powershell
cd C:\Github\realtime_demo
.\.venv\Scripts\Activate.ps1
az account get-access-token --resource https://storage.azure.com/ --output none
uvicorn app.main:app --reload
```

If the Azure token check fails, sign in to the tenant that owns the demo resources and then start the app:

```powershell
az logout
az login --tenant 1a8f6d42-be1a-4de7-a668-2857bc39ce8a --scope https://storage.azure.com/.default
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`, allow microphone access, and start a new conversation. The existing `.env`, virtual environment, Azure resources, uploaded documents, and role assignments are reused.

## 1. Open a terminal in the project folder

```powershell
cd C:\Github\realtime_demo
```

## 2. Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

If the virtual environment does not exist yet:

```powershell
cd C:\Github\realtime_demo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## 3. Install dependencies

```powershell
pip install -e ".[dev]"
```

## 4. Create the local environment file

```powershell
# Copy-Item .env.example .env
```

Then fill in the required Azure values in `.env`, especially:

- `AZURE_SEARCH_ENDPOINT`
- `AZURE_STORAGE_ACCOUNT_URL`

## 5. Start the FastAPI app

```powershell
uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## 6. Use the app

The app supports:

- Auto language selection
- Danish
- English

Allow microphone access in the browser when prompted.

## 7. Check that the API is healthy

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

## 8. Run quality checks

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m pytest
```

## 9. Azure deployment

This project is prepared for Azure deployment with azd:

```powershell
azd auth login
azd env select realtime-dev
$clientId = azd env get-value ENTRA_CLIENT_ID
az ad app update --id $clientId --enable-id-token-issuance true
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"
azd provision --no-prompt
azd deploy --no-prompt
```

## 10. Recreate the Azure environment after cleanup

The existing resource group `rg-ai103` is shared with resources that are not owned by this demo. Choose a new, dedicated resource group when prompted if you want the entire group to follow the demo lifecycle. The infrastructure can be recreated from `azure.yaml` and `infra/main.bicep`.

The Foundry resource and its three model deployments are created in the selected resource group. The existing Entra app registration is reused. Uploaded knowledge-base documents are not restored automatically and must be uploaded again.

### 10.1 Create or select the azd environment

```powershell
azd auth login
az login

azd env new realtime-dev
```

If `realtime-dev` already exists locally, use this instead:

```powershell
azd env select realtime-dev
```

Configure the deployment values:

```powershell
azd env set AZURE_SUBSCRIPTION_ID "40bfcd72-ab71-4a15-be1a-be1cff1d2498"
azd env set AZURE_LOCATION "swedencentral"
azd env set AZURE_OPENAI_REALTIME_DEPLOYMENT "gpt-realtime-1.5"
azd env set AZURE_OPENAI_REALTIME_MODEL_VERSION "2026-02-23"
azd env set AZURE_OPENAI_EMBEDDING_DEPLOYMENT "text-embedding-3-large"
azd env set AZURE_OPENAI_EMBEDDING_MODEL_VERSION "1"
azd env set AZURE_OPENAI_TRANSCRIPTION_DEPLOYMENT "gpt-4o-mini-transcribe"
azd env set AZURE_OPENAI_TRANSCRIPTION_MODEL_VERSION "2025-12-15"
azd env set AZURE_SEARCH_SKU "serverless"

$principalId = az ad signed-in-user show --query id --output tsv
azd env set AZURE_PRINCIPAL_ID $principalId
```

The Foundry account receives a globally unique generated name. Set `AZURE_FOUNDRY_RESOURCE_NAME` before `azd up` only when a specific unused account name is required.

### 10.2 Create a new Easy Auth secret

The Entra app registration is retained when the Azure resources are removed. Its application client ID is `f81bf6c1-4e63-4038-b048-3a62400922e5`. Create a short-lived secret immediately before redeployment:

```powershell
$clientId = "f81bf6c1-4e63-4038-b048-3a62400922e5"
$secretName = "realtime-demo-$(Get-Date -Format yyyyMMdd)"
$expires = (Get-Date).AddDays(30).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

$clientSecret = az ad app credential reset `
	--id $clientId `
	--append `
	--display-name $secretName `
	--end-date $expires `
	--query password `
	--output tsv

azd env set ENTRA_CLIENT_ID $clientId
azd env set ENTRA_CLIENT_SECRET $clientSecret
Remove-Variable clientSecret
```

The secret is stored in the Git-ignored local `.azure` directory. Do not add it to source control, documentation, or `.env.example`.

### 10.3 Recreate and deploy the application

```powershell
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"
azd up
```

`azd up` asks which resource group should contain the demo resources. Enter an existing or new resource group name, or press Enter to keep the value already stored in the selected azd environment. The Foundry resource and model deployments are created in that same resource group.

`azd up` provisions the infrastructure, builds and deploys the container image, and runs the post-provision hook that configures the Search index, data source, skillset, and indexer.

### 10.4 Update the Entra callback URL

A recreated Container Apps Environment can give the app a new hostname. Update the app registration after `azd up`:

```powershell
$fqdn = az containerapp show `
	--resource-group rg-ai103 `
	--name ca-realtime-realtime-dev `
	--query properties.configuration.ingress.fqdn `
	--output tsv

$callback = "https://$fqdn/.auth/login/aad/callback"

$currentUris = az ad app show `
	--id $clientId `
	--query web.redirectUris `
	--output json | ConvertFrom-Json

$redirectUris = @(
	$currentUris | Where-Object {
		$_ -notlike "https://ca-realtime-realtime-dev.*.azurecontainerapps.io/.auth/login/aad/callback"
	}
) + $callback

az ad app update `
	--id $clientId `
	--enable-id-token-issuance true `
	--web-redirect-uris ($redirectUris | Sort-Object -Unique)
```

Open the URL returned by `azd up` and verify that it redirects to Microsoft sign-in. The health endpoint remains available without authentication at `/api/health`.

## 11. Notes

- The app reads configuration from `.env` via `app/config.py`.
- The project uses Azure identity and managed access rather than embedded API keys.

## 12. Typical causes of issues

- Missing or incorrect Azure environment values in `.env`
- Not logged into Azure CLI
- Missing local data-plane permissions for Search and Storage
- Not activating the virtual environment before running commands

## 13. Quick restart sequence

```powershell
cd C:\Github\MyLearning
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```
