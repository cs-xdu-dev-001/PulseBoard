$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path (Join-Path $Root ".env"))) {
    throw ".env not found. Run .\scripts\setup-local.ps1 first."
}

Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$Root\scripts\run-backend.ps1`""
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$Root\scripts\run-frontend.ps1`""

Write-Host "Started backend and frontend terminals."
Write-Host "Open http://127.0.0.1:5173"

