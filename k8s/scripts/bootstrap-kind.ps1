param(
    [string]$ClusterName = "bhm-lab",
    [string]$Namespace = "bhm-lab",
    [string]$EnvFile = ".env.dev",
    [string]$KindConfig = "k8s/kind/cluster.yaml",
    [ValidateSet("podman", "docker")]
    [string]$Provider = "podman",
    [string]$KindCommand = "kind",
    [string]$KubectlCommand = "kubectl",
    [int]$WebHostPort = 22000,
    [int]$MqttHostPort = 21900,
    [int]$MqttWsHostPort = 29001,
    [switch]$LoadLocalImage,
    [string[]]$LocalImages = @("bunkermtest-bunkerm:latest", "bunkermtest-mosquitto:latest"),
    [string]$BhmImage = "localhost/bunkermtest-bunkerm:latest",
    [string]$MosquittoImage = "localhost/bunkermtest-mosquitto:latest",
    [string]$GreenhouseSimulatorImage = "localhost/greenhouse-simulator:latest"
)

$ErrorActionPreference = "Stop"

function Assert-LastExitCode {
    param([string]$Step)

    if ($LASTEXITCODE -ne 0) {
        throw "$Step fallo con exit code $LASTEXITCODE."
    }
}

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
    foreach ($name in $names) {
        $candidates.Add((Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\$name"))
        $candidates.Add((Join-Path $env:ProgramFiles "$($name -replace '\.exe$', '')\$name"))
        $candidates.Add((Join-Path $env:USERPROFILE "bin\$name"))
        $candidates.Add((Join-Path $env:USERPROFILE "scoop\shims\$name"))
        $candidates.Add((Join-Path $env:LOCALAPPDATA "Programs\$($name -replace '\.exe$', '')\$name"))

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
    }

    return $candidates | Select-Object -Unique
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

    foreach ($fallbackCandidate in Get-CommandFallbackCandidates -Candidate $Candidate) {
        if (Test-Path $fallbackCandidate) {
            return (Resolve-Path $fallbackCandidate).Path
        }
    }

    throw "$DisplayName no esta disponible. Agregalo al PATH o pasa -$DisplayName`Command con la ruta completa al ejecutable."
}

function New-KindConfigForHostPorts {
    param(
        [string]$TemplatePath,
        [int]$WebHostPort,
        [int]$MqttHostPort,
        [int]$MqttWsHostPort
    )

    $content = Get-Content $TemplatePath -Raw
    $content = $content -replace 'hostPort:\s*22000', "hostPort: $WebHostPort"
    $content = $content -replace 'hostPort:\s*21900', "hostPort: $MqttHostPort"
    $content = $content -replace 'hostPort:\s*29001', "hostPort: $MqttWsHostPort"

    $tempPath = Join-Path ([System.IO.Path]::GetTempPath()) ("bhm-kind-cluster-" + [System.Guid]::NewGuid().ToString('N') + '.yaml')
    Set-Content -Path $tempPath -Value $content -Encoding ASCII
    return $tempPath
}

function New-KustomizeBaseWithFrontendUrl {
    param(
        [string]$BaseDirectory,
        [string]$FrontendUrl,
        [string]$BhmImage,
        [string]$MosquittoImage,
        [string]$GreenhouseSimulatorImage
    )

    $tempDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("bhm-k8s-base-" + [System.Guid]::NewGuid().ToString('N'))
    Copy-Item -Path $BaseDirectory -Destination $tempDirectory -Recurse -Force

    $kustomizationPath = Join-Path $tempDirectory 'kustomization.yaml'
    $kustomizationContent = Get-Content $kustomizationPath -Raw
    $kustomizationContent = $kustomizationContent -replace 'FRONTEND_URL=http://localhost:2000', "FRONTEND_URL=$FrontendUrl"
    $kustomizationContent = $kustomizationContent -replace 'FRONTEND_URL=http://localhost:22000', "FRONTEND_URL=$FrontendUrl"
    $kustomizationContent = $kustomizationContent -replace 'NEXTAUTH_URL=http://localhost:22000', "NEXTAUTH_URL=$FrontendUrl"
    $kustomizationContent = $kustomizationContent -replace 'NEXT_PUBLIC_API_URL=http://localhost:22000', "NEXT_PUBLIC_API_URL=$FrontendUrl"
    if ($BhmImage -match ':(?<tag>[^:@]+)$') {
        $bhmTag = $Matches['tag']
        $kustomizationContent = $kustomizationContent -replace '(name:\s+localhost/bunkermtest-bunkerm\s+newTag:\s+)[^\r\n]+', ('$1' + $bhmTag)
    }
    if ($MosquittoImage -match ':(?<tag>[^:@]+)$') {
        $mosquittoTag = $Matches['tag']
        $kustomizationContent = $kustomizationContent -replace '(name:\s+localhost/bunkermtest-mosquitto\s+newTag:\s+)[^\r\n]+', ('$1' + $mosquittoTag)
    }
    Set-Content -Path $kustomizationPath -Value $kustomizationContent -Encoding ASCII

    return $tempDirectory
}

function Get-KustomizeBootstrapSecretSeedRequirements {
    return @(
        'secrets/mosquitto_passwd',
        'secrets/ca.crt',
        'secrets/server.crt',
        'secrets/server.key'
    )
}

function Assert-KustomizeBootstrapSeedFiles {
    param(
        [string]$BaseDirectory
    )

    $missing = New-Object System.Collections.Generic.List[string]
    foreach ($relativePath in Get-KustomizeBootstrapSecretSeedRequirements) {
        $fullPath = Join-Path $BaseDirectory $relativePath
        if (-not (Test-Path $fullPath)) {
            $missing.Add($fullPath)
        }
    }

    if ($missing.Count -eq 0) {
        return
    }

    $joinedMissing = ($missing | ForEach-Object { " - $_" }) -join [Environment]::NewLine
    throw @"
Faltan archivos requeridos por kustomize secretGenerator para el bootstrap de kind:
$joinedMissing

Crea esos archivos (material real) en k8s/base/secrets antes de ejecutar bootstrap-kind.ps1.
"@
}

function Get-PodmanMachineState {
    param([string]$PodmanExecutable)

    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $machineJson = & $PodmanExecutable machine ls --format json 2>&1
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
    param([string]$PodmanExecutable)

    $machines = @(Get-PodmanMachineState -PodmanExecutable $PodmanExecutable)
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
    $connectionLines = @(& $PodmanExecutable system connection list 2>&1)
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

function Invoke-PodmanWslRecovery {
    param(
        [string]$PodmanExecutable,
        [string]$MachineName
    )

    Write-Host "[WARN] Recuperacion fuerte de Podman: ejecutando 'wsl --shutdown' y reintentando '$MachineName'..." -ForegroundColor Yellow
    wsl.exe --shutdown 2>&1 | Out-Null

    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $PodmanExecutable machine start $MachineName 2>&1 | Out-Null
    $startExitCode = $LASTEXITCODE
    & $PodmanExecutable system connection default "${MachineName}-root" 2>&1 | Out-Null
    $ErrorActionPreference = $savedPref

    if ($startExitCode -ne 0) {
        throw "No se pudo recuperar la maquina Podman '$MachineName' tras reiniciar WSL."
    }

    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $savedPref = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & $PodmanExecutable info 2>&1 | Out-Null
        $infoExitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedPref
        if ($infoExitCode -eq 0) {
            Write-Host "[OK] Podman recuperado tras reiniciar WSL." -ForegroundColor Green
            return
        }
    }

    throw "Podman sigue sin responder tras la recuperacion fuerte de WSL para '$MachineName'."
}

function Restart-PodmanProvider {
    param([string]$PodmanExecutable)

    $machineName = Get-PreferredPodmanMachineName -PodmanExecutable $PodmanExecutable
    if (-not $machineName) {
        throw "No se pudo determinar la maquina Podman a reiniciar."
    }

    Write-Host "[WARN] Reiniciando la maquina Podman '$machineName' para recuperar el socket remoto..." -ForegroundColor Yellow

    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $PodmanExecutable machine stop $machineName 2>&1 | Out-Null
    & $PodmanExecutable machine start $machineName 2>&1 | Out-Null
    $startExitCode = $LASTEXITCODE
    & $PodmanExecutable system connection default "${machineName}-root" 2>&1 | Out-Null
    $ErrorActionPreference = $savedPref

    if ($startExitCode -ne 0) {
        Invoke-PodmanWslRecovery -PodmanExecutable $PodmanExecutable -MachineName $machineName
        return
    }

    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        $savedPref = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & $PodmanExecutable info 2>&1 | Out-Null
        $infoExitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedPref
        if ($infoExitCode -eq 0) {
            Write-Host "[OK] Podman recuperado sobre la maquina '$machineName'." -ForegroundColor Green
            return
        }
    }

    Invoke-PodmanWslRecovery -PodmanExecutable $PodmanExecutable -MachineName $machineName
}

