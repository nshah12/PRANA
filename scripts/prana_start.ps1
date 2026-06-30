# PRANA Local Dev — Full Stack Startup
# Boots all services in dependency order with health checks.
# Run manually: .\scripts\prana_start.ps1
# Or auto-run on login via Task Scheduler (see scripts\register_startup.ps1)

param(
    [switch]$NoApi,      # skip starting uvicorn (if you want to start it manually)
    [switch]$NoPortal,   # skip starting vite dev server
    [switch]$Quiet       # suppress banner
)

$ROOT = Split-Path $PSScriptRoot -Parent
$LOG  = "$ROOT\scripts\prana_start.log"

function Log($msg) {
    $ts = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $LOG -Value $line
}

function Wait-Healthy($name, $timeoutSec = 120) {
    Log "Waiting for $name to be healthy..."
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        $status = docker inspect --format "{{.State.Health.Status}}" $name 2>$null
        if ($status -eq "healthy") { Log "$name is healthy."; return $true }
        $running = docker inspect --format "{{.State.Status}}" $name 2>$null
        if ($running -ne "running") { Log "ERROR: $name stopped unexpectedly (status=$running)."; return $false }
        Start-Sleep -Seconds 3
    }
    Log "TIMEOUT: $name did not become healthy in ${timeoutSec}s."
    return $false
}

