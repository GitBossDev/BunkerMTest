# BunkerM — Plan de Reestructuración

> **Scope**: Solo `bunkerm-source/` — backend Python + frontend Next.js.
> No incluye simuladores externos como `greenhouse-simulator/`.
>
> **Orden de prioridad acordado**: Seguridad → Arquitectura/Refactor → Calidad de código
> **Última actualización**: 2026-04-09

---

## Progreso general

| Fase | Estado | Descripción |
|------|--------|-------------|
| **Fase 1** | ✅ Completa | Seguridad crítica |
| **Fase 2** | ✅ Completa | Infraestructura |
| **Fase 3** | ✅ Completa | Consolidación del backend |
| **Fase 4** | ✅ Completa | Calidad del frontend |

---

## FASE 1 — Seguridad crítica

*Sin dependencias previas. Empieza aquí.*

### Pasos

| # | Estado | Archivo(s) | Descripción |
|---|--------|-----------|-------------|
| 1.1 | ✅ | `frontend/lib/users.ts`<br>`frontend/middleware.ts`<br>`frontend/lib/auth.ts`<br>`frontend/app/api/proxy/[...path]/route.ts` | Eliminar credenciales hardcodeadas y fallbacks inseguros. Reemplazar por variables de entorno obligatorias con fallo rápido (fail-fast) si están ausentes. |
| 1.2 | ✅ | `backend/app/clientlogs/main.py`<br>`backend/app/monitor/main.py` | Añadir autenticación `X-API-Key` a todos los endpoints sin proteger, especialmente `POST /enable/{username}` y `POST /disable/{username}`. Eliminar o proteger los endpoints `/test/*` de monitor. |
| 1.3 | ✅ | Todos los `main.py` de servicios backend | Corregir configuración CORS: `allow_origins=["*"]` con `allow_credentials=True` es inválido por spec. Usar `ALLOWED_ORIGINS` del env. Corregir el bug de nested list en `clientlogs`. |
| 1.4 | ✅ | `backend/app/dynsec/main.py` | Corregir `@app.middleware("https")` → `@app.middleware("http")`. Los security headers actualmente nunca se registran. |
| 1.5 | ✅ | `backend/app/config/main.py` | Agregar `import logging.handlers` faltante. El servicio crashea al arrancar. |

### Verificación de Fase 1
- [ ] Todos los endpoints devuelven `401` sin `X-API-Key` válido
- [ ] Arrancar sin `AUTH_SECRET`/`API_KEY` produce error explícito, no silencioso
- [ ] `curl -X POST http://localhost:2000/api/clientlogs/enable/testuser` sin auth → 401
- [ ] No hay strings de contraseñas literales en el código fuente
- [ ] CORS no devuelve `Access-Control-Allow-Origin: *` en requests con credentials

---

## FASE 2 — Infraestructura

*Depende de: Fase 1 completa.*

### Pasos

| # | Estado | Archivo(s) | Descripción |
|---|--------|-----------|-------------|
| 2.1 | ✅ | `docker-compose.yml`<br>`mosquitto-entrypoint.sh`<br>`backend/mosquitto/config/mosquitto.conf` | Separado Mosquitto a su propio servicio Docker (`eclipse-mosquitto:2`). Volúmenes movidos a `mosquitto`. `MQTT_BROKER=mosquitto`. `ALLOWED_ORIGINS` y `ALLOWED_HOSTS` ya no son wildcard. Volumen compartido `mosquitto_data` para DynSec JSON + passwd. |
| 2.2 | ✅ | `_legacy/` | Archivos legacy movidos a `_legacy/`: `Dockerfile.static`, `Dockerfile.fix`, `Dockerfile.multiarch`, `default.conf.static`, `docker-compose.yml.bak`, `frontend-index.html`, `tsconfig.vite-config.json`. |
| 2.3 | ✅ | `default-next.conf` | Agregado `location /api/ai/` que proxea al servicio `smart-anomaly` en `:8100`. |
| 2.4 | ⬜ | `default-next.conf` | *(Opcional)* Habilitar TLS en nginx. Los certificados existen en `/app/certs/` pero nginx escucha solo HTTP plano en `:2000`. |

