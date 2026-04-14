# ==========================================
# BunkerM Extended - Deployment Script for Windows
# ==========================================
# This script automates the deployment process on Windows

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet('setup', 'start', 'stop', 'restart', 'status', 'logs', 'clean', 'build', 'build-mosquitto', 'start-bunkerm', 'stop-bunkerm', 'patch-frontend', 'patch-backend', 'reload-mosquitto', 'test', 'smoke')]
    [string]$Action = 'setup',
    
    [Parameter(Mandatory=$false)]
    [switch]$WithTools,

    # Subconjunto de tests a ejecutar: 'all' (defecto), 'smart-anomaly', 'backend'
    [Parameter(Mandatory=$false)]
    [ValidateSet('all', 'smart-anomaly', 'backend')]
    [string]$TestPath = 'all',
    
    [Parameter(Mandatory=$false)]
    [switch]$Follow
)

$ErrorActionPreference = "Stop"

# Motores de contenedor (se asignan en Get-RuntimeEngines al inicio)
$script:CE = "docker"    # Container Engine: docker o podman
$script:CCE = "docker-compose"  # Compose Engine: docker-compose, docker compose, o podman compose

# Colors for output
function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }
function Write-Error { Write-Host $args -ForegroundColor Red }

# Detecta el motor de contenedores disponible: Podman (prioritario) o Docker
function Get-RuntimeEngines {
    $podmanFound = Get-Command podman -ErrorAction SilentlyContinue
    $dockerFound = Get-Command docker -ErrorAction SilentlyContinue

    if ($podmanFound) {
        $script:CE = "podman"
        Write-Info "Motor de contenedores: Podman"
        # Intentar podman compose (nativo Podman 4+ o proveedor externo)
        # Usar ErrorActionPreference local para que mensajes informativos de stderr no paren la ejecucion
        $savedPref = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        podman compose version 2>&1 | Out-Null
        $podmanComposeExitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedPref
        if ($podmanComposeExitCode -eq 0) {
            $script:CCE = "podman compose"
            Write-Info "Motor de compose: podman compose (disponible)"
        } else {
            # Intentar podman-compose como paquete pip
            $podmanComposePkg = Get-Command podman-compose -ErrorAction SilentlyContinue
            if ($podmanComposePkg) {
                $script:CCE = "podman-compose"
                Write-Info "Motor de compose: podman-compose (paquete externo)"
            } else {
                Write-Warning "[WARNING] No se encontro compose para Podman."
                Write-Warning "Instala con: pip install podman-compose"
                Write-Warning "O actualiza Podman a 4+ para compose nativo."
                exit 1
            }
        }
    } elseif ($dockerFound) {
        $script:CE = "docker"
        Write-Info "Motor de contenedores: Docker"
        # Intentar docker compose v2 nativo
        $savedPref = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        docker compose version 2>&1 | Out-Null
        $dockerComposeExitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedPref
        if ($dockerComposeExitCode -eq 0) {
            $script:CCE = "docker compose"
            Write-Info "Motor de compose: docker compose (v2 nativo)"
        } else {
            $dcV1 = Get-Command docker-compose -ErrorAction SilentlyContinue
            if ($dcV1) {
                $script:CCE = "docker-compose"
                Write-Info "Motor de compose: docker-compose (v1 standalone)"
            } else {
                Write-Warning "[WARNING] Docker Compose no encontrado."
                Write-Warning "Instala Docker Compose v2 o ejecuta: pip install docker-compose"
                exit 1
            }
        }
    } else {
        Write-Host "[ERROR] No se encontro Docker ni Podman." -ForegroundColor Red
        Write-Host "Instala Podman (https://podman.io) o Docker Desktop." -ForegroundColor Red
        exit 1
    }

    Write-Host ""
}

function Show-Banner {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Magenta
    Write-Host "   BunkerM Extended - Deployment Tool    " -ForegroundColor Magenta
    Write-Host "==========================================" -ForegroundColor Magenta
    Write-Host ""
}

