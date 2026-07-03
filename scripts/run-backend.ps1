$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"
$VenvAlembic = Join-Path $Backend ".venv\Scripts\alembic.exe"
$VenvUvicorn = Join-Path $Backend ".venv\Scripts\uvicorn.exe"

if (-not (Test-Path (Join-Path $Root ".env"))) {
    throw ".env not found. Run .\scripts\setup-local.ps1 first."
}

if (-not (Test-Path $VenvPython)) {
    throw "Backend virtualenv not found. Run .\scripts\setup-local.ps1 first."
}

Push-Location $Backend
try {
    & $VenvAlembic upgrade head
    & $VenvUvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
} finally {
    Pop-Location
}

