# BHM — Architecture Reference

> **Audience**: Developers contributing to this repository.
> **Last updated**: 2026-04-22 (Phase 5 completa — microservicios Compose + K8s)
> **Conventions**: code and file content in English, comments and documentation in Spanish, no emojis

---

## Topología de servicios (estado actual)

### Compose (entorno de desarrollo)

```
Host (localhost)
        |
        |  :2000  HTTP — Web UI (bhm-frontend: nginx + Next.js standalone)
        |  :1900  MQTT TCP — dispositivos / clientes externos
        |  :5432  PostgreSQL (expuesto para acceso dev)
        |
        v
  bunkerm-network (Docker/Podman bridge)
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │                                                                              │
  │  bhm-frontend  [bhm-frontend:latest]  port 2000                             │
  │    nginx :2000 → /api/v1/* → bhm-api:9001 (HTTP interno)                   │
  │               → /*         → Next.js :3000 (proceso interno)                │
  │                                                                              │
  │  bhm-api  [bhm-api:latest]  port 9001 (interno, accesible via nginx)        │
  │    FastAPI + uvicorn — todos los routers excepto identity                   │
  │                                                                              │
  │  bhm-identity  [bhm-identity:latest]  port 8080                             │
  │    FastAPI — solo router de identidad (/api/v1/identity/*)                  │
  │    DB: identity.bhm_users (PostgreSQL schema identity)                      │
  │                                                                              │
  │  bunkerm-mosquitto  [bhm-mosquitto:latest]  ports 1900, 9001                │
  │    Mosquitto 2 con DynSec; ciclo de vida independiente                      │
  │                                                                              │
  │  bhm-reconciler  [bhm-api:latest]                                           │
  │    Daemon: services.broker_reconcile_daemon --interval 5                    │
  │                                                                              │
  │  bhm-broker-observability  [bhm-api:latest]  port 9102 (interno)           │
  │    uvicorn services.broker_observability_api                                │
  │                                                                              │
  │  bhm-alert-delivery  [bhm-api:latest]                                       │
  │    Daemon: services.alert_delivery_daemon --interval 5                      │
  │                                                                              │
  │  postgres  [postgres:16-alpine]  port 5432                                  │
  │    DB: bhm_db — schemas: control_plane, history, reporting, identity        │
  └──────────────────────────────────────────────────────────────────────────────┘
```

### Kubernetes (laboratorio kind — runtime bhm-lab)

```
Host (localhost)
        |
        |  :22000  NodePort → bhm-frontend (Next.js + nginx)
        |  :21900  NodePort → mosquitto     (MQTT TCP)
        |  :80/:443  Ingress nginx (requiere -InstallIngress en bootstrap)
        |
        v
  namespace: bhm-lab
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  bhm-frontend  Deployment  [localhost/bhm-frontend:dev]  port 2000          │
  │  bhm-api       Deployment  [localhost/bhm-api:dev]       port 9001          │
  │  bhm-identity  Deployment  [localhost/bhm-identity:dev]  port 8080          │
  │  postgres      StatefulSet [postgres:16-alpine]          port 5432          │
  │  mosquitto     StatefulSet [localhost/bhm-mosquitto:dev] port 1900          │
  │    sidecars: reconciler (bhm-api), observability (bhm-api)                 │
  │  bhm-alert-delivery  Deployment  [localhost/bhm-api:dev]                   │
  │  bhm-ingress   Ingress nginx — /api/ → bhm-api, / → bhm-frontend           │
  └──────────────────────────────────────────────────────────────────────────────┘
```

---

## Imágenes Docker

| Imagen | Dockerfile | Contenido | Puerto |
|--------|-----------|-----------|--------|
| `bhm-frontend` | `bunkerm-source/Dockerfile.frontend` | Next.js standalone + nginx | 2000 |
| `bhm-api` | `bunkerm-source/Dockerfile.api` | FastAPI + uvicorn, todos los routers excepto identity | 9001 |
| `bhm-identity` | `bunkerm-source/Dockerfile.identity` | FastAPI + uvicorn, solo router identity | 8080 |
| `bhm-mosquitto` | `Dockerfile.mosquitto` | Mosquitto 2 + DynSec + entrypoint custom | 1900 |

---

## Base de datos PostgreSQL

