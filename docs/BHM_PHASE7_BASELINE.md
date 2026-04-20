# BHM - Baseline inicial de Fase 7

Este documento fija el primer carril ejecutable de hardening para Fase 7. El objetivo no es declarar el sistema como "rendimiento validado", sino dejar una referencia reproducible para medir latencia, conectividad MQTT y resiliencia básica antes de nuevos cambios estructurales.

## Alcance del primer corte

- baseline HTTP/MQTT reproducible sobre el runtime activo
- verificación de smoke previa a cada medición
- reutilización del stresser MQTT ya existente
- evidencia explícita de hallazgos negativos cuando la carga expone degradación

## Harness añadido

Script nuevo: `scripts/dev-tools/phase7_baseline.py`

Snapshot complementario de recursos: `scripts/dev-tools/phase7_resource_snapshot.py`

Provisioning medible del carril MQTT `per-client`: `scripts/dev-tools/phase7_provision_mqtt_clients.py`

Mide:

- latencia HTTP de endpoints base del producto publicados en host
- latencia de conexión TCP al puerto MQTT publicado
- estado agregado `ok/degraded`
- salida JSON apta para versionar o comparar entre ejecuciones

El snapshot de recursos intenta además:

- `kubectl top pods -n bhm-lab` para CPU y memoria por pod en `kind`
- `kubectl get pvc -n bhm-lab -o json` para capacidad declarada de almacenamiento
- `podman stats --no-stream --format json` para runtime Compose cuando se ejecute con `--runtime compose`

El script de provisioning MQTT permite además:

- crear o reconciliar clientes `1..N` por la API publicada del producto
- asignar el rol `subscribe-and-publish`
- esperar settlement `applied` real por cliente
- capturar una primera métrica broker-facing basada en `desiredUpdatedAt -> appliedAt`

Targets por defecto pensados para el laboratorio `kind` actual:

- `http://localhost:22000/`
- `http://localhost:22000/api/auth/me`
- `http://localhost:22000/api/monitor/health`
- `http://localhost:22000/api/dynsec/roles`
- `localhost:21900` para conectividad MQTT TCP

`reporting` puede medirse ya de forma estable a traves del proxy autenticado publicado en host (`/api/proxy/reports/...`).

`security` sigue siendo opcional en el baseline por defecto porque el carril publicado para esa capability no formaba parte del contrato host-facing usado en esta validacion de cierre.

## Ejecución recomendada

### 1. Confirmar runtime sano

```powershell
./deploy.ps1 -Action smoke -Runtime kind
```

### 2. Capturar baseline HTTP/MQTT

```powershell
c:/Projects/BunkerMTest/BunkerMTest/.venv/Scripts/python.exe scripts/dev-tools/phase7_baseline.py `
  --base-url http://localhost:22000 `
  --runtime-label kind `
  --mqtt-host localhost `
  --mqtt-port 21900 `
  --samples 5 `
  --output tmp/phase7-kind-baseline.json
```

### 3. Ejecutar carga MQTT ligera

```powershell
Push-Location greenhouse-simulator/src/Greenhouse.Sensors
podman run --rm --network kind --env-file mqtt-stresser.kind.env -e CLIENTS=8 -e MSGS=20 -e TIME=5 mqtt-stresser
Pop-Location
```

### 4. Capturar snapshot de recursos

```powershell
c:/Projects/BunkerMTest/BunkerMTest/.venv/Scripts/python.exe scripts/dev-tools/phase7_resource_snapshot.py `
  --runtime kind `
  --namespace bhm-lab `
  --output tmp/phase7-kind-resources.json
```

### 5. Reprovisionar clientes MQTT `per-client`

```powershell
c:/Projects/BunkerMTest/BunkerMTest/.venv/Scripts/python.exe scripts/dev-tools/phase7_provision_mqtt_clients.py `
  --base-url http://localhost:22000 `
  --runtime-label kind `
  --start-index 1 `
  --count 8 `
  --output tmp/phase7-kind-mqtt-provision.json
```

## Evidencia validada en esta iteración

- `./deploy.ps1 -Action smoke -Runtime kind` volvió a cerrar en `5/5 OK` antes de la toma del baseline.
- `c:/Projects/BunkerMTest/BunkerMTest/.venv/Scripts/python.exe scripts/dev-tools/phase7_baseline.py --base-url http://localhost:22000 --runtime-label kind --mqtt-host localhost --mqtt-port 21900 --samples 5 --output tmp/phase7-kind-baseline.json` terminó en `overallStatus=ok`.
- Resumen del baseline capturado sobre `kind`:
  - Web UI `/`: `mean=464.35 ms`, `median=48.35 ms`, `p95=1712.66 ms`.
  - `GET /api/auth/me`: `mean=49.93 ms`, `p95=54.54 ms`.
  - `GET /api/monitor/health`: `mean=49.68 ms`, `p95=52.13 ms`.
  - `GET /api/dynsec/roles`: `mean=47.82 ms`, `p95=51.05 ms`.
  - `GET /api/proxy/reports/broker/daily?days=7`: `mean=57.21 ms`, `p95=59.18 ms`.
  - MQTT TCP `localhost:21900`: `mean=5.08 ms`, `p95=17.59 ms`.
