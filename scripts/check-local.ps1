$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Check-Command($Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Host "[OK] $Name -> $($cmd.Source)"
        return $true
    }
    Write-Host "[MISS] $Name not found"
    return $false
}

Write-Host "PulseBoard local environment check"
Write-Host ""

$ok = $true
$ok = (Check-Command "py") -and $ok
$ok = (Check-Command "node") -and $ok
$ok = (Check-Command "npm") -and $ok
$ok = (Check-Command "mysql") -and $ok

$mysqlServices = Get-Service | Where-Object { $_.Name -like "*mysql*" -or $_.DisplayName -like "*mysql*" }
if ($mysqlServices) {
    $mysqlServices | ForEach-Object { Write-Host "[OK] MySQL service $($_.Name): $($_.Status)" }
} else {
    Write-Host "[WARN] No MySQL Windows service found"
}

if (Test-Path (Join-Path $Root ".env")) {
    Write-Host "[OK] .env exists"
} else {
    Write-Host "[MISS] .env not found. Run .\scripts\setup-local.ps1"
    $ok = $false
}

if (Test-Path (Join-Path $Root "backend\.venv\Scripts\python.exe")) {
    Write-Host "[OK] backend virtualenv exists"
} else {
    Write-Host "[MISS] backend virtualenv not found. Run .\scripts\setup-local.ps1"
    $ok = $false
}

if (Test-Path (Join-Path $Root "frontend\node_modules")) {
    Write-Host "[OK] frontend node_modules exists"
} else {
    Write-Host "[MISS] frontend dependencies not installed. Run .\scripts\setup-local.ps1"
    $ok = $false
}

if (-not $ok) {
    exit 1
}

Write-Host ""
Write-Host "Local environment looks ready."