### Verificación de Fase 2
- [ ] `docker compose up --build` levanta dos servicios: `bunkerm` y `mosquitto`
- [ ] La UI sigue accesible en `:2000`
- [ ] `curl http://localhost:2000/api/ai/health` → 200
- [ ] Los logs de Mosquitto aparecen en el panel
- [ ] No existen archivos legacy duplicados sin propósito

---

## FASE 3 — Consolidación del backend

*Depende de: Fase 2 completa. **Esta es la fase más grande.***

### Nueva estructura de directorios objetivo

```
backend/app/
├── main.py                    ← App FastAPI unificada, lifespan, include_router
├── core/
│   ├── __init__.py
│   ├── auth.py                ← get_api_key() compartido — UN SOLO LUGAR
│   ├── config.py              ← pydantic_settings Settings — UN SOLO LUGAR  
│   ├── database.py            ← SQLite engine async (SQLAlchemy)
│   └── mqtt.py                ← Cliente paho-mqtt compartido (si aplica)
├── models/
│   ├── __init__.py
│   ├── orm.py                 ← Modelos SQLAlchemy (consolida smart-anomaly + nuevos)
│   └── schemas.py             ← Modelos Pydantic (request/response)
├── routers/
│   ├── __init__.py
│   ├── dynsec.py              ← Migrado de dynsec/main.py
│   ├── monitor.py             ← Migrado de monitor/main.py
│   ├── clientlogs.py          ← Migrado de clientlogs/main.py
│   ├── config_mosquitto.py    ← Migrado de config/mosquitto_config.py
│   ├── config_dynsec.py       ← Migrado de config/dynsec_config.py
│   ├── aws_bridge.py          ← Migrado de aws-bridge/main.py
│   ├── azure_bridge.py        ← Migrado de azure-bridge/main.py
│   └── anomaly.py             ← Migrado de smart-anomaly/
└── services/
    ├── __init__.py
    ├── dynsec_service.py      ← Lógica de negocio dynsec (separada de HTTP)
    ├── monitor_service.py     ← MQTTStats, AlertEngine, HistoricalDataStorage
    ├── clientlogs_service.py  ← MQTTMonitor, log parsing
    └── anomaly_service.py     ← Detector, MetricsEngine
```

### Pasos

| # | Estado | Descripción |
|---|--------|-------------|
| 3.1 | ✅ | Crear estructura de directorios `core/`, `routers/`, `services/`, `models/` con archivos `__init__.py` vacíos. Crear `main.py` unificado con lifespan. |
| 3.2 | ✅ | Crear `core/auth.py`: dependencia FastAPI `get_api_key()` única. Eliminar las 6+ copias de `_get_current_api_key()` de cada servicio. |
| 3.3 | ✅ | Crear `core/config.py` con `pydantic_settings`. Consolidar todos los `.env.example` dispersos en uno solo. |
| 3.4 | ✅ | Definir modelos SQLAlchemy en `models/orm.py`: `HistoricalTick`, `AlertConfigEntry`, `BrokerBaseline`. Modelos Pydantic en `models/schemas.py`. |
| 3.5 | ✅ | Crear `services/monitor_service.py` con estado MQTT centralizado (AlertEngine, MQTTStats, TopicStore, NonceManager). |
| 3.6 | ✅ | Migrar cada servicio a su router + service: `routers/dynsec.py`, `routers/monitor.py`, `routers/clientlogs.py`, `routers/config_mosquitto.py`, `routers/config_dynsec.py`, `routers/aws_bridge.py`, `routers/azure_bridge.py`. |
| 3.7 | ✅ | Integrar smart-anomaly: routers montados con prefijo `/api/v1/ai` en `main.py`, URLs actualizadas a puerto 9001. |
| 3.8 | ✅ | Unificar `supervisord-next.conf`: un único programa `bunkerm-api` reemplaza los 7 microservicios anteriores. Puerto único: 9001. |
| 3.9 | ✅ | Actualizar `Dockerfile.next` y `start.sh` para la nueva estructura (verificar paths de COPY e instalación de dependencias). |

