# Plan de Integración de Headlamp

## Objetivo

Desplegar Headlamp como interfaz web de administración de Kubernetes en el mismo cluster
que aloja el proyecto BHM (Broker Health Manager) y el futuro proyecto de reporting, de
forma que los administradores puedan gestionar entidades de ambos proyectos desde una
sola UI sin modificar los manifests de ninguna aplicación.

---

## Contexto del cluster

| Elemento | Detalle |
|---|---|
| Runtime lab | `kind` — cluster `bhm-lab` (1 control-plane + 1 worker) |
| Namespace app BHM | `bhm-lab` |
| Namespace futuro reporting | Pendiente de definir (ej. `reporting-lab`) |
| Namespace Headlamp | `admin-tools` (nuevo, aislado) |
| Workloads BHM actuales | `postgres` (StatefulSet), `mosquitto` + sidecars (StatefulSet), `bhm-frontend`, `bhm-api`, `bhm-identity`, `bhm-alert-delivery` (Deployments) |
| Puerto Headlamp host | 23000 (libre; en uso: 22000 web, 21900 MQTT, 29001 MQTT WS) |
| Exposición | `kubectl port-forward` gestionado por `deploy.ps1`, igual que los servicios de la app |

---

## Decisión de toolchain: Helm para Headlamp, Kustomize para la app

La regla del ecosistema Kubernetes es: **Kustomize para tus propios manifests, Helm para
paquetes de terceros que publican un chart oficial**. No es preferencia sino separación de
responsabilidades:

- **Kustomize** es excelente para sobrescribir, mergear y parchear manifests propios entre
  entornos. No gestiona ciclos de vida de paquetes upstream.
- **Helm** es el gestor de paquetes estándar. Headlamp publica un chart oficial
  (`headlamp-k8s/headlamp`). Upgrades con `helm upgrade --version <x.y.z>` sin tocar YAML.

Usar solo Kustomize implicaría vendorizar los manifests generados por `helm template` y
mantenerlos manualmente — perdiendo la fuente de verdad upstream. La alternativa de
`helmCharts:` en `kustomization.yaml` requiere `--enable-helm` y añade complejidad al
flujo de bootstrap que hoy funciona con `kubectl apply -k`.

**Decisión:** Helm para Headlamp, invocado directamente desde `deploy.ps1` como acción
opt-in (`-WithAdminTools`). No altera el pipeline `kubectl apply -k` de la app.

---

## Plugins y herramientas de seguridad

### Kubescape

- **Modo de uso recomendado para el lab:** escaneo puntual desde el host, no operador in-cluster.
- El operador añade 4–5 pods, CRDs y storage PersistentVolume → overhead innecesario para `kind`.
- Comando: `kubescape scan framework nsa --context kind-bhm-lab`
- Reservar el operador + plugin Headlamp para cuando el cluster sea staging/producción real.

### Trivy Operator (Fase D2, opt-in)

- 1 Deployment, ~100 Mi RAM en reposo.
- Escanea imágenes de pods automáticamente al arrancar y genera `VulnerabilityReport` CRDs.
- Headlamp muestra esos CRDs nativamente sin plugin adicional.
- No bloqueante: se puede añadir después sin modificar ningún manifest de la app.

---

## Estructura de archivos

```
k8s/
└── admin-tools/
    ├── namespace.yaml          # Namespace admin-tools
    ├── headlamp-values.yaml    # Helm values para Headlamp
    ├── rbac.yaml               # ServiceAccount + ClusterRoleBinding + token Secret
    └── README.md               # Operativa para administradores
```

Ningún archivo bajo `k8s/base/` ni `k8s/kind/` se modifica.

---

## Fases de implementación

### Fase A — Namespace

**Archivos:** `k8s/admin-tools/namespace.yaml`

Namespace `admin-tools` sin las labels `app.kubernetes.io/part-of: bhm` para mantener
separación semántica entre infraestructura de administración y workloads de negocio.

No se añade a `k8s/base/kustomization.yaml` — lo aplica la función
`Install-HeadlampAdminTools` en `deploy.ps1` via `kubectl apply -f`.

---

### Fase B — Helm values de Headlamp

**Archivos:** `k8s/admin-tools/headlamp-values.yaml`

Valores clave:

| Clave | Valor | Razón |
|---|---|---|
| `service.type` | `ClusterIP` | Port-forward: consistente con el patrón actual del lab |
| `clusterRoleBinding.create` | `true` | El SA de Headlamp necesita acceso a la K8s API para proxear recursos |
| `replicaCount` | `1` | Lab local, no hay SLA de disponibilidad |
| `ingress.enabled` | `false` | Port-forward suficiente en el lab |
| `resources.requests` | cpu 50m / memory 64Mi | Conservador para kind |

La versión del chart se fija en el momento del primer despliegue con:
```powershell
helm search repo headlamp-k8s/headlamp
```
y se escribe en el README de admin-tools para reproducibilidad.

---

### Fase C — RBAC

**Archivos:** `k8s/admin-tools/rbac.yaml`

- `ServiceAccount: headlamp-admin` en `admin-tools`
- `ClusterRoleBinding` → `cluster-admin`: acceso cluster-wide que cubre `bhm-lab` y
  cualquier namespace futuro (incluyendo el del proyecto de reporting) sin reconfiguración.
