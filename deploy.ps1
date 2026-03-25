# ==========================================
# BunkerM Extended - Deployment Script for Windows
# ==========================================
# This script automates the deployment process on Windows

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet('setup', 'start', 'stop', 'restart', 'status', 'logs', 'clean', 'start-bunkerm', 'stop-bunkerm')]
    [string]$Action = 'setup',
    
    [Parameter(Mandatory=$false)]
    [switch]$WithTools,
    
    [Parameter(Mandatory=$false)]
    [switch]$Follow
)

$ErrorActionPreference = "Stop"

# Colors for output
function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }
function Write-Error { Write-Host $args -ForegroundColor Red }

function Show-Banner {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Magenta
    Write-Host "   BunkerM Extended - Deployment Tool    " -ForegroundColor Magenta
    Write-Host "==========================================" -ForegroundColor Magenta
    Write-Host ""
}

function Test-Prerequisites {
    Write-Info "Checking prerequisites..."
    
    # Check Docker
    try {
        $dockerVersion = docker --version
        Write-Success "[OK] Docker found: $dockerVersion"
    } catch {
        Write-Error "[ERROR] Docker not found. Please install Docker Desktop."
        exit 1
    }
    
    # Check Docker Compose
    try {
        $composeVersion = docker-compose --version
        Write-Success "[OK] Docker Compose found: $composeVersion"
    } catch {
        Write-Error "[ERROR] Docker Compose not found. Please install Docker Compose."
        exit 1
    }
    
    # Check Python
    try {
        $pythonVersion = python --version
        Write-Success "[OK] Python found: $pythonVersion"
    } catch {
        Write-Warning "[WARNING] Python not found. Scripts may not work."
    }
    
    Write-Host ""
}

function Invoke-Setup {
    Write-Info "Starting setup process..."
    Write-Host ""
    
    # Check if .env.dev exists
    if (Test-Path ".env.dev") {
        Write-Warning ".env.dev already exists."
        $overwrite = Read-Host "Do you want to regenerate it? (y/N)"
        if ($overwrite -eq 'y' -or $overwrite -eq 'Y') {
            Write-Info "Generating new .env.dev..."
            python scripts/generate-secrets.py
            Write-Success "[OK] New .env.dev generated"
        }
    } else {
        Write-Info "Generating .env.dev..."
        python scripts/generate-secrets.py
        Write-Success "[OK] .env.dev generated"
    }
    
    Write-Host ""
    Write-Info "Creating data directories..."
    
    $directories = @(
        "data/mosquitto/data",
        "data/mosquitto/log",
        "data/postgres",
        "data/logs",
        "data/backups",
        "data/pgadmin",
        "data/bunkerm/nextjs",
        "data/bunkerm/mosquitto",
        "data/bunkerm/logs/api",
        "data/bunkerm/logs/mosquitto",
        "data/bunkerm/logs/nginx"
    )
    
    foreach ($dir in $directories) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
            Write-Success "[OK] Created: $dir"
        } else {
            Write-Info "  Already exists: $dir"
        }
    }
    
    Write-Host ""
    Write-Success "Setup completed successfully!"
    Write-Host ""
    Write-Info "Next steps:"
    Write-Host "  1. Review .env.dev and update SMTP/Twilio settings if needed"
    Write-Host "  2. Run: .\deploy.ps1 -Action start"
    Write-Host ""
}

function Invoke-Start {
    Write-Info "Starting services..."
    Write-Host ""
    
    if (-not (Test-Path ".env.dev")) {
        Write-Error ".env.dev not found. Run setup first: .\deploy.ps1 -Action setup"
        exit 1
    }
    
    $composeCmd = "docker-compose --env-file .env.dev -f docker-compose.dev.yml"
    
    if ($WithTools) {
        Write-Info "Starting with tools profile (includes pgAdmin)..."
        $composeCmd += " --profile tools"
    }
    
    $composeCmd += " up -d"
    
    Invoke-Expression $composeCmd
    
    Write-Host ""
    Write-Success "[OK] Services started successfully!"
    Write-Host ""
    Write-Info "Waiting for services to be ready (30 seconds)..."
    Start-Sleep -Seconds 30
    
    Write-Host ""
    Write-Info "Service URLs:"
    Write-Host "  - Web UI:    http://localhost:2000" -ForegroundColor Cyan
    Write-Host "  - MQTT:      localhost:1900" -ForegroundColor Cyan
    Write-Host "  - PostgreSQL: localhost:5432" -ForegroundColor Cyan
    
    if ($WithTools) {
        Write-Host "  - pgAdmin:   http://localhost:5050" -ForegroundColor Cyan
    }
    
    Write-Host ""
    Write-Info "Run health check: .\deploy.ps1 -Action status"
    Write-Host ""
}

function Invoke-Stop {
    Write-Info "Stopping services..."
    Write-Host ""
    
    $composeCmd = "docker-compose --env-file .env.dev -f docker-compose.dev.yml"
    
    if ($WithTools) {
        $composeCmd += " --profile tools"
    }
    
    $composeCmd += " down"
    
    Invoke-Expression $composeCmd
    
    Write-Host ""
    Write-Success "[OK] Services stopped successfully!"
    Write-Host ""
}

function Invoke-Restart {
    Write-Info "Restarting services..."
    Invoke-Stop
    Start-Sleep -Seconds 5
    Invoke-Start
}