function Ensure-PodmanProviderReady {
    param([string]$PodmanExecutable)

    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $PodmanExecutable info 2>&1 | Out-Null
    $infoExitCode = $LASTEXITCODE
    $ErrorActionPreference = $savedPref

    if ($infoExitCode -eq 0) {
        return
    }

    $machineName = Get-PreferredPodmanMachineName -PodmanExecutable $PodmanExecutable
    if (-not $machineName) {
        throw "No se pudo determinar la maquina Podman a recuperar."
    }

    Restart-PodmanProvider -PodmanExecutable $PodmanExecutable
}

function Test-LocalImageExists {
    param(
        [string]$ContainerEngineExecutable,
        [string]$ImageReference
    )

    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $ContainerEngineExecutable image exists $ImageReference 2>&1 | Out-Null
    $imageExitCode = $LASTEXITCODE
    $ErrorActionPreference = $savedPref

    return ($imageExitCode -eq 0)
}

function Resolve-LocalImageReference {
    param(
        [string]$ContainerEngineExecutable,
        [string]$ImageReference
    )

    if (Test-LocalImageExists -ContainerEngineExecutable $ContainerEngineExecutable -ImageReference $ImageReference) {
        $savedPref = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $repoTags = & $ContainerEngineExecutable image inspect $ImageReference --format "{{range .RepoTags}}{{println .}}{{end}}" 2>&1
        $inspectExitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedPref

        if ($inspectExitCode -eq 0) {
            $canonicalTag = @($repoTags | Where-Object { $_ -and $_.Trim() }) | Select-Object -First 1
            if ($canonicalTag) {
                return "$canonicalTag".Trim()
            }
        }

        return $ImageReference
    }

    if ($ImageReference -notmatch '^[^/]+/') {
        $localhostImageReference = "localhost/$ImageReference"
        if (Test-LocalImageExists -ContainerEngineExecutable $ContainerEngineExecutable -ImageReference $localhostImageReference) {
            return $localhostImageReference
        }
    }

    return $ImageReference
}

