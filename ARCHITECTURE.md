# BHM — Architecture Reference

> **Audience**: Developers contributing to this repository.  
> **Purpose**: Document the port topology, authentication flow, immovable design decisions,
> and shared volume layout that resulted from the Phase 1-4 consolidation. Reading this
> document prevents accidentally reverting those decisions.

> **Naming note**: The active product name is BHM (Broker Health Manager). Runtime names such as `bunkerm-platform`, `bunkerm-mosquitto`, `bunkerm-*` volumes and `bunkerm-source/` remain in place for now as technical identifiers until a dedicated rename phase is executed.

---

## Port Topology

```
External (host machine)
        |
        |  :1900  MQTT (TCP)      — devices, external clients
        |  :2000  HTTP/HTTPS      — Web UI + all API calls via nginx
        |
        v
  +---------------------------------------------------------------------------+
  |  bunkerm-platform  (single container)                                     |
  |                                                                           |
  |  nginx :2000                                                              |
  |    |                                                                      |
  |    +-- /api/v1/*             --> uvicorn :9001  (FastAPI unified backend) |
  |    +-- /api/openapi.json     --> uvicorn :9001                            |
  |    +-- /*  (everything else) --> Next.js :3000  (frontend)                |
  |                                                                           |
  |  uvicorn :9001   (single Python process, single port)                     |
  |    Routers: dynsec | monitor | clientlogs | config | aws-bridge          |
  |             azure-bridge | smart-anomaly (under /api/v1/ai)               |
  |                                                                           |
  +---------------------------------------------------------------------------+
        |
        |  bunkerm-network (internal Docker/Podman bridge)
        |
  +---------------------------------------------------------------------------+
  |  bunkerm-mosquitto  (standalone MQTT broker)                              |
  |                                                                           |
  |  :1900  MQTT (TCP)   — exposed externally; also used by bunkerm-platform  |
  |  :9001  MQTT-WS      — optional WebSocket endpoint (container-internal)   |
  +---------------------------------------------------------------------------+
```

### Legacy ports (MUST NOT be reintroduced)

Before the Phase 1-4 consolidation, the backend ran as 7 independent microservices, each
on its own port inside the container. These ports are permanently retired:

| Port | Former service        |
|------|-----------------------|
| 1000 | dynsec-api            |
| 1001 | monitor-api           |
| 1002 | clientlogs            |
| 1003 | aws-bridge-api        |
| 1004 | azure-bridge-api      |
| 1005 | config-api            |
| 8100 | smart-anomaly         |

The invariant test `tests/test_architecture.py::test_unified_port_in_supervisord`
enforces that none of these ports reappear in `supervisord-next.conf`.

---

## Authentication Flow

```
Browser / curl
    |
    |  HTTP :2000
    v
nginx (inside bunkerm-platform)
    |
    |  Strips X-API-Key / Authorization headers?  NO — passes through to Next.js
    v
Next.js :3000  (app/api/proxy/[...path]/route.ts — transparent byte forwarder)
    |
    |  Forwards request including all headers (X-API-Key, Authorization)
    v
uvicorn :9001  (FastAPI — core/auth.py)
    |
    |  get_api_key dependency checks X-API-Key against settings.api_key
    |  get_current_user  checks Bearer JWT against settings.jwt_secret
    v
Router handler (dynsec, monitor, config, bridges, …)
    |
    |  dynsec/config routers read/write:
    v
mosquitto DynSec JSON  (/var/lib/mosquitto/dynamic-security.json)
mosquitto.conf         (/etc/mosquitto/mosquitto.conf)
    |
    |  (reloaded via mosquitto_ctrl or SIGHUP)
    v
bunkerm-mosquitto container (same named volumes)
```

### Auth rules summary

| Endpoint group           | Required credential          |
|--------------------------|------------------------------|
| `GET /api/v1/monitor/stats/health` | None (public)       |
| `GET /api/v1/monitor/stats`        | `nonce` + `timestamp` query params |
| All other `/api/v1/*`    | `X-API-Key` header matching `API_KEY` env var |
| Next.js auth routes      | JWT issued by NextAuth (stored in `AUTH_SECRET`) |

---

## Immovable Design Decisions

These decisions were deliberately made during Phases 1-4 and must not be reverted
without a corresponding update to this document and the architecture tests.

### 1. Single backend process on port 9001

The backend is **always a single `uvicorn` process** bound to `0.0.0.0:9001`.
There is no service discovery, no inter-process communication between backend services.
All routers run in the same Python process and share the same `Settings` singleton.

