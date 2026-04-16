param(
    [string]$ClusterName = "bhm-lab",
    [string]$Namespace = "bhm-lab",
    [string]$EnvFile = ".env.dev",
    [string]$KindConfig = "k8s/kind/cluster.yaml",
    [ValidateSet("podman", "docker")]
    [string]$Provider = "podman",
    [string]$KindCommand = "kind",
    [string]$KubectlCommand = "kubectl",
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

    throw "$DisplayName no esta disponible. Agregalo al PATH o pasa -$DisplayName`Command con la ruta completa al ejecutable."
}

$kindExecutable = Resolve-CommandTarget -Candidate $KindCommand -DisplayName "Kind"
$kubectlExecutable = Resolve-CommandTarget -Candidate $KubectlCommand -DisplayName "Kubectl"

if (-not (Test-Path $EnvFile)) {
    throw "No existe el archivo de entorno: $EnvFile"
}

if ($Provider -eq "podman") {
    $env:KIND_EXPERIMENTAL_PROVIDER = "podman"
}

$clusterExists = & $kindExecutable get clusters | Where-Object { $_ -eq $ClusterName }
Assert-LastExitCode "kind get clusters"

if (-not $clusterExists) {
    Write-Host "[INFO] Creando cluster kind '$ClusterName'..." -ForegroundColor Cyan
    & $kindExecutable create cluster --name $ClusterName --config $KindConfig
    Assert-LastExitCode "kind create cluster"
} else {
    Write-Host "[INFO] Reutilizando cluster kind existente '$ClusterName'." -ForegroundColor Yellow
}

if ($LoadLocalImage) {
    foreach ($localImage in $LocalImages) {
        Write-Host "[INFO] Cargando imagen local '$localImage' en kind..." -ForegroundColor Cyan
        & $kindExecutable load docker-image $localImage --name $ClusterName
        Assert-LastExitCode "kind load docker-image $localImage"
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
& $kubectlExecutable apply -k k8s/base | Out-Null
Assert-LastExitCode "kubectl apply -k k8s/base"

Write-Host "" 
Write-Host "[OK] Laboratorio inicial aplicado." -ForegroundColor Green
Write-Host "     UI/API: http://localhost:22000" -ForegroundColor Green
Write-Host "     MQTT: localhost:21900" -ForegroundColor Green
Write-Host "     MQTT WS: localhost:29001" -ForegroundColor Green
Write-Host "     Namespace: $Namespace" -ForegroundColor Green
Write-Host "" 
Write-Host "Sugerencias de verificacion:" -ForegroundColor White
Write-Host "  kubectl get pods -n $Namespace" -ForegroundColor Gray
Write-Host "  kubectl get svc -n $Namespace" -ForegroundColor Gray
Write-Host "  kubectl logs deployment/bunkerm-platform -n $Namespace" -ForegroundColor Gray
Write-Host "  kubectl logs statefulset/mosquitto -n $Namespace -c reconciler" -ForegroundColor Gray
