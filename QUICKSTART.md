# BHM — Quick Start

> **Sistema**: Windows (PowerShell) + Podman Desktop + kind (Kubernetes)
> **Ultima revision**: 2026-04-23

---

## Requisitos previos

| Herramienta | Version minima | Notas |
|-------------|----------------|-------|
| Podman Desktop | 1.4+ | debe estar corriendo |
| PowerShell | 5.1+ | incluido en Windows 10/11 |
| kind | 0.20+ | en el PATH |
| kubectl | 1.28+ | en el PATH |

```powershell
kind version ; kubectl version --client ; podman version
```

---

## Ciclo de vida completo

### 1. Setup inicial (primera vez)

```powershell
cd C:\Projects\BunkerMTest\BunkerMTest

# Si PowerShell bloquea la ejecucion de scripts:
Unblock-File deploy.ps1

# Genera .env.dev con secretos aleatorios y crea directorios de datos
.\deploy.ps1 -Action setup
```

`setup` genera con valores seguros aleatorios: `JWT_SECRET`, `AUTH_SECRET`, `API_KEY`,
`POSTGRES_PASSWORD`, `NEXTAUTH_SECRET`, `ADMIN_INITIAL_PASSWORD`.

### 2. Construir imagenes

```powershell
.\deploy.ps1 -Action build            # bhm-frontend, bhm-api, bhm-identity
.\deploy.ps1 -Action build-mosquitto  # broker MQTT (solo si cambia Dockerfile.mosquitto)
```

### 3. Iniciar el cluster y los servicios

```powershell
.\deploy.ps1 -Action start
```

Crea (o reutiliza) el cluster kind `bhm-lab`, carga las imagenes, aplica los manifiestos
Kubernetes y espera a que todos los pods esten listos.

Pods levantados: `postgres`, `mosquitto`, `bhm-frontend`, `bhm-api`,
`bhm-identity`, `bhm-alert-delivery`.

> **Primera vez**: espera 3-5 minutos. PostgreSQL debe inicializarse y los servicios
> Python aplicar las migraciones Alembic antes de arrancar.

### 4. Verificar estado

```powershell
.\deploy.ps1 -Action status   # lista pods y servicios del namespace bhm-lab
.\deploy.ps1 -Action smoke    # checks de endpoints — deben mostrar OK
```

### 5. Acceder a la plataforma

| Servicio | Acceso |
|---------|--------|
| Web UI | http://localhost:22000 |
| API docs (OpenAPI) | http://localhost:22000/api/docs |
| MQTT broker (TCP) | `localhost:21900` |
| MQTT broker (WS) | `localhost:29001` |

```powershell
# Ver credenciales del admin inicial generadas en setup
Get-Content .env.dev | Select-String "ADMIN_INITIAL"
```

---

## Gestion con kubectl

### Estado general

```powershell
kubectl get pods -n bhm-lab                                    # estado de todos los pods
kubectl get svc  -n bhm-lab                                    # servicios y puertos
kubectl get all  -n bhm-lab                                    # todos los recursos
kubectl get events -n bhm-lab --sort-by='.lastTimestamp'       # eventos recientes
```

### Logs

```powershell
kubectl logs deployment/bhm-frontend   -n bhm-lab --tail=100
kubectl logs deployment/bhm-api        -n bhm-lab --tail=100
kubectl logs deployment/bhm-identity   -n bhm-lab --tail=100
kubectl logs statefulset/mosquitto     -n bhm-lab -c mosquitto  --tail=100
kubectl logs statefulset/mosquitto     -n bhm-lab -c reconciler --tail=100
kubectl logs statefulset/postgres      -n bhm-lab --tail=50

# Seguir logs en tiempo real (Ctrl+C para salir)
kubectl logs deployment/bhm-api -n bhm-lab -f
```

### Rollouts y reinicios

```powershell
kubectl rollout restart deployment/bhm-api      -n bhm-lab
kubectl rollout restart deployment/bhm-identity -n bhm-lab
kubectl rollout restart deployment/bhm-frontend -n bhm-lab

# Verificar que un rollout termino correctamente
kubectl rollout status deployment/bhm-api -n bhm-lab
```

### Ejecutar comandos en pods

```powershell
# Abrir shell interactivo
kubectl exec -it -n bhm-lab deployment/bhm-api      -- sh
kubectl exec -it -n bhm-lab deployment/bhm-identity -- sh

# Ver variables de entorno de un pod
kubectl exec -n bhm-lab deployment/bhm-identity -- env

# Migraciones Alembic desde el pod bhm-api
kubectl exec -n bhm-lab deployment/bhm-api -- sh -c "cd /app && alembic upgrade head"
kubectl exec -n bhm-lab deployment/bhm-api -- sh -c "cd /app && alembic current"
```

### Escalar deployments

