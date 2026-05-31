# PAGE_TOKEN_SECRET Environment Variable Setup Script (Windows PowerShell)
# Usage: .\scripts\setup_env.ps1
# Sets the current session's PAGE_TOKEN_SECRET and outputs permanent configuration instructions

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Delta Sharing - PAGE_TOKEN_SECRET Setup"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Delta Sharing - PAGE_TOKEN_SECRET Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Generate cryptographically secure random key (32 bytes = 64 hex chars)
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$secret = -join ($bytes | ForEach-Object { $_.ToString("x2") })

Write-Host "[OK] Secure random key generated" -ForegroundColor Green
Write-Host ""

# Set environment variable for current session
$env:PAGE_TOKEN_SECRET = $secret

Write-Host "[Current Session] Environment variable set:" -ForegroundColor Yellow
Write-Host "  `$env:PAGE_TOKEN_SECRET = $secret"
Write-Host ""

# Permanent configuration instructions
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Permanent Configuration (choose one):" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[Option 1] User-level environment variable (Recommended):" -ForegroundColor Yellow
Write-Host "  Run the following command:" -ForegroundColor Gray
Write-Host "  [System.Environment]::SetEnvironmentVariable(" -ForegroundColor White -NoNewline
Write-Host "'PAGE_TOKEN_SECRET'" -ForegroundColor Magenta -NoNewline
Write-Host ", " -ForegroundColor White -NoNewline
Write-Host "'$secret'" -ForegroundColor Magenta -NoNewline
Write-Host ", 'User')" -ForegroundColor White
Write-Host ""

Write-Host "[Option 2] System-level environment variable (all users):" -ForegroundColor Yellow
Write-Host "  Run as Administrator in PowerShell:" -ForegroundColor Gray
Write-Host "  [System.Environment]::SetEnvironmentVariable(" -ForegroundColor White -NoNewline
Write-Host "'PAGE_TOKEN_SECRET'" -ForegroundColor Magenta -NoNewline
Write-Host ", " -ForegroundColor White -NoNewline
Write-Host "'$secret'" -ForegroundColor Magenta -NoNewline
Write-Host ", 'Machine')" -ForegroundColor White
Write-Host ""

Write-Host "[Option 3] .env.local file (project-level):" -ForegroundColor Yellow
# Resolve script directory regardless of how the script is invoked
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$envFile = Join-Path $scriptDir "..\server\.env.local" | Resolve-Path -ErrorAction SilentlyContinue
if (-not $envFile) {
    $envFile = Join-Path $scriptDir "..\server\.env.local"
}
$exists = Test-Path $envFile
if (-not $exists) {
    $parentDir = Split-Path $envFile -Parent
    if (-not (Test-Path $parentDir)) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }
    Set-Content -Path $envFile -Value "PAGE_TOKEN_SECRET=$secret" -Encoding UTF8
    Write-Host "  Created: $envFile" -ForegroundColor Green
} else {
    $content = Get-Content $envFile -Raw
    if ($content -match "PAGE_TOKEN_SECRET=") {
        $newContent = $content -replace "PAGE_TOKEN_SECRET=.*", "PAGE_TOKEN_SECRET=$secret"
        Set-Content -Path $envFile -Value $newContent -Encoding UTF8 -NoNewline
    } else {
        $lastChar = (Get-Content $envFile -Tail 1 -Raw)
        if ($lastChar -and (-not $lastChar.EndsWith("`n"))) {
            Add-Content -Path $envFile -Value "" -Encoding UTF8 -NoNewline
            Add-Content -Path $envFile -Value "" -Encoding UTF8
        }
        Add-Content -Path $envFile -Value "PAGE_TOKEN_SECRET=$secret" -Encoding UTF8
    }
    Write-Host "  Updated: $envFile" -ForegroundColor Green
}
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Verification:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Current value: $env:PAGE_TOKEN_SECRET"
Write-Host ""

Write-Host "[DONE] Setup complete! Restart terminal for permanent changes." -ForegroundColor Green
