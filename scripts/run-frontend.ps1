$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root "frontend"

Push-Location $Frontend
try {
    if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
        npm install
    }
    npm run dev
} finally {
    Pop-Location
}