### Verificación de Fase 3
- [ ] `uvicorn app.main:app` arranca desde `backend/app/` sin errores
- [ ] Todas las URLs públicas del proxy frontend siguen funcionando (sin cambios de ruta pública)
- [ ] Las estadísticas históricas persisten en SQLite tras restart del servicio
- [ ] `grep -r "_get_current_api_key" .` → 0 resultados (solo existe en `core/auth.py`)
- [ ] Solo un proceso uvicorn en supervisord

---

## FASE 4 — Calidad del frontend

*Depende de: Fase 3 completa (las rutas públicas del proxy no cambian).*

### Pasos

| # | Estado | Archivo(s) | Descripción |
|---|--------|-----------|-------------|
| 4.1 | ✅ | `frontend/src/` | Eliminar directorio completo (app Vue 3 legacy, ~30+ archivos muertos, excluida del tsconfig). |
| 4.2 | ✅ | `frontend/app/layout.tsx` | Eliminar `'BrokerPanel - Para CIC'` hardcodeado. Usar env `APP_TITLE` o simplemente `'BunkerM'`. |
| 4.3 | ✅ | `frontend/lib/api.ts` | Auditar que 0 páginas usen `fetch()` inline. Reemplazar todos los tipos `any` con tipos correctos usando `types/index.ts`. |
| 4.4 | ✅ | `frontend/lib/utils.ts` | `generateNonce()` usa `Math.random()` — renombrar a `generateCacheBuster()` o reemplazar con `crypto.getRandomValues()` real. |
| 4.5 | ✅ | `frontend/lib/api.ts` | `removeRoleACL()`: agregar `encodeURIComponent(aclType)` al construir la URL. |
| 4.6 | ✅ | `frontend/components/` | Crear `ErrorBoundary.tsx` (React class component) y wrappear los layouts `(auth)` y `(dashboard)`. |
| 4.7 | ✅ | `frontend/app/(dashboard)/ai/` | Decidir: completar o eliminar `anomalies/`, `alerts/`, `metrics/` (rutas no enlazadas en el sidebar). |

### Verificación de Fase 4
- [ ] `next build` sin errores TypeScript
- [ ] `frontend/src/` no existe
- [ ] No hay strings de contraseñas en el código
- [ ] `grep -r "Para CIC" .` → 0 resultados
- [ ] `grep -r "Math.random" frontend/lib/` → 0 resultados (o explicado si se mantiene)

---

## Notas y decisiones de diseño

| Tema | Decisión |
|------|----------|
| Arquitectura backend | Consolidar en una sola app FastAPI con routers separados |
| Almacenamiento | Migrar JSON planos a SQLite (mismo motor que smart-anomaly) |
| Vue 3 legacy | Eliminar `frontend/src/` completo |
| Prioridad | Seguridad → Arquitectura → Calidad |
| Mosquitto | Servicio Docker separado |
| smart-anomaly | Se integra al backend unificado, no queda como microservicio |
| NonceManager en monitor | Evaluar si hacerlo opcional via flag de env |
| `_seen_event_ids` set | Con migración a SQLite, reemplazar por consulta `EXISTS` |
| `DYNSEC_BASE_COMMAND` | Evaluar lectura lazy de credenciales al consolidar |

---

## Cómo usar este plan

Para el trabajo en cada iteración, indicar el paso específico:
- `"Implementa el paso 1.1"` — un paso a la vez
- `"Implementa los pasos 1.2 y 1.3"` — pasos independientes dentro de la misma fase se pueden pedir juntos
- **Nunca** pedir pasos de distintas fases antes de verificar la fase anterior

Al completar cada paso, se actualiza la columna Estado (⬜ → ✅) en este archivo y se actualiza `ARCHITECTURE.md`.
