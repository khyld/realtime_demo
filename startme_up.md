# Start guide for the project

This file is a quick reference for starting the application locally and for understanding the project setup.

## 1. Open a terminal in the project folder

```powershell
cd C:\Github\MyLearning
```

## 2. Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

If the virtual environment does not exist yet:

```powershell
cd C:\Github\MyLearning
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## 3. Install dependencies

```powershell
pip install -e ".[dev]"
```

## 4. Create the local environment file

```powershell
Copy-Item .env.example .env
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

## 10. Notes

- The app reads configuration from `.env` via `app/config.py`.
- `learning.py` is an older learning script and is not part of the web app.
- The project uses Azure identity and managed access rather than embedded API keys.

## 11. Typical causes of issues

- Missing or incorrect Azure environment values in `.env`
- Not logged into Azure CLI
- Missing local data-plane permissions for Search and Storage
- Not activating the virtual environment before running commands

## 12. Quick restart sequence

```powershell
cd C:\Github\MyLearning
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```
