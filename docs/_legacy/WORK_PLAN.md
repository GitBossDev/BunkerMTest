# BHM — Plan de Trabajo Post-Reestructuración

> **Contexto**: Las Fases 1–4 de `bunkerm-source/` han sido completadas (ver `bunkerm-source/RESTRUCTURE_PLAN.md`).
> Este documento cubre las dos tareas pendientes: verificar que la integración funciona de extremo a extremo,
> y ordenar el workspace raíz eliminando ruido (archivos duplicados, scripts dispersos, configuraciones obsoletas).
>
> **Motor de contenedores**: Podman Desktop (`podman` / `podman compose`)
> **Última actualización**: 2026-04-10

---

## Progreso general

| Parte | Estado | Descripción |
|-------|--------|-------------|
| **Parte V** | ✅ Completa | Verificación de integración (3 sub-fases) |
| **Parte C** | ✅ Completa | Limpieza del workspace raíz (6 sub-fases) |

---

## PARTE V — Verificación de integración

*Ejecutar en orden. No avanzar a Parte C hasta completar V3.*

---

### V1 — Validación estática (sin contenedores)

*Sin levantar Podman. Detecta errores antes de un build costoso.*

| # | Estado | Comando / Acción |
|---|--------|-----------------|
| V1.1 | ⚠️ | `npm run build` — Node.js no instalado localmente. El build TypeScript se valida dentro del contenedor en V2.2 (`FROM node:20-alpine`). |
| V1.2 | ✅ | `grep -r "Para CIC" bunkerm-source/` → 0 resultados |
| V1.3 | ✅ | `grep -r "generateNonce" bunkerm-source/frontend/` → 0 resultados |
| V1.4 | ✅ | `grep -r "Math.random" bunkerm-source/frontend/lib/` → 0 resultados |
| V1.5 | ✅ | `bunkerm-source/frontend/src/` no existe |
| V1.6 | ✅ | Syntax check Python: `main.py` + 15 archivos de Fase 3 (core, models, routers, services) → 15 OK, 0 FAIL |
| V1.7 | ✅ | `Dockerfile.next` línea 180: `PYTHONPATH=/app:/app/smart-anomaly` |
| V1.8 | ✅ | `supervisord-next.conf` tiene 3 programas: `bunkerm-api` (Python/9001), `nextjs-frontend` (Node/3000), `nginx` — correcto. Un solo proceso Python de backend. |
| V1.9 | ✅ | `default-next.conf`: 9 locations a `http://127.0.0.1:9001` + 1 a `http://127.0.0.1:3000` (Next.js frontend — correcto) |

---

### V2 — Build de imágenes Podman

| # | Estado | Comando / Acción |
|---|--------|-----------------|
| V2.1 | ✅ | `.\.deploy.ps1 -Action build-mosquitto` — `bunkermtest-mosquitto:latest` construida (63.3 MB) |
| V2.2 | ✅ | `.\.deploy.ps1 -Action build` — `bunkermtest-bunkerm:latest` construida (926 MB). pip install OK + `npm run build` OK |
| V2.3 | ⬜ | Si el build falla en el stage Python: revisar que `bunkerm-source/Dockerfile.next` tiene `asyncpg>=0.29.0` en el bloque pip |
| V2.4 | ⬜ | Si el build falla en el stage Next.js: revisar errores del paso V1.1 primero |

---

### V3 — Validación en runtime

| # | Estado | Comando / Acción |
|---|--------|-----------------|
| V3.1 | ✅ | `.\deploy.ps1 -Action start` — `bunkerm-mosquitto` (healthy) + `bunkerm-platform` (healthy) arrancados |
| V3.2 | ✅ | `podman ps` — ambos Up y healthy. Puertos externos: `:2000` (BHM), `:1900` (MQTT). |
| V3.3 | ✅ | `GET http://localhost:2000` → 200 (Next.js sirviendo) |
| V3.4 | ✅ | `GET http://localhost:2000/api/auth/me` → 401 (sin autenticación, correcto) |
| V3.5 | ✅ | `GET http://localhost:2000/api/dynsec/clients` con `X-API-Key` → 200 |
| V3.6 | ✅ | `/api/monitor/stats` → 422 (requiere `nonce`+`timestamp`). `/api/monitor/stats/health` → 200 ✓ |
| V3.7 | ✅ | `GET http://localhost:2000/api/config/mosquitto-config` con `X-API-Key` → 200 |
| V3.8 | ✅ | `GET http://localhost:2000/api/clientlogs/events` con `X-API-Key` → 200 |
| V3.9 | ✅ | `GET http://localhost:2000/api/v1/ai/health` con `X-API-Key` → 200. (Prefijo real: `/api/v1/ai`) |
| V3.10 | ✅ | `podman exec bunkerm-platform ls /nextjs/data/backups` → directorio existe (vacío) |
| V3.11 | ✅ | `netstat -tlnp` → solo `9001` (uvicorn), `2000` (nginx), `127.0.0.1:3000` (Next.js). Cero puertos 1000-1005 o 8100. |
| V3.12 | ✅ | Login manual en la UI: `http://localhost:2000/login` → crear sesión y navegar a Dashboard, Clientes, Monitoring |

