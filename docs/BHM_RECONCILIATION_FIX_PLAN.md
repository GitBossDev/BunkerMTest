# BHM — Plan: Corrección de Reconciliación y Config del Broker en Kubernetes

> **Estado**: Implementado  
> **Fecha**: 2026-04-24  
> **Iteraciones**: 1

---

## Síntomas reportados

| # | Error | Acción que lo dispara |
|---|-------|-----------------------|
| 1 | `Client reconciliation failed: createClient:X: [Errno 2] No such file or directory: 'mosquitto_ctrl'` | Crear cliente |
| 2 | `Role reconciliation failed: createRole:X: [Errno 2] No such file or directory: 'mosquitto_ctrl'` | Crear rol |
| 3 | `Group reconciliation failed: createGroup:X: [Errno 2] No such file or directory: 'mosquitto_ctrl'` | Crear grupo |
| 4 | `Duplicate listener port 1900 found in configuration` | Guardar configuración del broker |
| 5 | `Failed to update default ACL access` | Modificar ACL por defecto |
| 6 | No se pueden eliminar clientes ni modificar permisos tras la importación | Operaciones dynsec post-import |

---

## Diagnóstico: causas raíz

### Causa A — `mosquitto_ctrl` no instalado en la imagen `bhm-api`

El sidecar `reconciler` del `StatefulSet/mosquitto` usa la imagen `bhm-api`. Este sidecar ejecuta toda la reconciliación: `createClient`, `createRole`, `createGroup`, `deleteClient`, `setDefaultACLAccess`, etc., mediante:

```python
subprocess.run(["mosquitto_ctrl", "-h", ..., "dynsec", ...])
```

El binario `mosquitto_ctrl` pertenece al paquete Linux **`mosquitto-clients`**, que **no estaba instalado** en el `Dockerfile.api`. Por eso `subprocess.run` lanza `[Errno 2] No such file or directory`.

**Esta única causa explica los issues 1, 2, 3, 5 y 6.**

### Causa B — `bhm-api` no tiene el volumen `mosquitto-conf` montado

`bhm-api.yaml` solo monta `api-logs: emptyDir`. El deployment `bhm-api` no tiene acceso a `/etc/mosquitto/mosquitto.conf`. Cuando la ruta `POST /api/v1/config/mosquitto-config` invoca `parse_mosquitto_conf()` → `FileNotFoundError` → retorna `{}` → el endpoint luego intenta **escribir directamente** a `/etc/mosquitto/mosquitto.conf` en el pod bhm-api, que no tiene ese path → falla silenciosamente o genera config corrupta.

Adicionalmente, `generate_mosquitto_conf()` no tenía `'listener'` en `_SKIP_KEYS`, por lo que si el dict `config_data` contenía la clave `listener` (artefacto del parsing), se emitía una línea suelta `listener <valor>` **además** de los bloques `listener` normales → duplicado de puerto 1900.

**Esta causa explica el issue 4.**

---

## Fases de implementación

### Fase 1 — `Dockerfile.api`: instalar `mosquitto-clients`

**Archivo**: `bunkerm-source/Dockerfile.api`  
**Cambio**: añadir `mosquitto-clients \` al bloque `apt-get install`.

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libffi-dev \
    libpq-dev \
    mosquitto-clients \       # ← AÑADIDO
    && rm -rf /var/lib/apt/lists/*
```

Provee los binarios `mosquitto_ctrl`, `mosquitto_pub` y `mosquitto_sub` en `/usr/bin/`.

---

### Fase 2 — `bhm-api.yaml`: montar `mosquitto-conf` como ReadOnly

**Archivo**: `k8s/base/bhm-api.yaml`  
**Cambio**: añadir `volumeMount` y `volume` para que `bhm-api` pueda leer `/etc/mosquitto/mosquitto.conf`.

```yaml
# volumeMounts del container bhm-api
- name: mosquitto-conf
  mountPath: /etc/mosquitto
  readOnly: true

# volumes del pod
- name: mosquitto-conf
  persistentVolumeClaim:
    claimName: mosquitto-conf-mosquitto-0
```