function Import-ImageIntoKind {
    param(
        [string]$KindExecutable,
        [string]$ClusterName,
        [string]$Provider,
        [string]$ContainerEngineExecutable,
        [string]$ImageReference
    )

    if ($Provider -eq 'podman') {
        $archivePath = Join-Path ([System.IO.Path]::GetTempPath()) ("kind-image-" + [System.Guid]::NewGuid().ToString('N') + ".tar")
        try {
            for ($attempt = 1; $attempt -le 2; $attempt++) {
                Ensure-PodmanProviderReady -PodmanExecutable $ContainerEngineExecutable

                if (Test-Path $archivePath) {
                    Remove-Item $archivePath -Force -ErrorAction SilentlyContinue
                }

                & $ContainerEngineExecutable save --format oci-archive -o $archivePath $ImageReference
                if ($LASTEXITCODE -eq 0) {
                    & $KindExecutable load image-archive $archivePath --name $ClusterName
                    if ($LASTEXITCODE -eq 0) {
                        return
                    }

                    $failedStep = "kind load image-archive $ImageReference"
                } else {
                    $failedStep = "podman save $ImageReference"
                }

                if ($attempt -ge 2) {
                    Assert-LastExitCode $failedStep
                }

                Write-Host "[WARN] '$failedStep' fallo; reintentando tras reiniciar Podman..." -ForegroundColor Yellow
                Restart-PodmanProvider -PodmanExecutable $ContainerEngineExecutable
            }
        } finally {
            if (Test-Path $archivePath) {
                Remove-Item $archivePath -Force -ErrorAction SilentlyContinue
            }
        }

        return
    }

    & $KindExecutable load docker-image $ImageReference --name $ClusterName
    Assert-LastExitCode "kind load docker-image $ImageReference"
}

$kindExecutable = Resolve-CommandTarget -Candidate $KindCommand -DisplayName "Kind"
$kubectlExecutable = Resolve-CommandTarget -Candidate $KubectlCommand -DisplayName "Kubectl"
$containerEngineExecutable = $null
$resolvedKindConfig = $null
$resolvedKustomizeBase = $null
$frontendUrl = "http://localhost:$WebHostPort"

if (-not (Test-Path $EnvFile)) {
    throw "No existe el archivo de entorno: $EnvFile"
}

if ($Provider -eq "podman") {
    $podmanExecutable = Resolve-CommandTarget -Candidate "podman" -DisplayName "Podman"
    Ensure-PodmanProviderReady -PodmanExecutable $podmanExecutable
    $env:KIND_EXPERIMENTAL_PROVIDER = "podman"
    $containerEngineExecutable = $podmanExecutable
} else {
    $containerEngineExecutable = Resolve-CommandTarget -Candidate "docker" -DisplayName "Docker"
}