---

## PARTE C — Limpieza del workspace raíz

*Ejecutar después de que V3 esté completa. Todos los movimientos de archivos usan `_legacy/` como destino.*

---

### C1 — Mover archivos duplicados u obsoletos a `_legacy/`

Los siguientes archivos tuvieron utilidad pero ya están reemplazados o son redundantes.
Se mueven a `_legacy/` en lugar de eliminarse para conservar referencia histórica.

| # | Estado | Archivo | Motivo |
|---|--------|---------|--------|
| C1.1 | ✅ | `bunkerm-source/docker-compose.yml` | Compose upstream original con bind mounts a `./backend/mosquitto/` y `./backend/etc/mosquitto/certs` que ya no existen. No es usado por `deploy.ps1`. Reemplazado por `docker-compose.dev.yml` en raíz. |
| C1.2 | ✅ | `config/nginx/nginx.conf` | Placeholder de nginx standalone con HTML de bienvenida incrustado. No está montado en ningún contenedor. El nginx real usa `bunkerm-source/nginx.conf` y `default-next.conf` copiados en la imagen. |
| C1.3 | ✅ | `deploy.bat` | Wrapper para CMD (Windows legacy). En entorno con PowerShell disponible es redundante. |

**Carpeta destino**: `_legacy/` en la raíz del workspace.

---

### C2 — Eliminar port bindings obsoletos de `docker-compose.dev.yml`

Tras la Fase 3, el backend está unificado en el puerto interno 9001. El servicio `bunkerm` en el compose todavía expone al host los puertos de los antiguos microservicios, que ya no tienen ningún proceso escuchando.

| # | Estado | Acción |
|---|--------|--------|
| C2.1 | ✅ | Eliminar del servicio `bunkerm` los bindings: `1000:1000`, `1001:1001`, `1002:1002`, `1003:1003`, `1004:1004`, `1005:1005`, `8100:8100` |
| C2.2 | ✅ | Actualizar el comentario del bloque de ports para que refleje solo el puerto `2000` como punto de entrada |

---

### C3 — Actualizar `deploy.ps1`

| # | Estado | Acción |
|---|--------|--------|
| C3.1 | ✅ | `Invoke-PatchBackend`: reemplazar los 5 bloques de servicios individuales (dynsec, monitor, clientlogs, config, smart-anomaly con patrones `uvicorn main:app.*1000` etc.) por un patch único: `podman cp bunkerm-source/backend/app/. bunkerm-platform:/app/` + kill/HUP del proceso `uvicorn main:app.*9001` |
| C3.2 | ✅ | `Invoke-StartBunkerM`: eliminar las 3 líneas de output que muestran las URLs de puertos viejos (`Dynsec API: 1000`, `Monitor API: 1001`, `Config API: 1005`). Solo mostrar `http://localhost:2000` |

---

### C4 — Mover los 12 scripts `_*.py` a `scripts/dev-tools/`

Scripts de debug y mantenimiento escritos orgánicamente durante el desarrollo. No pertenecen a la raíz del repositorio. Se mueven y renombran eliminando el prefijo `_`.

| # | Estado | Script original | Nuevo nombre en `scripts/dev-tools/` |
|---|--------|----------------|--------------------------------------|
| C4.1 | ✅ | `_add_nginx_clients.py` | `add_nginx_clients.py` |
| C4.2 | ✅ | `_add_nginx_clients2.py` | `add_nginx_clients_v2.py` |
| C4.3 | ✅ | `_analyze_brokerlogs.py` | `analyze_brokerlogs.py` |
| C4.4 | ✅ | `_analyze_clientlogs.py` | `analyze_clientlogs.py` |
| C4.5 | ✅ | `_analyze_clientlogs2.py` | `analyze_clientlogs_v2.py` |
| C4.6 | ✅ | `_analyze_clientlogs3.py` | `analyze_clientlogs_v3.py` |
| C4.7 | ✅ | `_check_dynsec.py` | `check_dynsec.py` |
| C4.8 | ✅ | `_fix_dynsec_admin_acl.py` | `fix_dynsec_admin_acl.py` |
| C4.9 | ✅ | `_fix_nginx.py` | `fix_nginx.py` |
| C4.10 | ✅ | `_patch_nginx_apikey.py` | `patch_nginx_apikey.py` |
| C4.11 | ✅ | `_test_acl.py` | `test_acl.py` |
| C4.12 | ✅ | `_update_plant_config.py` | `update_plant_config.py` |

