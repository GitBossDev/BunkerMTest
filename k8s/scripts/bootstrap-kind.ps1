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
    [string[]]$LocalImages = @("bunkermtest-bunkerm:latest", "bunkermtest-mosquitto:latest")
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
        [string]$FrontendUrl
    )

    $tempDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("bhm-k8s-base-" + [System.Guid]::NewGuid().ToString('N'))
    Copy-Item -Path $BaseDirectory -Destination $tempDirectory -Recurse -Force

    $kustomizationPath = Join-Path $tempDirectory 'kustomization.yaml'
    $kustomizationContent = Get-Content $kustomizationPath -Raw
    $kustomizationContent = $kustomizationContent -replace 'FRONTEND_URL=http://localhost:2000', "FRONTEND_URL=$FrontendUrl"
    $kustomizationContent = $kustomizationContent -replace 'FRONTEND_URL=http://localhost:22000', "FRONTEND_URL=$FrontendUrl"
    $kustomizationContent = $kustomizationContent -replace 'NEXTAUTH_URL=http://localhost:22000', "NEXTAUTH_URL=$FrontendUrl"
    $kustomizationContent = $kustomizationContent -replace 'NEXT_PUBLIC_API_URL=http://localhost:22000', "NEXT_PUBLIC_API_URL=$FrontendUrl"
    Set-Content -Path $kustomizationPath -Value $kustomizationContent -Encoding ASCII

    return $tempDirectory
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

    $machines = @(Get-PodmanMachineState -PodmanExecutable $PodmanExecutable)
    if (-not $machines.Count) {
        throw "Podman no responde y no hay maquinas configuradas para recuperarlo automaticamente."
    }

    $preferredMachine = $machines | Where-Object { $_.Default -eq $true } | Select-Object -First 1
    if (-not $preferredMachine) {
        $preferredMachine = $machines | Select-Object -First 1
    }

    $machineName = "$($preferredMachine.Name)"
    if (-not $machineName) {
        throw "No se pudo determinar la maquina Podman a recuperar."
    }

    Write-Host "[WARN] Podman no respondio. Recuperando la maquina '$machineName'..." -ForegroundColor Yellow

    $isRunning = $false
    if ($preferredMachine.PSObject.Properties.Name -contains 'Running') {
        $isRunning = [bool]$preferredMachine.Running
    } elseif ("$($preferredMachine.LastUp)" -match 'Currently running') {
        $isRunning = $true
    }

    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    if ($isRunning) {
        & $PodmanExecutable machine stop $machineName 2>&1 | Out-Null
    }
    & $PodmanExecutable machine start $machineName 2>&1 | Out-Null
    $startExitCode = $LASTEXITCODE
    & $PodmanExecutable system connection default "${machineName}-root" 2>&1 | Out-Null
    $ErrorActionPreference = $savedPref

    if ($startExitCode -ne 0) {
        throw "No se pudo iniciar la maquina Podman '$machineName'."
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

        Start-Sleep -Seconds 3
    }

    throw "Podman sigue sin responder tras reiniciar la maquina '$machineName'."
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
            & $ContainerEngineExecutable save --format oci-archive -o $archivePath $ImageReference
            Assert-LastExitCode "podman save $ImageReference"

            & $KindExecutable load image-archive $archivePath --name $ClusterName
            Assert-LastExitCode "kind load image-archive $ImageReference"
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
    & $kubectlExecutable apply -k $resolvedKustomizeBase | Out-Null
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
