<#
.SYNOPSIS
    Script de gestión del simulador de invernadero.

.DESCRIPTION
    Controla el MQTT stresser de greenhouse-simulator para Broker Health Manager.
    Permite construirlo, ejecutarlo, inspeccionar logs y limpiar recursos.

.PARAMETER Action
    Acción a ejecutar: start, stop, restart, status, logs, anomalies, build, clean

.EXAMPLE
    .\simulator.ps1 start
    .\simulator.ps1 logs
    .\simulator.ps1 build
#>

param(
    [Parameter(Position=0)]
    [ValidateSet('start', 'stop', 'restart', 'status', 'logs', 'anomalies', 'build', 'clean')]
    [string]$Action = 'status',
    
    [Parameter(Position=1)]
    [string]$SubAction = '',
    
    [switch]$Follow
)

# Configuración
$ErrorActionPreference = 'Continue'
$ComposeFile = 'docker-compose.simulator.yml'
$EnvFile = '.env.dev'
$ServiceName = 'greenhouse-simulator'

# Motores de contenedor (se asignan en Get-RuntimeEngines al inicio)
$script:CE = "docker"    # Container Engine: docker o podman
$script:CCE = "docker-compose"  # Compose Engine: docker-compose, docker compose, o podman compose

# Colores para output
function Write-ColorOutput {
    param(
        [string]$Message,
        [ValidateSet('OK', 'ERROR', 'WARNING', 'INFO')]
        [string]$Type = 'INFO'
    )
    
    $colors = @{
        'OK' = 'Green'
        'ERROR' = 'Red'
        'WARNING' = 'Yellow'
        'INFO' = 'Cyan'
    }
    
    $prefix = "[$Type]"
    Write-Host "$prefix " -ForegroundColor $colors[$Type] -NoNewline
    Write-Host $Message
}

# Detecta el motor de contenedores disponible: Podman (prioritario) o Docker
function Get-RuntimeEngines {
    $podmanFound = Get-Command podman -ErrorAction SilentlyContinue
    $dockerFound = Get-Command docker -ErrorAction SilentlyContinue

    if ($podmanFound) {
        $script:CE = "podman"
        Write-ColorOutput "Motor de contenedores: Podman" -Type INFO
        # Intentar podman compose (nativo Podman 4+ o proveedor externo)
        # Usar ErrorActionPreference local para que mensajes informativos de stderr no paren la ejecucion
        $savedPref = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        podman compose version 2>&1 | Out-Null
        $podmanComposeExitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedPref
        if ($podmanComposeExitCode -eq 0) {
            $script:CCE = "podman compose"
            Write-ColorOutput "Motor de compose: podman compose (disponible)" -Type INFO
        } else {
            # Intentar podman-compose como paquete pip
            $podmanComposePkg = Get-Command podman-compose -ErrorAction SilentlyContinue
            if ($podmanComposePkg) {
                $script:CCE = "podman-compose"
                Write-ColorOutput "Motor de compose: podman-compose (paquete externo)" -Type INFO
            } else {
                Write-ColorOutput "No se encontro compose para Podman." -Type WARNING
                Write-ColorOutput "Instala con: pip install podman-compose" -Type WARNING
                Write-ColorOutput "O actualiza Podman a 4+ para compose nativo." -Type WARNING
                exit 1
            }
        }
    } elseif ($dockerFound) {
        $script:CE = "docker"
        Write-ColorOutput "Motor de contenedores: Docker" -Type INFO
        # Intentar docker compose v2 nativo
        $savedPref = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        docker compose version 2>&1 | Out-Null
        $dockerComposeExitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedPref
        if ($dockerComposeExitCode -eq 0) {
            $script:CCE = "docker compose"
            Write-ColorOutput "Motor de compose: docker compose (v2 nativo)" -Type INFO
        } else {
            $dcV1 = Get-Command docker-compose -ErrorAction SilentlyContinue
            if ($dcV1) {
                $script:CCE = "docker-compose"
                Write-ColorOutput "Motor de compose: docker-compose (v1 standalone)" -Type INFO
            } else {
                Write-ColorOutput "Docker Compose no encontrado." -Type WARNING
                Write-ColorOutput "Instala Docker Compose v2 o: pip install docker-compose" -Type WARNING
                exit 1
            }
        }
    } else {
        Write-ColorOutput "No se encontro Docker ni Podman." -Type ERROR
        Write-ColorOutput "Instala Podman (https://podman.io) o Docker Desktop." -Type ERROR
        exit 1
    }

    Write-Host ""
}

