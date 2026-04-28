# Headlamp — Herramienta de administración del cluster

Headlamp es la interfaz web de administración de Kubernetes desplegada en el namespace
`admin-tools`. Permite a los administradores gestionar entidades de Kubernetes (Pods,
Deployments, StatefulSets, Secrets, ConfigMaps, etc.) de todos los namespaces del cluster
desde el navegador.

## Acceso

```
http://localhost:23000
```

El puerto 23000 es el default. Si se personalizó con `-KindHeadlampHostPort`, usar ese
puerto.

## Arranque con Headlamp

```powershell
.\deploy.ps1 -Action start -Runtime kind -ImageTag 2.0.0 -WithAdminTools
```

El script:
1. Despliega los workloads de la app normalmente.
2. Instala Headlamp via Helm en el namespace `admin-tools`.
3. Aplica el RBAC (`ServiceAccount headlamp-admin` + `ClusterRoleBinding cluster-admin`).
4. Abre el port-forward en `localhost:23000`.
5. Imprime el token de acceso.

## Obtener el token de acceso manualmente

```powershell
kubectl get secret headlamp-token -n admin-tools `
  -o jsonpath='{.data.token}' | `
  ForEach-Object { [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($_)) }
```

Pegar ese token en el campo "Access Token" de la pantalla de login de Headlamp.

## Actualizar Headlamp a una nueva version estable

```powershell
# Consultar version estable disponible
helm search repo headlamp/headlamp

# Actualizar
helm upgrade --install headlamp headlamp/headlamp `
  -n admin-tools `
  -f k8s/admin-tools/headlamp-values.yaml `
  --version <version>
```

No es necesario reiniciar los workloads de la app.

## Escaneo de seguridad desde host (Kubescape)

Kubescape se ejecuta como herramienta puntual desde el host, no como operador in-cluster,
para mantener el overhead del cluster kind bajo.

```powershell
# Instalar Kubescape (una sola vez)
# https://github.com/kubescape/kubescape

# Escaneo contra frameworks NSA y MITRE
kubescape scan framework nsa  --context kind-bhm-lab
kubescape scan framework mitre --context kind-bhm-lab

# Escaneo de un namespace concreto
kubescape scan framework nsa --context kind-bhm-lab -n bhm-lab
```

## Trivy Operator (seguridad in-cluster, opt-in)

Para escaneo continuo de vulnerabilidades en imágenes de pods:

```powershell
helm repo add aqua https://aquasecurity.github.io/helm-charts/ --force-update
helm upgrade --install trivy-operator aqua/trivy-operator `
  -n admin-tools `
  --set targetNamespaces="bhm-lab"
```

Los resultados aparecen como `VulnerabilityReport` CRDs visibles directamente en la UI
de Headlamp sin configuracion adicional.

## Estructura de archivos

| Archivo | Proposito |
|---|---|
| `namespace.yaml` | Namespace `admin-tools` |
| `headlamp-values.yaml` | Helm values para Headlamp |
| `rbac.yaml` | SA + ClusterRoleBinding + token Secret |

## Notas de seguridad

- El `ClusterRoleBinding` usa el rol `cluster-admin` — acceso completo al cluster.
  Adecuado para el laboratorio local. En produccion, reemplazar por un `ClusterRole`
  custom con los permisos minimos necesarios.
- El token de acceso no caduca por defecto en Kubernetes. Rotarlo periodicamente en
  entornos con mas de un administrador.
