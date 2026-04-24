# BHM — Plan: Acciones de Deploy Granular por Componente

> **Estado**: Implementado  
> **Fecha**: 2026-04-23  
> **Alcance**: `deploy.ps1` + `QUICKSTART.md`  
> **Arquitectura**: Kubernetes (kind) — sin rastros Compose

---

## Motivación

El ciclo heredado (`clean → setup → build → start`) fue diseñado para un monolito Docker Compose.
Con la arquitectura Kubernetes actual los 6 workloads son independientes:

| Pod | Tipo | Imagen |
|-----|------|--------|
| `postgres` | StatefulSet | `postgres:16-alpine` |
| `mosquitto` | StatefulSet + sidecars | `localhost/bhm-mosquitto` |
| `bhm-frontend` | Deployment | `localhost/bhm-frontend` |
| `bhm-api` | Deployment | `localhost/bhm-api` |
| `bhm-identity` | Deployment | `localhost/bhm-identity` |
| `bhm-alert-delivery` | Deployment | `localhost/bhm-api` (misma imagen) |

Actualizar cualquiera de ellos no debería requerir derribar el cluster completo.

---

## Fases de implementación

### Fase A — Refactorización de `Invoke-Build`

Extraer tres funciones atómicas desde `Invoke-Build`:

- `Invoke-BuildFrontendImage` → `docker build -f Dockerfile.frontend`
- `Invoke-BuildApiImage` → `docker build -f Dockerfile.api`
- `Invoke-BuildIdentityImage` → `docker build -f Dockerfile.identity`

`Invoke-Build` se refactoriza para llamar a las tres en secuencia (comportamiento idéntico al original). `Invoke-BuildMosquitto` ya existe y no cambia.

### Fase B — Helpers de infraestructura Kind

Dos funciones reutilizables:

**`Invoke-LoadImageIntoKind [string]$ImageName`**  
Carga una imagen local al nodo kind sin necesidad de re-ejecutar el bootstrap completo:
- Podman: `podman save --format oci-archive` → `kind load image-archive`
- Docker: `kind load docker-image`

**`Invoke-RolloutRestart [string]$Resource`**  
Ejecuta `kubectl rollout restart` + `kubectl rollout status --timeout=120s` y propaga errores.

### Fase C — 5 acciones de actualización por componente

| Acción | Build | Load en Kind | Rollout |
|--------|-------|-------------|---------|
| `update-frontend` | `bhm-frontend` | ✓ | `deployment/bhm-frontend` |
| `update-api` | `bhm-api` | ✓ | `deployment/bhm-api` + `deployment/bhm-alert-delivery` |
| `update-identity` | `bhm-identity` | ✓ | `deployment/bhm-identity` |
| `update-mosquitto` | `bhm-mosquitto` | ✓ | `statefulset/mosquitto` |
| `update-all` | todas las anteriores en secuencia | — | — |

Todas verifican que el cluster kind exista antes de proceder.

> `bhm-alert-delivery` comparte imagen con `bhm-api`, por eso `update-api` hace rollout de ambos.

### Fase D — Acción `rollout` (reinicio sin rebuild)

Nuevo parámetro `-Component` (`frontend` | `api` | `identity` | `mosquitto` | `alerts` | `all`).

Reinicia el workload indicado sin construir ninguna imagen. Útil cuando solo cambió un
ConfigMap, Secret, o se quiere recuperar un pod colgado.

```powershell
.\deploy.ps1 -Action rollout -Component api
.\deploy.ps1 -Action rollout -Component all
```

### Fase E — 3 acciones de operación y mantenimiento

**`redeploy`**  
Destruye el cluster (`clean` sin borrar `.env.dev`) y ejecuta `start` completo.
Equivale al ciclo `clean → start` preservando todos los secretos.

```powershell
.\deploy.ps1 -Action redeploy
```

**`env-sync`**  
Re-inyecta las variables de `.env.dev` en el Secret `bhm-env` del cluster activo.
Ofrece hacer rollout de todos los pods para que los cambios tengan efecto.
Útil después de rotar contraseñas o cambiar parámetros sin reconstruir imágenes.

```powershell
.\deploy.ps1 -Action env-sync
```

**`db-migrate`**  
Ejecuta `alembic upgrade head` dentro del pod `bhm-api` en estado Running.
Permite aplicar migraciones de base de datos sin reiniciar ningún servicio.

```powershell
.\deploy.ps1 -Action db-migrate
```

### Fase F — Limpieza Compose

Eliminar del script todas las referencias a Docker Compose:
- Función `Invoke-StartBunkerM` (redirección obsoleta)
- Función `Invoke-StopBunkerM` (redirección obsoleta)
- Acciones `start-bunkerm` y `stop-bunkerm` del `ValidateSet` y `switch`
- Mensajes de texto que mencionan Compose

### Fase G — Actualización QUICKSTART.md

1. Corregir bug: puerto MQTT WS `21901` → `29001`
2. Sección: Actualización de componentes individuales (`update-*`, `rollout`)
3. Sección: Redeploy completo preservando secretos (`redeploy`)
4. Sección: Operaciones de mantenimiento (`env-sync`, `db-migrate`)
5. Tabla de referencia rápida con todas las acciones

---

## Tabla de acciones completa (post-implementación)

| Acción | Descripción |
|--------|-------------|
| `setup` | Genera `.env.dev` y directorios de datos |
| `build` | Construye las 4 imágenes (frontend, api, identity, mosquitto) |
| `build-mosquitto` | Construye solo la imagen del broker |
| `start` | Levanta el cluster kind y todos los workloads |
| `stop` | Escala todos los workloads a 0 (preserva cluster y PVCs) |
| `restart` | `stop` + `start` |
| `status` | Lista pods y servicios del namespace |
| `logs` | Muestra logs de los pods principales |
| `smoke` | Checks de endpoints críticos |
| `test` | Ejecuta pytest dentro del pod bhm-api |
| `clean` | Elimina el cluster kind (pide confirmación) |
| `redeploy` | Destruye el cluster y lo recrea desde cero (preserva `.env.dev`) |
| `update-frontend` | Rebuild + recarga en kind + rollout solo del frontend |
| `update-api` | Rebuild + recarga en kind + rollout del api y alert-delivery |
| `update-identity` | Rebuild + recarga en kind + rollout solo del identity |
| `update-mosquitto` | Rebuild + recarga en kind + rollout solo de mosquitto |
| `update-all` | Rebuild + recarga + rollout de todos los componentes |
| `rollout` | Rollout sin rebuild del componente indicado con `-Component` |
| `patch-frontend` | Hot-copy de fuentes al pod + rollout (sin rebuild de imagen) |
| `patch-backend` | Hot-copy de fuentes al pod + rollout (sin rebuild de imagen) |
| `env-sync` | Re-inyecta `.env.dev` en el Secret bhm-env del cluster |
| `db-migrate` | Ejecuta `alembic upgrade head` en el pod bhm-api |
| `reload-mosquitto` | Envía señal de recarga de configuración al pod mosquitto |

---

## Decisiones de diseño

- **`postgres` sin `update-postgres`**: es un StatefulSet con datos persistentes. Actualizar su imagen sin un proceso de migración cuidadoso puede corromper datos. Usar `kubectl` directamente si se necesita.
- **`-ImageTag`**: el parámetro existente aplica a todas las imágenes simultáneamente. No se añade soporte multi-tag por ahora.
- **`-Runtime`**: se mantiene el parámetro pero solo `kind` es soportado. El resto del flujo Compose ha sido eliminado.
