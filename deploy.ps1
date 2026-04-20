# ==========================================
# Broker Health Manager - Deployment Script for Windows
# ==========================================
# This script automates the deployment process on Windows

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet('setup', 'start', 'stop', 'restart', 'status', 'logs', 'clean', 'build', 'build-mosquitto', 'start-bunkerm', 'stop-bunkerm', 'patch-frontend', 'patch-backend', 'reload-mosquitto', 'test', 'smoke')]
    [string]$Action = 'setup',

    [Parameter(Mandatory=$false)]
    [ValidateSet('kind', 'compose', 'both')]
    [string]$Runtime = 'kind',
    
    [Parameter(Mandatory=$false)]
    [switch]$WithTools,

    # Subconjunto de tests a ejecutar: 'all' (defecto), 'smart-anomaly', 'backend'
    [Parameter(Mandatory=$false)]
    [ValidateSet('all', 'smart-anomaly', 'backend')]
    [string]$TestPath = 'all',

    [Parameter(Mandatory=$false)]
    [ValidateSet('podman', 'docker')]
    [string]$KindProvider = 'podman',

    [Parameter(Mandatory=$false)]
    [string]$KindClusterName = 'bhm-lab',

    [Parameter(Mandatory=$false)]
    [string]$KindNamespace = 'bhm-lab',

    [Parameter(Mandatory=$false)]
    [string]$KindCommand = 'kind',

    [Parameter(Mandatory=$false)]
    [string]$KubectlCommand = 'kubectl',

    [Parameter(Mandatory=$false)]
    [int]$KindWebHostPort = 22000,

    [Parameter(Mandatory=$false)]
    [int]$KindMqttHostPort = 21900,

    [Parameter(Mandatory=$false)]
    [int]$KindMqttWsHostPort = 29001,

    [Parameter(Mandatory=$false)]
    [string]$ImageTag = 'latest',
    
    [Parameter(Mandatory=$false)]
    [switch]$Follow
)

$ErrorActionPreference = "Stop"

# Motores de contenedor (se asignan en Get-RuntimeEngines al inicio)
$script:CE = "docker"    # Container Engine: docker o podman
$script:CCE = "docker-compose"  # Compose Engine: docker-compose, docker compose, o podman compose
$script:KindExecutable = $null
$script:KubectlExecutable = $null
$script:BhmPlatformImageName = 'bunkermtest-bunkerm'
$script:MosquittoImageName = 'bunkermtest-mosquitto'
$script:WaterPlantSimulatorImageName = 'water-plant-simulator'
$script:KindImages = @("$($script:BhmPlatformImageName):$ImageTag", "$($script:MosquittoImageName):$ImageTag", "$($script:WaterPlantSimulatorImageName):$ImageTag")
$script:KindWebBaseUrl = "http://localhost:$KindWebHostPort"
$script:KindKubectlContext = "kind-$KindClusterName"
$script:KindPortForwardDir = Join-Path $PSScriptRoot 'tmp\kind-port-forward'
$script:KindPortForwardStatePath = Join-Path $script:KindPortForwardDir 'processes.json'

# Colors for output
function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }
function Write-Error { Write-Host $args -ForegroundColor Red }

function Get-CommandFallbackCandidates {
    param([string]$Candidate)

    $candidateLower = $Candidate.ToLowerInvariant()
    $names = switch ($candidateLower) {
        'kind' { @('kind.exe') }
        'kind.exe' { @('kind.exe') }
        'kubectl' { @('kubectl.exe') }
        'kubectl.exe' { @('kubectl.exe') }
        default { @() }
    }

    if (-not $names.Count) {
        return @()
    }

    $candidates = New-Object System.Collections.Generic.List[string]
    $chocoRoot = if ($env:ChocolateyInstall) { $env:ChocolateyInstall } else { 'C:\ProgramData\chocolatey' }
    $customToolsRoot = 'C:\tools'

    foreach ($name in $names) {
        $candidates.Add((Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\$name"))
        $candidates.Add((Join-Path $env:ProgramFiles "$($name -replace '\.exe$', '')\$name"))
        $candidates.Add((Join-Path $env:USERPROFILE "bin\$name"))
        $candidates.Add((Join-Path $env:USERPROFILE "scoop\shims\$name"))
        $candidates.Add((Join-Path $env:LOCALAPPDATA "Programs\$($name -replace '\.exe$', '')\$name"))
        $candidates.Add((Join-Path $chocoRoot "bin\$name"))

        $binaryName = ($name -replace '\.exe$', '')
        $candidates.Add((Join-Path $customToolsRoot $name))
        $candidates.Add((Join-Path $customToolsRoot "$binaryName\$name"))
        $candidates.Add((Join-Path $customToolsRoot "$binaryName-win-amd64\$name"))

        $localProgramsRoot = Join-Path $env:LOCALAPPDATA 'Programs'
        if (Test-Path $localProgramsRoot) {
            $programMatches = Get-ChildItem $localProgramsRoot -Recurse -Filter $name -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty FullName
            foreach ($match in $programMatches) {
                $candidates.Add($match)
            }
        }

        $wingetPackagesRoot = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
        if (Test-Path $wingetPackagesRoot) {
            $wingetMatches = Get-ChildItem $wingetPackagesRoot -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -like "*$($name -replace '.exe', '')*" } |
                ForEach-Object { Join-Path $_.FullName $name }
            foreach ($match in $wingetMatches) {
                $candidates.Add($match)
            }
        }

        if (Test-Path $customToolsRoot) {
            $toolsMatches = Get-ChildItem $customToolsRoot -Recurse -Filter $name -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty FullName
            foreach ($match in $toolsMatches) {
                $candidates.Add($match)
            }
        }
    }

    return $candidates | Select-Object -Unique
}

function Get-PodmanMachineState {
    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $machineJson = podman machine ls --format json 2>&1
    $machineExitCode = $LASTEXITCODE
    $ErrorActionPreference = $savedPref

    if ($machineExitCode -ne 0) {
        return @()
    }

    try {
        $machines = $machineJson | ConvertFrom-Json
        if ($null -eq $machines) {
            return @()
        }
        if ($machines -is [System.Array]) {
            return $machines
        }
        return @($machines)
    } catch {
        return @()
    }
}

function Ensure-PodmanServiceAvailable {
    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    podman info 2>&1 | Out-Null
    $infoExitCode = $LASTEXITCODE
    $ErrorActionPreference = $savedPref

    if ($infoExitCode -eq 0) {
        return
    }

    $machines = @(Get-PodmanMachineState)
    if (-not $machines.Count) {
        throw 'Podman no responde y no hay maquinas configuradas para recuperarlo automaticamente. Ejecuta podman machine init/start o revisa podman system connection list.'
    }

    $preferredMachine = $machines | Where-Object { $_.Default -eq $true } | Select-Object -First 1
    if (-not $preferredMachine) {
        $preferredMachine = $machines | Select-Object -First 1
    }

    $machineName = "$($preferredMachine.Name)"
    if (-not $machineName) {
        throw 'No se pudo determinar la maquina Podman a recuperar.'
    }

    Write-Warning "Podman no respondio. Intentando recuperar la maquina '$machineName'..."

    $isRunning = $false
    if ($preferredMachine.PSObject.Properties.Name -contains 'Running') {
        $isRunning = [bool]$preferredMachine.Running
    } elseif ("$($preferredMachine.LastUp)" -match 'Currently running') {
        $isRunning = $true
    }

    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    if ($isRunning) {
        podman machine stop $machineName 2>&1 | Out-Null
    }
    podman machine start $machineName 2>&1 | Out-Null
    $startExitCode = $LASTEXITCODE
    podman system connection default "${machineName}-root" 2>&1 | Out-Null
    $ErrorActionPreference = $savedPref

    if ($startExitCode -ne 0) {
        Invoke-PodmanWslRecovery -MachineName $machineName
        return
    }

    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        $savedPref = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        podman info 2>&1 | Out-Null
        $infoExitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedPref
        if ($infoExitCode -eq 0) {
            Write-Success "[OK] Podman recuperado sobre la maquina '$machineName'."
            return
        }

        Start-Sleep -Seconds 3
    }

    Invoke-PodmanWslRecovery -MachineName $machineName
}