function Test-Prerequisites {
    Write-Info "Verificando prerequisitos..."

    # Detectar motor de contenedores (Podman o Docker)
    Get-RuntimeEngines

    # Check Python
    try {
        $pythonVersion = python --version
        Write-Success "[OK] Python: $pythonVersion"
    } catch {
        Write-Warning "[WARNING] Python no encontrado. Algunos scripts pueden no funcionar."
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
        "data/logs",
        "data/backups",
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
    
    # Verificar codigo fuente de BunkerM
    Write-Host ""
    if (-not (Test-Path "bunkerm-source")) {
        Write-Warning "El directorio 'bunkerm-source' no existe."
        Write-Info "Es necesario para construir la imagen de BunkerM."
        $cloneNow = Read-Host "Clonar repositorio BunkerM ahora? (y/N)"
        if ($cloneNow -eq 'y' -or $cloneNow -eq 'Y') {
            Write-Info "Clonando BunkerM desde GitHub..."
            git clone https://github.com/bunkeriot/BunkerM bunkerm-source
            if ($LASTEXITCODE -eq 0) {
                Write-Success "[OK] BunkerM clonado en bunkerm-source/"
            } else {
                Write-Warning "Error al clonar. Hazlo manualmente:"
                Write-Host "  git clone https://github.com/bunkeriot/BunkerM bunkerm-source" -ForegroundColor Yellow
            }
        } else {
            Write-Warning "Recuerda clonar BunkerM antes de hacer build:"
            Write-Host "  git clone https://github.com/bunkeriot/BunkerM bunkerm-source" -ForegroundColor Yellow
        }
    } else {
        Write-Success "[OK] bunkerm-source/ encontrado"
    }

    # Verificar archivos requeridos para el build del contenedor
    Write-Host ""
    Write-Info "Verificando archivos necesarios para el build..."

    $requiredFiles = @(
        @{ Path = "bunkerm-source/backend/mosquitto/dynsec/dynamic-security.json"; Desc = "Bootstrap ACL de Mosquitto" },
        @{ Path = "bunkerm-source/backend/app/config/.env";                        Desc = "Env del servicio config" }
    )
    $buildOk = $true
    foreach ($f in $requiredFiles) {
        if (-not (Test-Path $f.Path)) {
            Write-Warning "Falta: $($f.Path) ($($f.Desc))"
            $buildOk = $false
        } else {
            Write-Success "[OK] $($f.Path)"
        }
    }
    if (-not $buildOk) {
        Write-Host ""
        Write-Warning "Uno o mas archivos requeridos estan ausentes."
        Write-Host "  Esto normalmente indica un problema con el .gitignore del repo fuente." -ForegroundColor Yellow
        Write-Host "  Ejecuta: git status bunkerm-source/ para diagnosticar." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Success "Setup completado correctamente!"
    Write-Host ""
    Write-Info "Proximos pasos:"
    Write-Host "  1. Revisa .env.dev y actualiza configuracion SMTP/Twilio si es necesario"
    Write-Host "  2. Ejecuta: .\deploy.ps1 -Action build"
    Write-Host "  3. Ejecuta: .\deploy.ps1 -Action start"
    Write-Host ""
}

function Invoke-Start {
    Write-Info "Starting services..."
    Write-Host ""

    if (-not (Test-Path ".env.dev")) {
        Write-Error ".env.dev not found. Run setup first: .\deploy.ps1 -Action setup"
        exit 1
    }

    # E2 -- Validar variables de entorno requeridas antes de levantar contenedores
    Write-Info "Validating environment variables..."
    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $validateOutput = & python scripts/validate-env.py 2>&1
    $validateExit = $LASTEXITCODE
    $ErrorActionPreference = $savedPref
    if ($validateExit -ne 0) {
        Write-Host "[ERROR] Environment validation failed:" -ForegroundColor Red
        $validateOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        Write-Host ""
        Write-Host "  Run '.\deploy.ps1 -Action setup' to regenerate secrets." -ForegroundColor Yellow
        exit 1
    }
    Write-Success $validateOutput
    Write-Host ""

    # Si bunkerm-source existe pero no tiene .env, crear uno vacio para que compose no falle
    if (Test-Path "bunkerm-source") {
        if (-not (Test-Path "bunkerm-source\.env")) {
            Write-Warning "bunkerm-source/.env no encontrado. Creando archivo vacio para evitar error de compose..."
            New-Item -ItemType File -Path "bunkerm-source\.env" -Force | Out-Null
            Write-Info "Si BunkerM requiere variables propias, edita bunkerm-source/.env"
        }
    } else {
        Write-Warning "bunkerm-source/ no existe. El servicio 'bunkerm' no se construira."
        Write-Warning "Para incluirlo ejecuta: git clone https://github.com/bunkeriot/BunkerM bunkerm-source"
        Write-Host ""
    }

    # Limpiar contenedores huerfanos con el mismo nombre (ej. iniciados manualmente)
    $orphanContainers = @('bunkerm-platform')
    foreach ($cname in $orphanContainers) {
        $exists = & $script:CE ps -a --format "{{.Names}}" 2>&1 | Select-String "^${cname}$"
        if ($exists) {
            Write-Warning "Contenedor huerfano encontrado: $cname. Eliminando antes de compose..."
            $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
            & $script:CE stop $cname 2>&1 | Out-Null
            & $script:CE rm $cname 2>&1 | Out-Null
            $ErrorActionPreference = $savedPref
            Write-Success "[OK] $cname eliminado"
        }
    }

    $composeCmd = "$script:CCE --env-file .env.dev -f docker-compose.dev.yml"

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

    # Auto-apply local source changes so container always runs the latest code.
    # patch-backend and patch-frontend copy source files into the running container
    # and restart the affected processes. Without this step, a stop+start would lose
    # any changes applied via a previous patch (because compose down destroys the container).
    Write-Host ""
    Write-Info "Applying local source patches to the running container..."
    Invoke-PatchBackend
    Invoke-PatchFrontend

    # A3 — Smoke automatico: verificar que el stack responde tras los patches
    Write-Host ""
    Write-Info "Ejecutando smoke test del stack (A3)..."
    Start-Sleep -Seconds 8   # margen para que Next.js termine de arrancar
    $smokeFailures = Invoke-Smoke
    if ($smokeFailures -gt 0) {
        Write-Warning "[AVISO] El smoke test detecto $smokeFailures fallo(s). El stack sigue corriendo para debug manual."
        Write-Host "  Logs: .\deploy.ps1 -Action logs" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Info "Service URLs:"
    Write-Host "  - Web UI:    http://localhost:2000" -ForegroundColor Cyan
    Write-Host "  - MQTT:      localhost:1900" -ForegroundColor Cyan
    
    if ($WithTools) {
        Write-Host "  - pgAdmin:   http://localhost:5050" -ForegroundColor Cyan
        Write-Host "  - PostgreSQL: localhost:5432" -ForegroundColor Cyan
    }
    
    Write-Host ""
    Write-Info "Run health check: .\deploy.ps1 -Action status"
    Write-Host ""
}

function Invoke-Stop {
    Write-Info "Stopping services..."
    Write-Host ""
    
    $composeCmd = "$script:CCE --env-file .env.dev -f docker-compose.dev.yml"

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

    # Contenedores activos
    Write-Host "Contenedores:" -ForegroundColor Yellow
    $containers = & $script:CE ps --format json 2>$null | ConvertFrom-Json -ErrorAction SilentlyContinue
    if ($containers) {
        # Podman devuelve array de objetos; filtrar los de bunkerm
        $containers | Where-Object { $_.Names -match 'bunkerm|water-plant' } |
            Format-Table @{L='Nombre';E={$_.Names}}, @{L='Estado';E={$_.State}}, @{L='Puertos';E={$_.Ports}} -AutoSize
    } else {
        # Fallback: salida de texto plana
        Invoke-Expression "$script:CE ps" | Select-String 'bunkerm|water-plant|NAME'
    }

    Write-Host ""
    Write-Host "Health Checks:" -ForegroundColor Yellow
    Write-Host ""

    # BunkerM broker MQTT standalone (puerto 1900)
    Write-Host -NoNewline "  Mosquitto MQTT standalone (localhost:1900)... "
    $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    try {
        $tcpClient.Connect('localhost', 1900)
        Write-Success "[OK] puerto 1900 accesible"
        $tcpClient.Close()
    } catch {
        Write-Host "[NO DISPONIBLE]" -ForegroundColor Red
    } finally {
        $ErrorActionPreference = $savedPref
    }

    # Nginx / Web UI → BunkerM en puerto 2000 (redirige a /login, acepta 200 y 3xx)
    Write-Host -NoNewline "  BunkerM Web UI (http://localhost:2000)... "
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:2000" -UseBasicParsing -TimeoutSec 5 -MaximumRedirection 5 -ErrorAction Stop
        Write-Success "[OK] HTTP $($resp.StatusCode)"
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -ge 300 -and $code -lt 400) {
            Write-Success "[OK] HTTP $code (redirect al login)"
        } else {
            Write-Host "[NO DISPONIBLE]" -ForegroundColor Red
        }
    }

    # BunkerM Auth API (confirma que el backend esta respondiendo)
    Write-Host -NoNewline "  BunkerM API (/api/auth/me)... "
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:2000/api/auth/me" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        Write-Success "[OK] HTTP $($resp.StatusCode)"
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -in @(401, 403)) {
            Write-Success "[OK] HTTP $($_.Exception.Response.StatusCode.value__) (no autenticado, backend activo)"
        } else {
            Write-Host "[NO DISPONIBLE]" -ForegroundColor Red
        }
    }

    Write-Host ""
}