function Invoke-Status {
    Write-Info "Checking service status..."
    Write-Host ""
    
    # Check containers
    Write-Host "Docker Containers:" -ForegroundColor Yellow
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | Select-String "bunkerm"
    
    Write-Host ""
    
    # Try to run health check script
    if (Test-Path "scripts/check-health.sh") {
        Write-Info "Running health check..."
        if (Get-Command bash -ErrorAction SilentlyContinue) {
            bash scripts/check-health.sh
        } else {
            Write-Warning "bash not found. Manual health check:"
            Write-Host ""
            
            # Manual checks
            Write-Info "Nginx Health Check..."
            try {
                $response = Invoke-WebRequest -Uri "http://localhost:2000/health" -UseBasicParsing -TimeoutSec 5
                if ($response.StatusCode -eq 200) {
                    Write-Success "[OK] Nginx is responding"
                }
            } catch {
                Write-Error "[ERROR] Nginx is not responding"
            }
            
            Write-Host ""
            Write-Info "PostgreSQL Health Check..."
            try {
                docker exec bunkerm-postgres pg_isready -U bunkerm -d bunkerm_db 2>$null
                if ($LASTEXITCODE -eq 0) {
                    Write-Success "[OK] PostgreSQL is ready"
                } else {
                    Write-Error "[ERROR] PostgreSQL is not ready"
                }
            } catch {
                Write-Error "[ERROR] PostgreSQL container not found"
            }
        }
    }
    
    Write-Host ""
}

function Invoke-Logs {
    Write-Info "Showing logs..."
    Write-Host ""
    
    $composeCmd = "docker-compose --env-file .env.dev -f docker-compose.dev.yml logs"
    
    if ($Follow) {
        $composeCmd += " -f"
        Write-Info "Following logs (Ctrl+C to exit)..."
    } else {
        $composeCmd += " --tail=100"
    }
    
    Invoke-Expression $composeCmd
}

function Invoke-Clean {
    Write-Warning "This will remove all containers, volumes, and data!"
    $confirm = Read-Host "Are you sure? Type 'yes' to confirm"
    
    if ($confirm -eq 'yes') {
        Write-Info "Cleaning up..."
        Write-Host ""
        
        # Stop services
        docker-compose --env-file .env.dev -f docker-compose.dev.yml --profile tools down -v
        
        # Remove data directories
        Write-Info "Removing data directories..."
        $dataDir = "data"
        if (Test-Path $dataDir) {
            Remove-Item -Recurse -Force "$dataDir/*" -ErrorAction SilentlyContinue
            Write-Success "[OK] Data directories cleaned"
        }
        
        # Remove .env.dev
        if (Test-Path ".env.dev") {
            $removeEnv = Read-Host "Remove .env.dev as well? (y/N)"
            if ($removeEnv -eq 'y' -or $removeEnv -eq 'Y') {
                Remove-Item ".env.dev"
                Write-Success "[OK] .env.dev removed"
            }
        }
        
        Write-Host ""
        Write-Success "[OK] Cleanup completed!"
        Write-Info "Run setup again: .\deploy.ps1 -Action setup"
        Write-Host ""
    } else {
        Write-Info "Cleanup cancelled."
    }
}

function Invoke-StartBunkerM {
    Write-Info "Starting BunkerM platform..."
    Write-Host ""
    
    if (-not (Test-Path ".env.dev")) {
        Write-Error ".env.dev not found. Run setup first: .\deploy.ps1 -Action setup"
        exit 1
    }
    
    # Verificar que la red exista
    Write-Info "Verificando red Docker..."
    $networkExists = docker network ls | Select-String "bunkerm-network"
    if (-not $networkExists) {
        Write-Info "Creando red bunkerm-network..."
        docker network create bunkerm-network
        Write-Success "[OK] Red creada"
    }
    
    # Iniciar solo el servicio bunkerm y sus dependencias
    Write-Info "Iniciando PostgreSQL y BunkerM..."
    docker-compose --env-file .env.dev -f docker-compose.dev.yml up -d postgres bunkerm
    
    Write-Host ""
    Write-Success "[OK] BunkerM iniciado!"
    Write-Host ""
    Write-Info "Esperando a que BunkerM esté listo (60 segundos)..."
    Start-Sleep -Seconds 60
    
    Write-Host ""
    Write-Info "URLs de acceso:"
    Write-Host "  - Web UI:    http://localhost:3000" -ForegroundColor Cyan
    Write-Host "  - MQTT:      localhost:1901" -ForegroundColor Cyan
    Write-Host "  - Dynsec API: http://localhost:1000" -ForegroundColor Cyan
    Write-Host "  - Monitor API: http://localhost:1001" -ForegroundColor Cyan
    Write-Host "  - Config API: http://localhost:1005" -ForegroundColor Cyan
    Write-Host ""
    Write-Info "Verificar estado: .\deploy.ps1 -Action status"
    Write-Info "Ver logs: docker logs bunkerm-platform -f"
    Write-Host ""
}

function Invoke-StopBunkerM {
    Write-Info "Deteniendo BunkerM platform..."
    Write-Host ""
    
    docker-compose --env-file .env.dev -f docker-compose.dev.yml stop bunkerm
    
    Write-Host ""
    Write-Success "[OK] BunkerM detenido!"
    Write-Host ""
}

# Main execution
Show-Banner
Test-Prerequisites

switch ($Action) {
    'setup' { Invoke-Setup }
    'start' { Invoke-Start }
    'stop' { Invoke-Stop }
    'restart' { Invoke-Restart }
    'status' { Invoke-Status }
    'logs' { Invoke-Logs }
    'clean' { Invoke-Clean }
    'start-bunkerm' { Invoke-StartBunkerM }
    'stop-bunkerm' { Invoke-StopBunkerM }
    default { 
        Write-Error "Unknown action: $Action"
        Write-Info "Available actions: setup, start, stop, restart, status, logs, clean, start-bunkerm, stop-bunkerm"
    }
}

Write-Host ""
