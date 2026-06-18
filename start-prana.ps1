# PRANA local dev startup script
# Run this after Docker Desktop is running
# Usage: .\start-prana.ps1

$ErrorActionPreference = "Stop"
$root = "C:\Nilesh\claude-code"

Write-Host ""
Write-Host "=== PRANA Dev Stack Startup ===" -ForegroundColor Cyan
Write-Host ""

# 1. Start Docker services (YugabyteDB + Redis + db-init)
Write-Host "[1/4] Starting YugabyteDB + Redis..." -ForegroundColor Yellow
Set-Location $root
docker compose up -d yugabyte redis
Write-Host "      Waiting for DB to be healthy (up to 60s)..."
$retries = 0
do {
    Start-Sleep 5
    $retries++
    $health = docker inspect --format="{{.State.Health.Status}}" prana-yugabyte 2>$null
} while ($health -ne "healthy" -and $retries -lt 12)

if ($health -ne "healthy") {
    Write-Host "ERROR: YugabyteDB did not become healthy in time." -ForegroundColor Red
    exit 1
}
Write-Host "      YugabyteDB is healthy." -ForegroundColor Green

# 2. Run DB init (schema + seed) — only runs once, skips if already done
Write-Host "[2/4] Applying schema + seed data..." -ForegroundColor Yellow
docker compose up db-init
Write-Host "      DB init complete." -ForegroundColor Green

# 3. Install Python deps
Write-Host "[3/4] Installing Python dependencies..." -ForegroundColor Yellow
Set-Location "$root\prana-api"
pip install -r requirements.txt -q
Write-Host "      Python deps installed." -ForegroundColor Green

# 4. Start prana-api
Write-Host "[4/4] Starting prana-api on http://localhost:8000 ..." -ForegroundColor Yellow
Write-Host ""
Write-Host "=== Stack is ready ===" -ForegroundColor Green
Write-Host "  prana-api  ->  http://localhost:8000" -ForegroundColor Cyan
Write-Host "  API docs   ->  http://localhost:8000/docs  (debug mode)" -ForegroundColor Cyan
Write-Host "  YugabyteDB ->  localhost:5433" -ForegroundColor Cyan
Write-Host "  Redis      ->  localhost:6379" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the API server." -ForegroundColor Gray
Write-Host ""

Set-Location "$root\prana-api"
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