try {
    $resolvedKindConfig = New-KindConfigForHostPorts `
        -TemplatePath $KindConfig `
        -WebHostPort $WebHostPort `
        -MqttHostPort $MqttHostPort `
        -MqttWsHostPort $MqttWsHostPort
    $resolvedKustomizeBase = New-KustomizeBaseWithFrontendUrl `
        -BaseDirectory (Join-Path (Split-Path $PSScriptRoot -Parent) 'base') `
        -FrontendUrl $frontendUrl
    Assert-KustomizeBootstrapSeedFiles -BaseDirectory $resolvedKustomizeBase

    $clusterExists = & $kindExecutable get clusters | Where-Object { $_ -eq $ClusterName }
    Assert-LastExitCode "kind get clusters"

    if (-not $clusterExists) {
        Write-Host "[INFO] Creando cluster kind '$ClusterName'..." -ForegroundColor Cyan
        & $kindExecutable create cluster --name $ClusterName --config $resolvedKindConfig
        Assert-LastExitCode "kind create cluster"
    } else {
        Write-Host "[INFO] Reutilizando cluster kind existente '$ClusterName'." -ForegroundColor Yellow
    }

    if ($LoadLocalImage) {
        foreach ($localImage in $LocalImages) {
            $resolvedLocalImage = Resolve-LocalImageReference -ContainerEngineExecutable $containerEngineExecutable -ImageReference $localImage
            Write-Host "[INFO] Cargando imagen local '$resolvedLocalImage' en kind..." -ForegroundColor Cyan
            Import-ImageIntoKind `
                -KindExecutable $kindExecutable `
                -ClusterName $ClusterName `
                -Provider $Provider `
                -ContainerEngineExecutable $containerEngineExecutable `
                -ImageReference $resolvedLocalImage
        }
    }

    Write-Host "[INFO] Creando namespace '$Namespace' si no existe..." -ForegroundColor Cyan
    $namespaceYaml = & $kubectlExecutable create namespace $Namespace --dry-run=client -o yaml
    Assert-LastExitCode "kubectl create namespace"
    $namespaceYaml | & $kubectlExecutable apply -f - | Out-Null
    Assert-LastExitCode "kubectl apply namespace"

    Write-Host "[INFO] Sincronizando secret bhm-env desde $EnvFile..." -ForegroundColor Cyan
    $secretYaml = & $kubectlExecutable create secret generic bhm-env --namespace $Namespace --from-env-file=$EnvFile --dry-run=client -o yaml
    Assert-LastExitCode "kubectl create secret"
    $secretYaml | & $kubectlExecutable apply -f - | Out-Null
    Assert-LastExitCode "kubectl apply secret"

    Write-Host "[INFO] Aplicando scaffold base de Kubernetes..." -ForegroundColor Cyan
    & $kubectlExecutable apply -k $resolvedKustomizeBase
    Assert-LastExitCode "kubectl apply -k $resolvedKustomizeBase"

    Write-Host "" 
    Write-Host "[OK] Laboratorio inicial aplicado." -ForegroundColor Green
    Write-Host "     UI/API: $frontendUrl" -ForegroundColor Green
    Write-Host "     MQTT: localhost:$MqttHostPort" -ForegroundColor Green
    Write-Host "     MQTT WS: localhost:$MqttWsHostPort" -ForegroundColor Green
    Write-Host "     Namespace: $Namespace" -ForegroundColor Green
    Write-Host "" 
    Write-Host "Sugerencias de verificacion:" -ForegroundColor White
    Write-Host "  kubectl get pods -n $Namespace" -ForegroundColor Gray
    Write-Host "  kubectl get svc -n $Namespace" -ForegroundColor Gray
    Write-Host "  kubectl logs deployment/bunkerm-platform -n $Namespace" -ForegroundColor Gray
    Write-Host "  kubectl logs statefulset/mosquitto -n $Namespace -c reconciler" -ForegroundColor Gray
} finally {
    if ($resolvedKindConfig -and (Test-Path $resolvedKindConfig)) {
        Remove-Item $resolvedKindConfig -Force -ErrorAction SilentlyContinue
    }
    if ($resolvedKustomizeBase -and (Test-Path $resolvedKustomizeBase)) {
        Remove-Item $resolvedKustomizeBase -Recurse -Force -ErrorAction SilentlyContinue
    }
}