| Schema | Dueño lógico | Tablas clave | URL (search_path) |
|--------|-------------|-------------|-------------------|
| `control_plane` | bhm-api | `brokers`, `reconcile_state`, `alert_rules`, … | `?options=-csearch_path%3Dcontrol_plane` |
| `history` | bhm-api | `client_events`, `broker_stats` | `?options=-csearch_path%3Dhistory` |
| `reporting` | bhm-api | `daily_broker_reports` | `?options=-csearch_path%3Dreporting` |
| `identity` | bhm-identity | `bhm_users` | `?options=-csearch_path%3Didentity` |

**Alembic**: cadena de 6 migraciones en `bunkerm-source/backend/app/alembic/versions/` (001–006).
La migración 006 crea `identity.bhm_users`. Correr: `alembic upgrade head` desde `/app` en el contenedor bhm-api.

---

## Flujo de autenticación (post fase 5B)

```
Browser
    │  cookie bunkerm_token (JWT firmado con AUTH_SECRET)
    ▼
Next.js (app/api/auth/*)            ← servidor Next.js valida cookie
    │  POST /api/v1/identity/verify (X-API-Key, JSON {email, password})
    ▼
bhm-identity :8080                  ← verifica bcrypt, devuelve UserOut o 401
    │  SELECT FROM identity.bhm_users
    ▼
PostgreSQL :5432 (schema identity)
```

| Ruta | Credencial requerida |
|------|--------------------|
| `GET /health` (bhm-identity, bhm-api) | ninguna |
| `POST /api/v1/identity/verify` | X-API-Key |
| `GET/POST /api/v1/identity/users` | X-API-Key |
| `GET /api/v1/monitor/stats/health` | ninguna |
| Resto de `/api/v1/*` | X-API-Key o Bearer JWT |
| Next.js auth routes | cookie JWT (`bunkerm_token`) |

---

## Variables de entorno críticas

| Variable | Servicio | Descripción |
|----------|---------|-------------|
| `DATABASE_URL` | bhm-api, workers | PostgreSQL default (search_path=control_plane) |
| `CONTROL_PLANE_DATABASE_URL` | bhm-api | Esquema control_plane explícito |
| `HISTORY_DATABASE_URL` | bhm-api | Esquema history |
| `REPORTING_DATABASE_URL` | bhm-api | Esquema reporting |
| `IDENTITY_DATABASE_URL` | bhm-identity | Esquema identity |
| `IDENTITY_API_URL` | bhm-frontend (Next.js server) | URL de bhm-identity (`http://bhm-identity:8080`) |
| `IDENTITY_API_KEY` | bhm-frontend | Alias de `API_KEY` — para llamadas a bhm-identity |
| `API_KEY` | todos | Clave compartida para X-API-Key |
| `JWT_SECRET` | bhm-api | Firma de tokens JWT de API |
| `AUTH_SECRET` | bhm-frontend | Firma de cookies de sesión Next.js |
| `ADMIN_INITIAL_EMAIL` | bhm-identity | Email del primer admin (seed en DB vacía) |
| `ADMIN_INITIAL_PASSWORD` | bhm-identity | Contraseña del primer admin |

---

## Volúmenes compartidos (Compose)

| Volumen | Montado en | Path interno | Contenido |
|---------|-----------|-------------|-----------|
| `mosquitto-data` | mosquitto, reconciler | `/var/lib/mosquitto` | DynSec JSON, persistencia MQTT |
| `mosquitto-conf` | mosquitto, reconciler | `/etc/mosquitto` | `mosquitto.conf`, `conf.d/` |
| `mosquitto-log` | mosquitto, observability | `/var/log/mosquitto` | Logs del broker |
| `postgres-data` | postgres | `/var/lib/postgresql/data` | Datos PostgreSQL |
| `bunkerm-nextjs` | bunkerm-platform | `/nextjs/data` | Datos Next.js (uploads, backups) |
| `bunkerm-logs-api` | bunkerm-platform, workers | `/var/log/api` | Logs FastAPI |

---

## Ficheros clave del código fuente

