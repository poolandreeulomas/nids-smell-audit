# Activate the top-level .venv for Phase3 development (if present).
# Usage: run this from PowerShell in the Phase3 folder or dot-source it from Activate.ps1
$projectRoot = Resolve-Path "$PSScriptRoot\..\.."
$venvActivate = Join-Path $projectRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    & $venvActivate
} else {
    Write-Host "Top-level .venv not found at $venvActivate" -ForegroundColor Yellow
}
