# BHM Kubernetes Lab

Este directorio abre un carril opcional de laboratorio sobre `kind` para validar la portabilidad del baseline Compose-first sin convertir Kubernetes en el nuevo entorno diario de desarrollo.

## Alcance de este primer corte

- `PostgreSQL` como estado persistente del control-plane.
- `bunkerm-platform` como `Deployment` de control-plane HTTP.
- `bhm-alert-delivery` como `Deployment` separado consumiendo el outbox persistido de alertas.
- `mosquitto` como `StatefulSet` broker-owned con PVCs propios.
- `bhm-reconciler` y `bhm-broker-observability` como sidecars dentro del pod del broker.
- `mosquitto_passwd` y TLS ya tienen traducción inicial a `Secret` dedicados de Kubernetes.
- `greenhouse-simulator` permanece como herramienta externa de carga MQTT, fuera del baseline persistente de `kind`.

## Decisión transicional relevante

El secreto efímero usado por `create_client` ya no depende de `/nextjs/data/reconcile-secrets`; ahora se stagea cifrado dentro del control-plane PostgreSQL. Eso permitió separar el pod HTTP del broker. Aun así, el reconciliador sigue siendo broker-facing y mantiene dependencias reales sobre `/var/lib/mosquitto`, `/etc/mosquitto` y la señal `.dynsec-reload`, así que en Kubernetes queda modelado como sidecar del `StatefulSet` del broker, no como pod remoto con PVC compartido artificialmente.

Eso deja visible el gap real hacia la fase posterior:

- decidir si el reconciliador seguirá como sidecar, `Job`, `Deployment` cercano o patrón operador cuando desaparezca la dependencia de filesystem broker-local
- endurecer storage y configuración residual de `/nextjs/data` para el proceso web sin reintroducir coupling broker-facing
- sustituir los placeholders actuales de bootstrap por material TLS real y por una estrategia de rotación/control-plane para `mosquitto_passwd`

## Estructura

- `kind/cluster.yaml`: clúster local mínimo con `1` control-plane y `1` worker
- `base/`: manifiestos iniciales del laboratorio, incluyendo `StatefulSet` broker-owned
- `admin-tools/`: herramientas de administración del cluster (Headlamp)
- `PORTABILITY_INVENTORY.md`: inventario Compose -> Kubernetes y gaps transicionales visibles
- `IMAGE_PACKAGING.md`: lineamiento operativo para tags, build y arranque del laboratorio sin depender de `latest`

## Herramientas de administración del cluster

