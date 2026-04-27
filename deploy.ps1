# ==========================================
# Broker Health Manager - Deployment Script for Windows
# ==========================================
# This script automates the deployment process on Windows

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet(
        'setup', 'start', 'stop', 'restart', 'status', 'logs', 'clean',
        'build', 'build-mosquitto',
        'update-frontend', 'update-api', 'update-identity', 'update-mosquitto', 'update-all',
        'rollout', 'redeploy', 'env-sync', 'db-migrate',
        'patch-frontend', 'patch-backend', 'reload-mosquitto',
        'test', 'smoke'
    )]
    [string]$Action = 'setup',

    # Componente objetivo para la accion 'rollout'
    [Parameter(Mandatory=$false)]
    [ValidateSet('frontend', 'api', 'identity', 'mosquitto', 'alerts', 'all')]
    [string]$Component = 'all',

    [Parameter(Mandatory=$false)]
    [string]$ImageTag = '2.0.0',

    [Parameter(Mandatory=$false)]
    [ValidateSet('kind')]
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
    [string]$KindPortForwardAddress = '127.0.0.1',
    
    [Parameter(Mandatory=$false)]
    [switch]$Follow
)

$ErrorActionPreference = "Stop"

$ErrorActionPreference = "Stop"

# Motores de contenedor (se asignan en Get-RuntimeEngines al inicio)
$script:CE = "docker"    # Container Engine: docker o podman
$script:KindExecutable = $null
$script:KubectlExecutable = $null
$script:ImageTag = '2.0.0'
$script:BhmFrontendImageName = 'bhm-frontend'
$script:BhmApiImageName = 'bhm-api'
$script:BhmIdentityImageName = 'bhm-identity'
$script:MosquittoImageName = 'bhm-mosquitto'
$script:KindBaseImages = @(
    'postgres:16-alpine'
)
$script:KindImages = @(
    "$($script:BhmFrontendImageName):$($script:ImageTag)",
    "$($script:BhmApiImageName):$($script:ImageTag)",
    "$($script:BhmIdentityImageName):$($script:ImageTag)",
    "$($script:MosquittoImageName):$($script:ImageTag)"
)
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

function Get-PreferredPodmanMachineName {
    $machines = @(Get-PodmanMachineState)
    if ($machines.Count) {
        $preferredMachine = $machines | Where-Object { $_.Default -eq $true } | Select-Object -First 1
        if (-not $preferredMachine) {
            $preferredMachine = $machines | Select-Object -First 1
        }

        $machineName = "$($preferredMachine.Name)".Trim()
        if ($machineName) {
            return $machineName
        }
    }

    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $connectionLines = @(podman system connection list 2>&1)
    $connectionExitCode = $LASTEXITCODE
    $ErrorActionPreference = $savedPref

    if ($connectionExitCode -eq 0) {
        foreach ($line in $connectionLines) {
            $trimmedLine = "$line".Trim()
            if (-not $trimmedLine -or $trimmedLine -like 'Name *') {
                continue
            }

            if ($trimmedLine -match '^(?<name>\S+)(?:\s+.+?)?\s+(?<default>true|false)\s+(?<rw>true|false)\s*$') {
                $connectionName = $Matches['name']
                if ($Matches['default'] -eq 'true') {
                    return ($connectionName -replace '-root$', '')
                }
            }
        }

        foreach ($line in $connectionLines) {
            $trimmedLine = "$line".Trim()
            if (-not $trimmedLine -or $trimmedLine -like 'Name *') {
                continue
            }

            if ($trimmedLine -match '^(?<name>\S+)') {
                return (($Matches['name']) -replace '-root$', '')
            }
        }
    }

    if ($env:PODMAN_MACHINE_NAME) {
        return $env:PODMAN_MACHINE_NAME.Trim()
    }

    return 'podman-machine-default'
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

    $machineName = Get-PreferredPodmanMachineName
    if (-not $machineName) {
        throw 'No se pudo determinar la maquina Podman a recuperar.'
    }

    Write-Warning "Podman no respondio. Intentando recuperar la maquina '$machineName'..."

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
            Write-Success "[OK] Podman recuperado sobre la maquina '$machineName'."
            return
        }

        Start-Sleep -Seconds 3
    }

    Invoke-PodmanWslRecovery -MachineName $machineName
}

