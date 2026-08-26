Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$currentResourceGroup = $env:AZURE_RESOURCE_GROUP
$prompt = if ([string]::IsNullOrWhiteSpace($currentResourceGroup)) {
    "Azure resource group (existing or new)"
} else {
    "Azure resource group (press Enter to keep '$currentResourceGroup')"
}

$selectedResourceGroup = (Read-Host $prompt).Trim()
if ([string]::IsNullOrWhiteSpace($selectedResourceGroup)) {
    $selectedResourceGroup = $currentResourceGroup
}

if ([string]::IsNullOrWhiteSpace($selectedResourceGroup)) {
    throw "A resource group name is required."
}

if ($selectedResourceGroup.Length -gt 90 -or
    $selectedResourceGroup -notmatch '^[A-Za-z0-9._()\-]+$' -or
    $selectedResourceGroup.EndsWith('.')) {
    throw "Invalid resource group name '$selectedResourceGroup'. Use 1-90 letters, numbers, periods, underscores, hyphens, or parentheses, and do not end with a period."
}

azd env set AZURE_RESOURCE_GROUP $selectedResourceGroup
if ($LASTEXITCODE -ne 0) {
    throw "Could not save AZURE_RESOURCE_GROUP in the current azd environment."
}

Write-Host "Azure resources will be provisioned in resource group '$selectedResourceGroup'."
