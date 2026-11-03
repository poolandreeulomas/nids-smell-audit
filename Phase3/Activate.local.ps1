# Activate the .venv for Phase3 development (searches Phase3, repo root, or parent workspace).
# Usage: run this from PowerShell in the Phase3 folder: .\Activate.local.ps1

$candidates = @(
    (Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1"),
    (Join-Path (Resolve-Path "$PSScriptRoot\..") ".venv\Scripts\Activate.ps1"),
    (Join-Path (Resolve-Path "$PSScriptRoot\..\..") ".venv\Scripts\Activate.ps1")
)

$found = $false
foreach ($venvActivate in $candidates) {
    if (Test-Path $venvActivate) {
        & $venvActivate
        $found = $true
        break
    }
}

if (-not $found) {
    Write-Host "Virtual environment .venv not found in Phase3, repository root, or parent directory." -ForegroundColor Yellow
}
