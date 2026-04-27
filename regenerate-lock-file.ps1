#!/usr/bin/env pwsh
# Regenerate package-lock.json with correct dependencies

Write-Host "=== Regenerating package-lock.json ===" -ForegroundColor Cyan
Write-Host ""

# Navigate to frontend directory
Push-Location "bunkerm-source/frontend"

try {
    # Remove old lock file to force regeneration
    if (Test-Path "package-lock.json") {
        Write-Host "Removing old package-lock.json..." -ForegroundColor Yellow
        Remove-Item "package-lock.json" -Force
    }

    # Clear npm cache
    Write-Host "Clearing npm cache..." -ForegroundColor Yellow
    npm cache clean --force 2>&1 | Out-Null

    # Install with correct versions (will generate new package-lock.json)
    Write-Host "Installing dependencies with npm install..." -ForegroundColor Yellow
    Write-Host "(This may take a minute...)" -ForegroundColor Gray
    npm install --legacy-peer-deps --prefer-offline

    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: npm install failed!" -ForegroundColor Red
        exit 1
    }

    Write-Host ""
    Write-Host "=== Package-lock.json regenerated successfully ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "Verifying next-auth version..." -ForegroundColor Cyan
    npm ls next-auth
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✓ SUCCESS: next-auth correctly installed" -ForegroundColor Green
    }
}
finally {
    Pop-Location
}