**Why**: Eliminates the class of bugs caused by services starting in different orders,
port conflicts, and inconsistent configuration across multiple processes.

**Enforced by**: `tests/test_architecture.py::test_unified_port_in_supervisord`

### 2. Broker is a separate container (bunkerm-mosquitto)

Mosquitto runs in its own container with its own lifecycle. BHM platform connects to
the broker via the internal Docker/Podman network (`MQTT_BROKER=mosquitto`). The platform
container never runs a Mosquitto process internally.

**Why**: Allows the broker to survive platform restarts, and devices can remain connected
while the platform is being updated.

### 3. Shared volumes between containers

The DynSec JSON file and `mosquitto.conf` are mounted in **both** containers at the same
internal paths. Any write by BHM's config API is immediately visible to Mosquitto.

### 4. No direct database access from the frontend

The Next.js frontend never connects to a database directly. All data flows through the
FastAPI backend via the internal proxy at `app/api/proxy/[...path]/route.ts`.

### 5. API_KEY is the primary auth mechanism for backend-to-backend calls

The `X-API-Key` header value must match `settings.api_key` (env: `API_KEY`).
It is generated by `scripts/generate-secrets.py` and injected at build time as
`NEXT_PUBLIC_API_KEY` so Next.js can include it in every proxied request.

---

## Shared Volumes

| Named volume        | Mounted in               | Internal path                     | Contents                                      |
|---------------------|--------------------------|-----------------------------------|-----------------------------------------------|
| `mosquitto-data`    | bunkerm-platform         | `/var/lib/mosquitto`              | `dynamic-security.json`, MQTT persistence     |
| `mosquitto-data`    | bunkerm-mosquitto        | `/var/lib/mosquitto`              | Same volume — read/write by both containers   |
| `mosquitto-conf`    | bunkerm-platform         | `/etc/mosquitto`                  | `mosquitto.conf`, `conf.d/`                   |
| `mosquitto-conf`    | bunkerm-mosquitto        | `/etc/mosquitto`                  | Same volume — read/write by both containers   |
| `mosquitto-log`     | bunkerm-platform         | `/var/log/mosquitto`              | Broker log parsed by clientlogs service       |
| `mosquitto-log`     | bunkerm-mosquitto        | `/var/log/mosquitto`              | Same volume — written by Mosquitto            |
| `bunkerm-nextjs`    | bunkerm-platform only    | `/nextjs/data`                    | SQLite DBs, file uploads, backups             |
| `bunkerm-logs-api`  | bunkerm-platform only    | `/var/log/api`                    | FastAPI activity log                          |
| `bunkerm-logs-nginx`| bunkerm-platform only    | `/var/log/nginx`                  | Nginx access/error logs                       |

---

## Key Files

| File                                      | Role                                                          |
|-------------------------------------------|---------------------------------------------------------------|
| `bunkerm-source/backend/app/main.py`      | FastAPI application; registers all routers                    |
| `bunkerm-source/backend/app/core/config.py` | Pydantic Settings — single source of truth for all env vars |
| `bunkerm-source/supervisord-next.conf`    | Process manager — starts nginx, uvicorn :9001, Next.js :3000  |
| `bunkerm-source/default-next.conf`        | Nginx routing rules (port 2000 -> 9001 + 3000)               |
| `bunkerm-source/frontend/lib/api.ts`      | Typed HTTP client used by all frontend components             |
| `bunkerm-source/frontend/types/api.generated.ts` | TypeScript types generated from OpenAPI schema         |
| `docker-compose.dev.yml`                  | Container topology for development                            |
| `deploy.ps1`                              | One-stop deploy script (setup/build/start/patch/test/smoke)   |
| `scripts/validate-env.py`                 | Pre-flight check: all required env vars present in .env.dev   |

---

## Development Workflow

```
1. Edit source in bunkerm-source/
2. .\deploy.ps1 -Action patch-backend     (or patch-frontend)
3. .\deploy.ps1 -Action test              (backend unit tests — must stay green)
4. .\deploy.ps1 -Action smoke             (5 endpoint checks — must all pass)
5. Commit
```

### After any backend schema change

```powershell
# Regenerate TypeScript types from live OpenAPI schema (stack must be running)
cd bunkerm-source\frontend
npm run gen-types
```

---

## Last Updated

April 10, 2026 — after completing Quality Plan Phases T, A, C, E, D.