function Restart-PodmanMachine {
    $machines = @(Get-PodmanMachineState)
    if (-not $machines.Count) {
        throw 'No hay maquinas Podman disponibles para reiniciar.'
    }

    $preferredMachine = $machines | Where-Object { $_.Default -eq $true } | Select-Object -First 1
    if (-not $preferredMachine) {
        $preferredMachine = $machines | Select-Object -First 1
    }

    $machineName = "$($preferredMachine.Name)"
    if (-not $machineName) {
        throw 'No se pudo determinar la maquina Podman a reiniciar.'
    }

    Write-Warning "Reiniciando la maquina Podman '$machineName' para limpiar forwards huerfanos..."

    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    podman machine stop $machineName 2>&1 | Out-Null
    podman machine start $machineName 2>&1 | Out-Null
    $startExitCode = $LASTEXITCODE
    podman system connection default "${machineName}-root" 2>&1 | Out-Null
    $ErrorActionPreference = $savedPref

    if ($startExitCode -ne 0) {
        Invoke-PodmanWslRecovery -MachineName $machineName
        return
    }

    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        $savedPref = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        podman info 2>&1 | Out-Null
        $infoExitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedPref
        if ($infoExitCode -eq 0) {
            return
        }

        Start-Sleep -Seconds 3
    }

    Invoke-PodmanWslRecovery -MachineName $machineName
}

function Invoke-PodmanWslRecovery {
    param(
        [string]$MachineName
    )

    Write-Warning "Recuperacion fuerte de Podman: ejecutando 'wsl --shutdown' y reintentando '$MachineName'..."
    wsl.exe --shutdown 2>&1 | Out-Null

    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    podman machine start $MachineName 2>&1 | Out-Null
    $startExitCode = $LASTEXITCODE
    podman system connection default "${MachineName}-root" 2>&1 | Out-Null
    $ErrorActionPreference = $savedPref

    if ($startExitCode -ne 0) {
        throw "No se pudo recuperar la maquina Podman '$MachineName' tras reiniciar WSL."
    }

    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $savedPref = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        podman info 2>&1 | Out-Null
        $infoExitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedPref
        if ($infoExitCode -eq 0) {
            Write-Success "[OK] Podman recuperado tras reiniciar WSL."
            return
        }

        Start-Sleep -Seconds 3
    }

    throw "Podman sigue sin responder tras la recuperacion fuerte de WSL para '$MachineName'."
}