- `./deploy.ps1 -Action restart -Runtime kind` recreó por completo el laboratorio y el smoke posterior volvió a cerrar en `5/5 OK`, dejando validado el carril mínimo de restart controlado en esta fase.
- La resiliencia por fallo parcial ya quedó validada mas alla del restart completo: tras eliminar el pod `bunkerm-platform`, Kubernetes recuperó el deployment y `./deploy.ps1 -Action smoke -Runtime kind` volvió a cerrar en `5/5 OK` despues de endurecer la autorecuperacion de `kubectl port-forward` y la liberacion de puertos en Windows.
- El stresser quedó endurecido para no abortar toda la corrida por una desconexión individual antes del bloque principal de manejo de errores y para cerrar conexiones limpiamente al terminar cada task.
- Tras reconstruir la imagen `mqtt-stresser`, el modo `per-client` ya no tumba la corrida aunque falle la autenticación: la misma prueba corta cerró con `8` errores contenidos y `0` relaciones, evidenciando que el bloqueo actual después del `restart` de `kind` está en el provisioning DynSec `1..8`, no en una caída no controlada del proceso.
- Como baseline mínimo de throughput MQTT ya quedó validado el modo `shared`: `CLIENTS=8`, `MSGS=20`, `TIME=1` terminó con `160` relaciones simuladas, `79` publicaciones, `81` suscripciones y `0` errores.
- `scripts/dev-tools/phase7_provision_mqtt_clients.py --base-url http://localhost:22000 --runtime-label kind --start-index 1 --count 8 --output tmp/phase7-kind-mqtt-provision.json` reprovisionó correctamente los clientes DynSec `1..8` y dejó una primera métrica broker-facing de apply: ventana `desiredUpdatedAt -> appliedAt` entre `256.68 ms` y `1009.46 ms`, con media `880.78 ms` y mediana `984.32 ms`.
- Tras ese reprovisioning, el carril recomendado `per-client` volvió a quedar verde en `kind`: `CLIENTS=8`, `MSGS=20`, `TIME=5` terminó con `160` relaciones simuladas, `70` publicaciones, `90` suscripciones y `0` errores.
- El snapshot de recursos `tmp/phase7-kind-resources.json` ya quedó verde en `kind` usando fallback `crictl` sobre todos los nodos del cluster, manteniendo la advertencia de `Metrics API not available` pero capturando CPU y memoria reales por pod: `bunkerm-platform 12.06 mCPU / 154.69 MiB`, `mosquitto-0 8.50 mCPU / 132.69 MiB` y `postgres-0 5.81 mCPU / 41.79 MiB`.
- La validacion ligera de concurrencia API también quedó verde sobre el runtime host-publicado: `10/10` respuestas correctas en `monitor/health`, `dynsec/roles` y `reports/broker/daily`.
- El burst MQTT corto también quedó verde: `CLIENTS=8`, `MSGS=60`, `TIME=1` terminó con `480` relaciones simuladas y `0` errores de autorización.
- El churn real de clientes DynSec quedó validado de punta a punta tras reconstruir y redeployar la imagen actualizada: para `phase7-churn-1..4`, el estado final de borrado convergió a `status=applied`, `driftDetected=false`, `desired.deleted=true` y `observed=null`.
- La corrección de semántica de borrado quedó confirmada en runtime; la regresión local aislada de `pytest` sobre `test_delete_client_marks_desired_state_as_deleted` sigue fallando fuera del runtime por resolución DNS de `postgres`, pero ese fallo es de entorno de test local y no contradice la validación real sobre `kind`.

## Qué considerar "verde" en este corte

- smoke `kind` en verde antes de medir
- baseline JSON generado sin checks degradados en HTTP/MQTT base
- stresser MQTT capaz de completar su carga sin desconexión abrupta del cliente
- resiliencia host-facing verde ante restart completo y ante reemplazo parcial del pod principal
- churn DynSec borrado/applied sin drift falso en runtime real

## Qué queda pendiente después de este corte

- decidir si `reporting` pasa a target por defecto del harness o se mantiene opcional por requerir autenticación de sesión
- convertir las validaciones de fallo parcial, concurrencia y churn en carriles automatizados dentro del harness o de `deploy.ps1`
- ampliar la carga MQTT desde smoke ligero a baseline reportable con throughput, duración y error budget