function Invoke-Logs {
    Write-Info "Showing logs..."
    Write-Host ""
    
    $composeCmd = "$script:CCE --env-file .env.dev -f docker-compose.dev.yml logs"
    
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
        Invoke-Expression "$script:CCE --env-file .env.dev -f docker-compose.dev.yml --profile tools down -v"
        
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

function Invoke-Build {
    Write-Info "Construyendo imagen de BunkerM..."
    Write-Host ""

    if (-not (Test-Path "bunkerm-source")) {
        Write-Host "[ERROR] bunkerm-source/ no encontrado." -ForegroundColor Red
        Write-Host "  git clone https://github.com/bunkeriot/BunkerM bunkerm-source" -ForegroundColor Yellow
        exit 1
    }

    # Construir Mosquitto primero (más rápido; BunkerM depende de él en runtime)
    Invoke-BuildMosquitto

    # Convertir CRLF a LF en scripts .sh antes de construir
    Write-Info "Normalizando line endings en scripts shell..."
    Get-ChildItem bunkerm-source -Recurse -Filter "*.sh" | ForEach-Object {
        $content = [System.IO.File]::ReadAllText($_.FullName)
        if ($content -match "`r`n") {
            $fixed = $content -replace "`r`n", "`n"
            [System.IO.File]::WriteAllText($_.FullName, $fixed, [System.Text.UTF8Encoding]::new($false))
            Write-Info "  Normalizado: $($_.Name)"
        }
    }

    Write-Info "Construyendo imagen (puede tardar 5-15 minutos la primera vez)..."
    $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
    & $script:CE build `
        -t bunkermtest-bunkerm:latest `
        -f bunkerm-source/Dockerfile.next `
        bunkerm-source
    $buildExit = $LASTEXITCODE
    $ErrorActionPreference = $savedPref

    if ($buildExit -eq 0) {
        Write-Success "[OK] Imagen BunkerM construida correctamente: bunkermtest-bunkerm:latest"
        Write-Info "Ahora ejecuta: .\deploy.ps1 -Action start"
    } else {
        Write-Host "[ERROR] Fallo en el build. Revisa los logs de arriba." -ForegroundColor Red
        exit 1
    }
    Write-Host ""
}

function Invoke-BuildMosquitto {
    Write-Info "Construyendo imagen de Mosquitto standalone..."
    Write-Host ""

    if (-not (Test-Path "Dockerfile.mosquitto")) {
        Write-Host "[ERROR] Dockerfile.mosquitto no encontrado en el directorio raiz." -ForegroundColor Red
        exit 1
    }

    # Normalizar line endings en el entrypoint script
    $entrypoint = Join-Path $PSScriptRoot "mosquitto-entrypoint.sh"
    if (Test-Path $entrypoint) {
        $content = [System.IO.File]::ReadAllText($entrypoint)
        if ($content -match "`r`n") {
            $fixed = $content -replace "`r`n", "`n"
            [System.IO.File]::WriteAllText($entrypoint, $fixed, [System.Text.UTF8Encoding]::new($false))
            Write-Info "  Normalizado: mosquitto-entrypoint.sh"
        }
    }

    & $script:CE build `
        -t bunkermtest-mosquitto:latest `
        -f Dockerfile.mosquitto `
        .
    $buildExit = $LASTEXITCODE

    if ($buildExit -eq 0) {
        Write-Success "[OK] Imagen Mosquitto construida: bunkermtest-mosquitto:latest"
    } else {
        Write-Host "[ERROR] Fallo en el build de Mosquitto." -ForegroundColor Red
        exit 1
    }
    Write-Host ""
}

function Invoke-Smoke {
    # Verifica que los endpoints criticos del stack esten respondiendo correctamente.
    # Retorna el numero de checks fallidos (0 = todo OK).
    # Se usa como accion standalone ('smoke') o llamado automaticamente desde Invoke-Start (A3).
    Write-Info "Smoke test -- verificando stack en ejecucion..."
    Write-Host ""

    # Leer API key del archivo de entorno
    $apiKey = ""
    if (Test-Path ".env.dev") {
        $line = Get-Content ".env.dev" | Select-String "^API_KEY=" | Select-Object -First 1
        if ($line) { $apiKey = "$line" -replace "^API_KEY=", "" }
    }
    if (-not $apiKey) {
        Write-Warning "  API_KEY no encontrada en .env.dev -- check autenticado sera omitido"
    }

    $passed = 0
    $failed = 0
    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'

    # ── 1. Puerto MQTT 1900 ──────────────────────────────────────────────────
    Write-Host -NoNewline "  [1/5] MQTT puerto 1900 .......................... "
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    try {
        $tcpClient.Connect('localhost', 1900)
        Write-Host "OK" -ForegroundColor Green
        $passed++
        $tcpClient.Close()
    } catch {
        Write-Host "FAIL" -ForegroundColor Red
        $failed++
    }

    # ── 2. Nginx / Web UI ────────────────────────────────────────────────────
    Write-Host -NoNewline "  [2/5] Web UI http://localhost:2000 .............. "
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:2000" -UseBasicParsing -TimeoutSec 5 -MaximumRedirection 5 -ErrorAction Stop
        Write-Host "OK HTTP $($r.StatusCode)" -ForegroundColor Green
        $passed++
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -ge 200 -and $code -lt 400) {
            Write-Host "OK HTTP $code" -ForegroundColor Green; $passed++
        } else {
            Write-Host "FAIL HTTP $code" -ForegroundColor Red; $failed++
        }
    }

    # ── 3. Next.js / Auth ────────────────────────────────────────────────────
    Write-Host -NoNewline "  [3/5] Auth API /api/auth/me ..................... "
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:2000/api/auth/me" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        Write-Host "OK HTTP $($r.StatusCode)" -ForegroundColor Green
        $passed++
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -in @(401, 403)) {
            Write-Host "OK HTTP $code (sin sesion activa)" -ForegroundColor Green; $passed++
        } else {
            Write-Host "FAIL HTTP $code" -ForegroundColor Red; $failed++
        }
    }

    # ── 4. Backend health: ruta publica legacy o ruta autenticada actual ─────
    Write-Host -NoNewline "  [4/5] Backend monitor health ..................... "
    $healthOk = $false
    $healthNote = ""
    foreach ($attempt in 1..3) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:2000/api/monitor/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            Write-Host "OK HTTP $($r.StatusCode) (/api/monitor/health)" -ForegroundColor Green
            $passed++
            $healthOk = $true
            break
        } catch {
            $code = $_.Exception.Response.StatusCode.value__
            if ($code) {
                $healthNote = "HTTP $code en /api/monitor/health"
            } elseif ($_.Exception.Message) {
                $healthNote = "$($_.Exception.Message) en /api/monitor/health"
            }

            if ($attempt -lt 3) {
                Start-Sleep -Seconds 2
            }
        }
    }
    if (-not $healthOk) {
        if ($apiKey) {
            foreach ($attempt in 1..3) {
                try {
                    $r = Invoke-WebRequest -Uri "http://localhost:2000/api/monitor/stats/health" -UseBasicParsing -TimeoutSec 5 -Headers @{ 'X-API-Key' = $apiKey } -ErrorAction Stop
                    Write-Host "OK HTTP $($r.StatusCode) (/api/monitor/stats/health con API key)" -ForegroundColor Green
                    $passed++
                    $healthOk = $true
                    break
                } catch {
                    $code = $_.Exception.Response.StatusCode.value__
                    if ($code) {
                        $healthNote = "$healthNote; HTTP $code en /api/monitor/stats/health"
                    } elseif ($_.Exception.Message) {
                        $healthNote = "$healthNote; $($_.Exception.Message) en /api/monitor/stats/health"
                    }

                    if ($attempt -lt 3) {
                        Start-Sleep -Seconds 2
                    }
                }
            }
        }
    }
    if (-not $healthOk) {
        Write-Host "FAIL $healthNote" -ForegroundColor Red
        $failed++
    }

    # ── 5. Backend autenticado: /api/dynsec/clients ──────────────────────────
    if ($apiKey) {
        Write-Host -NoNewline "  [5/5] Backend /api/dynsec/clients (API key) ..... "
        $dynsecOk = $false
        $dynsecError = ""
        foreach ($attempt in 1..5) {
            try {
                $r = Invoke-WebRequest -Uri "http://localhost:2000/api/dynsec/clients?page=1&limit=1" -UseBasicParsing -TimeoutSec 10 -Headers @{ 'X-API-Key' = $apiKey } -ErrorAction Stop
                Write-Host "OK HTTP $($r.StatusCode)" -ForegroundColor Green
                $passed++
                $dynsecOk = $true
                break
            } catch {
                $code = $_.Exception.Response.StatusCode.value__
                if ($code) {
                    $dynsecError = "HTTP $code"
                } elseif ($_.Exception.Message) {
                    $dynsecError = $_.Exception.Message
                } else {
                    $dynsecError = "error no especificado"
                }

                if ($attempt -lt 5) {
                    Start-Sleep -Seconds 3
                }
            }
        }

        if (-not $dynsecOk) {
            Write-Host "FAIL $dynsecError" -ForegroundColor Red
            $failed++
        }
    } else {
        Write-Host "  [5/5] Backend /api/dynsec/clients ................ OMITIDO (sin API key)" -ForegroundColor Yellow
    }

    $ErrorActionPreference = $savedPref

    Write-Host ""
    $total = $passed + $failed
    if ($failed -eq 0) {
        Write-Host "  Resultado: $passed/$total OK" -ForegroundColor Green
        Write-Success "[SMOKE OK] Stack operativo."
    } else {
        Write-Host "  Resultado: $passed/$total OK, $failed FAIL(s)" -ForegroundColor Red
        Write-Host "[SMOKE FAIL] Ejecuta '.\deploy.ps1 -Action logs' para diagnosticar." -ForegroundColor Red
    }
    Write-Host ""

    return $failed
}

function Invoke-Test {
    # Ejecuta los tests de pytest dentro del contenedor bunkerm-platform en ejecucion.
    # Requiere que el contenedor este corriendo: .\.deploy.ps1 -Action start
    Write-Info "Ejecutando tests dentro del contenedor bunkerm-platform..."
    Write-Host ""

    $containerRunning = & $script:CE ps --format "{{.Names}}" 2>&1 | Select-String "bunkerm-platform"
    if (-not $containerRunning) {
        Write-Host "[ERROR] El contenedor bunkerm-platform no esta corriendo. Ejecuta: .\deploy.ps1 -Action start" -ForegroundColor Red
        exit 1
    }

    # Determinar la ruta de tests segun el parametro -TestPath
    switch ($TestPath) {
        'smart-anomaly' {
            $testDir = '/app/smart-anomaly/tests'
            Write-Info "Corriendo tests de smart-anomaly: $testDir"
        }
        'backend' {
            $testDir = '/app/tests'
            Write-Info "Corriendo tests del backend unificado: $testDir"
        }
        default {
            # Correr ambas suites
            Write-Info "Corriendo todas las suites de tests..."
            $testDir = $null
        }
    }

    $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
    if ($testDir) {
        & $script:CE exec bunkerm-platform pytest $testDir -v
    } else {
        # Primero backend unificado (si el directorio existe), luego smart-anomaly
        $backendTestsExist = & $script:CE exec bunkerm-platform sh -c "test -d /app/tests && echo yes || echo no" 2>&1
        if ($backendTestsExist -match 'yes') {
            Write-Info "Suite: backend unificado (/app/tests)"
            & $script:CE exec bunkerm-platform pytest /app/tests -v
        } else {
            Write-Warning "/app/tests no existe aun. Implementar Fase T del QUALITY_PLAN.md"
        }
        Write-Host ""
        Write-Info "Suite: smart-anomaly (/app/smart-anomaly/tests)"
        & $script:CE exec bunkerm-platform pytest /app/smart-anomaly/tests -v
    }
    $testExit = $LASTEXITCODE
    $ErrorActionPreference = $savedPref

    Write-Host ""
    if ($testExit -eq 0) {
        Write-Success "[OK] Todos los tests pasaron."
    } else {
        Write-Host "[FAIL] Algunos tests fallaron. Revisa la salida de arriba." -ForegroundColor Red
    }
    Write-Host ""
    exit $testExit
}

function Invoke-ReloadMosquitto {
    Write-Info "Enviando señal de recarga a Mosquitto standalone..."
    $mqContainer = & $script:CE ps --format "{{.Names}}" 2>&1 | Select-String "bunkerm-mosquitto"
    if (-not $mqContainer) {
        Write-Host "[ERROR] El contenedor bunkerm-mosquitto no esta corriendo." -ForegroundColor Red
        exit 1
    }
    # Write the reload trigger file directly in the mosquitto container
    & $script:CE exec bunkerm-mosquitto sh -c "touch /var/lib/mosquitto/.reload"
    Write-Success "[OK] Señal enviada. Mosquitto recargara su configuracion en ~2 segundos."
    Write-Host ""
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
    $networkExists = Invoke-Expression "$script:CE network ls" | Select-String "bunkerm-network"
    if (-not $networkExists) {
        Write-Info "Creando red bunkerm-network..."
        & $script:CE network create bunkerm-network
        Write-Success "[OK] Red creada"
    }

    # Iniciar mosquitto standalone primero (BunkerM depende de el)
    Write-Info "Iniciando Mosquitto standalone..."
    Invoke-Expression "$script:CCE --env-file .env.dev -f docker-compose.dev.yml up -d mosquitto"
    
    Write-Info "Esperando a que Mosquitto este listo (15 segundos)..."
    Start-Sleep -Seconds 15

    # Iniciar solo el servicio bunkerm (BunkerM usa SQLite internamente, postgres no es necesario)
    Write-Info "Iniciando BunkerM..."
    Invoke-Expression "$script:CCE --env-file .env.dev -f docker-compose.dev.yml up -d bunkerm"
    
    Write-Host ""
    Write-Success "[OK] BunkerM iniciado!"
    Write-Host ""
    Write-Info "Esperando a que BunkerM esté listo (60 segundos)..."
    Start-Sleep -Seconds 60
    
    Write-Host ""
    Write-Info "URLs de acceso:"
    Write-Host "  - Web UI:    http://localhost:2000" -ForegroundColor Cyan
    Write-Host "  - MQTT:      localhost:1900" -ForegroundColor Cyan
    Write-Host ""
    Write-Info "Verificar estado: .\deploy.ps1 -Action status"
    Write-Info "Ver logs: $script:CE logs bunkerm-platform -f"
    Write-Host ""
}

function Invoke-StopBunkerM {
    Write-Info "Deteniendo BunkerM platform..."
    Write-Host ""
    
    Invoke-Expression "$script:CCE --env-file .env.dev -f docker-compose.dev.yml stop bunkerm mosquitto"

    Write-Host ""
    Write-Success "[OK] BunkerM y Mosquitto detenidos!"
    Write-Host ""
}

function Invoke-PatchFrontend {
    Write-Info "Hot-patch del frontend Next.js..."
    Write-Host ""

    $frontendPath = Join-Path $PSScriptRoot "bunkerm-source\frontend"
    if (-not (Test-Path $frontendPath)) {
        Write-Host "[ERROR] bunkerm-source/frontend no encontrado." -ForegroundColor Red
        exit 1
    }

    # Verificar si el contenedor esta corriendo
    $containerRunning = & $script:CE ps --format "{{.Names}}" 2>&1 | Select-String "bunkerm-platform"
    if (-not $containerRunning) {
        Write-Host "[ERROR] El contenedor bunkerm-platform no esta corriendo. Ejecuta: .\deploy.ps1 -Action start" -ForegroundColor Red
        exit 1
    }

    Write-Info "Compilando frontend con Node.js..."
    # Nota: se monta el directorio frontend en el contenedor node para el build
    & $script:CE run --rm `
        -v "${frontendPath}:/frontend" `
        -w /frontend `
        -e AUTH_SECRET=build-placeholder `
        -e NEXT_TELEMETRY_DISABLED=1 `
        node:20-alpine `
        sh -c "npm run build 2>&1 | tail -15"

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Fallo el build del frontend." -ForegroundColor Red
        exit 1
    }

    Write-Info "Desplegando al contenedor..."

    # Copiar standalone (servidor Next.js)
    # Se usa la ruta con '\.' para copiar el CONTENIDO del directorio, no el directorio mismo
    $standalonePath = Join-Path $frontendPath ".next\standalone"
    & $script:CE cp "${standalonePath}/." "bunkerm-platform:/nextjs/"

    # Copiar estaticos: IMPORTANTE usar '\.' al final para copiar el CONTENIDO
    # sin esto, podman crea un directorio anidado static/static/ en vez de sobreescribir
    $staticPath = Join-Path $frontendPath ".next\static"
    & $script:CE cp "${staticPath}/." "bunkerm-platform:/nextjs/.next/static/"

    # Limpiar cualquier directorio 'static' anidado si quedó de deploys anteriores
    $nestedStatic = & $script:CE exec bunkerm-platform sh -c "test -d /nextjs/.next/static/static && echo exists || echo none" 2>&1
    if ($nestedStatic -match "exists") {
        Write-Info "Limpiando directorio static anidado de deploys anteriores..."
        & $script:CE exec bunkerm-platform sh -c "cp -rf /nextjs/.next/static/static/. /nextjs/.next/static/ && rm -rf /nextjs/.next/static/static"
    }

    # Reiniciar el servidor Next.js (supervisord lo relanzara automaticamente)
    Write-Info "Reiniciando servidor Next.js..."
    $nextPid = & $script:CE exec bunkerm-platform sh -c "ps aux | grep next-server | grep -v grep | sed 's/^ *//' | cut -d' ' -f1" 2>&1 | Select-Object -First 1
    if ($nextPid) {
        & $script:CE exec bunkerm-platform sh -c "kill $nextPid"
        Start-Sleep -Seconds 3
    }

    Write-Success "[OK] Frontend actualizado correctamente!"
    Write-Host "  Recarga la pagina del navegador (Ctrl+Shift+R) para ver los cambios." -ForegroundColor Cyan
    Write-Host ""
}

function Invoke-PatchBackend {
    Write-Info "Hot-patch de servicios Python del backend..."
    Write-Host ""

    $backendPath = Join-Path $PSScriptRoot "bunkerm-source\backend\app"
    if (-not (Test-Path $backendPath)) {
        Write-Host "[ERROR] bunkerm-source/backend/app no encontrado." -ForegroundColor Red
        exit 1
    }

    $containerRunning = & $script:CE ps --format "{{.Names}}" 2>&1 | Select-String "bunkerm-platform"
    if (-not $containerRunning) {
        Write-Host "[ERROR] El contenedor bunkerm-platform no esta corriendo." -ForegroundColor Red
        exit 1
    }

    # Patch único: copiar todo el directorio app/ de una vez y recargar el proceso uvicorn unificado
    $serviceNames = @('dynsec', 'monitor', 'clientlogs', 'config', 'smart-anomaly')
    foreach ($name in $serviceNames) {
        Write-Info "  Copiando $name..."
    }
    & $script:CE cp "${backendPath}/." "bunkerm-platform:/app/"

    # Recargar el proceso uvicorn unificado (puerto 9001)
    $svcPid = & $script:CE exec bunkerm-platform sh -c "ps aux | grep 'uvicorn main:app.*9001' | grep -v grep | awk '{print `$1}'" 2>&1 | Select-Object -First 1
    if ($svcPid -match '\d+') {
        & $script:CE exec bunkerm-platform sh -c "kill -HUP $svcPid" 2>&1 | Out-Null
        Write-Info "    Proceso $svcPid recargado (SIGHUP)"
    }

    # D2 -- Verificar que uvicorn sigue vivo 3 segundos despues del SIGHUP
    Start-Sleep -Seconds 3
    $uvicornAlive = & $script:CE exec bunkerm-platform sh -c "ps aux | grep 'uvicorn main:app.*9001' | grep -v grep" 2>&1
    if (-not $uvicornAlive) {
        Write-Host "" 
        Write-Host "[AVISO] uvicorn (puerto 9001) no aparece en ps aux tras el SIGHUP." -ForegroundColor Yellow
        Write-Host "  Ultimas 30 lineas de log de uvicorn:" -ForegroundColor Yellow
        & $script:CE exec bunkerm-platform sh -c "tail -30 /var/log/supervisor/bunkerm-api.out.log 2>/dev/null || echo '(log no disponible)'" 2>&1 |
            ForEach-Object { Write-Host "    $_" -ForegroundColor DarkYellow }
        Write-Host ""
        Write-Host "  El backend puede no estar respondiendo. Comprueba con: .\deploy.ps1 -Action smoke" -ForegroundColor Yellow
    } else {
        Write-Success "[OK] Backend actualizado. Los servicios afectados se han recargado."
    }
    Write-Host ""
}