El PVC `mosquitto-conf-mosquitto-0` es creado automáticamente por el `volumeClaimTemplate` del `StatefulSet/mosquitto`. En kind (single-node) el modo `ReadWriteOnce` permite múltiples lectores en el mismo nodo.

---

### Fase 3a — `mosquitto_config.py`: añadir `'listener'` a `_SKIP_KEYS`

**Archivo**: `bunkerm-source/backend/app/config/mosquitto_config.py`  
**Cambio**: en `generate_mosquitto_conf`, añadir `'listener'` al set `_SKIP_KEYS` para que la clave nunca se emita como línea plana.

```python
_SKIP_KEYS = {"plugin", "plugin_opt_config_file", "log_type", "listener"}
```

---

### Fase 3b — `config_mosquitto.py`: POST usa desired_state en lugar de escritura directa

**Archivo**: `bunkerm-source/backend/app/routers/config_mosquitto.py`  
**Cambio**: el endpoint `POST /mosquitto-config` delega en `desired_state_svc` + reconciler, siguiendo el mismo patrón que todos los demás endpoints. El reconciler (que SÍ tiene el volumen `mosquitto-conf` montado en escritura) es quien escribe el archivo físico.

---

## Secuencia de deploy

```powershell
# Rebuild + reload del sidecar reconciler (imagen compartida bhm-api)
.\deploy.ps1 -Action update-api

# El sidecar reconciler está en el StatefulSet mosquitto, no en bhm-api deployment
# update-api hace rollout de deployment/bhm-api pero NO del statefulset/mosquitto sidecar
# → necesitamos rollout del statefulset también
.\deploy.ps1 -Action rollout -Component mosquitto

# Aplicar cambios de manifiesto (montaje del PVC)
kubectl apply -k k8s/base --context kind-bhm-lab
kubectl rollout restart deployment/bhm-api -n bhm-lab
kubectl rollout status deployment/bhm-api -n bhm-lab
```

---

## Testing básico post-deploy

```powershell
# 1. Smoke check general
.\deploy.ps1 -Action smoke

# 2. Verificar que mosquitto_ctrl está disponible en el sidecar
$pod = kubectl get pods -n bhm-lab -l app.kubernetes.io/name=mosquitto -o jsonpath='{.items[0].metadata.name}'
kubectl exec -n bhm-lab $pod -c reconciler -- which mosquitto_ctrl

# 3. Crear un cliente de prueba via API
$apiKey = (Get-Content .env.dev | Select-String "^API_KEY=").Line.Split("=",2)[1]
Invoke-RestMethod -Uri "http://localhost:22000/api/v1/dynsec/clients" `
    -Method POST `
    -Headers @{"X-API-Key"=$apiKey; "Content-Type"="application/json"} `
    -Body '{"username":"testuser","password":"Test1234!"}'

# 4. Crear un rol de prueba
Invoke-RestMethod -Uri "http://localhost:22000/api/v1/dynsec/roles" `
    -Method POST `
    -Headers @{"X-API-Key"=$apiKey; "Content-Type"="application/json"} `
    -Body '{"rolename":"testrol"}'

# 5. Eliminar el cliente de prueba
Invoke-RestMethod -Uri "http://localhost:22000/api/v1/dynsec/clients/testuser" `
    -Method DELETE `
    -Headers @{"X-API-Key"=$apiKey}

# 6. Verificar configuración del broker (GET debe retornar config real)
Invoke-RestMethod -Uri "http://localhost:22000/api/v1/config/mosquitto-config" `
    -Headers @{"X-API-Key"=$apiKey}
```

---

## Archivos modificados

| Archivo | Tipo de cambio |
|---------|---------------|
| `bunkerm-source/Dockerfile.api` | Añadir `mosquitto-clients` al apt-get |
| `k8s/base/bhm-api.yaml` | Montar PVC `mosquitto-conf` como ReadOnly |
| `bunkerm-source/backend/app/config/mosquitto_config.py` | Añadir `'listener'` a `_SKIP_KEYS` |
| `bunkerm-source/backend/app/routers/config_mosquitto.py` | POST delega en desired_state_svc |
