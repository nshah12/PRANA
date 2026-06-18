# Post-edit hook for prana-api files (PowerShell — Windows)
# Reminds to verify process state after editing API code

param($FilePath)

if ($FilePath -like "*prana-api*") {
    Write-Host ""
    Write-Host "API FILE EDITED: $FilePath" -ForegroundColor Yellow
    Write-Host "Before testing, verify:" -ForegroundColor Cyan
    Write-Host "  netstat -ano | findstr ':8000'  <- exactly 1 PID?" -ForegroundColor White
    Write-Host "  If 2+ PIDs: Stop-Process all, wait, restart" -ForegroundColor White
    Write-Host ""
}
