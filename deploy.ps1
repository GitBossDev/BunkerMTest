# ==========================================
# BunkerM Extended - Deployment Script for Windows
# ==========================================
# This script automates the deployment process on Windows

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet('setup', 'start', 'stop', 'restart', 'status', 'logs', 'clean', 'build', 'start-bunkerm', 'stop-bunkerm', 'patch-frontend', 'patch-backend')]
    [string]$Action = 'setup',
    
    [Parameter(Mandatory=$false)]
    [switch]$WithTools,
    
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

    Write-Host ""
    Write-Info "Service URLs:"
    Write-Host "  - Web UI:    http://localhost:2000" -ForegroundColor Cyan
    Write-Host "  - MQTT:      localhost:1901" -ForegroundColor Cyan
    
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

    # BunkerM broker MQTT interno (puerto 1901)
    Write-Host -NoNewline "  BunkerM MQTT (localhost:1901)... "
    $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    try {
        $tcpClient.Connect('localhost', 1901)
        Write-Success "[OK] puerto 1901 accesible"
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

    # Leer API_KEY del .env.dev para el build arg
    $apiKey = (Get-Content .env.dev | Select-String "^API_KEY=" | Select-Object -First 1) -replace "^API_KEY=", ""
    if (-not $apiKey) { $apiKey = "default_api_key_replace_in_production" }

    Write-Info "Construyendo imagen (puede tardar 5-15 minutos la primera vez)..."
    $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
    & $script:CE build `
        --build-arg "NEXT_PUBLIC_API_KEY=$apiKey" `
        -t bunkermtest-bunkerm:latest `
        -f bunkerm-source/Dockerfile.next `
        bunkerm-source
    $buildExit = $LASTEXITCODE
    $ErrorActionPreference = $savedPref

    if ($buildExit -eq 0) {
        Write-Success "[OK] Imagen construida correctamente: bunkermtest-bunkerm:latest"
        Write-Info "Ahora ejecuta: .\deploy.ps1 -Action start"
    } else {
        Write-Host "[ERROR] Fallo en el build. Revisa los logs de arriba." -ForegroundColor Red
        exit 1
    }
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
    Write-Host "  - MQTT:      localhost:1901" -ForegroundColor Cyan
    Write-Host "  - Dynsec API: http://localhost:1000" -ForegroundColor Cyan
    Write-Host "  - Monitor API: http://localhost:1001" -ForegroundColor Cyan
    Write-Host "  - Config API: http://localhost:1005" -ForegroundColor Cyan
    Write-Host ""
    Write-Info "Verificar estado: .\deploy.ps1 -Action status"
    Write-Info "Ver logs: $script:CE logs bunkerm-platform -f"
    Write-Host ""
}

function Invoke-StopBunkerM {
    Write-Info "Deteniendo BunkerM platform..."
    Write-Host ""
    
    Invoke-Expression "$script:CCE --env-file .env.dev -f docker-compose.dev.yml stop bunkerm"

    Write-Host ""
    Write-Success "[OK] BunkerM detenido!"
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

    # Map: local subfolder -> container path + process pattern to kill/reload
    $services = @(
        @{ Name = 'dynsec';         Src = "$backendPath\dynsec";         Dst = '/app/dynsec';         Pattern = 'uvicorn main:app.*1000' },
        @{ Name = 'monitor';        Src = "$backendPath\monitor";        Dst = '/app/monitor';        Pattern = 'uvicorn main:app.*1001' },
        @{ Name = 'clientlogs';     Src = "$backendPath\clientlogs";     Dst = '/app/clientlogs';     Pattern = '/app/clientlogs/main.py' },
        @{ Name = 'config';         Src = "$backendPath\config";         Dst = '/app/config';         Pattern = 'uvicorn main:app.*1005' },
        @{ Name = 'smart-anomaly';  Src = "$backendPath\smart-anomaly";  Dst = '/app/smart-anomaly';  Pattern = 'uvicorn app.main:app.*8100' }
    )

    foreach ($svc in $services) {
        if (Test-Path $svc.Src) {
            Write-Info "  Copiando $($svc.Name)..."
            & $script:CE cp "$($svc.Src)/." "bunkerm-platform:$($svc.Dst)/"
            # Find PID and kill so supervisord restarts with new code
            $svcPid = & $script:CE exec bunkerm-platform sh -c "ps aux | grep '$($svc.Pattern)' | grep -v grep | awk '{print `$1}'" 2>&1 | Select-Object -First 1
            if ($svcPid -match '\d+') {
                & $script:CE exec bunkerm-platform sh -c "kill -HUP $svcPid" 2>&1 | Out-Null
                Write-Info "    Proceso $svcPid reiniciado (SIGHUP)"
            }
        }
    }

    Start-Sleep -Seconds 2
    Write-Success "[OK] Backend actualizado. Los servicios afectados se han recargado."
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
    'build' { Invoke-Build }
    'start-bunkerm' { Invoke-StartBunkerM }
    'stop-bunkerm'  { Invoke-StopBunkerM }
    'patch-frontend'{ Invoke-PatchFrontend }
    'patch-backend' { Invoke-PatchBackend }
    'stop-bunkerm' { Invoke-StopBunkerM }
    default {
        Write-Error "Unknown action: $Action"
        Write-Info "Acciones disponibles: setup, start, stop, restart, status, logs, clean, build, start-bunkerm, stop-bunkerm"
    }
}

Write-Host ""