```powershell
kubectl scale deployment/bhm-api -n bhm-lab --replicas=0   # pausar
kubectl scale deployment/bhm-api -n bhm-lab --replicas=1   # restaurar
```

### Secrets y ConfigMaps

```powershell
# Listar claves del Secret (valores en base64)
kubectl get secret bhm-env -n bhm-lab -o jsonpath='{.data}' | ConvertFrom-Json

# Ver ConfigMap de variables no secretas
kubectl get configmap bhm-k8s-config -n bhm-lab -o yaml
```

---

## Acceso a PostgreSQL

### Port-forward (requerido para conexion externa)

```powershell
# Abrir en una terminal separada; dejar corriendo mientras usas la BD
kubectl port-forward -n bhm-lab statefulset/postgres 5432:5432
```

### Parametros de conexion para herramientas externas

Con el port-forward activo:

| Campo | Valor |
|-------|-------|
| Host | `localhost` |
| Puerto | `5432` |
| Base de datos | `bhm_db` |
| Usuario | `bhm` |
| Contrasena | valor de `POSTGRES_PASSWORD` en `.env.dev` |

```powershell
Get-Content .env.dev | Select-String "POSTGRES_PASSWORD"
```

#### pgAdmin 4

1. Descargar desde https://www.pgadmin.org/download/ e instalar
2. Iniciar el port-forward (ver arriba)
3. En pgAdmin: **Add New Server**
   - **General > Name**: `BHM Dev`
   - **Connection > Host**: `localhost`
   - **Connection > Port**: `5432`
   - **Connection > Username**: `bhm`
   - **Connection > Password**: valor de `POSTGRES_PASSWORD`
   - **Connection > Maintenance database**: `bhm_db`

#### DBeaver Community

1. Descargar desde https://dbeaver.io/download/ e instalar
2. Iniciar el port-forward
3. Nueva conexion > tipo **PostgreSQL**
   - Server Host: `localhost` / Port: `5432`
   - Database: `bhm_db` / Username: `bhm` / Password: valor de `POSTGRES_PASSWORD`
4. Aceptar la descarga del driver JDBC cuando DBeaver lo solicite

### Conexion psql directo en el pod (sin port-forward)

```powershell
kubectl exec -it -n bhm-lab statefulset/postgres -- psql -U bhm -d bhm_db
```

### Consultas utiles

```sql
-- Schemas disponibles
\dn

-- Usuarios del panel (schema identity)
SET search_path TO identity;
SELECT id, email, role, created_at FROM bhm_users;

-- Estado de reconciliacion del broker (schema control_plane)
SET search_path TO control_plane;
SELECT * FROM reconcile_state ORDER BY updated_at DESC LIMIT 10;

-- Estadisticas diarias (schema reporting)
SET search_path TO reporting;
SELECT * FROM daily_broker_reports ORDER BY date DESC LIMIT 7;

-- Ultimos eventos de clientes (schema history)
SET search_path TO history;
SELECT * FROM client_events ORDER BY created_at DESC LIMIT 20;
```

---

## Port-forwards para otros servicios

```powershell
kubectl port-forward -n bhm-lab service/bhm-api      9001:9001   # API directo
kubectl port-forward -n bhm-lab service/bhm-identity 8080:8080   # Identity directo
kubectl port-forward -n bhm-lab service/bhm-frontend 2000:2000   # alternativa al NodePort
```

---

## Actualizacion de componentes individuales

Con el cluster corriendo puedes reconstruir y desplegar cualquier componente de forma
aislada sin tocar los demas pods ni perder el estado de PostgreSQL.

### Reconstruir y aplicar un solo componente

```powershell
# Solo el frontend (Next.js + nginx)
.\deploy.ps1 -Action update-frontend

# Solo el backend API (bhm-api + bhm-alert-delivery comparten imagen)
.\deploy.ps1 -Action update-api

# Solo el servicio de identidad / login
.\deploy.ps1 -Action update-identity

# Solo el broker MQTT (mosquitto + sidecars reconciler/observability)
.\deploy.ps1 -Action update-mosquitto

# Todos los componentes en secuencia (sin recrear el cluster)
.\deploy.ps1 -Action update-all
```

Cada `update-*` ejecuta: **build de imagen → carga en kind → rollout restart**.

> `update-api` hace rollout de `deployment/bhm-api` **y** `deployment/bhm-alert-delivery`
> porque comparten la misma imagen `bhm-api`.

---

## Rollout sin rebuild de imagen

Si solo necesitas reiniciar un pod (cambio de ConfigMap, Secret o pod colgado) sin
reconstruir ninguna imagen:

```powershell
# Reiniciar un componente especifico
.\deploy.ps1 -Action rollout -Component frontend
.\deploy.ps1 -Action rollout -Component api          # api + alert-delivery
.\deploy.ps1 -Action rollout -Component identity
.\deploy.ps1 -Action rollout -Component mosquitto
.\deploy.ps1 -Action rollout -Component alerts       # solo alert-delivery

# Reiniciar todos los pods
.\deploy.ps1 -Action rollout -Component all
```

