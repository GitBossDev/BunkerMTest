<#
.SYNOPSIS
    Script de gestión del simulador de planta de tratamiento.

.DESCRIPTION
    Controla el simulador de IoT industrial para BunkerM.
    Permite iniciar, detener, reiniciar, y gestionar anomalías.

.PARAMETER Action
    Acción a ejecutar: start, stop, restart, status, logs, anomalies, build, clean

.EXAMPLE
    .\simulator.ps1 start
    .\simulator.ps1 logs -Follow
    .\simulator.ps1 anomalies enable
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
$ErrorActionPreference = 'Stop'
$ComposeFile = 'docker-compose.simulator.yml'
$EnvFile = '.env.dev'
$ServiceName = 'water-plant-simulator'

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
}

# Iniciar simulador
function Invoke-Start {
    Write-ColorOutput "Iniciando simulador de planta de tratamiento..." -Type INFO
    
    # Verificar que Mosquitto esté corriendo
    $mosquittoRunning = docker ps --filter "name=mosquitto" --filter "status=running" -q
    if (-not $mosquittoRunning) {
        Write-ColorOutput "Mosquitto no está corriendo. Inicia los servicios base primero:" -Type ERROR
        Write-Host "  .\deploy.ps1 start" -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
    
    # Build si no existe la imagen
    $imageExists = docker images -q water-plant-simulator
    if (-not $imageExists) {
        Write-ColorOutput "Construyendo imagen del simulador..." -Type INFO
        Invoke-Build
    }
    
    # Iniciar servicio
    docker-compose -f $ComposeFile --env-file $EnvFile up -d
    
    if ($LASTEXITCODE -eq 0) {
        Write-ColorOutput "Simulador iniciado correctamente" -Type OK
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
    
    docker-compose -f $ComposeFile --env-file $EnvFile down
    
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
    
    docker-compose -f $ComposeFile --env-file $EnvFile ps
    
    Write-Host ""
    
    # Verificar si está corriendo
    $running = docker ps --filter "name=$ServiceName" --filter "status=running" -q
    
    if ($running) {
        Write-ColorOutput "Simulador en ejecución" -Type OK
        
        # Mostrar estadísticas
        Write-Host ""
        Write-ColorOutput "Estadísticas del contenedor:" -Type INFO
        docker stats --no-stream $ServiceName
    } else {
        Write-ColorOutput "Simulador detenido" -Type WARNING
    }
}

# Ver logs
function Invoke-Logs {
    if ($Follow) {
        Write-ColorOutput "Mostrando logs en tiempo real (Ctrl+C para salir)..." -Type INFO
        docker-compose -f $ComposeFile --env-file $EnvFile logs -f $ServiceName
    } else {
        Write-ColorOutput "Últimos logs del simulador:" -Type INFO
        docker-compose -f $ComposeFile --env-file $EnvFile logs --tail=50 $ServiceName
    }
}

# Gestionar anomalías
function Invoke-Anomalies {
    param([string]$SubCommand)
    
    if (-not $SubCommand) {
        Write-ColorOutput "Uso: .\simulator.ps1 anomalies <enable|disable|trigger>" -Type WARNING
        Write-Host ""
        Write-Host "Comandos disponibles:"
        Write-Host "  enable   - Habilitar generación automática de anomalías"
        Write-Host "  disable  - Deshabilitar generación automática de anomalías"
        Write-Host "  trigger  - Generar anomalía específica (requiere parámetros adicionales)"
        return
    }
    
    switch ($SubCommand.ToLower()) {
        'enable' {
            Write-ColorOutput "Habilitando generación de anomalías..." -Type INFO
            Write-ColorOutput "NOTA: Esta funcionalidad requiere API del simulador" -Type WARNING
            Write-ColorOutput "Actualiza plant_config.yaml y reinicia el simulador" -Type INFO
        }
        
        'disable' {
            Write-ColorOutput "Deshabilitando generación de anomalías..." -Type INFO
            Write-ColorOutput "NOTA: Esta funcionalidad requiere API del simulador" -Type WARNING
            Write-ColorOutput "Actualiza plant_config.yaml y reinicia el simulador" -Type INFO
        }
        
        'trigger' {
            Write-ColorOutput "Para generar una anomalía específica:" -Type INFO
            Write-Host "1. Edita water-plant-simulator/config/plant_config.yaml"
            Write-Host "2. Ajusta parámetros de anomalies.enabled y probability"
            Write-Host "3. Reinicia el simulador: .\simulator.ps1 restart"
        }
        
        default {
            Write-ColorOutput "Subcomando desconocido: $SubCommand" -Type ERROR
            Invoke-Anomalies -SubCommand ''
        }
    }
}

# Construir imagen
function Invoke-Build {
    Write-ColorOutput "Construyendo imagen del simulador..." -Type INFO
    
    docker build -t water-plant-simulator ./water-plant-simulator
    
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
        docker-compose -f $ComposeFile --env-file $EnvFile down -v
        
        # Eliminar imagen
        docker rmi water-plant-simulator -f 2>$null
        
        # Limpiar logs
        if (Test-Path ".\water-plant-simulator\logs") {
            Remove-Item ".\water-plant-simulator\logs\*" -Force -ErrorAction SilentlyContinue
        }
        
        Write-ColorOutput "Recursos eliminados" -Type OK
    } else {
        Write-ColorOutput "Operación cancelada" -Type INFO
    }
}

# Banner
function Show-Banner {
    Write-Host ""
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host "  Water Plant Simulator - BunkerM Test" -ForegroundColor Cyan
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
    Write-Host "  anomalies  - Gestionar anomalías (enable|disable|trigger)"
    Write-Host "  build      - Construir imagen Docker"
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