function Restart-PodmanMachine {
    $machineName = Get-PreferredPodmanMachineName
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
    } elseif ($dockerFound) {
        $script:CE = "docker"
        Write-Info "Motor de contenedores: Docker"
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

function Test-KindRuntime {
    return $true
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

function Ensure-LocalImagePresent {
    param(
        [string]$ImageName,
        [switch]$AllowPull
    )

    if (Test-LocalImagePresent -ImageName $ImageName) {
        return $true
    }

    if (-not $AllowPull) {
        return $false
    }

    Write-Info "Imagen base no encontrada en cache local: $ImageName. Intentando descargarla una vez..."
    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $script:CE pull $ImageName 2>&1 | Out-Null
    $pullExitCode = $LASTEXITCODE
    $ErrorActionPreference = $savedPref

    return ($pullExitCode -eq 0 -and (Test-LocalImagePresent -ImageName $ImageName))
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

function Get-ProcessCommandLine {
    param(
        [int]$ProcessId
    )

    if ($ProcessId -le 0) {
        return ''
    }

    try {
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
        if ($null -eq $processInfo -or $null -eq $processInfo.CommandLine) {
            return ''
        }
        return [string]$processInfo.CommandLine
    } catch {
        return ''
    }
}

function Stop-KindPortForwardListeners {
    param(
        [int[]]$Ports
    )

    $conflicts = @(Get-ListeningPortProcesses -Ports $Ports)
    if (-not $conflicts.Count) {
        return @()
    }

    $kindContext = "kind-$KindClusterName".ToLowerInvariant()
    $pidsToStop = @{}

    foreach ($conflict in $conflicts) {
        $processName = "$($conflict.ProcessName)".ToLowerInvariant()
        if ($processName -notlike 'kubectl*') {
            continue
        }

        $commandLine = (Get-ProcessCommandLine -ProcessId ([int]$conflict.Pid)).ToLowerInvariant()
        if (-not $commandLine.Contains('port-forward')) {
            continue
        }
        if (-not $commandLine.Contains($kindContext)) {
            continue
        }

        $pidsToStop[[string]([int]$conflict.Pid)] = [int]$conflict.Pid
    }

    foreach ($processIdToStop in $pidsToStop.Values) {
        Stop-Process -Id $processIdToStop -Force -ErrorAction SilentlyContinue
    }

    if ($pidsToStop.Count -gt 0) {
        Start-Sleep -Seconds 2
    }

    return @(Get-ListeningPortProcesses -Ports $Ports)
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

    $conflicts = @(Stop-KindPortForwardListeners -Ports $ports)
    if (-not $conflicts.Count) {
        return
    }

    $summary = ($conflicts | ForEach-Object { "$($_.ProcessName) pid=$($_.Pid) port=$($_.LocalPort)" }) -join '; '
    throw "Los puertos del laboratorio kind ya estan ocupados: $summary"
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
    ) + $Mappings + @('--address', $KindPortForwardAddress)

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

function Wait-KubernetesApiResponsive {
    param(
        [int]$TimeoutSeconds = 45,
        [int]$IntervalSeconds = 3
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $savedPref = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & $script:KubectlExecutable --context $script:KindKubectlContext get namespace $KindNamespace 2>&1 | Out-Null
        $kubectlExitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedPref

        if ($kubectlExitCode -eq 0) {
            return $true
        }

        Start-Sleep -Seconds $IntervalSeconds
    }

    return $false
}

function Start-KindPortForwards {
    Ensure-KubernetesTooling

    $lastFailure = $null
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        Stop-KindPortForwards

        if (-not (Wait-KubernetesApiResponsive -TimeoutSeconds 45)) {
            $lastFailure = "El API server del cluster kind no respondio a tiempo antes de abrir los port-forward."
            if ($attempt -lt 3) {
                Write-Warning "Reintentando port-forward tras espera adicional del API server (intento $attempt/3)..."
                continue
            }

            throw $lastFailure
        }

        try {
            $entries = @(
                (Start-KindPortForwardProcess -Name 'frontend' -Resource 'service/bhm-frontend' -Mappings @("${KindWebHostPort}:2000") -LocalPorts @($KindWebHostPort)),
                (Start-KindPortForwardProcess -Name 'mosquitto' -Resource 'service/mosquitto' -Mappings @("${KindMqttHostPort}:1900", "${KindMqttWsHostPort}:9001") -LocalPorts @($KindMqttHostPort, $KindMqttWsHostPort))
            )

            foreach ($entry in $entries) {
                Wait-KindPortForwardReady -Entry $entry
            }

            $entries | ConvertTo-Json | Set-Content -Path $script:KindPortForwardStatePath -Encoding ASCII
            return
        } catch {
            $lastFailure = $_
            Stop-KindPortForwards
            if ($attempt -lt 3) {
                Write-Warning "Fallo transitorio al levantar port-forward de kind (intento $attempt/3). Reintentando..."
                Start-Sleep -Seconds 5
                continue
            }
        }
    }

    throw $lastFailure
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

function Test-KindClusterExists {
    Ensure-KubernetesTooling

    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $clusters = & $script:KindExecutable get clusters 2>&1
    $kindExitCode = $LASTEXITCODE
    $ErrorActionPreference = $savedPref

    return ($kindExitCode -eq 0 -and ($clusters | Where-Object { $_ -eq $KindClusterName }))
}

# ---------------------------------------------------------------------------
# Kubernetes readiness helpers
# ---------------------------------------------------------------------------

# Returns the first terminal waiting reason found for pods belonging to a
# workload (e.g. CrashLoopBackOff, ImagePullBackOff). Returns $null when no
# terminal state is found or when kubectl itself fails (avoids false positives).
function Get-WorkloadTerminalFailureReason {
    param([string]$ResourceName, [string]$Namespace)

    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $jsonRaw = & $script:KubectlExecutable --context $script:KindKubectlContext `
        get pods -n $Namespace `
        -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .status.containerStatuses[*]}{.state.waiting.reason}{.state.terminated.reason}{"\n"}{end}{end}' 2>&1
    $ErrorActionPreference = $savedPref

    if ($LASTEXITCODE -ne 0) { return $null }

    $terminalReasons = @(
        'CrashLoopBackOff', 'ImagePullBackOff', 'ErrImageNeverPull', 'ErrImagePull',
        'InvalidImageName', 'CreateContainerConfigError', 'RunContainerError'
    )
    foreach ($line in ($jsonRaw -split "`n")) {
        if ($line -match [regex]::Escape($ResourceName)) {
            foreach ($reason in $terminalReasons) {
                if ($line -match $reason) { return $reason }
            }
        }
    }
    return $null
}

# Prints pod list + last 40 lines of describe for $Target to help diagnose
# stuck or failing workloads.
function Write-WorkloadDiagnostics {
    param([string]$Target, [string]$Namespace)

    Write-Host "`n=== DIAGNOSTICO: $Target ===" -ForegroundColor Yellow
    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    Write-Host "--- kubectl get pods ---" -ForegroundColor Yellow
    & $script:KubectlExecutable --context $script:KindKubectlContext get pods -n $Namespace 2>&1 | Out-Host
    Write-Host "--- kubectl describe $Target (ultimas 40 lineas) ---" -ForegroundColor Yellow
    & $script:KubectlExecutable --context $script:KindKubectlContext describe $Target -n $Namespace 2>&1 |
        Select-Object -Last 40 | Out-Host
    $ErrorActionPreference = $savedPref
    
    # Diagnóstico específico para Mosquitto
    if ($Target -match 'mosquitto') {
        Write-Host "`n--- Diagnostico especifico de Mosquitto ---" -ForegroundColor Yellow
        Write-Host "`nVerifica que .env.dev tiene MQTT_USERNAME y MQTT_PASSWORD" -ForegroundColor Cyan
        Write-Host "Luego ejecuta: .\deploy.ps1 -Action diagnose-mosquitto para un diagnostico completo" -ForegroundColor Cyan
    }
    
    # Diagnóstico para bhm-api (probablemente falla por Mosquitto)
    if ($Target -match 'bhm-api' -or $Target -match 'bhm-identity') {
        Write-Host "`n--- Diagnostico para $Target ---" -ForegroundColor Yellow
        Write-Host "[!] Este pod probablemente falla porque mosquitto no esta listo." -ForegroundColor Yellow
        Write-Host "    Asegurate de que Mosquitto se inicie primero: .\deploy.ps1 -Action start" -ForegroundColor Gray
    }
}

function Wait-KubernetesRuntimeReady {
    Ensure-KubernetesTooling

    # Per-workload overall budget in minutes. Sized to cover the pod's own
    # startupProbe window plus a generous margin for slow/CI environments.
    $workloadBudgets = @{
        'statefulset/postgres'          = 5
        'statefulset/mosquitto'         = 5
        'deployment/bhm-identity'       = 5
        'deployment/bhm-frontend'       = 5
        'deployment/bhm-api'            = 5
        'deployment/bhm-alert-delivery' = 5
    }

    # Each kubectl rollout status call is given this window before we check again.
    $perAttemptTimeout = '90s'

    $orderedTargets = @(
        'statefulset/postgres',
        'statefulset/mosquitto',
        'deployment/bhm-identity',
        'deployment/bhm-frontend',
        'deployment/bhm-api',
        'deployment/bhm-alert-delivery'
    )

    foreach ($target in $orderedTargets) {
        $budgetMinutes = $workloadBudgets[$target]
        $deadline = (Get-Date).AddMinutes($budgetMinutes)
        $lastRolloutOutput = ''

        Write-Host "[INFO] Esperando $target (presupuesto: ${budgetMinutes} min)..." -ForegroundColor Cyan

        while ((Get-Date) -lt $deadline) {
            $savedPref = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            $rolloutOutput = & $script:KubectlExecutable --context $script:KindKubectlContext `
                rollout status $target -n $KindNamespace --timeout=$perAttemptTimeout 2>&1
            $rolloutExitCode = $LASTEXITCODE
            $ErrorActionPreference = $savedPref

            if ($rolloutExitCode -eq 0) {
                Write-Success "[OK] $target listo."
                $lastRolloutOutput = ''
                break
            }

            $lastRolloutOutput = ($rolloutOutput | Out-String)
            $normalizedOutput = $lastRolloutOutput.ToLowerInvariant()

            # ── Network-level transient errors: API server not yet reachable ──
            $isNetworkError = (
                $normalizedOutput.Contains('tls handshake timeout') -or
                $normalizedOutput.Contains('unable to connect to the server') -or
                $normalizedOutput.Contains('i/o timeout') -or
                $normalizedOutput.Contains('connection refused') -or
                $normalizedOutput.Contains('eof')
            )
            if ($isNetworkError) {
                Write-Warning "Error de red transitorio al esperar $target. Reintentando en 5 s..."
                Start-Sleep -Seconds 5
                continue
            }

            # ── Rollout still in progress (pod not ready yet) ────────────────
            $isRolloutPending = (
                $normalizedOutput.Contains('timed out waiting for the condition') -or
                $normalizedOutput.Contains('updated replicas are available') -or
                $normalizedOutput.Contains('waiting for deployment')
            )
            if ($isRolloutPending) {
                # Fast-fail if the pod has crashed or has a pull error.
                $resourceName = $target -replace '^[^/]+/', ''
                $terminalReason = Get-WorkloadTerminalFailureReason `
                    -ResourceName $resourceName -Namespace $KindNamespace
                if ($terminalReason) {
                    Write-Error "$target esta en estado terminal ($terminalReason) -- abortando."
                    Write-WorkloadDiagnostics -Target $target -Namespace $KindNamespace
                    exit 1
                }
                $remaining = [int](($deadline - (Get-Date)).TotalSeconds)
                Write-Warning "$target aun no listo ($($remaining)s restantes del presupuesto). Reintentando..."
                continue
            }

            # ── Unexpected error ──────────────────────────────────────────────
            Write-Error "$target reporto un error inesperado: $lastRolloutOutput"
            Write-WorkloadDiagnostics -Target $target -Namespace $KindNamespace
            exit 1
        }

        if ($lastRolloutOutput) {
            Write-Error "$target no alcanzo estado listo en ${budgetMinutes} minutos."
            Write-WorkloadDiagnostics -Target $target -Namespace $KindNamespace
            exit 1
        }
    }
}

function Set-KindWorkloadReplicas {
    param(
        [ValidateRange(0, 10)]
        [int]$ReplicaCount
    )

    Ensure-KubernetesTooling

    $workloads = @(
        'statefulset/postgres',
        'statefulset/mosquitto',
        'deployment/bhm-frontend',
        'deployment/bhm-api',
        'deployment/bhm-alert-delivery'
    )

    foreach ($workload in $workloads) {
        & $script:KubectlExecutable get $workload -n $KindNamespace *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "No se encontro $workload en kind; se omite el escalado."
            continue
        }

        Write-Info "Escalando $workload a $ReplicaCount replica(s)..."
        & $script:KubectlExecutable scale $workload -n $KindNamespace --replicas=$ReplicaCount *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Error "No se pudo escalar $workload a $ReplicaCount replica(s)."
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
    foreach ($imageName in $script:KindBaseImages) {
        if (-not (Ensure-LocalImagePresent -ImageName $imageName -AllowPull)) {
            Write-Error "No se encontro la imagen base $imageName y no se pudo dejar disponible en cache local. El laboratorio kind no debe depender de pulls en caliente para PostgreSQL."
            exit 1
        }
    }

    if (Test-KindClusterExists) {
        Write-Info "Reutilizando cluster kind '$KindClusterName' para preservar PVC y estado del broker/PostgreSQL..."
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
        -LocalImages ($script:KindImages + $script:KindBaseImages) `
        -BhmFrontendImage "localhost/$($script:BhmFrontendImageName):$ImageTag" `
        -BhmApiImage "localhost/$($script:BhmApiImageName):$ImageTag" `
        -BhmIdentityImage "localhost/$($script:BhmIdentityImageName):$ImageTag" `
        -MosquittoImage "localhost/$($script:MosquittoImageName):$ImageTag"

    if ($LASTEXITCODE -ne 0) {
        Write-Error 'Fallo el arranque del laboratorio kind. Revisa la salida anterior.'
        exit 1
    }

    Wait-KubernetesRuntimeReady
    Start-KindPortForwards
}

function Invoke-StopKindRuntime {
    param(
        [switch]$DeleteCluster
    )

    Ensure-KubernetesTooling
    Stop-KindPortForwards
    if (-not (Test-KindClusterExists)) {
        Write-Info "El cluster kind '$KindClusterName' no esta creado."
        return
    }

    if (-not $DeleteCluster) {
        Set-KindWorkloadReplicas -ReplicaCount 0
        Write-Success "[OK] Workloads kind detenidos. Cluster '$KindClusterName' y PVC preservados."
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

    Invoke-StartKindRuntime

    Write-Host ''
    Write-Info 'Ejecutando smoke test del stack...'
    $smokeFailures = Invoke-Smoke
    if ($smokeFailures -gt 0) {
        Write-Warning "[AVISO] El smoke test detecto $smokeFailures fallo(s). El stack sigue corriendo para debug manual."
        Write-Host "  Logs: .\deploy.ps1 -Action logs" -ForegroundColor Yellow
    }

    Write-Host ''
    Write-Info 'Service URLs:'
    Write-Host "  - kind Web UI:       $script:KindWebBaseUrl" -ForegroundColor Cyan
    Write-Host "  - kind MQTT:         localhost:$KindMqttHostPort" -ForegroundColor Cyan
    Write-Host "  - kind MQTT WS:      localhost:$KindMqttWsHostPort" -ForegroundColor Cyan

    Write-Host ''
    Write-Info "Run health check: .\deploy.ps1 -Action status"
    Write-Host ''
}

function Invoke-Stop {
    Write-Info "Stopping services..."
    Write-Host ""

    Invoke-StopKindRuntime

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

    Ensure-KubernetesTooling
    Write-Host 'Workloads kind:' -ForegroundColor Yellow
    if (Test-KindClusterExists) {
        & $script:KubectlExecutable get pods,svc -n $KindNamespace
    } else {
        Write-Warning "El cluster kind '$KindClusterName' no existe."
    }
    Write-Host ''
}

function Invoke-Logs {
    Write-Info "Showing logs..."
    Write-Host ""

    Ensure-KubernetesTooling
    if (-not (Test-KindClusterExists)) {
        Write-Warning "El cluster kind '$KindClusterName' no existe."
        return
    }

    if ($Follow) {
        Write-Info 'Following bhm-frontend logs in kind (Ctrl+C to exit)...'
        & $script:KubectlExecutable logs deployment/bhm-frontend -n $KindNamespace -f --all-containers=true
    } else {
        Write-Info 'kind pods:'
        & $script:KubectlExecutable get pods -n $KindNamespace
        Write-Host ''
        Write-Info 'bhm-frontend:'
        & $script:KubectlExecutable logs deployment/bhm-frontend -n $KindNamespace --all-containers=true --tail=80
        Write-Host ''
        Write-Info 'bhm-api:'
        & $script:KubectlExecutable logs deployment/bhm-api -n $KindNamespace --tail=80
        Write-Host ''
        Write-Info 'mosquitto/reconciler:'
        & $script:KubectlExecutable logs statefulset/mosquitto -n $KindNamespace -c reconciler --tail=80
    }
}

function Invoke-Clean {
    Write-Warning "This will remove all containers, volumes, and data!"
    $confirm = Read-Host "Are you sure? Type 'yes' to confirm"
    
    if ($confirm -eq 'yes') {
        Write-Info "Cleaning up..."
        Write-Host ""

        Invoke-StopKindRuntime -DeleteCluster

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

# ---------------------------------------------------------------------------
# Build helpers - una funcion por imagen para permitir builds individuales
# ---------------------------------------------------------------------------

function Invoke-NormalizeShellScripts {
    Write-Info "Normalizando line endings en scripts shell..."
    Get-ChildItem bunkerm-source -Recurse -Filter "*.sh" | ForEach-Object {
        $content = [System.IO.File]::ReadAllText($_.FullName)
        if ($content -match "`r`n") {
            $fixed = $content -replace "`r`n", "`n"
            [System.IO.File]::WriteAllText($_.FullName, $fixed, [System.Text.UTF8Encoding]::new($false))
            Write-Info "  Normalizado: $($_.Name)"
        }
    }
}

function Invoke-EnsureBunkerMSource {
    if (-not (Test-Path "bunkerm-source")) {
        Write-Host "[ERROR] bunkerm-source/ no encontrado." -ForegroundColor Red
        Write-Host "  git clone https://github.com/bunkeriot/BunkerM bunkerm-source" -ForegroundColor Yellow
        exit 1
    }
}

function Invoke-BuildFrontendImage {
    Invoke-EnsureBunkerMSource
    Write-Info "Construyendo $($script:BhmFrontendImageName):$ImageTag ..."
    $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
    & $script:CE build `
        -t "$($script:BhmFrontendImageName):$ImageTag" `
        -f bunkerm-source/Dockerfile.frontend `
        bunkerm-source
    $buildExit = $LASTEXITCODE
    $ErrorActionPreference = $savedPref
    if ($buildExit -ne 0) {
        Write-Host "[ERROR] Fallo en el build de bhm-frontend. Revisa los logs de arriba." -ForegroundColor Red
        exit 1
    }
    Write-Success "[OK] $($script:BhmFrontendImageName):$ImageTag construida."
}

function Invoke-BuildApiImage {
    Invoke-EnsureBunkerMSource
    Write-Info "Construyendo $($script:BhmApiImageName):$ImageTag ..."
    $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
    & $script:CE build `
        -t "$($script:BhmApiImageName):$ImageTag" `
        -f bunkerm-source/Dockerfile.api `
        bunkerm-source
    $buildExit = $LASTEXITCODE
    $ErrorActionPreference = $savedPref
    if ($buildExit -ne 0) {
        Write-Host "[ERROR] Fallo en el build de bhm-api. Revisa los logs de arriba." -ForegroundColor Red
        exit 1
    }
    Write-Success "[OK] $($script:BhmApiImageName):$ImageTag construida."
}

function Invoke-BuildIdentityImage {
    Invoke-EnsureBunkerMSource
    Write-Info "Construyendo $($script:BhmIdentityImageName):$ImageTag ..."
    $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
    & $script:CE build `
        -t "$($script:BhmIdentityImageName):$ImageTag" `
        -f bunkerm-source/Dockerfile.identity `
        bunkerm-source
    $buildExit = $LASTEXITCODE
    $ErrorActionPreference = $savedPref
    if ($buildExit -ne 0) {
        Write-Host "[ERROR] Fallo en el build de bhm-identity. Revisa los logs de arriba." -ForegroundColor Red
        exit 1
    }
    Write-Success "[OK] $($script:BhmIdentityImageName):$ImageTag construida."
}

function Invoke-Build {
    Write-Info "Construyendo todas las imagenes de Broker Health Manager..."
    Write-Host ""

    Invoke-EnsureBunkerMSource

    # Construir Mosquitto primero
    Invoke-BuildMosquitto

    Invoke-NormalizeShellScripts

    Invoke-BuildFrontendImage
    Invoke-BuildApiImage
    Invoke-BuildIdentityImage

    Write-Host ""
    Write-Success "[OK] Imagenes BHM construidas: $($script:BhmFrontendImageName):$ImageTag, $($script:BhmApiImageName):$ImageTag, $($script:BhmIdentityImageName):$ImageTag y $($script:MosquittoImageName):$ImageTag"
    Write-Info "Ahora ejecuta: .\deploy.ps1 -Action start"
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

# ---------------------------------------------------------------------------
# Kind image loading helper
# ---------------------------------------------------------------------------

function Invoke-LoadImageIntoKind {
    param(
        [Parameter(Mandatory=$true)]
        [string]$ImageName
    )

    Ensure-KubernetesTooling

    Write-Info "Cargando imagen '$ImageName' en el cluster kind '$KindClusterName'..."

    if ($script:CE -eq 'podman') {
        $tmpArchive = Join-Path $env:TEMP ("bhm-kind-load-" + [System.IO.Path]::GetRandomFileName() + ".tar")
        try {
            $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
            & $script:CE save --format oci-archive -o $tmpArchive $ImageName 2>&1 | Out-Null
            $saveExit = $LASTEXITCODE
            $ErrorActionPreference = $savedPref

            if ($saveExit -ne 0) {
                throw "podman save fallo para '$ImageName'."
            }

            $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
            & $script:KindExecutable load image-archive $tmpArchive --name $KindClusterName 2>&1
            $loadExit = $LASTEXITCODE
            $ErrorActionPreference = $savedPref

            if ($loadExit -ne 0) {
                throw "kind load image-archive fallo para '$ImageName'."
            }
        } finally {
            if (Test-Path $tmpArchive) {
                Remove-Item $tmpArchive -Force -ErrorAction SilentlyContinue
            }
        }
    } else {
        $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
        & $script:KindExecutable load docker-image $ImageName --name $KindClusterName 2>&1
        $loadExit = $LASTEXITCODE
        $ErrorActionPreference = $savedPref

        if ($loadExit -ne 0) {
            throw "kind load docker-image fallo para '$ImageName'."
        }
    }

    Write-Success "[OK] Imagen '$ImageName' cargada en kind."
}

# ---------------------------------------------------------------------------
# Rollout helper
# ---------------------------------------------------------------------------

function Invoke-RolloutRestart {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Resource,
        [int]$TimeoutSeconds = 120
    )

    Ensure-KubernetesTooling

    Write-Info "Rollout restart: $Resource ..."
    $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
    & $script:KubectlExecutable --context $script:KindKubectlContext rollout restart $Resource -n $KindNamespace 2>&1
    $restartExit = $LASTEXITCODE
    $ErrorActionPreference = $savedPref

    if ($restartExit -ne 0) {
        throw "kubectl rollout restart fallo para '$Resource'."
    }

    $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
    & $script:KubectlExecutable --context $script:KindKubectlContext rollout status $Resource -n $KindNamespace --timeout="${TimeoutSeconds}s" 2>&1
    $statusExit = $LASTEXITCODE
    $ErrorActionPreference = $savedPref

    if ($statusExit -ne 0) {
        throw "kubectl rollout status indico fallo o timeout para '$Resource'."
    }

    Write-Success "[OK] $Resource listo."
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
    $totalChecks = if ($apiKey) { 5 } else { 4 }

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

    if ($apiKey) {
        Write-Host -NoNewline "  [5/$totalChecks] Backend /api/dynsec/roles (API key) ...... "
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

function Invoke-Smoke {
    return Invoke-KubernetesSmoke
}

function Invoke-Test {
    # Ejecuta los tests de pytest dentro del pod bhm-api en Kubernetes.
    # Requiere que el cluster este corriendo: .\deploy.ps1 -Action start
    Write-Info "Ejecutando tests dentro del pod bhm-api en Kubernetes..."
    Write-Host ""

    Ensure-KubernetesTooling
    if (-not (Test-KindClusterExists)) {
        Write-Host "[ERROR] El cluster kind '$KindClusterName' no existe. Ejecuta: .\deploy.ps1 -Action start" -ForegroundColor Red
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
    $apiPod = & $script:KubectlExecutable get pods -n $KindNamespace -l app.kubernetes.io/name=bhm-api --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>&1
    if (-not $apiPod -or $LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] No se encontro pod bhm-api en estado Running." -ForegroundColor Red
        exit 1
    }
    if ($testDir) {
        & $script:KubectlExecutable exec -n $KindNamespace $apiPod -- pytest $testDir -v
    } else {
        $backendTestsExist = & $script:KubectlExecutable exec -n $KindNamespace $apiPod -- sh -c "test -d /app/tests `&`& echo yes `|`| echo no" 2>&1
        if ($backendTestsExist -match 'yes') {
            Write-Info "Suite: backend unificado (/app/tests)"
            & $script:KubectlExecutable exec -n $KindNamespace $apiPod -- pytest /app/tests -v
        } else {
            Write-Warning "/app/tests no existe aun. Implementar Fase T del QUALITY_PLAN.md"
        }
        Write-Host ""
        Write-Info "Suite: smart-anomaly (/app/smart-anomaly/tests)"
        & $script:KubectlExecutable exec -n $KindNamespace $apiPod -- pytest /app/smart-anomaly/tests -v
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
    Write-Info "Enviando senal de recarga a Mosquitto en Kubernetes..."
    Ensure-KubernetesTooling
    if (-not (Test-KindClusterExists)) {
        Write-Host "[ERROR] El cluster kind '$KindClusterName' no existe. Ejecuta: .\deploy.ps1 -Action start" -ForegroundColor Red
        exit 1
    }
    $mqPod = & $script:KubectlExecutable get pods -n $KindNamespace -l app.kubernetes.io/name=mosquitto --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>&1
    if (-not $mqPod -or $LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] No se encontro pod mosquitto en estado Running." -ForegroundColor Red
        exit 1
    }
    & $script:KubectlExecutable exec -n $KindNamespace $mqPod -- sh -c "touch /var/lib/mosquitto/.reload"
    Write-Success "[OK] Senal enviada. Mosquitto recargara su configuracion en ~2 segundos."
    Write-Host ""
}

function Invoke-StartBunkerM {
    Write-Warning "'start-bunkerm' ha sido eliminado. Usa: .\deploy.ps1 -Action start"
    Invoke-Start
}

function Invoke-StopBunkerM {
    Write-Warning "'stop-bunkerm' ha sido eliminado. Usa: .\deploy.ps1 -Action stop"
    Invoke-StopKindRuntime
}

function Invoke-PatchFrontend {
    Write-Info "Hot-patch del frontend Next.js (Kubernetes)..."
    Write-Host ""

    Ensure-KubernetesTooling
    if (-not (Test-KindClusterExists)) {
        Write-Host "[ERROR] El cluster kind '$KindClusterName' no existe. Ejecuta: .\deploy.ps1 -Action start" -ForegroundColor Red
        exit 1
    }

    $frontendPath = Join-Path $PSScriptRoot "bunkerm-source\frontend"
    if (-not (Test-Path $frontendPath)) {
        Write-Host "[ERROR] bunkerm-source/frontend no encontrado." -ForegroundColor Red
        exit 1
    }

    Write-Info "Copiando fuentes del frontend al pod bhm-frontend..."
    $pod = & $script:KubectlExecutable get pods -n $KindNamespace -l app.kubernetes.io/name=bhm-frontend --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>&1
    if (-not $pod -or $LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] No se encontro un pod bhm-frontend en estado Running." -ForegroundColor Red
        exit 1
    }

    & $script:KubectlExecutable cp "${frontendPath}/." "$KindNamespace/${pod}:/nextjs/" 2>&1 | Out-Null
    Write-Info "Reiniciando deployment bhm-frontend..."
    & $script:KubectlExecutable rollout restart deployment/bhm-frontend -n $KindNamespace
    & $script:KubectlExecutable rollout status deployment/bhm-frontend -n $KindNamespace --timeout=90s

    Write-Success "[OK] Frontend reiniciado en Kubernetes."
    Write-Host "  Recarga la pagina del navegador (Ctrl+Shift+R) para ver los cambios." -ForegroundColor Cyan
    Write-Host ""
}

function Invoke-PatchBackend {
    Write-Info "Hot-patch del backend Python (Kubernetes)..."
    Write-Host ""

    Ensure-KubernetesTooling
    if (-not (Test-KindClusterExists)) {
        Write-Host "[ERROR] El cluster kind '$KindClusterName' no existe. Ejecuta: .\deploy.ps1 -Action start" -ForegroundColor Red
        exit 1
    }

    $backendPath = Join-Path $PSScriptRoot "bunkerm-source\backend\app"
    if (-not (Test-Path $backendPath)) {
        Write-Host "[ERROR] bunkerm-source/backend/app no encontrado." -ForegroundColor Red
        exit 1
    }

    Write-Info "Copiando fuentes del backend al pod bhm-api..."
    $pod = & $script:KubectlExecutable get pods -n $KindNamespace -l app.kubernetes.io/name=bhm-api --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>&1
    if (-not $pod -or $LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] No se encontro un pod bhm-api en estado Running." -ForegroundColor Red
        exit 1
    }

    & $script:KubectlExecutable cp "${backendPath}/." "$KindNamespace/${pod}:/app/" 2>&1 | Out-Null

    Write-Info "Reiniciando deployment bhm-api..."
    & $script:KubectlExecutable rollout restart deployment/bhm-api -n $KindNamespace
    & $script:KubectlExecutable rollout status deployment/bhm-api -n $KindNamespace --timeout=90s

    Write-Success "[OK] Backend reiniciado en Kubernetes."
    Write-Host ""
}

# ---------------------------------------------------------------------------
# Acciones de actualizacion por componente (Phase C)
# ---------------------------------------------------------------------------

function Invoke-EnsureClusterRunning {
    Ensure-KubernetesTooling
    if (-not (Test-KindClusterExists)) {
        Write-Host "[ERROR] El cluster kind '$KindClusterName' no existe. Ejecuta: .\deploy.ps1 -Action start" -ForegroundColor Red
        exit 1
    }
}

function Invoke-UpdateFrontend {
    Write-Info "Actualizando componente: bhm-frontend (build + load + rollout)..."
    Write-Host ""
    Invoke-EnsureClusterRunning
    Invoke-NormalizeShellScripts
    Invoke-BuildFrontendImage
    Invoke-LoadImageIntoKind -ImageName "$($script:BhmFrontendImageName):$ImageTag"
    Invoke-RolloutRestart -Resource 'deployment/bhm-frontend'
    Write-Host ""
    Write-Success "[OK] bhm-frontend actualizado."
    Write-Host ""
}

function Invoke-UpdateApi {
    Write-Info "Actualizando componente: bhm-api + bhm-alert-delivery (build + load + rollout)..."
    Write-Host ""
    Invoke-EnsureClusterRunning
    Invoke-NormalizeShellScripts
    Invoke-BuildApiImage
    Invoke-LoadImageIntoKind -ImageName "$($script:BhmApiImageName):$ImageTag"
    Invoke-RolloutRestart -Resource 'deployment/bhm-api'
    Invoke-RolloutRestart -Resource 'deployment/bhm-alert-delivery'
    Write-Host ""
    Write-Success "[OK] bhm-api y bhm-alert-delivery actualizados."
    Write-Host ""
}

function Invoke-UpdateIdentity {
    Write-Info "Actualizando componente: bhm-identity (build + load + rollout)..."
    Write-Host ""
    Invoke-EnsureClusterRunning
    Invoke-NormalizeShellScripts
    Invoke-BuildIdentityImage
    Invoke-LoadImageIntoKind -ImageName "$($script:BhmIdentityImageName):$ImageTag"
    Invoke-RolloutRestart -Resource 'deployment/bhm-identity'
    Write-Host ""
    Write-Success "[OK] bhm-identity actualizado."
    Write-Host ""
}

function Invoke-UpdateMosquitto {
    Write-Info "Actualizando componente: mosquitto (build + load + rollout)..."
    Write-Host ""
    Invoke-EnsureClusterRunning
    Invoke-BuildMosquitto
    Invoke-LoadImageIntoKind -ImageName "$($script:MosquittoImageName):$ImageTag"
    Invoke-RolloutRestart -Resource 'statefulset/mosquitto'
    Write-Host ""
    Write-Success "[OK] Mosquitto actualizado."
    Write-Host ""
}

function Invoke-UpdateAll {
    Write-Info "Actualizando todos los componentes..."
    Write-Host ""
    Invoke-EnsureClusterRunning
    Invoke-UpdateFrontend
    Invoke-UpdateApi
    Invoke-UpdateIdentity
    Invoke-UpdateMosquitto
    Write-Host ""
    Write-Success "[OK] Todos los componentes actualizados."
    Write-Host ""
}

# ---------------------------------------------------------------------------
# Accion rollout - reinicio sin rebuild (Phase D)
# ---------------------------------------------------------------------------

function Invoke-Rollout {
    Write-Info "Rollout restart del componente: $Component ..."
    Write-Host ""
    Invoke-EnsureClusterRunning

    switch ($Component) {
        'frontend'  {
            Invoke-RolloutRestart -Resource 'deployment/bhm-frontend'
        }
        'api'       {
            Invoke-RolloutRestart -Resource 'deployment/bhm-api'
            Invoke-RolloutRestart -Resource 'deployment/bhm-alert-delivery'
        }
        'identity'  {
            Invoke-RolloutRestart -Resource 'deployment/bhm-identity'
        }
        'mosquitto' {
            Invoke-RolloutRestart -Resource 'statefulset/mosquitto'
        }
        'alerts'    {
            Invoke-RolloutRestart -Resource 'deployment/bhm-alert-delivery'
        }
        'all'       {
            Invoke-RolloutRestart -Resource 'deployment/bhm-frontend'
            Invoke-RolloutRestart -Resource 'deployment/bhm-api'
            Invoke-RolloutRestart -Resource 'deployment/bhm-identity'
            Invoke-RolloutRestart -Resource 'deployment/bhm-alert-delivery'
            Invoke-RolloutRestart -Resource 'statefulset/mosquitto'
        }
    }

    Write-Host ""
    Write-Success "[OK] Rollout completado para: $Component"
    Write-Host ""
}

# ---------------------------------------------------------------------------
# Acciones de operacion y mantenimiento (Phase E)
# ---------------------------------------------------------------------------

function Invoke-Redeploy {
    Write-Warning "Redeploy completo: se eliminara el cluster kind y se recreara desde cero."
    Write-Warning ".env.dev NO se eliminara - los secretos se preservan."
    $confirm = Read-Host "Continuar? (y/N)"
    if ($confirm -ne 'y' -and $confirm -ne 'Y') {
        Write-Info "Redeploy cancelado."
        return
    }

    Write-Info "Eliminando cluster kind '$KindClusterName'..."
    Ensure-KubernetesTooling
    if (Test-KindClusterExists) {
        Stop-KindPortForwards
        & $script:KindExecutable delete cluster --name $KindClusterName
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] No se pudo eliminar el cluster kind." -ForegroundColor Red
            exit 1
        }
        Write-Success "[OK] Cluster eliminado."
    } else {
        Write-Info "El cluster kind no existe, continuando con start..."
    }

    Write-Host ""
    Invoke-Start
}

function Invoke-EnvSync {
    Write-Info "Sincronizando secretos de .env.dev con el cluster kind..."
    Write-Host ""

    if (-not (Test-Path '.env.dev')) {
        Write-Host "[ERROR] .env.dev no encontrado." -ForegroundColor Red
        exit 1
    }

    Invoke-EnsureClusterRunning

    # Leer el .env.dev y construir los argumentos --from-literal
    $envMap = Get-EnvMap -Path '.env.dev'
    if ($envMap.Count -eq 0) {
        Write-Warning ".env.dev esta vacio o no tiene pares clave=valor."
        return
    }

    Write-Info "Recreando Secret 'bhm-env' en el namespace '$KindNamespace'..."

    $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
    & $script:KubectlExecutable --context $script:KindKubectlContext `
        delete secret bhm-env -n $KindNamespace 2>&1 | Out-Null
    $ErrorActionPreference = $savedPref

    $literalArgs = @()
    foreach ($key in $envMap.Keys) {
        $literalArgs += "--from-literal=${key}=$($envMap[$key])"
    }

    $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
    & $script:KubectlExecutable --context $script:KindKubectlContext `
        create secret generic bhm-env `
        -n $KindNamespace `
        @literalArgs 2>&1
    $createExit = $LASTEXITCODE
    $ErrorActionPreference = $savedPref

    if ($createExit -ne 0) {
        Write-Host "[ERROR] No se pudo crear el Secret bhm-env." -ForegroundColor Red
        exit 1
    }

    Write-Success "[OK] Secret bhm-env actualizado con $($envMap.Count) variables."
    Write-Host ""

    $doRollout = Read-Host "Hacer rollout de todos los pods para que apliquen los nuevos secretos? (y/N)"
    if ($doRollout -eq 'y' -or $doRollout -eq 'Y') {
        $Component = 'all'
        Invoke-Rollout
    } else {
        Write-Warning "Los pods seguiran usando los valores del Secret anterior hasta reiniciarse."
    }

    Write-Host ""
}

function Invoke-DiagnoseMosquitto {
    Write-Info "Diagnosticando problemas de Mosquitto..."
    Write-Host ""

    Ensure-KubernetesTooling
    if (-not (Test-KindClusterExists)) {
        Write-Host "[ERROR] El cluster kind '$KindClusterName' no existe." -ForegroundColor Red
        exit 1
    }

    Write-Host "=== DIAGNOSTICO DE MOSQUITTO ===" -ForegroundColor Yellow
    Write-Host ""
    
    # 1. Verificar .env.dev
    Write-Host "[1] Estado de .env.dev:" -ForegroundColor Cyan
    if (Test-Path '.env.dev') {
        $envContent = Get-Content '.env.dev'
        if ($envContent -match '^MQTT_USERNAME=') {
            Write-Host "    [OK] MQTT_USERNAME esta configurado" -ForegroundColor Green
        } else {
            Write-Host "    [FAIL] MQTT_USERNAME NO esta configurado (PROBLEMA)" -ForegroundColor Red
        }
        if ($envContent -match '^MQTT_PASSWORD=') {
            Write-Host "    [OK] MQTT_PASSWORD esta configurado" -ForegroundColor Green
        } else {
            Write-Host "    [FAIL] MQTT_PASSWORD NO esta configurado (PROBLEMA)" -ForegroundColor Red
        }
    } else {
        Write-Host "    [FAIL] .env.dev no existe (ejecuta: .\deploy.ps1 -Action setup)" -ForegroundColor Red
        exit 1
    }
    
    Write-Host ""
    Write-Host "[2] Secrets en Kubernetes:" -ForegroundColor Cyan
    $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
    
    $secrets = @('mosquitto-passwd-bootstrap', 'mosquitto-tls-bootstrap', 'bhm-env')
    foreach ($secret in $secrets) {
        & $script:KubectlExecutable --context $script:KindKubectlContext get secret $secret -n $KindNamespace -o jsonpath='{.metadata.name}' 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    [OK] Secret '$secret' existe" -ForegroundColor Green
        } else {
            Write-Host "    [FAIL] Secret '$secret' FALTA (PROBLEMA)" -ForegroundColor Red
        }
    }
    
    Write-Host ""
    Write-Host "[3] Estado del pod mosquitto-0:" -ForegroundColor Cyan
    & $script:KubectlExecutable --context $script:KindKubectlContext get pod mosquitto-0 -n $KindNamespace -o wide 2>&1 | Out-Host
    
    Write-Host ""
    Write-Host "[4] Ultimos logs del contenedor mosquitto:" -ForegroundColor Cyan
    & $script:KubectlExecutable --context $script:KindKubectlContext logs statefulset/mosquitto -n $KindNamespace -c mosquitto --tail=30 2>&1 | Out-Host
    
    Write-Host ""
    Write-Host "[5] Ultimos logs del reconciler:" -ForegroundColor Cyan
    & $script:KubectlExecutable --context $script:KindKubectlContext logs statefulset/mosquitto -n $KindNamespace -c reconciler --tail=30 2>&1 | Out-Host
    
    Write-Host ""
    Write-Host "[6] Estado de los volumenes (PVC):" -ForegroundColor Cyan
    & $script:KubectlExecutable --context $script:KindKubectlContext get pvc -n $KindNamespace -l app.kubernetes.io/name=mosquitto 2>&1 | Out-Host
    
    Write-Host ""
    Write-Host "=== RECOMENDACIONES ===" -ForegroundColor Yellow
    Write-Host "Si ves problemas, intenta:" -ForegroundColor Gray
    Write-Host "  1. Verifica que .env.dev tiene MQTT_USERNAME y MQTT_PASSWORD" -ForegroundColor Gray
    Write-Host "  2. Ejecuta: .\deploy.ps1 -Action env-sync" -ForegroundColor Gray
    Write-Host "  3. Ejecuta: .\deploy.ps1 -Action rollout -Component mosquitto" -ForegroundColor Gray
    Write-Host "  4. Si sigue fallando, intenta: .\deploy.ps1 -Action redeploy" -ForegroundColor Gray
    Write-Host ""
    
    $ErrorActionPreference = $savedPref
}

function Invoke-DbMigrate {
    Write-Info "Ejecutando migraciones Alembic en el pod bhm-api..."
    Write-Host ""

    Invoke-EnsureClusterRunning

    $savedPref = $ErrorActionPreference ; $ErrorActionPreference = 'Continue'
    $apiPod = & $script:KubectlExecutable --context $script:KindKubectlContext `
        get pods -n $KindNamespace `
        -l app.kubernetes.io/name=bhm-api `
        --field-selector=status.phase=Running `
        -o jsonpath='{.items[0].metadata.name}' 2>&1
    $ErrorActionPreference = $savedPref

    if (-not $apiPod -or $LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] No se encontro pod bhm-api en estado Running." -ForegroundColor Red
        exit 1
    }

    Write-Info "Pod: $apiPod"
    Write-Info "Ejecutando: alembic upgrade head"
    Write-Host ""

    & $script:KubectlExecutable --context $script:KindKubectlContext `
        exec -n $KindNamespace $apiPod -- sh -c "cd /app `&`& alembic upgrade head"
    $migrateExit = $LASTEXITCODE

    Write-Host ""
    if ($migrateExit -eq 0) {
        Write-Success "[OK] Migraciones aplicadas correctamente."
    } else {
        Write-Host "[ERROR] Las migraciones fallaron. Revisa la salida de arriba." -ForegroundColor Red
        exit 1
    }
    Write-Host ""
}

# Main execution
Show-Banner
Test-Prerequisites

switch ($Action)
{
    'setup'
    {
        Invoke-Setup
    }
    'start'
    {
        Invoke-Start
    }
    'stop'
    {
        Invoke-Stop
    }
    'restart'
    {
        Invoke-Restart
    }
    'status'
    {
        Invoke-Status
    }
    'logs'
    {
        Invoke-Logs
    }
    'clean'
    {
        Invoke-Clean
    }
    'build'
    {
        Invoke-Build
    }
    'build-mosquitto'
    {
        Invoke-BuildMosquitto
    }
    'update-frontend'
    {
        Invoke-UpdateFrontend
    }
    'update-api'
    {
        Invoke-UpdateApi
    }
    'update-identity'
    {
        Invoke-UpdateIdentity
    }
    'update-mosquitto'
    {
        Invoke-UpdateMosquitto
    }
    'update-all'
    {
        Invoke-UpdateAll
    }
    'rollout'
    {
        Invoke-Rollout
    }
    'redeploy'
    {
        Invoke-Redeploy
    }
    'env-sync'
    {
        Invoke-EnvSync
    }
    'db-migrate'
    {
        Invoke-DbMigrate
    }
    'patch-frontend'
    {
        Invoke-PatchFrontend
    }
    'patch-backend'
    {
        Invoke-PatchBackend
    }
    'reload-mosquitto'
    {
        Invoke-ReloadMosquitto
    }
    'diagnose-mosquitto'
    {
        Invoke-DiagnoseMosquitto
    }
    'test'
    {
        Invoke-Test
    }
    'smoke'
    {
        $smokeResult = Invoke-Smoke
        if ($smokeResult -gt 0) { exit 1 }
    }
    default
    {
        Write-Error "Unknown action: $Action"
    }
}

Write-Host ""