El subdirectorio `admin-tools/` contiene los manifests y Helm values para desplegar
[Headlamp](https://headlamp.dev) como interfaz web de administración del cluster en el
namespace `admin-tools`.

### Requisitos previos

- **Helm v3** instalado en el host: `winget install Helm.Helm`

### Despliegue

Añadir el flag `-WithAdminTools` al arranque del lab:

```powershell
.\deploy.ps1 -Action start -Runtime kind -ImageTag 2.0.0 -WithAdminTools
```

El script instala Headlamp via Helm, aplica el RBAC, abre el port-forward en el puerto
23000 e imprime el token de acceso.

| Recurso | Valor |
|---|---|
| URL | `http://localhost:23000` |
| Namespace | `admin-tools` |
| Puerto host | 23000 (personalizable con `-KindHeadlampHostPort`) |

### Port-forward manual

Si el cluster ya está corriendo sin `-WithAdminTools`:

```powershell
kubectl port-forward service/headlamp -n admin-tools 23000:4466 --context kind-bhm-lab
```

Consulta `k8s/admin-tools/README.md` para la operativa completa (obtener token,
actualizar Headlamp, Kubescape scanning, Trivy Operator).
- `RECONCILER_CONTROL_LOOP_EVOLUTION.md`: verificacion tecnica del paso sidecar -> control loop -> controlador
- `FINAL_TOPOLOGY.md`: topologia final minima ya materializada para Fase 9, centrada en los workloads persistentes del core BHM
- `scripts/bootstrap-kind.ps1`: crea el clúster, genera el secret desde `.env.dev`, aplica el scaffold y opcionalmente carga la imagen local

## Secrets broker-facing en este laboratorio

- `mosquitto-passwd-bootstrap`: seed inicial para `mosquitto_passwd`
- `mosquitto-tls-bootstrap`: seed inicial para `ca.crt`, `server.crt` y `server.key`

El patrón actual no monta esos `Secret` directamente como rutas finales del broker. En su lugar, un `initContainer` los copia a rutas escribibles dentro de los PVC del broker para no romper la reconciliación actual, que sigue necesitando ownership broker-local sobre `mosquitto_passwd` y `/etc/mosquitto/certs`.

Eso es deliberadamente transicional: ya existe traducción a primitivas de Kubernetes, pero todavía no hay rotación nativa ni reconciliación directa sobre objetos `Secret`.

## Prerrequisitos

- `kind`
- `kubectl`
- imágenes locales `bunkermtest-bunkerm:latest` y `bunkermtest-mosquitto:latest` ya construidas con `./deploy.ps1 -Action build`
- `.env.dev` existente y válido

Este laboratorio asume imágenes locales cargadas en `kind` para los workloads propios de BHM. Dentro de los nodos de `kind` esas imágenes quedan registradas como `localhost/bunkermtest-bunkerm:latest` y `localhost/bunkermtest-mosquitto:latest`, por eso los manifiestos usan esos nombres junto con `imagePullPolicy: Never`.

Si Podman Desktop muestra extensiones activas pero la terminal no resuelve los binarios, hay dos opciones válidas:

- agregar `kind.exe` y `kubectl.exe` al `PATH` de Windows
- pasar las rutas explícitas al bootstrap con `-KindCommand` y `-KubectlCommand`

Si agregas los binarios al `PATH` del usuario mientras VS Code ya está abierto, normalmente necesitarás una terminal nueva o recargar el `PATH` del proceso antes de ejecutar el bootstrap.

## Arranque rápido

```powershell
./k8s/scripts/bootstrap-kind.ps1 -Provider podman
```

Si quieres forzar la carga de la imagen local dentro del clúster:

```powershell
./k8s/scripts/bootstrap-kind.ps1 -Provider podman -LoadLocalImage
```

Si quieres fijar un tag explicito para el laboratorio:

```powershell
./deploy.ps1 -Action build -Runtime kind -ImageTag phase8-lab
./deploy.ps1 -Action start -Runtime kind -ImageTag phase8-lab
```

Si `kubectl` o `kind` no están en `PATH`:

```powershell
./k8s/scripts/bootstrap-kind.ps1 -Provider podman -KubectlCommand "C:\ruta\a\kubectl.exe" -KindCommand "C:\ruta\a\kind.exe"
```

Acceso esperado tras el bootstrap:

- UI/API: `http://localhost:22000`
- MQTT: `localhost:21900`
- MQTT over WebSockets: `localhost:29001`
- namespace: `bhm-lab`

Comandos útiles:

```powershell
kubectl get pods -n bhm-lab
kubectl get svc -n bhm-lab
kubectl logs deployment/bunkerm-platform -n bhm-lab
kubectl logs deployment/bhm-alert-delivery -n bhm-lab
kubectl logs statefulset/mosquitto -n bhm-lab -c broker
kubectl logs statefulset/mosquitto -n bhm-lab -c reconciler
kubectl logs statefulset/mosquitto -n bhm-lab -c observability
```

## Límites del laboratorio

- No sustituye `docker-compose.dev.yml`.
- El broker ya tiene workload real, pero sigue siendo un laboratorio temprano y no un baseline soportado.
- La estrategia de rollback DynSec depende de backups persistidos en `/var/lib/mosquitto/backups` y de la señal `.dynsec-reload` del runtime actual; todavía no es un operador nativo de Kubernetes.
- Si `kind` no puede consumir tu runtime local en Windows/Podman de forma estable, usa este carril solo con imágenes accesibles para el runtime real de `kind`.

## Siguiente corte recomendado

1. Sustituir los placeholders actuales de TLS y `mosquitto_passwd` por material real y por una estrategia de rotación/control-plane que no dependa del seed inicial.
2. Decidir si el reconciliador evoluciona desde sidecar a controlador o job broker-owned una vez desaparezcan las dependencias de filesystem local.
3. Revisar si el estado residual de `/nextjs/data` del proceso web debe persistirse con PVC o extraerse por completo al control-plane.
4. Revisar estrategia de escalado del `Deployment` de `bhm-alert-delivery` si el worker deja de ser single-replica; el laboratorio ya incorpora readiness con chequeo real a PostgreSQL y politicas base de recursos.