# Verificar archivos necesarios
function Test-Prerequisites {
    if (-not (Test-Path $ComposeFile)) {
        Write-ColorOutput "No se encuentra $ComposeFile" -Type ERROR
        exit 1
    }
    
    if (-not (Test-Path $EnvFile)) {
        Write-ColorOutput "No se encuentra $EnvFile. Ejecuta: .\scripts\generate-secrets.py" -Type ERROR
        exit 1
    }

    # Detectar motor de contenedores
    Get-RuntimeEngines
}

# Iniciar simulador
function Invoke-Start {
    Write-ColorOutput "Iniciando simulador de invernadero..." -Type INFO
    
    # Verificar que bunkerm-platform (que incluye el broker MQTT interno) esté corriendo
    $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
    $platformRunning = & $script:CE ps --filter "name=bunkerm-platform" --filter "status=running" -q 2>$null
    $ErrorActionPreference = $savedPref
    if (-not $platformRunning) {
        Write-ColorOutput "Broker Health Manager (bunkerm-platform) no está corriendo. Inícialo primero:" -Type ERROR
        Write-Host "  .\deploy.ps1 -Action start" -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
    
    # Build si no existe la imagen
    $imageExists = & $script:CE images -q greenhouse-simulator
    if (-not $imageExists) {
        Write-ColorOutput "Construyendo imagen del simulador..." -Type INFO
        Invoke-Build
    }
    
    # Iniciar servicio
    Invoke-Expression "$script:CCE -f $ComposeFile --env-file $EnvFile up -d"

    if ($LASTEXITCODE -eq 0) {
        Write-ColorOutput "Simulador iniciado correctamente" -Type OK
        Write-ColorOutput "El stresser es un proceso one-shot: puede quedar en estado Exited tras completar la carga MQTT." -Type INFO
        Start-Sleep -Seconds 3
        Invoke-Status
    } else {
        Write-ColorOutput "Error al iniciar el simulador" -Type ERROR
        exit 1
    }
}

# Detener simulador
function Invoke-Stop {
    Write-ColorOutput "Deteniendo simulador..." -Type INFO
    
    Invoke-Expression "$script:CCE -f $ComposeFile --env-file $EnvFile down"

    if ($LASTEXITCODE -eq 0) {
        Write-ColorOutput "Simulador detenido" -Type OK
    } else {
        Write-ColorOutput "Error al detener el simulador" -Type ERROR
        exit 1
    }
}

# Reiniciar simulador
function Invoke-Restart {
    Write-ColorOutput "Reiniciando simulador..." -Type INFO
    Invoke-Stop
    Start-Sleep -Seconds 2
    Invoke-Start
}

# Estado del simulador
function Invoke-Status {
    Write-ColorOutput "Estado del simulador:" -Type INFO
    Write-Host ""
    
    Invoke-Expression "$script:CCE -f $ComposeFile --env-file $EnvFile ps"

    Write-Host ""

    # Verificar si esta corriendo
    $running = & $script:CE ps --filter "name=$ServiceName" --filter "status=running" -q
    
    if ($running) {
        Write-ColorOutput "Simulador en ejecución" -Type OK
        
        # Mostrar estadisticas
        Write-Host ""
        Write-ColorOutput "Estadisticas del contenedor:" -Type INFO
        & $script:CE stats --no-stream $ServiceName
    } else {
        Write-ColorOutput "Simulador detenido" -Type WARNING
    }
}

# Ver logs
function Invoke-Logs {
    if ($Follow) {
        Write-ColorOutput "Mostrando logs en tiempo real (Ctrl+C para salir)..." -Type INFO
        Invoke-Expression "$script:CCE -f $ComposeFile --env-file $EnvFile logs -f $ServiceName"
    } else {
        Write-ColorOutput "Ultimos logs del simulador:" -Type INFO
        Invoke-Expression "$script:CCE -f $ComposeFile --env-file $EnvFile logs --tail=50 $ServiceName"
    }
}

# Gestionar anomalías
function Invoke-Anomalies {
    param([string]$SubCommand)

    Write-ColorOutput "El simulador activo es greenhouse-simulator y no expone gestión de anomalías desde este wrapper." -Type WARNING
    Write-ColorOutput "Usa greenhouse-simulator/STRESSER_RUNBOOK.md para ajustar el perfil de carga MQTT." -Type INFO
}

# Construir imagen
function Invoke-Build {
    Write-ColorOutput "Construyendo imagen del simulador..." -Type INFO

    & $script:CE build -t greenhouse-simulator ./greenhouse-simulator/src/Greenhouse.Sensors
    
    if ($LASTEXITCODE -eq 0) {
        Write-ColorOutput "Imagen construida correctamente" -Type OK
    } else {
        Write-ColorOutput "Error al construir la imagen" -Type ERROR
        exit 1
    }
}

# Limpiar recursos
function Invoke-Clean {
    Write-ColorOutput "Limpiando recursos del simulador..." -Type WARNING
    Write-Host ""
    
    $confirm = Read-Host "¿Eliminar contenedor, imagen y volúmenes? (y/N)"
    
    if ($confirm -eq 'y' -or $confirm -eq 'Y') {
        # Detener y eliminar contenedor
        Invoke-Expression "$script:CCE -f $ComposeFile --env-file $EnvFile down -v"

        # Eliminar imagen
        & $script:CE rmi greenhouse-simulator -f 2>$null
        
        Write-ColorOutput "Recursos eliminados" -Type OK
    } else {
        Write-ColorOutput "Operación cancelada" -Type INFO
    }
}

# Banner
function Show-Banner {
    Write-Host ""
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host "  Greenhouse Simulator - BHM Test" -ForegroundColor Cyan
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host ""
}

# Menú principal
function Show-Menu {
    Write-Host "Acciones disponibles:"
    Write-Host "  start      - Iniciar simulador"
    Write-Host "  stop       - Detener simulador"
    Write-Host "  restart    - Reiniciar simulador"
    Write-Host "  status     - Ver estado actual"
    Write-Host "  logs       - Ver logs (usa -Follow para tiempo real)"
    Write-Host "  anomalies  - Mostrar nota sobre tuning del stresser"
    Write-Host "  build      - Construir imagen de contenedor"
    Write-Host "  clean      - Eliminar recursos"
    Write-Host ""
    Write-Host "Ejemplos:"
    Write-Host "  .\simulator.ps1 start"
    Write-Host "  .\simulator.ps1 logs -Follow"
    Write-Host "  .\simulator.ps1 anomalies enable"
    Write-Host ""
}

# Ejecución principal
try {
    Show-Banner
    Test-Prerequisites
    
    switch ($Action) {
        'start'     { Invoke-Start }
        'stop'      { Invoke-Stop }
        'restart'   { Invoke-Restart }
        'status'    { Invoke-Status }
        'logs'      { Invoke-Logs }
        'anomalies' { Invoke-Anomalies -SubCommand $SubAction }
        'build'     { Invoke-Build }
        'clean'     { Invoke-Clean }
        default     { 
            Show-Menu
            Invoke-Status
        }
    }
    
} catch {
    Write-ColorOutput "Error inesperado: $_" -Type ERROR
    exit 1
}