# Detecta el motor de contenedores disponible: Podman (prioritario) o Docker
function Get-RuntimeEngines {
    $podmanFound = Get-Command podman -ErrorAction SilentlyContinue
    $dockerFound = Get-Command docker -ErrorAction SilentlyContinue

    if ($podmanFound) {
        $script:CE = "podman"
        Ensure-PodmanServiceAvailable
        Write-Info "Motor de contenedores: Podman"
        if ($Runtime -in @('compose', 'both')) {
            # Intentar podman compose (nativo Podman 4+ o proveedor externo)
            $savedPref = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            podman compose version 2>&1 | Out-Null
            $podmanComposeExitCode = $LASTEXITCODE
            $ErrorActionPreference = $savedPref
            if ($podmanComposeExitCode -eq 0) {
                $script:CCE = "podman compose"
                Write-Info "Motor de compose: podman compose (disponible)"
            } else {
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
        }
    } elseif ($dockerFound) {
        $script:CE = "docker"
        Write-Info "Motor de contenedores: Docker"
        if ($Runtime -in @('compose', 'both')) {
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
    Write-Host " Broker Health Manager - Deployment Tool " -ForegroundColor Magenta
    Write-Host "==========================================" -ForegroundColor Magenta
    Write-Host ""
}

function Warn-DeprecatedWithTools {
    if ($WithTools) {
        Write-Warning "El argumento -WithTools ya no tiene efecto. PostgreSQL forma parte del baseline Compose-first y pgAdmin queda fuera del flujo normal de deploy."
    }
}

function Test-Prerequisites {
    Write-Info "Verificando prerequisitos..."

    # Detectar motor de contenedores (Podman o Docker)
    Get-RuntimeEngines
    Warn-DeprecatedWithTools

    # Check Python
    try {
        $pythonVersion = python --version
        Write-Success "[OK] Python: $pythonVersion"
    } catch {
        Write-Warning "[WARNING] Python no encontrado. Algunos scripts pueden no funcionar."
    }

    Write-Host ""
}

function Get-EnvMap {
    param(
        [string]$Path = ".env.dev"
    )

    $values = @{}
    if (-not (Test-Path $Path)) {
        return $values
    }

    foreach ($rawLine in Get-Content $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#')) {
            continue
        }

        $parts = $line.Split('=', 2)
        if ($parts.Count -lt 2) {
            continue
        }

        $values[$parts[0].Trim()] = $parts[1]
    }

    return $values
}

function Test-PostgresUrl {
    param(
        [string]$Value
    )

    if (-not $Value) {
        return $false
    }

    return $Value.Trim().ToLowerInvariant().StartsWith('postgresql')
}

function Test-PostgresRequired {
    param(
        [hashtable]$EnvMap
    )

    foreach ($name in @('CONTROL_PLANE_DATABASE_URL', 'HISTORY_DATABASE_URL', 'REPORTING_DATABASE_URL', 'DATABASE_URL')) {
        if (Test-PostgresUrl -Value $EnvMap[$name]) {
            return $true
        }
    }

    return $false
}

function Test-ComposeRuntime {
    return $Runtime -in @('compose', 'both')
}

function Test-KindRuntime {
    return $Runtime -in @('kind', 'both')
}

function Resolve-CommandTarget {
    param(
        [string]$Candidate,
        [string]$DisplayName
    )

    if (Test-Path $Candidate) {
        return (Resolve-Path $Candidate).Path
    }

    $command = Get-Command $Candidate -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $whereMatches = @(where.exe $Candidate 2>$null)
    $ErrorActionPreference = $savedPref
    foreach ($whereMatch in $whereMatches) {
        if (Test-Path $whereMatch) {
            return (Resolve-Path $whereMatch).Path
        }
    }

    foreach ($fallbackCandidate in Get-CommandFallbackCandidates -Candidate $Candidate) {
        if (Test-Path $fallbackCandidate) {
            return (Resolve-Path $fallbackCandidate).Path
        }
    }

    throw "$DisplayName no esta disponible. Agregalo al PATH o pasa -$DisplayName`Command con la ruta completa al ejecutable."
}

function Ensure-KubernetesTooling {
    if ($script:KindExecutable -and $script:KubectlExecutable) {
        return
    }

    $script:KindExecutable = Resolve-CommandTarget -Candidate $KindCommand -DisplayName 'Kind'
    $script:KubectlExecutable = Resolve-CommandTarget -Candidate $KubectlCommand -DisplayName 'Kubectl'
}

function Test-LocalImagePresent {
    param(
        [string]$ImageName
    )

    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $script:CE image inspect $ImageName 2>&1 | Out-Null
    $imageExists = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $savedPref

    return $imageExists
}

function Get-ApiKey {
    if (-not (Test-Path '.env.dev')) {
        return ''
    }

    $line = Get-Content '.env.dev' | Select-String '^API_KEY=' | Select-Object -First 1
    if ($line) {
        return ("$line" -replace '^API_KEY=', '')
    }

    return ''
}

function Get-ListeningPortProcesses {
    param(
        [int[]]$Ports
    )

    $results = New-Object System.Collections.Generic.List[object]
    foreach ($targetPort in $Ports) {
        $connections = @(Get-NetTCPConnection -State Listen -LocalPort $targetPort -ErrorAction SilentlyContinue)
        foreach ($connection in $connections) {
            $processId = [int]$connection.OwningProcess
            $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
            $results.Add([PSCustomObject]@{
                LocalAddress = $connection.LocalAddress
                LocalPort = $targetPort
                Pid = $processId
                ProcessName = if ($process) { $process.ProcessName } else { 'unknown' }
            })
        }
    }

    return @($results | Sort-Object LocalPort, Pid -Unique)
}

function Clear-KindHostPortConflicts {
    $ports = @($KindWebHostPort, $KindMqttHostPort, $KindMqttWsHostPort)
    $conflicts = @(Get-ListeningPortProcesses -Ports $ports)
    if (-not $conflicts.Count) {
        return
    }

    $allWslRelay = $true
    foreach ($conflict in $conflicts) {
        if ("$($conflict.ProcessName)".ToLowerInvariant() -ne 'wslrelay') {
            $allWslRelay = $false
            break
        }
    }

    if ($KindProvider -eq 'podman' -and $allWslRelay) {
        Restart-PodmanMachine
        $remainingConflicts = @(Get-ListeningPortProcesses -Ports $ports)
        if (-not $remainingConflicts.Count) {
            return
        }
        foreach ($remainingConflict in $remainingConflicts) {
            if ("$($remainingConflict.ProcessName)".ToLowerInvariant() -eq 'wslrelay') {
                Stop-Process -Id $remainingConflict.Pid -Force -ErrorAction SilentlyContinue
            }
        }
        Start-Sleep -Seconds 2
        $remainingConflicts = @(Get-ListeningPortProcesses -Ports $ports)
        if (-not $remainingConflicts.Count) {
            return
        }
        $remainingSummary = ($remainingConflicts | ForEach-Object { "$($_.ProcessName) pid=$($_.Pid) port=$($_.LocalPort)" }) -join '; '
        throw "Persisten listeners sobre los puertos kind tras reiniciar Podman: $remainingSummary"
    }

    $summary = ($conflicts | ForEach-Object { "$($_.ProcessName) pid=$($_.Pid) port=$($_.LocalPort)" }) -join '; '
    throw "Los puertos del laboratorio kind ya estan ocupados: $summary"
}

function Wait-ContainerRunning {
    param(
        [string]$ContainerName,
        [int]$TimeoutSeconds = 90
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $status = & $script:CE inspect -f "{{.State.Status}}" $ContainerName 2>$null
        if ($LASTEXITCODE -eq 0) {
            $normalizedStatus = ($status | Out-String).Trim().ToLowerInvariant()
            if ($normalizedStatus -eq 'running') {
                return $true
            }
            if ($normalizedStatus -in @('exited', 'dead')) {
                return $false
            }
        }

        Start-Sleep -Seconds 2
    }

    return $false
}

function Test-TcpPortOpen {
    param(
        [int]$Port,
        [string]$HostName = '127.0.0.1',
        [int]$TimeoutMilliseconds = 1000
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMilliseconds, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Get-KindPortForwardEntries {
    if (-not (Test-Path $script:KindPortForwardStatePath)) {
        return @()
    }

    try {
        $state = Get-Content $script:KindPortForwardStatePath -Raw | ConvertFrom-Json
        if ($state -is [System.Array]) {
            return @($state)
        }
        if ($null -ne $state) {
            return @($state)
        }
    } catch {
    }

    return @()
}

function Stop-KindPortForwards {
    $entries = @(Get-KindPortForwardEntries)
    $portsToRelease = @()
    foreach ($entry in $entries) {
        if ($entry.PSObject.Properties.Name -contains 'Ports') {
            $portsToRelease += @($entry.Ports)
        }

        $processIdToStop = 0
        try {
            $processIdToStop = [int]$entry.Pid
        } catch {
            $processIdToStop = 0
        }

        if ($processIdToStop -le 0) {
            continue
        }

        $process = Get-Process -Id $processIdToStop -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $processIdToStop -Force -ErrorAction SilentlyContinue
            $deadline = (Get-Date).AddSeconds(10)
            while ((Get-Date) -lt $deadline) {
                if (-not (Get-Process -Id $processIdToStop -ErrorAction SilentlyContinue)) {
                    break
                }
                Start-Sleep -Milliseconds 250
            }
        }
    }

    foreach ($port in ($portsToRelease | Sort-Object -Unique)) {
        $deadline = (Get-Date).AddSeconds(10)
        while ((Get-Date) -lt $deadline) {
            if (-not (Test-TcpPortOpen -Port $port)) {
                break
            }
            Start-Sleep -Milliseconds 250
        }
    }

    if (Test-Path $script:KindPortForwardStatePath) {
        Remove-Item $script:KindPortForwardStatePath -Force -ErrorAction SilentlyContinue
    }
}

function Start-KindPortForwardProcess {
    param(
        [string]$Name,
        [string]$Resource,
        [string[]]$Mappings,
        [int[]]$LocalPorts
    )

    New-Item -ItemType Directory -Path $script:KindPortForwardDir -Force | Out-Null
    $stdoutLog = Join-Path $script:KindPortForwardDir "$Name.stdout.log"
    $stderrLog = Join-Path $script:KindPortForwardDir "$Name.stderr.log"
    Remove-Item $stdoutLog, $stderrLog -Force -ErrorAction SilentlyContinue

    $argumentList = @(
        '--context', $script:KindKubectlContext,
        '-n', $KindNamespace,
        'port-forward',
        $Resource
    ) + $Mappings + @('--address', '127.0.0.1')

    $process = Start-Process -FilePath $script:KubectlExecutable -ArgumentList $argumentList -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru -WindowStyle Hidden

    return @{
        Name = $Name
        Pid = $process.Id
        StdoutLog = $stdoutLog
        StderrLog = $stderrLog
        Ports = $LocalPorts
    }
}

function Wait-KindPortForwardReady {
    param(
        [hashtable]$Entry,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $process = Get-Process -Id $Entry.Pid -ErrorAction SilentlyContinue
        if (-not $process) {
            $stderr = if (Test-Path $Entry.StderrLog) { (Get-Content $Entry.StderrLog -Raw) } else { '' }
            $stdout = if (Test-Path $Entry.StdoutLog) { (Get-Content $Entry.StdoutLog -Raw) } else { '' }
            throw "El port-forward '$($Entry.Name)' termino antes de quedar listo. STDERR: $stderr STDOUT: $stdout"
        }

        $allPortsReady = $true
        foreach ($port in $Entry.Ports) {
            if (-not (Test-TcpPortOpen -Port $port)) {
                $allPortsReady = $false
                break
            }
        }

        if ($allPortsReady) {
            return
        }

        Start-Sleep -Seconds 1
    }

    throw "El port-forward '$($Entry.Name)' no quedo listo dentro de ${TimeoutSeconds}s."
}

function Start-KindPortForwards {
    Ensure-KubernetesTooling
    Stop-KindPortForwards

    $entries = @(
        (Start-KindPortForwardProcess -Name 'platform' -Resource 'service/bunkerm-platform' -Mappings @("${KindWebHostPort}:2000") -LocalPorts @($KindWebHostPort)),
        (Start-KindPortForwardProcess -Name 'mosquitto' -Resource 'service/mosquitto' -Mappings @("${KindMqttHostPort}:1900", "${KindMqttWsHostPort}:9001") -LocalPorts @($KindMqttHostPort, $KindMqttWsHostPort))
    )

    foreach ($entry in $entries) {
        Wait-KindPortForwardReady -Entry $entry
    }

    $entries | ConvertTo-Json | Set-Content -Path $script:KindPortForwardStatePath -Encoding ASCII
}

function Ensure-KindPortForwardsHealthy {
    Ensure-KubernetesTooling

    $entries = @(Get-KindPortForwardEntries)
    if ($entries.Count -eq 0) {
        Start-KindPortForwards
        return
    }

    foreach ($entry in $entries) {
        $process = Get-Process -Id $entry.Pid -ErrorAction SilentlyContinue
        if (-not $process) {
            Start-KindPortForwards
            return
        }

        foreach ($port in $entry.Ports) {
            if (-not (Test-TcpPortOpen -Port $port)) {
                Start-KindPortForwards
                return
            }
        }
    }
}

function Wait-HttpEndpoint {
    param(
        [string]$Uri,
        [int[]]$AcceptStatusCodes,
        [hashtable]$Headers = @{},
        [int]$TimeoutSeconds = 120,
        [int]$IntervalSeconds = 3
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 10 -Headers $Headers -ErrorAction Stop
            if ($response.StatusCode -in $AcceptStatusCodes) {
                return $true
            }
        } catch {
            $code = $_.Exception.Response.StatusCode.value__
            if ($code -in $AcceptStatusCodes) {
                return $true
            }
        }

        Start-Sleep -Seconds $IntervalSeconds
    }

    return $false
}

function Wait-ComposeRuntimeReady {
    param(
        [bool]$PostgresRequired,
        [string]$ApiKey
    )

    Write-Info 'Esperando readiness real del runtime Compose-first...'

    if (-not (Wait-ContainerHealthy -ContainerName 'bunkerm-platform' -TimeoutSeconds 180)) {
        Write-Error 'bunkerm-platform no alcanzo estado healthy. Revisa: .\deploy.ps1 -Action logs'
        exit 1
    }

    if (-not (Wait-ContainerRunning -ContainerName 'bunkerm-reconciler' -TimeoutSeconds 120)) {
        Write-Error 'bunkerm-reconciler no alcanzo estado running. Revisa: .\deploy.ps1 -Action logs'
        exit 1
    }

    if (-not (Wait-HttpEndpoint -Uri 'http://localhost:2000/api/auth/me' -AcceptStatusCodes @(200, 401, 403) -TimeoutSeconds 120)) {
        Write-Error 'El backend no expuso /api/auth/me a tiempo. Revisa: .\deploy.ps1 -Action logs'
        exit 1
    }

    if ($ApiKey) {
        if (-not (Wait-HttpEndpoint -Uri 'http://localhost:2000/api/dynsec/roles' -AcceptStatusCodes @(200) -Headers @{ 'X-API-Key' = $ApiKey } -TimeoutSeconds 120)) {
            Write-Error 'El backend no expuso /api/dynsec/roles a tiempo. Revisa: .\deploy.ps1 -Action logs'
            exit 1
        }
    }

    if ($PostgresRequired) {
        $deadline = (Get-Date).AddSeconds(90)
        while ((Get-Date) -lt $deadline) {
            $reconcilerPgCheck = Test-ContainerControlPlanePostgresConnectivity -ContainerName 'bunkerm-reconciler'
            if ($reconcilerPgCheck.Success) {
                return
            }

            Start-Sleep -Seconds 3
        }

        Write-Error 'bunkerm-reconciler no pudo confirmar conectividad con PostgreSQL. Revisa: .\deploy.ps1 -Action logs'
        exit 1
    }
}

function Test-KindClusterExists {
    Ensure-KubernetesTooling

    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $clusters = & $script:KindExecutable get clusters 2>&1
    $kindExitCode = $LASTEXITCODE
    $ErrorActionPreference = $savedPref

    return ($kindExitCode -eq 0 -and ($clusters | Where-Object { $_ -eq $KindClusterName }))
}

function Wait-KubernetesRuntimeReady {
    Ensure-KubernetesTooling

    $timeout = '240s'
    foreach ($target in @('statefulset/postgres', 'statefulset/mosquitto', 'deployment/bunkerm-platform', 'deployment/water-plant-simulator', 'deployment/bhm-alert-delivery')) {
        & $script:KubectlExecutable rollout status $target -n $KindNamespace --timeout=$timeout | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Error "El workload $target no alcanzo estado listo en Kubernetes."
            exit 1
        }
    }
}

function Invoke-StartKindRuntime {
    if (-not (Test-Path '.env.dev')) {
        Write-Error '.env.dev not found. Run setup first: .\deploy.ps1 -Action setup'
        exit 1
    }

    Ensure-KubernetesTooling
    foreach ($imageName in $script:KindImages) {
        if (-not (Test-LocalImagePresent -ImageName $imageName)) {
            Write-Error "No se encontro la imagen local $imageName. Ejecuta .\deploy.ps1 -Action build antes de iniciar el runtime kind."
            exit 1
        }
    }

    if (Test-KindClusterExists) {
        Write-Info "Recreando cluster kind '$KindClusterName' para evitar drift de secretos, imagenes y credenciales persistidas..."
        Invoke-StopKindRuntime
        Write-Host ''
    }

    Clear-KindHostPortConflicts

    Write-Info 'Starting Kubernetes lab...'
    Write-Host ''

    & (Join-Path $PSScriptRoot 'k8s\scripts\bootstrap-kind.ps1') `
        -ClusterName $KindClusterName `
        -Namespace $KindNamespace `
        -EnvFile '.env.dev' `
        -KindConfig 'k8s/kind/cluster.yaml' `
        -Provider $KindProvider `
        -KindCommand $script:KindExecutable `
        -KubectlCommand $script:KubectlExecutable `
        -WebHostPort $KindWebHostPort `
        -MqttHostPort $KindMqttHostPort `
        -MqttWsHostPort $KindMqttWsHostPort `
        -LoadLocalImage `
        -LocalImages $script:KindImages `
        -BhmImage "localhost/$($script:BhmPlatformImageName):$ImageTag" `
        -MosquittoImage "localhost/$($script:MosquittoImageName):$ImageTag" `
        -WaterPlantSimulatorImage "localhost/$($script:WaterPlantSimulatorImageName):$ImageTag"

    if ($LASTEXITCODE -ne 0) {
        Write-Error 'Fallo el arranque del laboratorio kind. Revisa la salida anterior.'
        exit 1
    }

    Wait-KubernetesRuntimeReady
    Start-KindPortForwards
}

function Invoke-StopKindRuntime {
    Ensure-KubernetesTooling
    Stop-KindPortForwards
    if (-not (Test-KindClusterExists)) {
        Write-Info "El cluster kind '$KindClusterName' no esta creado."
        return
    }

    Write-Info "Eliminando cluster kind '$KindClusterName'..."
    & $script:KindExecutable delete cluster --name $KindClusterName
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'No se pudo eliminar el cluster kind.'
        exit 1
    }

    Write-Success "[OK] Cluster kind '$KindClusterName' eliminado."
}

function Wait-ContainerHealthy {
    param(
        [string]$ContainerName,
        [int]$TimeoutSeconds = 90
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $status = & $script:CE inspect -f "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" $ContainerName 2>$null
        if ($LASTEXITCODE -eq 0) {
            $normalizedStatus = ($status | Out-String).Trim().ToLowerInvariant()
            if ($normalizedStatus -in @('healthy', 'running')) {
                return $true
            }
            if ($normalizedStatus -in @('exited', 'dead')) {
                return $false
            }
        }

        Start-Sleep -Seconds 2
    }

    return $false
}

function Test-ContainerControlPlanePostgresConnectivity {
    param(
        [string]$ContainerName
    )

    $pythonSnippet = "import sys; sys.path.insert(0, '/app'); from sqlalchemy import create_engine, text; from core.config import Settings; from core.database_url import get_sync_database_url; settings = Settings(); resolved_url = settings.resolved_control_plane_database_url; assert resolved_url.lower().startswith('postgresql'), f'resolved_control_plane_database_url is not PostgreSQL: {resolved_url}'; engine = create_engine(get_sync_database_url(resolved_url), future=True); connection = engine.connect(); connection.execute(text('SELECT 1')); connection.close(); print('OK')"

    $output = & $script:CE exec $ContainerName /opt/venv/bin/python -c $pythonSnippet 2>&1
    return @{
        Success = ($LASTEXITCODE -eq 0)
        Output = (($output | Out-String).Trim())
    }
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
    Write-Host "  1. Revisa .env.dev y actualiza configuracion SMTP si es necesario"
    Write-Host "  2. Ejecuta: .\deploy.ps1 -Action build"
    Write-Host "  3. Ejecuta: .\deploy.ps1 -Action start"
    Write-Host ""
}

function Invoke-Start {
    Write-Info "Starting services..."
    Write-Host ""

    if (-not (Test-Path '.env.dev')) {
        Write-Error '.env.dev not found. Run setup first: .\deploy.ps1 -Action setup'
        exit 1
    }

    Write-Info 'Validating environment variables...'
    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $validateOutput = & python scripts/validate-env.py 2>&1
    $validateExit = $LASTEXITCODE
    $ErrorActionPreference = $savedPref
    if ($validateExit -ne 0) {
        Write-Host '[ERROR] Environment validation failed:' -ForegroundColor Red
        $validateOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        Write-Host ''
        Write-Host "  Run '.\deploy.ps1 -Action setup' to regenerate secrets." -ForegroundColor Yellow
        exit 1
    }
    Write-Success $validateOutput
    Write-Host ''

    $envMap = Get-EnvMap -Path '.env.dev'
    $postgresRequired = Test-PostgresRequired -EnvMap $envMap
    $apiKey = Get-ApiKey

    if (Test-ComposeRuntime) {
        if (Test-Path 'bunkerm-source') {
            if (-not (Test-Path 'bunkerm-source\.env')) {
                Write-Warning 'bunkerm-source/.env no encontrado. Creando archivo vacio para evitar error de compose...'
                New-Item -ItemType File -Path 'bunkerm-source\.env' -Force | Out-Null
                Write-Info 'Si BunkerM requiere variables propias, edita bunkerm-source/.env'
            }
        } else {
            Write-Warning "bunkerm-source/ no existe. El servicio 'bunkerm' no se construira."
            Write-Warning 'Para incluirlo ejecuta: git clone https://github.com/bunkeriot/BunkerM bunkerm-source'
            Write-Host ''
        }

        $orphanContainers = @('bunkerm-platform', 'bunkerm-reconciler')
        foreach ($cname in $orphanContainers) {
            $exists = & $script:CE ps -a --format '{{.Names}}' 2>&1 | Select-String "^${cname}$"
            if ($exists) {
                Write-Warning "Contenedor huerfano encontrado: $cname. Eliminando antes de compose..."
                $savedPref = $ErrorActionPreference
                $ErrorActionPreference = 'Continue'
                & $script:CE stop $cname 2>&1 | Out-Null
                & $script:CE rm $cname 2>&1 | Out-Null
                $ErrorActionPreference = $savedPref
                Write-Success "[OK] $cname eliminado"
            }
        }

        $composeCmd = "$script:CCE --env-file .env.dev -f docker-compose.dev.yml up -d"
        Invoke-Expression $composeCmd

        if ($LASTEXITCODE -ne 0) {
            Write-Error 'Fallo el arranque del stack Compose-first. Revisa: .\deploy.ps1 -Action logs'
            exit 1
        }

        Write-Host ''
        Write-Success '[OK] Runtime Compose-first iniciado.'
        Write-Host ''

        if ($postgresRequired) {
            Write-Info 'Esperando a que PostgreSQL quede healthy para el runtime Compose-first...'
            if (-not (Wait-ContainerHealthy -ContainerName 'bunkerm-postgres' -TimeoutSeconds 90)) {
                Write-Error 'PostgreSQL no alcanzo estado healthy. Revisa: .\deploy.ps1 -Action logs'
                exit 1
            }
        }

        Write-Host ''
        Write-Info 'Applying local source patches to the running container...'
        Invoke-PatchBackend
        Invoke-PatchFrontend
        Wait-ComposeRuntimeReady -PostgresRequired $postgresRequired -ApiKey $apiKey
    }

    if (Test-KindRuntime) {
        if (Test-ComposeRuntime) {
            Write-Host ''
        }

        Invoke-StartKindRuntime
    }

    Write-Host ''
    Write-Info 'Ejecutando smoke test del stack...'
    $smokeFailures = Invoke-Smoke
    if ($smokeFailures -gt 0) {
        Write-Warning "[AVISO] El smoke test detecto $smokeFailures fallo(s). El stack sigue corriendo para debug manual."
        Write-Host "  Logs: .\deploy.ps1 -Action logs -Runtime $Runtime" -ForegroundColor Yellow
    }

    Write-Host ''
    Write-Info 'Service URLs:'
    if (Test-ComposeRuntime) {
        Write-Host '  - Compose Web UI:    http://localhost:2000' -ForegroundColor Cyan
        Write-Host '  - Compose MQTT:      localhost:1900' -ForegroundColor Cyan
        if ($postgresRequired) {
            Write-Host '  - Compose PostgreSQL: localhost:5432' -ForegroundColor Cyan
        }
    }
    if (Test-KindRuntime) {
        Write-Host "  - kind Web UI:       $script:KindWebBaseUrl" -ForegroundColor Cyan
        Write-Host "  - kind MQTT:         localhost:$KindMqttHostPort" -ForegroundColor Cyan
        Write-Host "  - kind MQTT WS:      localhost:$KindMqttWsHostPort" -ForegroundColor Cyan
    }

    Write-Host ''
    Write-Info "Run health check: .\deploy.ps1 -Action status -Runtime $Runtime"
    Write-Host ''
}

function Invoke-Stop {
    Write-Info "Stopping services..."
    Write-Host ""

    if (Test-ComposeRuntime) {
        $composeCmd = "$script:CCE --env-file .env.dev -f docker-compose.dev.yml down"
        Invoke-Expression $composeCmd
    }

    if (Test-KindRuntime) {
        Invoke-StopKindRuntime
    }

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

    if (Test-ComposeRuntime) {
        Write-Host 'Contenedores Compose:' -ForegroundColor Yellow
        $containers = & $script:CE ps --format json 2>$null | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($containers) {
            $containers | Where-Object { $_.Names -match 'bunkerm|water-plant' } |
                Format-Table @{L='Nombre';E={$_.Names}}, @{L='Estado';E={$_.State}}, @{L='Puertos';E={$_.Ports}} -AutoSize
        } else {
            Invoke-Expression "$script:CE ps" | Select-String 'bunkerm|water-plant|NAME'
        }

        Write-Host ''
        Write-Host 'Health Checks Compose:' -ForegroundColor Yellow
        Write-Host ''

        Write-Host -NoNewline '  Mosquitto MQTT standalone (localhost:1900)... '
        $savedPref = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        try {
            $tcpClient.Connect('localhost', 1900)
            Write-Success '[OK] puerto 1900 accesible'
            $tcpClient.Close()
        } catch {
            Write-Host '[NO DISPONIBLE]' -ForegroundColor Red
        } finally {
            $ErrorActionPreference = $savedPref
        }

        Write-Host -NoNewline '  BHM Web UI (http://localhost:2000)... '
        try {
            $resp = Invoke-WebRequest -Uri 'http://localhost:2000' -UseBasicParsing -TimeoutSec 5 -MaximumRedirection 5 -ErrorAction Stop
            Write-Success "[OK] HTTP $($resp.StatusCode)"
        } catch {
            $code = $_.Exception.Response.StatusCode.value__
            if ($code -ge 300 -and $code -lt 400) {
                Write-Success "[OK] HTTP $code (redirect al login)"
            } else {
                Write-Host '[NO DISPONIBLE]' -ForegroundColor Red
            }
        }

        Write-Host -NoNewline '  BHM API (/api/auth/me)... '
        try {
            $resp = Invoke-WebRequest -Uri 'http://localhost:2000/api/auth/me' -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            Write-Success "[OK] HTTP $($resp.StatusCode)"
        } catch {
            if ($_.Exception.Response.StatusCode.value__ -in @(401, 403)) {
                Write-Success "[OK] HTTP $($_.Exception.Response.StatusCode.value__) (no autenticado, backend activo)"
            } else {
                Write-Host '[NO DISPONIBLE]' -ForegroundColor Red
            }
        }

        Write-Host ''
    }

    if (Test-KindRuntime) {
        Ensure-KubernetesTooling
        Write-Host 'Workloads kind:' -ForegroundColor Yellow
        if (Test-KindClusterExists) {
            & $script:KubectlExecutable get pods,svc -n $KindNamespace
        } else {
            Write-Warning "El cluster kind '$KindClusterName' no existe."
        }
        Write-Host ''
    }
}

function Invoke-Logs {
    Write-Info "Showing logs..."
    Write-Host ""

    if (Test-ComposeRuntime) {
        $composeCmd = "$script:CCE --env-file .env.dev -f docker-compose.dev.yml logs"
        if ($Follow) {
            $composeCmd += ' -f'
            Write-Info 'Following Compose logs (Ctrl+C to exit)...'
        } else {
            $composeCmd += ' --tail=100'
        }

        Invoke-Expression $composeCmd
    }

    if (Test-KindRuntime) {
        Ensure-KubernetesTooling
        if (-not (Test-KindClusterExists)) {
            Write-Warning "El cluster kind '$KindClusterName' no existe."
            return
        }

        if (Test-ComposeRuntime) {
            Write-Host ''
        }

        if ($Follow) {
            Write-Info 'Following bunkerm-platform logs in kind (Ctrl+C to exit)...'
            & $script:KubectlExecutable logs deployment/bunkerm-platform -n $KindNamespace -f --all-containers=true
        } else {
            Write-Info 'kind pods:'
            & $script:KubectlExecutable get pods -n $KindNamespace
            Write-Host ''
            Write-Info 'bunkerm-platform:'
            & $script:KubectlExecutable logs deployment/bunkerm-platform -n $KindNamespace --all-containers=true --tail=80
            Write-Host ''
            Write-Info 'water-plant-simulator:'
            & $script:KubectlExecutable logs deployment/water-plant-simulator -n $KindNamespace --tail=80
            Write-Host ''
            Write-Info 'mosquitto/reconciler:'
            & $script:KubectlExecutable logs statefulset/mosquitto -n $KindNamespace -c reconciler --tail=80
        }
    }
}

function Invoke-Clean {
    Write-Warning "This will remove all containers, volumes, and data!"
    $confirm = Read-Host "Are you sure? Type 'yes' to confirm"
    
    if ($confirm -eq 'yes') {
        Write-Info "Cleaning up..."
        Write-Host ""
        
        if (Test-ComposeRuntime) {
            Invoke-Expression "$script:CCE --env-file .env.dev -f docker-compose.dev.yml down -v"
        }

        if (Test-KindRuntime) {
            Invoke-StopKindRuntime
        }
        
        if (Test-ComposeRuntime) {
            Write-Info 'Removing data directories...'
            $dataDir = 'data'
            if (Test-Path $dataDir) {
                Remove-Item -Recurse -Force "$dataDir/*" -ErrorAction SilentlyContinue
                Write-Success '[OK] Data directories cleaned'
            }
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
    Write-Info "Construyendo imagen de Broker Health Manager..."
    Write-Host ""

    if (-not (Test-Path "bunkerm-source")) {
        Write-Host "[ERROR] bunkerm-source/ no encontrado." -ForegroundColor Red
        Write-Host "  git clone https://github.com/bunkeriot/BunkerM bunkerm-source" -ForegroundColor Yellow
        exit 1
    }

    # Construir Mosquitto primero (más rápido; Broker Health Manager depende de él en runtime)
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
        -t "$($script:BhmPlatformImageName):$ImageTag" `
        -f bunkerm-source/Dockerfile.next `
        bunkerm-source
    $buildExit = $LASTEXITCODE
    $ErrorActionPreference = $savedPref

    if ($buildExit -eq 0) {
        Write-Success "[OK] Imagen de Broker Health Manager construida correctamente: $($script:BhmPlatformImageName):$ImageTag"
        Write-Info "Ahora ejecuta: .\deploy.ps1 -Action start"
    } else {
        Write-Host "[ERROR] Fallo en el build. Revisa los logs de arriba." -ForegroundColor Red
        exit 1
    }

    Invoke-BuildWaterPlantSimulator
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
        -t "$($script:MosquittoImageName):$ImageTag" `
        -f Dockerfile.mosquitto `
        .
    $buildExit = $LASTEXITCODE

    if ($buildExit -eq 0) {
        Write-Success "[OK] Imagen Mosquitto construida: $($script:MosquittoImageName):$ImageTag"
    } else {
        Write-Host "[ERROR] Fallo en el build de Mosquitto." -ForegroundColor Red
        exit 1
    }
    Write-Host ""
}

function Invoke-BuildWaterPlantSimulator {
    Write-Info "Construyendo imagen de Water Plant Simulator..."
    Write-Host ""

    if (-not (Test-Path "water-plant-simulator\Dockerfile")) {
        Write-Host "[ERROR] water-plant-simulator/Dockerfile no encontrado." -ForegroundColor Red
        exit 1
    }

    & $script:CE build `
        -t "$($script:WaterPlantSimulatorImageName):$ImageTag" `
        .\water-plant-simulator
    $buildExit = $LASTEXITCODE

    if ($buildExit -eq 0) {
        Write-Success "[OK] Imagen Water Plant Simulator construida: $($script:WaterPlantSimulatorImageName):$ImageTag"
    } else {
        Write-Host "[ERROR] Fallo en el build de Water Plant Simulator." -ForegroundColor Red
        exit 1
    }
    Write-Host ""
}

function Invoke-KubernetesSmoke {
    Write-Info 'Smoke test -- verificando runtime kind...'
    Write-Host ''

    Ensure-KubernetesTooling
    Ensure-KindPortForwardsHealthy
    $apiKey = Get-ApiKey
    if (-not $apiKey) {
        Write-Warning '  API_KEY no encontrada en .env.dev -- el check autenticado se omitira si aplica'
    }

    $passed = 0
    $failed = 0
    $totalChecks = if ($apiKey) { 6 } else { 5 }

    Write-Host -NoNewline "  [1/$totalChecks] Workloads Kubernetes listos ............... "
    try {
        Wait-KubernetesRuntimeReady
        Write-Host 'OK' -ForegroundColor Green
        $passed++
    } catch {
        Write-Host "FAIL $($_.Exception.Message)" -ForegroundColor Red
        $failed++
    }

    Write-Host -NoNewline "  [2/$totalChecks] MQTT puerto $KindMqttHostPort ......................... "
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    try {
        $tcpClient.Connect('localhost', $KindMqttHostPort)
        Write-Host 'OK' -ForegroundColor Green
        $passed++
        $tcpClient.Close()
    } catch {
        Write-Host 'FAIL' -ForegroundColor Red
        $failed++
    }

    Write-Host -NoNewline "  [3/$totalChecks] Web UI $script:KindWebBaseUrl ............. "
    try {
        $r = Invoke-WebRequest -Uri $script:KindWebBaseUrl -UseBasicParsing -TimeoutSec 5 -MaximumRedirection 5 -ErrorAction Stop
        Write-Host "OK HTTP $($r.StatusCode)" -ForegroundColor Green
        $passed++
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -ge 200 -and $code -lt 400) {
            Write-Host "OK HTTP $code" -ForegroundColor Green
            $passed++
        } else {
            Write-Host "FAIL HTTP $code" -ForegroundColor Red
            $failed++
        }
    }

    Write-Host -NoNewline "  [4/$totalChecks] Backend monitor health .................... "
    try {
        $r = Invoke-WebRequest -Uri "$script:KindWebBaseUrl/api/monitor/health" -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
        Write-Host "OK HTTP $($r.StatusCode)" -ForegroundColor Green
        $passed++
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        Write-Host "FAIL HTTP $code" -ForegroundColor Red
        $failed++
    }

    Write-Host -NoNewline "  [5/$totalChecks] Water Plant Simulator readiness .......... "
    try {
        $simulatorPod = & $script:KubectlExecutable get pod -n $KindNamespace -l app.kubernetes.io/name=water-plant-simulator -o jsonpath='{.items[0].metadata.name}'
        if ($LASTEXITCODE -ne 0 -or -not $simulatorPod) {
            throw 'No se encontro el pod del simulador.'
        }

        & $script:KubectlExecutable exec -n $KindNamespace $simulatorPod -- python -m src.healthcheck --mode readiness --max-heartbeat-age 30 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'El healthcheck de readiness del simulador devolvio error.'
        }

        Write-Host 'OK' -ForegroundColor Green
        $passed++
    } catch {
        Write-Host "FAIL $($_.Exception.Message)" -ForegroundColor Red
        $failed++
    }

    if ($apiKey) {
        Write-Host -NoNewline "  [6/$totalChecks] Backend /api/dynsec/roles (API key) ...... "
        try {
            $r = Invoke-WebRequest -Uri "$script:KindWebBaseUrl/api/dynsec/roles" -UseBasicParsing -TimeoutSec 10 -Headers @{ 'X-API-Key' = $apiKey } -ErrorAction Stop
            Write-Host "OK HTTP $($r.StatusCode)" -ForegroundColor Green
            $passed++
        } catch {
            $code = $_.Exception.Response.StatusCode.value__
            Write-Host "FAIL HTTP $code" -ForegroundColor Red
            $failed++
        }
    }

    Write-Host ''
    $total = $passed + $failed
    if ($failed -eq 0) {
        Write-Host "  Resultado: $passed/$total OK" -ForegroundColor Green
        Write-Success '[SMOKE OK] Runtime kind operativo.'
    } else {
        Write-Host "  Resultado: $passed/$total OK, $failed FAIL(s)" -ForegroundColor Red
        Write-Host '[SMOKE FAIL] Ejecuta ''.\deploy.ps1 -Action logs -Runtime kind'' para diagnosticar.' -ForegroundColor Red
    }
    Write-Host ''

    return $failed
}

function Invoke-ComposeSmoke {
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

    $envMap = Get-EnvMap -Path ".env.dev"
    $postgresRequired = Test-PostgresRequired -EnvMap $envMap
    $totalChecks = if ($postgresRequired) { 7 } else { 5 }

    $passed = 0
    $failed = 0
    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'

    # ── 1. Puerto MQTT 1900 ──────────────────────────────────────────────────
    Write-Host -NoNewline "  [1/$totalChecks] MQTT puerto 1900 .......................... "
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
    Write-Host -NoNewline "  [2/$totalChecks] Web UI http://localhost:2000 .............. "
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
    Write-Host -NoNewline "  [3/$totalChecks] Auth API /api/auth/me ..................... "
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
    Write-Host -NoNewline "  [4/$totalChecks] Backend monitor health ..................... "
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

    # ── 5. Backend autenticado: endpoint DynSec ligero ───────────────────────
    if ($apiKey) {
        Write-Host -NoNewline "  [5/$totalChecks] Backend /api/dynsec/roles (API key) ....... "
        $dynsecOk = $false
        $dynsecError = ""
        foreach ($attempt in 1..5) {
            try {
                $r = Invoke-WebRequest -Uri "http://localhost:2000/api/dynsec/roles" -UseBasicParsing -TimeoutSec 10 -Headers @{ 'X-API-Key' = $apiKey } -ErrorAction Stop
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
        Write-Host "  [5/$totalChecks] Backend /api/dynsec/roles .................. OMITIDO (sin API key)" -ForegroundColor Yellow
    }

    if ($postgresRequired) {
        Write-Host -NoNewline "  [6/$totalChecks] bhm-api -> PostgreSQL control-plane ....... "
        $platformPgCheck = Test-ContainerControlPlanePostgresConnectivity -ContainerName "bunkerm-platform"
        if ($platformPgCheck.Success) {
            Write-Host "OK" -ForegroundColor Green
            $passed++
        } else {
            $platformError = if ($platformPgCheck.Output) { $platformPgCheck.Output } else { "error no especificado" }
            Write-Host "FAIL $platformError" -ForegroundColor Red
            $failed++
        }

        Write-Host -NoNewline "  [7/$totalChecks] bhm-reconciler -> PostgreSQL control-plane . "
        $reconcilerPgCheck = Test-ContainerControlPlanePostgresConnectivity -ContainerName "bunkerm-reconciler"
        if ($reconcilerPgCheck.Success) {
            Write-Host "OK" -ForegroundColor Green
            $passed++
        } else {
            $reconcilerError = if ($reconcilerPgCheck.Output) { $reconcilerPgCheck.Output } else { "error no especificado" }
            Write-Host "FAIL $reconcilerError" -ForegroundColor Red
            $failed++
        }
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

function Invoke-Smoke {
    $failures = 0

    if (Test-ComposeRuntime) {
        $failures += Invoke-ComposeSmoke
    }

    if (Test-KindRuntime) {
        if (Test-ComposeRuntime) {
            Write-Host ''
        }

        $failures += Invoke-KubernetesSmoke
    }

    return $failures
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
    Write-Info "Starting Broker Health Manager platform..."
    Write-Host ""
    
    if (-not (Test-Path ".env.dev")) {
        Write-Error ".env.dev not found. Run setup first: .\deploy.ps1 -Action setup"
        exit 1
    }

    $envMap = Get-EnvMap -Path ".env.dev"
    $postgresRequired = Test-PostgresRequired -EnvMap $envMap
    
    # Verificar que la red exista
    Write-Info "Verificando red Docker..."
    $networkExists = Invoke-Expression "$script:CE network ls" | Select-String "bunkerm-network"
    if (-not $networkExists) {
        Write-Info "Creando red bunkerm-network..."
        & $script:CE network create bunkerm-network
        Write-Success "[OK] Red creada"
    }

    # Iniciar mosquitto standalone primero (Broker Health Manager depende de el)
    Write-Info "Iniciando Mosquitto standalone..."
    Invoke-Expression "$script:CCE --env-file .env.dev -f docker-compose.dev.yml up -d mosquitto"
    
    Write-Info "Esperando a que Mosquitto este listo (15 segundos)..."
    Start-Sleep -Seconds 15

    if ($postgresRequired) {
        Write-Info "La configuracion actual requiere PostgreSQL. Iniciando el servicio postgres del baseline Compose-first..."
        Invoke-Expression "$script:CCE --env-file .env.dev -f docker-compose.dev.yml up -d postgres"
        if ($LASTEXITCODE -ne 0) {
            Write-Error "No se pudo iniciar el servicio postgres requerido por la configuracion actual."
            exit 1
        }
        if (-not (Wait-ContainerHealthy -ContainerName "bunkerm-postgres" -TimeoutSeconds 90)) {
            Write-Error "PostgreSQL no alcanzo estado healthy. Revisa: .\deploy.ps1 -Action logs"
            exit 1
        }
    }

    # Iniciar solo el servicio bunkerm. Si la configuracion ya apunta a PostgreSQL,
    # se levanta antes el servicio postgres para que el runtime no arranque degradado.
    Write-Info "Iniciando Broker Health Manager..."
    Invoke-Expression "$script:CCE --env-file .env.dev -f docker-compose.dev.yml up -d bunkerm"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Fallo el arranque del servicio bunkerm. Revisa: .\deploy.ps1 -Action logs"
        exit 1
    }
    
    Write-Host ""
    Write-Success "[OK] Broker Health Manager iniciado!"
    Write-Host ""
    Write-Info "Esperando a que Broker Health Manager esté listo (60 segundos)..."
    Start-Sleep -Seconds 60
    
    Write-Host ""
    Write-Info "URLs de acceso:"
    Write-Host "  - Web UI:    http://localhost:2000" -ForegroundColor Cyan
    Write-Host "  - MQTT:      localhost:1900" -ForegroundColor Cyan
    if ($postgresRequired) {
        Write-Host "  - PostgreSQL: localhost:5432" -ForegroundColor Cyan
    }
    Write-Host ""
    Write-Info "Verificar estado: .\deploy.ps1 -Action status"
    Write-Info "Ver logs: $script:CE logs bunkerm-platform -f"
    Write-Host ""
}

function Invoke-StopBunkerM {
    Write-Info "Deteniendo Broker Health Manager platform..."
    Write-Host ""

    $envMap = Get-EnvMap -Path ".env.dev"
    $postgresRequired = Test-PostgresRequired -EnvMap $envMap
    $services = if ($postgresRequired) { "bunkerm mosquitto postgres" } else { "bunkerm mosquitto" }

    Invoke-Expression "$script:CCE --env-file .env.dev -f docker-compose.dev.yml stop $services"

    Write-Host ""
    Write-Success "[OK] Broker Health Manager y Mosquitto detenidos!"
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

    $platformRunning = & $script:CE ps --format "{{.Names}}" 2>&1 | Select-String "^bunkerm-platform$"
    if (-not $platformRunning) {
        Write-Host "[ERROR] El contenedor bunkerm-platform no esta corriendo." -ForegroundColor Red
        exit 1
    }

    $reconcilerRunning = & $script:CE ps --format "{{.Names}}" 2>&1 | Select-String "^bunkerm-reconciler$"

    # Patch único: copiar todo el directorio app/ de una vez y recargar el proceso uvicorn unificado
    $serviceNames = @('dynsec', 'monitor', 'clientlogs', 'config', 'smart-anomaly')
    foreach ($name in $serviceNames) {
        Write-Info "  Copiando $name..."
    }
    & $script:CE cp "${backendPath}/." "bunkerm-platform:/app/"
    if ($reconcilerRunning) {
        & $script:CE cp "${backendPath}/." "bunkerm-reconciler:/app/"
    }

    # Recargar el proceso uvicorn unificado (puerto 9001)
    $svcPid = & $script:CE exec bunkerm-platform sh -c "ps aux | grep 'uvicorn main:app.*9001' | grep -v grep | awk '{print `$2; exit}'" 2>&1 | Select-Object -First 1
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

    if ($reconcilerRunning) {
        & $script:CE restart bunkerm-reconciler 2>&1 | Out-Null
        Write-Info "    Contenedor bunkerm-reconciler reiniciado para recargar el daemon broker-facing"
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