---

## Desarrollo: hot-patch sin rebuild de imagen

Para iterar rapido en el codigo fuente sin esperar un build de imagen completo:

```powershell
.\deploy.ps1 -Action patch-backend   # copia /backend/app al pod y reinicia bhm-api
.\deploy.ps1 -Action patch-frontend  # copia /frontend al pod y reinicia bhm-frontend
```

> Nota: los cambios del hot-patch se pierden con el siguiente rollout o recreacion
> del pod. Para persistirlos hay que hacer un `update-*`.

---

## Redeploy completo preservando secretos

Destruye el cluster kind y lo recrea desde cero, sin tocar `.env.dev`.

```powershell
.\deploy.ps1 -Action redeploy
```

Equivalente manual:
```powershell
.\deploy.ps1 -Action clean    # elimina el cluster (pide confirmacion)
.\deploy.ps1 -Action start    # recrea el cluster con los secretos existentes
```

---

## Mantenimiento

### Re-inyectar secretos despues de cambiar .env.dev

Si rotaste una contrasena o cambiaste una variable en `.env.dev` sin recrear el cluster:

```powershell
.\deploy.ps1 -Action env-sync
```

El script elimina y recrea el Secret `bhm-env` con los valores actuales de `.env.dev`.
Al finalizar pregunta si hacer rollout de todos los pods para aplicar los cambios.

### Aplicar migraciones de base de datos

```powershell
.\deploy.ps1 -Action db-migrate
```

Ejecuta `alembic upgrade head` dentro del pod `bhm-api` en estado Running y muestra
la salida completa. No reinicia ningun servicio.

### Recargar configuracion de Mosquitto

```powershell
.\deploy.ps1 -Action reload-mosquitto
```

Envia una senal de recarga al pod mosquitto. Util despues de cambiar reglas ACL
o configuracion del broker sin necesidad de reiniciar el StatefulSet.

---

## Tests y smoke

```powershell
.\deploy.ps1 -Action test    # pytest en el pod bhm-api
.\deploy.ps1 -Action smoke   # checks de endpoints del stack
```

---

## Ciclo de vida del cluster

```powershell
.\deploy.ps1 -Action stop      # escala todos los workloads a 0 (preserva cluster y PVCs)
.\deploy.ps1 -Action restart   # stop + start
.\deploy.ps1 -Action logs      # logs de los deployments principales
.\deploy.ps1 -Action clean     # PELIGRO: elimina el cluster completo
```

---

## Diagnostico rapido

```powershell
# Por que no arranca un pod
kubectl describe pod -n bhm-lab -l app.kubernetes.io/name=bhm-identity

# Eventos de warning del namespace
kubectl get events -n bhm-lab --field-selector=type=Warning

# Verificar que el Secret de credenciales existe
kubectl get secret bhm-env -n bhm-lab
```

---

## Referencia rapida de todas las acciones

| Accion | Descripcion |
|--------|-------------|
| `setup` | Genera `.env.dev` con secretos aleatorios y crea directorios de datos |
| `build` | Construye las 4 imagenes (frontend, api, identity, mosquitto) |
| `build-mosquitto` | Construye solo la imagen del broker MQTT |
| `start` | Crea (o reutiliza) el cluster kind y levanta todos los workloads |
| `stop` | Escala los workloads a 0; preserva el cluster y los PVCs |
| `restart` | `stop` + `start` |
| `status` | Lista pods y servicios del namespace bhm-lab |
| `logs` | Muestra logs de los pods principales |
| `smoke` | Checks de endpoints — deben mostrar OK |
| `test` | Ejecuta pytest dentro del pod bhm-api |
| `clean` | Elimina el cluster kind completo (pide confirmacion) |
| `redeploy` | Destruye el cluster y lo recrea preservando `.env.dev` |
| `update-frontend` | Build + carga en kind + rollout de bhm-frontend |
| `update-api` | Build + carga en kind + rollout de bhm-api y bhm-alert-delivery |
| `update-identity` | Build + carga en kind + rollout de bhm-identity |
| `update-mosquitto` | Build + carga en kind + rollout de mosquitto |
| `update-all` | Todos los `update-*` en secuencia |
| `rollout -Component <X>` | Rollout restart sin rebuild (`frontend\|api\|identity\|mosquitto\|alerts\|all`) |
| `patch-frontend` | Hot-copy de fuentes al pod + rollout (sin rebuild) |
| `patch-backend` | Hot-copy de fuentes al pod + rollout (sin rebuild) |
| `env-sync` | Recrea el Secret `bhm-env` con los valores de `.env.dev` |
| `db-migrate` | Ejecuta `alembic upgrade head` en el pod bhm-api |
| `reload-mosquitto` | Envia senal de recarga al pod mosquitto |

