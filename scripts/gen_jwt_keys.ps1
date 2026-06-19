# Generates RS256 JWT keypair for local dev
# Run once: .\scripts\gen_jwt_keys.ps1

$keysDir = "$PSScriptRoot\..\keys"
New-Item -ItemType Directory -Force -Path $keysDir | Out-Null

# Check if openssl is available (comes with Git for Windows)
$openssl = (Get-Command openssl -ErrorAction SilentlyContinue)?.Source
if (-not $openssl) {
    # Try Git bundled openssl
    $openssl = "C:\Program Files\Git\usr\bin\openssl.exe"
    if (-not (Test-Path $openssl)) {
        Write-Error "openssl not found. Install Git for Windows or OpenSSL."
        exit 1
    }
}

Write-Host "Generating RS256 keypair in $keysDir ..."

& $openssl genrsa -out "$keysDir\jwt_private.pem" 2048 2>$null
& $openssl rsa -in "$keysDir\jwt_private.pem" -pubout -out "$keysDir\jwt_public.pem" 2>$null

Write-Host "Done."
Write-Host "  Private key: keys\jwt_private.pem"
Write-Host "  Public key:  keys\jwt_public.pem"
Write-Host ""
Write-Host "These are mounted into prana-api at /keys/ (read-only)."
Write-Host "Never commit the keys/ directory."