- `Secret` de tipo `kubernetes.io/service-account-token` anotado con el SA → token de
  larga duración que los administradores pegan en la pantalla de login de Headlamp.

> **Nota de seguridad:** `cluster-admin` es adecuado para un lab cerrado. En producción o
> staging con acceso externo se debe crear un `ClusterRole` custom con los permisos mínimos
> necesarios (get/list/watch sobre recursos de la app + patch/create limitado).

---

### Fase D — Integración en `deploy.ps1`

Cambios quirúrgicos, todos **no-breaking** para el flujo existente:

1. **Parámetro `$Namespace` en `Start-KindPortForwardProcess`** (default `$KindNamespace`)
   — permite lanzar port-forwards en cualquier namespace sin cambiar las llamadas existentes.

2. **Parámetro `[int]$KindHeadlampHostPort = 23000`** en el bloque `param()` del script.

3. **Switch `[switch]$WithAdminTools`** en el bloque `param()` — opt-in, no altera el
   flujo normal de `start`.

4. **Función `Install-HeadlampAdminTools`**:
   - `kubectl apply -f k8s/admin-tools/namespace.yaml`
   - `helm repo add headlamp https://kubernetes-sigs.github.io/headlamp/ --force-update`
   - `helm upgrade --install headlamp headlamp/headlamp -n admin-tools -f k8s/admin-tools/headlamp-values.yaml`
   - `kubectl apply -f k8s/admin-tools/rbac.yaml`
   - `kubectl rollout status deployment/headlamp -n admin-tools --timeout=120s`
   - Imprime el token de acceso al final.

5. **Port-forward de Headlamp en `Start-KindPortForwards`** condicionado a `$WithAdminTools`
   o a que el pod `headlamp` ya exista en `admin-tools`:
   `Start-KindPortForwardProcess -Name 'headlamp' -Resource 'service/headlamp' -Namespace 'admin-tools' -Mappings @("${KindHeadlampHostPort}:4466") -LocalPorts @($KindHeadlampHostPort)`

6. **`Invoke-Start`**: llamada a `Install-HeadlampAdminTools` condicionada a `-WithAdminTools`,
   más impresión de la URL de Headlamp en el bloque de Service URLs.

7. **`Invoke-Status`**: muestra pods de `admin-tools` si el namespace existe.

---

### Fase E — Documentación

- `k8s/admin-tools/README.md`: URL de acceso, cómo recuperar el token, upgrade de Headlamp,
  escaneo Kubescape desde host.
- `k8s/README.md`: nueva sección "Herramientas de administración del cluster".

---

## Comandos de uso

### Despliegue inicial con Headlamp

```powershell
.\deploy.ps1 -Action start -Runtime kind -ImageTag 2.0.0 -WithAdminTools
```

### Arrancar el lab sin Headlamp (flujo normal sin cambios)

```powershell
.\deploy.ps1 -Action start -Runtime kind -ImageTag 2.0.0
```

### Reinstalar/actualizar Headlamp sin reiniciar la app

```powershell
helm upgrade --install headlamp headlamp/headlamp `
  -n admin-tools `
  -f k8s/admin-tools/headlamp-values.yaml `
  --version <nueva-version>
```

### Obtener el token de acceso manualmente

```powershell
kubectl get secret headlamp-admin-token -n admin-tools `
  -o jsonpath='{.data.token}' | `
  ForEach-Object { [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($_)) }
```

### Escaneo de seguridad desde host (Kubescape)

```powershell
kubescape scan framework nsa --context kind-bhm-lab
kubescape scan framework mitre --context kind-bhm-lab
```

---

## Verificación

1. `kubectl get pods -n admin-tools` → pod `headlamp-*` en estado `Running`
2. `deploy.ps1 -Action start -WithAdminTools` imprime el token y la URL (`http://localhost:23000`)
3. Navegador: `http://localhost:23000` → pantalla de login de Headlamp
4. Login con el token → Headlamp muestra namespaces `bhm-lab` y `admin-tools`
5. En `bhm-lab`: Deployments, StatefulSets, Pods, Services, Secrets y ConfigMaps del broker visibles
6. `kubectl get clusterrolebinding headlamp-admin` → binding verificado
7. `deploy.ps1 -Action status` refleja pods de `admin-tools`

---

## Scope de cambios — qué NO se toca

| Archivo | Estado |
|---|---|
| `k8s/kind/cluster.yaml` | Sin cambios |
| `k8s/base/kustomization.yaml` | Sin cambios |
| `k8s/base/*.yaml` (manifests app) | Sin cambios |
| `k8s/kind/kustomization.yaml` | Sin cambios |
| `.env.dev` / secretos de la app | Sin cambios |

---

## Fase D2 — Trivy Operator (opt-in futuro)

```powershell
helm repo add aqua https://aquasecurity.github.io/helm-charts/ --force-update
helm upgrade --install trivy-operator aqua/trivy-operator `
  -n admin-tools `
  --set targetNamespaces="bhm-lab\,reporting-lab"
```

Headlamp mostrará los `VulnerabilityReport` CRDs generados automáticamente sin
configuración adicional en la UI.