| Fichero | Rol |
|---------|-----|
| `bunkerm-source/backend/app/main.py` | Entry point bhm-api — registra todos los routers excepto identity |
| `bunkerm-source/backend/identity_main.py` | Entry point bhm-identity — solo router identity, port 8080 |
| `bunkerm-source/docker/entrypoint-frontend.sh` | Entrypoint bhm-frontend — envsubst BACKEND_URL en nginx, arranca nginx + Next.js |
| `bunkerm-source/backend/app/core/config.py` | Settings pydantic-settings — fuente única de configuración |
| `bunkerm-source/backend/app/core/database.py` | Sesión async SQLAlchemy para control_plane |
| `bunkerm-source/backend/app/core/identity_database.py` | Sesión async SQLAlchemy para identity |
| `bunkerm-source/backend/app/routers/identity.py` | Router FastAPI — CRUD usuarios + endpoint verify |
| `bunkerm-source/backend/app/models/orm.py` | Todos los modelos ORM (incl. `BhmUser`) |
| `bunkerm-source/backend/app/alembic/` | Migraciones Alembic 001–006 |
| `bunkerm-source/frontend/lib/users-api.ts` | Cliente HTTP Next.js (server-side) → bhm-identity |
| `bunkerm-source/frontend/app/api/auth/` | Rutas NextAuth: login, users, change-password, me |
| `k8s/base/` | Manifiestos Kustomize base (namespace, postgres, frontend, api, identity, mosquitto, ingress) |
| `k8s/kind/` | Overlay kind (NodePorts, ALLOWED_HOSTS=*, cluster.yaml con extraPortMappings) |
| `k8s/scripts/bootstrap-kind.ps1` | Bootstrap del laboratorio kind (cluster + secretos + kustomize apply) |
| `deploy.ps1` | Script único de ciclo de vida: setup/build/start/patch/test/smoke |
| `scripts/validate-env.py` | Pre-flight: verifica que todas las variables requeridas estén en .env.dev |
| `scripts/migrate-users-json-to-postgres.py` | Migración one-time: users.json → identity.bhm_users |

---

## Decisiones de diseño inmutables

### 1. Separación frontend / API / identity en K8s

En Kubernetes, `bhm-frontend`, `bhm-api` y `bhm-identity` son Deployments independientes.
El frontend nunca accede directamente a PostgreSQL — todas las operaciones de usuario pasan
por `bhm-identity` vía HTTP con `X-API-Key`.

### 2. El broker es un contenedor (StatefulSet) independiente

Mosquitto corre en su propio pod/contenedor. BHM se conecta al broker vía red interna
(`MQTT_BROKER=mosquitto`). Nunca hay un proceso Mosquitto dentro del contenedor/pod de la API.

### 3. Un solo proceso uvicorn por imagen de API

`bhm-api` arranca un único proceso `uvicorn main:app --port 9001`.
`bhm-identity` arranca un único proceso `uvicorn identity_main:app --port 8080`.
No hay service discovery ni IPC entre routers.

### 4. Schemas PostgreSQL aislados por servicio

Cada servicio tiene su propio `search_path` en la URL de conexión. Los modelos ORM usan
`schema=` explícito. Las migraciones Alembic (001–006) crean los schemas con `IF NOT EXISTS`.

### 5. La API key es el mecanismo primario de autenticación inter-servicio

Todas las llamadas de Next.js → bhm-identity usan `X-API-Key`. No hay tokens OAuth2
internos. El valor se genera con `scripts/generate-secrets.py` e inyecta via Secret en K8s
o via `.env.dev` en Compose.

---

## Workflow de desarrollo

```powershell
# Compose (modo habitual)
.\deploy.ps1 -Action build          # Construye bhm-frontend, bhm-api, bhm-identity
.\deploy.ps1 -Action start          # Levanta todos los servicios
.\deploy.ps1 -Action patch-backend  # Hot-patch Python sin rebuild (bhm-api)
.\deploy.ps1 -Action test           # Tests unitarios backend
.\deploy.ps1 -Action smoke          # 5 checks de endpoints

# Kubernetes (laboratorio kind)
.\k8s\scripts\bootstrap-kind.ps1              # Primera vez: crea cluster + aplica manifiestos
.\deploy.ps1 -Action start -Runtime kind      # Rebuild + kind load + rollout restart
.\deploy.ps1 -Action smoke -Runtime kind      # Smoke test contra NodePort :22000
```

### Tras cualquier cambio de schema en el backend

```powershell
# Regenerar tipos TypeScript desde el OpenAPI live (stack corriendo)
cd bunkerm-source\frontend
npm run gen-types
```