# Main execution
Show-Banner
Test-Prerequisites

switch ($Action) {
    'setup'            { Invoke-Setup }
    'start'            { Invoke-Start }
    'stop'             { Invoke-Stop }
    'restart'          { Invoke-Restart }
    'status'           { Invoke-Status }
    'logs'             { Invoke-Logs }
    'clean'            { Invoke-Clean }
    'build'            { Invoke-Build }
    'build-mosquitto'  { Invoke-BuildMosquitto }
    'start-bunkerm'    { Invoke-StartBunkerM }
    'stop-bunkerm'     { Invoke-StopBunkerM }
    'patch-frontend'   { Invoke-PatchFrontend }
    'patch-backend'    { Invoke-PatchBackend }
    'reload-mosquitto' { Invoke-ReloadMosquitto }
    'test'             { Invoke-Test }
    'smoke'            {
        $smokeResult = Invoke-Smoke
        if ($smokeResult -gt 0) { exit 1 }
    }
    default {
        Write-Error "Unknown action: $Action"
        Write-Info "Acciones disponibles: setup, start, stop, restart, status, logs, clean, build, build-mosquitto, start-bunkerm, stop-bunkerm, patch-frontend, patch-backend, reload-mosquitto, test, smoke"
    }
}

Write-Host ""
