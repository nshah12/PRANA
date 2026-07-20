# PRANA Pre-Deploy Gate
# Runs ALL enforcement checks. Nothing ships until this passes.
# Usage: powershell -File scripts/pre_deploy_check.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
$failed = $false

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PRANA PRE-DEPLOY GATE" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# [1/3] Rule enforcement
Write-Host ""
Write-Host "[1/3] Rule Enforcement Scanner..." -ForegroundColor Yellow
python "$ROOT\scripts\enforce_rules.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED: Rule violations found." -ForegroundColor Red
    $failed = $true
} else {
    Write-Host "PASSED" -ForegroundColor Green
}

# [2/3] API compatibility
Write-Host ""
Write-Host "[2/3] API Compatibility Check..." -ForegroundColor Yellow
python "$ROOT\scripts\check_api_compat.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED: API compatibility issues found." -ForegroundColor Red
    $failed = $true
} else {
    Write-Host "PASSED" -ForegroundColor Green
}

# [3/3] Test suite
Write-Host ""
Write-Host "[3/3] Running test suites..." -ForegroundColor Yellow
$MONOREPO = Split-Path -Parent $ROOT
$testPaths = @(
    "$ROOT\tests",
    "$MONOREPO\prana-ai\tests",
    "$MONOREPO\prana-ask\tests"
)
$existingPaths = $testPaths | Where-Object { Test-Path $_ }
if ($existingPaths.Count -eq 0) {
    Write-Host "WARNING: No test directories found." -ForegroundColor Yellow
} else {
    python -m pytest $existingPaths -v --tb=short -q 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: Test suite has failures." -ForegroundColor Red
        $failed = $true
    } else {
        Write-Host "PASSED" -ForegroundColor Green
    }
}

# Result
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($failed) {
    Write-Host "  DEPLOYMENT BLOCKED -- fix errors above" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Cyan
    exit 1
} else {
    Write-Host "  ALL CHECKS PASSED -- safe to deploy" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    exit 0
}