function Wait-Running($name, $timeoutSec = 60) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        $s = docker inspect --format "{{.State.Status}}" $name 2>$null
        if ($s -eq "running") { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Start-Container($name) {
    $status = docker inspect --format "{{.State.Status}}" $name 2>$null
    if ($status -eq "running") { Log "$name already running — skipping."; return }
    Log "Starting $name..."
    docker start $name | Out-Null
}

function Ensure-KafkaTopic($topic, $partitions = 12) {
    $exists = docker exec prana-kafka kafka-topics --list --bootstrap-server localhost:9092 2>$null | Select-String -SimpleMatch $topic
    if (-not $exists) {
        Log "Creating Kafka topic: $topic"
        docker exec prana-kafka kafka-topics --create --topic $topic --partitions $partitions --replication-factor 1 --bootstrap-server localhost:9092 2>$null | Out-Null
    }
}

# ── Banner ───────────────────────────────────────────────────────────────────
if (-not $Quiet) {
    Write-Host ""
    Write-Host "  ██████╗ ██████╗  █████╗ ███╗   ██╗ █████╗ " -ForegroundColor Cyan
    Write-Host "  ██╔══██╗██╔══██╗██╔══██╗████╗  ██║██╔══██╗" -ForegroundColor Cyan
    Write-Host "  ██████╔╝██████╔╝███████║██╔██╗ ██║███████║" -ForegroundColor Cyan
    Write-Host "  ██╔═══╝ ██╔══██╗██╔══██║██║╚██╗██║██╔══██║" -ForegroundColor Cyan
    Write-Host "  ██║     ██║  ██║██║  ██║██║ ╚████║██║  ██║" -ForegroundColor Cyan
    Write-Host "  ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝" -ForegroundColor Cyan
    Write-Host "  Local Dev Stack Startup" -ForegroundColor White
    Write-Host ""
}

Log "=== PRANA startup begin ==="

# ── Stage 1: Independent fast services ───────────────────────────────────────
Log "--- Stage 1: Redis, MinIO, Qdrant ---"
Start-Container "prana-redis"
Start-Container "prana-minio"
Start-Container "prana-qdrant"

# ── Stage 2: Kafka ────────────────────────────────────────────────────────────
Log "--- Stage 2: Kafka ---"
Start-Container "prana-kafka"
if (-not (Wait-Healthy "prana-kafka" 90)) { Log "FATAL: Kafka failed. Aborting."; exit 1 }

# ── Stage 3: Ensure all 21 Kafka topics exist ────────────────────────────────
Log "--- Stage 3: Kafka topics ---"
$topics = @(
    "prana.ingest.events", "prana.pipeline.events", "prana.vault.events",
    "prana.employee.events", "prana.tenant.events", "prana.oa_users.events",
    "prana.compliance.events", "prana.auth.events", "prana.security.events",
    "prana.statutory.events", "prana.analytics.events", "prana.integrations.events",
    "prana.platform.events", "prana.audit.events", "prana.cache.events",
    "prana.notifications.email", "prana.notifications.sms", "prana.notifications.push",
    "prana.notifications.whatsapp", "prana.notifications.portal_bell",
    "prana.notifications"
)
foreach ($t in $topics) { Ensure-KafkaTopic $t }
Log "All 21 Kafka topics present."

# ── Stage 4: Temporal Postgres ────────────────────────────────────────────────
Log "--- Stage 4: Temporal Postgres ---"
Start-Container "prana-temporal-postgres"
if (-not (Wait-Healthy "prana-temporal-postgres" 60)) { Log "WARN: temporal-postgres health timeout — continuing." }

# ── Stage 5: Temporal ─────────────────────────────────────────────────────────
Log "--- Stage 5: Temporal ---"
Start-Container "prana-temporal"
if (-not (Wait-Healthy "prana-temporal" 90)) { Log "WARN: Temporal health timeout — continuing." }

# ── Stage 6: YugabyteDB (needs most memory — start last among DBs) ─────────────
Log "--- Stage 6: YugabyteDB ---"
Start-Container "prana-yugabyte"
if (-not (Wait-Healthy "prana-yugabyte" 180)) { Log "FATAL: YugabyteDB failed to start. Aborting."; exit 1 }

# ── Stage 7: DB init (runs migrations + seeds — only if not yet done) ─────────
Log "--- Stage 7: DB init check ---"
$initStatus = docker inspect --format "{{.State.Status}}" prana-db-init 2>$null
if ($initStatus -ne "running") {
    # Check if schema already applied (idempotent guard)
    $tableCount = docker exec prana-yugabyte ysqlsh -U yugabyte -d prana -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>$null
    $tc = ($tableCount -replace '\s','')
    if ([int]$tc -gt 10) {
        Log "Schema already applied ($tc tables). Skipping db-init."
    } else {
        Log "Running db-init (migrations + seed)..."
        docker start prana-db-init | Out-Null
        # Wait for it to finish
        $deadline = (Get-Date).AddSeconds(120)
        while ((Get-Date) -lt $deadline) {
            $s = docker inspect --format "{{.State.Status}}" prana-db-init 2>$null
            if ($s -ne "running") { break }
            Start-Sleep -Seconds 3
        }
        Log "DB init complete."
    }
}

# ── Stage 8: prana-api ────────────────────────────────────────────────────────
if (-not $NoApi) {
    Log "--- Stage 8: prana-api (uvicorn) ---"
    $apiPid = netstat -ano 2>$null | Select-String ":8000.*LISTENING"
    if ($apiPid) {
        Log "prana-api already running on :8000 — skipping."
    } else {
        Log "Starting prana-api..."
        Start-Process powershell -ArgumentList "-NoExit", "-Command", `
            "cd '$ROOT\prana-api'; `$env:PYTHONUNBUFFERED='1'; python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload 2>&1 | Tee-Object -FilePath '$ROOT\prana-api\uvicorn.out.tmp'" `
            -WindowStyle Normal
        # Wait for port 8000
        $deadline = (Get-Date).AddSeconds(30)
        while ((Get-Date) -lt $deadline) {
            $up = netstat -ano 2>$null | Select-String ":8000.*LISTENING"
            if ($up) { Log "prana-api is up on :8000."; break }
            Start-Sleep -Seconds 2
        }
    }
}

# ── Stage 9: prana-portal (vite) ─────────────────────────────────────────────
if (-not $NoPortal) {
    Log "--- Stage 9: prana-portal (vite) ---"
    $portalUp = netstat -ano 2>$null | Select-String ":5173.*LISTENING"
    if ($portalUp) {
        Log "prana-portal already running on :5173 — skipping."
    } else {
        Log "Starting prana-portal..."
        Start-Process powershell -ArgumentList "-NoExit", "-Command", `
            "cd '$ROOT\prana-portal'; npm run dev" `
            -WindowStyle Normal
        Log "prana-portal starting (check :5173 in a moment)."
    }
}

# ── Done ─────────────────────────────────────────────────────────────────────
Log "=== PRANA stack is up ==="
Write-Host ""
Write-Host "  Portal (employer):  http://localhost:5173/org/login" -ForegroundColor Green
Write-Host "  Portal (admin):     http://localhost:5173/admin/login" -ForegroundColor Green
Write-Host "  API docs:           http://localhost:8000/docs" -ForegroundColor Green
Write-Host "  YugabyteDB UI:      http://localhost:15433" -ForegroundColor Green
Write-Host "  Temporal UI:        http://localhost:8233" -ForegroundColor Green
Write-Host "  MinIO console:      http://localhost:9001" -ForegroundColor Green
Write-Host ""
Write-Host "  Password for all dev accounts: Prana@Admin0124" -ForegroundColor Yellow
Write-Host ""
