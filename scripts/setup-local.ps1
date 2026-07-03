param(
    [string]$DbHost = "127.0.0.1",
    [int]$DbPort = 3306,
    [string]$DbUser = "root",
    [string]$DbPassword = "",
    [string]$Database = "pulseboard",
    [string]$SourceUrl = "http://100.64.0.14:8080/api/latest",
    [string]$NodeExporters = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"
$VenvPip = Join-Path $Backend ".venv\Scripts\pip.exe"
$VenvAlembic = Join-Path $Backend ".venv\Scripts\alembic.exe"

if (-not $DbPassword) {
    $secure = Read-Host "MySQL password for user '$DbUser'" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $DbPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

$escapedPassword = [uri]::EscapeDataString($DbPassword)
$databaseUrl = "mysql+pymysql://${DbUser}:${escapedPassword}@${DbHost}:${DbPort}/${Database}?charset=utf8mb4"

@"
PULSEBOARD_DATABASE_URL=$databaseUrl
PULSEBOARD_SOURCE_URL=$SourceUrl
PULSEBOARD_COLLECTION_INTERVAL_SECONDS=15
PULSEBOARD_RETENTION_DAYS=30
PULSEBOARD_FAILURE_DEGRADED_THRESHOLD=3
PULSEBOARD_FAILURE_UNREACHABLE_THRESHOLD=12
PULSEBOARD_COLLECTOR_ENABLED=true
PULSEBOARD_LAB_TIMEZONE=Asia/Shanghai
PULSEBOARD_NODE_EXPORTERS=$NodeExporters
PULSEBOARD_NODE_EXPORTER_INTERVAL_SECONDS=30
PULSEBOARD_TRAFFIC_QUOTA_NODE=vpn-gateway
PULSEBOARD_TRAFFIC_QUOTA_TOTAL_GB=250
PULSEBOARD_TRAFFIC_QUOTA_INITIAL_USED_GB=71.23
PULSEBOARD_TRAFFIC_QUOTA_RESET_DAY=18
"@ | Set-Content -Encoding ASCII (Join-Path $Root ".env")

$mysql = Get-Command mysql -ErrorAction SilentlyContinue
if (-not $mysql) {
    throw "mysql.exe not found in PATH. Add MySQL bin directory to PATH, then rerun this script."
}

$mysqlArgs = @("--protocol=tcp", "-h", $DbHost, "-P", "$DbPort", "-u", $DbUser)
if ($DbPassword) {
    $mysqlArgs += "-p$DbPassword"
}
$mysqlArgs += "-e"
$mysqlArgs += "CREATE DATABASE IF NOT EXISTS ``$Database`` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
& $mysql.Source @mysqlArgs

if (-not (Test-Path $VenvPython)) {
    py -3 -m venv (Join-Path $Backend ".venv")
}

& $VenvPython -m pip install --upgrade pip
& $VenvPip install -r (Join-Path $Backend "requirements.txt")

Push-Location $Backend
try {
    & $VenvAlembic upgrade head
} finally {
    Pop-Location
}

Push-Location $Frontend
try {
    if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
        npm install
    }
} finally {
    Pop-Location
}

Write-Host "Local setup complete."
Write-Host "Backend:  .\scripts\run-backend.ps1"
Write-Host "Frontend: .\scripts\run-frontend.ps1"