---

### C5 — Actualizar `scripts/generate-secrets.py`

El script genera en `.env.dev` variables para puertos de microservicios que ya no existen tras la Fase 3.

| # | Estado | Acción |
|---|--------|--------|
| C5.1 | ✅ | Eliminar del bloque generado: `DYNSEC_PORT`, `MONITOR_PORT`, `CLIENTLOGS_PORT`, `AWS_BRIDGE_PORT`, `AZURE_BRIDGE_PORT`, `CONFIG_PORT`, `SMART_ANOMALY_PORT` |
| C5.2 | ✅ | Eliminar puertos nunca implementados: `DASHBOARD_SERVICE_PORT=1006`, `BACKUP_SERVICE_PORT=1007`, `LOAD_SIMULATOR_PORT=1008` |
| C5.3 | ✅ | Agregar: `BUNKERM_API_PORT=9001` (documentado como el único proceso Python interno) |
| C5.4 | ✅ | Eliminar: `TIER=enterprise` (la variable no existe en `backend/app/core/config.py` Settings) |

---

### C6 — Actualizar `scripts/check-health.sh`

El script verifica puertos individuales 1000–1005 que ya no existen. Actualizar para el endpoint unificado.

| # | Estado | Acción |
|---|--------|--------|
| C6.1 | ✅ | Reemplazar los checks a puertos `1000`–`1005` y `8100` por checks al endpoint unificado: `http://localhost:2000/api/monitor/stats`, `http://localhost:2000/api/dynsec/clients`, `http://localhost:2000/api/ai/health` |
| C6.2 | ✅ | Mantener el check de MQTT en puerto `1900` (sigue siendo correcto) |

---

## Estructura del workspace raíz (objetivo)

```
BunkerMTest/
├── _legacy/                         # NUEVO — archivos con historial pero sin uso activo
│   ├── bunkerm-source_docker-compose.yml
│   ├── config_nginx_nginx.conf
│   └── deploy.bat
├── bunkerm-source/                  # Codigo fuente (Fases 1-4 completas)
├── config/
│   ├── mosquitto/                   # mosquitto.conf + dynamic-security.json (montados en bunkerm-mosquitto)
│   └── postgres/                    # init.sql (perfil --WithTools)
├── data/                            # Runtime, gitignoreado
├── scripts/
│   ├── generate-secrets.py          # Actualizado (C5)
│   ├── check-health.sh              # Actualizado (C6)
│   ├── migrate-to-postgres.py       # Sin cambios
│   └── dev-tools/                   # NUEVO — 12 scripts _*.py renombrados
├── docker-compose.dev.yml           # Actualizado (C2) — sin puertos 1000-1005
├── deploy.ps1                       # Actualizado (C3)
├── Dockerfile.mosquitto             # Sin cambios
├── mosquitto-entrypoint.sh          # Sin cambios
├── requirements.txt                 # Sin cambios (para scripts Python utilitarios)
├── simulator.ps1                    # Fuera de scope
├── WORK_PLAN.md                     # Este archivo
├── QUICKSTART.md
├── README.md
└── ROADMAP.md
```

---

## Notas de referencia

### Podman: comandos equivalentes relevantes

| Propósito | Comando |
|-----------|---------|
| Listar contenedores activos | `podman ps` |
| Ver procesos dentro del contenedor | `podman exec bunkerm-platform ps aux` |
| Copiar archivos al contenedor | `podman cp <src>. bunkerm-platform:<dst>/` |
| Ver logs en tiempo real | `podman logs -f bunkerm-platform` |
| Inspeccionar puertos escuchando | `podman exec bunkerm-platform ss -tlnp` |
| Ejecutar compose | `podman compose --env-file .env.dev -f docker-compose.dev.yml up -d` |

### Obtener el API_KEY para los tests de V3

```powershell
# Leer del archivo .env.dev
(Get-Content .env.dev | Select-String "^API_KEY=") -replace "^API_KEY=", ""

# O leer directamente del volumen persistente del contenedor
podman exec bunkerm-platform cat /nextjs/data/.api_key
```

### Rutas internas clave del contenedor `bunkerm-platform`

| Recurso | Ruta interna |
|---------|-------------|
| Backend Python (app unificada) | `/app/` |
| Smart-anomaly | `/app/smart-anomaly/` |
| Frontend Next.js | `/nextjs/` |
| Logs del broker (leídos por clientlogs) | `/var/log/mosquitto/mosquitto.log` |
| DynSec JSON (volumen compartido con mosquitto) | `/var/lib/mosquitto/dynamic-security.json` |
| Persistencia de datos (Next.js auth, DB SQLite) | `/nextjs/data/` |
| Backups de configuración | `/nextjs/data/backups/` |
| Log de actividad API | `/var/log/api/api_activity.log` |
