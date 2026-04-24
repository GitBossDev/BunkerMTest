# BHM Phase 5 — Monolith Restructure Plan

> Fecha: 2026-04-21
> Autor: GitHub Copilot (sesion de revision arquitectural)
> Prerequisito: Fases 1-4 del BHM_ARCH_REVIEW_PLAN completadas
> Conventions: code and file content in English, comments and documentation in Spanish, no emojis

---

## Contexto y objetivo

`bunkerm-platform` es actualmente un monolito supervisor: un solo contenedor ejecuta nginx,
Next.js (standalone) y uvicorn (FastAPI) coordinados por supervisord. Esto simplifica el
despliegue inicial pero introduce acoplamientos que bloquean la evolucion hacia un ecosistema
de microservicios compartidos.

Este plan cubre cuatro frentes de reestructuracion independientes pero relacionados:

| # | Frente | Impacto | Riesgo |
|---|--------|---------|--------|
| 5A | Split imagen: bunkerm-frontend / bunkerm-api | Alto | Medio |
| 5B | Extraccion del servicio de identidad (bhm-identity) | Alto | Alto |
| 5C | Aislamiento de esquemas PostgreSQL | Medio | Medio |
| 5D | Migracion nginx in-pod a K8s Ingress | Medio | Bajo |

Cada frente puede ejecutarse de forma incremental e independiente. La secuencia recomendada
es 5C -> 5A -> 5B -> 5D.

---

## Estado de cada frente

| Frente | Estado | Iniciado |
|--------|--------|----------|
| 5A — Image split | done | 2026-04-21 |
| 5B-1 — User store a PostgreSQL | done | 2026-04-21 |
| 5B-2 — bhm-identity service | done | 2026-04-30 |
| 5C — Schema isolation | done | 2026-04-21 |
| 5D — K8s Ingress | done | 2026-04-30 |

---

## Analisis del estado actual

### 1. El monolito supervisord

```
Dockerfile.next (imagen unica: localhost/bunkermtest-bunkerm)
  └── supervisord-next.conf
        ├── [program:nginx]        nginx -g 'daemon off;'      :2000 (externo)
        ├── [program:nextjs-frontend] node /nextjs/server.js   :3000 (interno)
        └── [program:bunkerm-api]  uvicorn main:app            :9001 (interno)
```

- nginx actua de reverse proxy: `/api/*` -> `127.0.0.1:9001`, `/*` -> `127.0.0.1:3000`
- La configuracion nginx (`default-next.conf`) tiene `proxy_pass` hardcodeado a `127.0.0.1:9001`
- En K8s esto es un contenedor unico en un solo pod (`control-plane.yaml`)

### 2. Autenticacion actual

- El login lo manejan rutas API de Next.js: `frontend/app/api/auth/login/route.ts`
- Los usuarios se persisten en `data/users.json` dentro del contenedor (en el volumen nextjs-data PVC)
- La sesion es un JWT firmado con `AUTH_SECRET` y almacenado en cookie `bunkerm_token`
- El backend FastAPI usa un mecanismo separado: header `X-API-Key` (no JWT)
- No hay relacion entre las sesiones de usuario del frontend y la autenticacion del backend

### 3. Servicio de alertas

- `bhm-alert-delivery` ya es un Deployment K8s separado (daemon outbox consumer) — correcto
- `notifications.py` router (CRUD de canales y consulta de eventos) esta dentro del backend FastAPI
- Esta division es la correcta: HTTP API en bunkerm-api, procesamiento en daemon separado
- **Decision: no se mueve notifications.py del backend**

### 4. nginx en Kubernetes

- Actualmente nginx corre en-pod (supervisord), no como K8s Ingress
- `default-next.conf` hace proxy a `127.0.0.1:9001` (loopback del mismo pod)
- En K8s con pods separados esto debe cambiar a un Service DNS name: `bunkerm-api:9001`
- K8s Ingress (nginx-ingress-controller) puede reemplazar el nginx in-pod para el edge,
  pero requiere instalar el controller en el cluster (el kind lab no lo tiene por defecto)
- La ruta de menor riesgo: actualizar primero el proxy_pass dentro del pod frontend,
  luego migrar a Ingress en una iteracion separada

---

## Frente 5C — Aislamiento de esquemas PostgreSQL

> Ejecutar primero porque 5B depende de ello y 5A no lo requiere pero se beneficia.

### Motivacion

Actualmente todo esta en la base de datos `bunkerm_db` sin separacion de esquemas.
Para compartir la instancia PostgreSQL con otros microservicios del ecosistema (incluido
el futuro servicio de datos de topics) cada dominio debe ocupar su propio schema,
permitiendo permisos independientes y migraciones aisladas.

### Decision: schemas PostgreSQL por dominio

```
bunkerm_db
  ├── schema: control_plane  -- tablas ORM actuales del backend unificado
  ├── schema: history         -- historical_ticks, reporting aggregates
  ├── schema: reporting       -- reporting tables
  └── schema: identity        -- users, sessions (futuro bhm-identity)
```

### Impacto en DATABASE_URL

Cada servicio recibe una URL apuntando a su schema via `search_path`:

```
postgresql://bunkerm_cp:pass@postgres:5432/bunkerm_db?options=-csearch_path%3Dcontrol_plane
postgresql://bunkerm_hist:pass@postgres:5432/bunkerm_db?options=-csearch_path%3Dhistory
postgresql://bunkerm_id:pass@postgres:5432/bunkerm_db?options=-csearch_path%3Didentity
```

Alternativa mas simple (y la recomendada para la iteracion inicial): mantener una sola
base de datos con un usuario por servicio, y usar el `search_path` solo como convencion.
La migracion de tablas entre schemas se hace con Alembic.

### Checklist 5C

#### Preparacion de schemas

- [ ] Crear script SQL `k8s/base/postgres-schemas.sql` que crea los schemas y usuarios:
  ```sql
  CREATE SCHEMA IF NOT EXISTS control_plane;
  CREATE SCHEMA IF NOT EXISTS history;
  CREATE SCHEMA IF NOT EXISTS reporting;
  CREATE SCHEMA IF NOT EXISTS identity;
  -- Usuario de solo lectura para observabilidad futura
  -- Permisos minimos por usuario de servicio
  ```
- [ ] Agregar el script como ConfigMap en `k8s/base/kustomization.yaml` (junto al init.sql existente)
  o incorporarlo al `postgres-init.sql` existente
- [ ] Actualizar `postgres-init.sql` existente para ejecutar la creacion de schemas al init

#### Migraciones Alembic

- [ ] Crear revision Alembic en `bunkerm-source/backend/app/alembic/` que mueve las tablas ORM
  actuales al schema `control_plane` (SET search_path en el script de migracion)
- [ ] Asegurar que `env.py` de Alembic incluye `include_schemas=True` y usa `version_table_schema`
- [ ] Crear revision separada en `history_reporting_alembic/` para mover historical/reporting tables
  al schema `history` / `reporting` respectivamente

#### Variables de entorno

- [ ] En `k8s/base/kustomization.yaml`, actualizar `DATABASE_URL` con `search_path=control_plane`
- [ ] Actualizar `HISTORY_DATABASE_URL` con `search_path=history`
- [ ] Actualizar `REPORTING_DATABASE_URL` con `search_path=reporting`
- [ ] En `docker-compose.dev.yml`, actualizar los mismos valores para el runtime Compose

#### Validacion 5C

- [ ] `psql bunkerm_db -c '\dn'` lista schemas: `control_plane`, `history`, `reporting`, `identity`
- [ ] `psql bunkerm_db -c '\dt control_plane.*'` lista las tablas ORM del backend
- [ ] Backend arranca sin errores de migracion: `docker compose up bunkerm --no-deps`
- [ ] `alembic current` muestra HEAD sin divergencias

---

## Frente 5A — Split imagen: bunkerm-frontend / bunkerm-api

> Pre-condicion: ninguna. Puede ejecutarse antes o despues de 5C.
> Post-condicion de 5A: la configuracion nginx pasa a usar variable de entorno para el backend URL.

### Motivacion

- Ciclos de build independientes: cambio de frontend no fuerza rebuild del backend Python y viceversa
- Resource requests independientes en K8s: la API puede escalar sin escalar nginx+Next.js
- Principio de responsabilidad unica por imagen
- Habilita 5B: el bhm-identity service necesita un backend separado para integrarse

### Arquitectura objetivo (Compose + K8s)

```
                                  :2000 (NodePort 32000 en K8s)
                                       |
  +------------------------------------+
  |  bunkerm-frontend                  |
  |  nginx :2000                       |
  |    /api/* -> $BACKEND_URL:9001     |
  |    /*     -> Next.js :3000         |
  +------------------------------------+
                   |
                   | K8s Service: bunkerm-api:9001
                   |
  +------------------------------------+
  |  bunkerm-api                       |
  |  uvicorn :9001                     |
  |    todos los routers actuales      |
  +------------------------------------+
```

### Sub-tarea 5A-1: Dockerfile.frontend

Nuevo archivo `bunkerm-source/Dockerfile.frontend`:
- Stage 1: build Next.js standalone (igual que en Dockerfile.next)
- Stage 2: imagen final con Node.js + nginx solamente (sin Python, sin supervisor para la API)
- supervisord solo gestiona nginx y nextjs-frontend
- Variable de entorno nueva: `BACKEND_URL` (default `http://bunkerm-api:9001` en K8s,
  `http://bunkerm:9001` en Compose, `http://127.0.0.1:9001` en desarrollo local)
- `default-next.conf` debe usar `$BACKEND_URL` o un archivo de configuracion de nginx
  con la directiva `resolver` para DNS dinamico en K8s

#### Checklist 5A-1

- [ ] Crear `bunkerm-source/Dockerfile.frontend`:
  - Stage 1: `node:20-alpine` — build Next.js (igual al stage 1 actual de Dockerfile.next)
  - Stage 2: `node:20-alpine` + nginx, sin Python
  - supervisord minimo: solo `nginx` y `nextjs-frontend`
- [ ] Modificar `bunkerm-source/default-next.conf` para hacer el `proxy_pass` configurable:
  ```nginx
  # Resolucion DNS dinamica en Kubernetes (necesario para upstream variables)
  resolver kube-dns.kube-system.svc.cluster.local valid=30s;
  set $backend_url http://bunkerm-api:9001;
  location /api/ {
      proxy_pass $backend_url/api/v1/;
      ...
  }
  ```
  - Alternativa mas simple: usar `envsubst` en el entrypoint para reemplazar
    `${BACKEND_URL}` en el template de nginx antes de arrancar
- [ ] Crear `bunkerm-source/supervisord-frontend.conf` (solo nginx + nextjs, sin uvicorn)
- [ ] Agregar nuevo servicio `bunkerm-frontend` en `docker-compose.dev.yml`
- [ ] En Compose, `BACKEND_URL=http://bunkerm-api:9001` (o el nombre de servicio de la API)

### Sub-tarea 5A-2: Dockerfile.api

Nuevo archivo `bunkerm-source/Dockerfile.api`:
- Imagen basada en Python 3.12-slim o Alpine con Python
- Sin Node.js, sin nginx, sin supervisord (uvicorn se inicia directamente)
- ENTRYPOINT: `uvicorn main:app --host 0.0.0.0 --port 9001`
- Copia solo `backend/app/`

#### Checklist 5A-2

- [ ] Crear `bunkerm-source/Dockerfile.api`:
  - Base: `python:3.12-slim` o Alpine equivalente
  - Instalar dependencias Python (igual que el stage base de Dockerfile.next)
  - `WORKDIR /app`, `COPY backend/app /app`
  - `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9001"]`
- [ ] Crear servicio `bunkerm-api` en `docker-compose.dev.yml`:
  - Mismas variables de entorno que el bloque `bunkerm` actual (sin `AUTH_SECRET`, `FRONTEND_URL`)
  - Puerto `9001` expuesto solo internamente (no mapeado al host)
- [ ] Verificar que los volumenes de logs (`/var/log/api`) siguen siendo accesibles para bunkerm-api

### Sub-tarea 5A-3: Manifiestos K8s

#### Checklist 5A-3

- [ ] Renombrar `k8s/base/control-plane.yaml` -> `k8s/base/bunkerm-frontend.yaml`
  - Deployment `bunkerm-frontend`, imagen `localhost/bunkermtest-bunkerm-frontend`
  - Agregar env `BACKEND_URL=http://bunkerm-api:9001`
  - Service `bunkerm-frontend`, NodePort 32000
- [ ] Crear `k8s/base/bunkerm-api.yaml`:
  - Deployment `bunkerm-api`, imagen `localhost/bunkermtest-bunkerm-api`
  - Service `bunkerm-api` ClusterIP, port 9001
  - Mismos envFrom (bhm-env Secret + bhm-k8s-config ConfigMap)
  - Health probes: `GET /api/v1/monitor/health` en puerto 9001
  - Resources: requests 200m/256Mi, limits 800m/512Mi
- [ ] Actualizar `k8s/base/kustomization.yaml`:
  - Reemplazar `control-plane.yaml` con `bunkerm-frontend.yaml` y `bunkerm-api.yaml`
  - Agregar imagen `localhost/bunkermtest-bunkerm-api` al bloque `images`
  - Actualizar nombre de imagen frontend de `bunkermtest-bunkerm` a `bunkermtest-bunkerm-frontend`
- [ ] Actualizar `k8s/scripts/bootstrap-kind.ps1`:
  - Build de dos imagenes en lugar de una
  - `kind load docker-image` para ambas

### Sub-tarea 5A-4: Actualizar deploy.ps1

#### Checklist 5A-4

- [ ] Identificar las secciones `build` y `push` en `deploy.ps1`
- [ ] Agregar build de `Dockerfile.frontend` -> `bunkermtest-bunkerm-frontend`
- [ ] Agregar build de `Dockerfile.api` -> `bunkermtest-bunkerm-api`
- [ ] Mantener compatibilidad: si `-Runtime compose`, construir ambas
- [ ] Actualizar el smoke test para verificar tanto el frontend (:2000) como la API (:9001)

#### Validacion 5A

- [ ] `docker compose -f docker-compose.dev.yml up bunkerm-frontend bunkerm-api` arrancan sin errores
- [ ] `curl http://localhost:2000/` devuelve el frontend Next.js
- [ ] `curl http://localhost:2000/api/monitor/health` devuelve 200 (pasando por nginx -> bunkerm-api)
- [ ] `curl http://localhost:9001/api/v1/monitor/health` devuelve 200 directamente desde la API
- [ ] `docker images | grep bunkermtest` muestra dos imagenes separadas
- [ ] En kind: `kubectl get pods -n bhm-lab` muestra `bunkerm-frontend-*` y `bunkerm-api-*`
- [ ] `.\deploy.ps1 -Action smoke` pasa

---

## Frente 5B — Extraccion del servicio de identidad (bhm-identity)

> Pre-condicion: 5C completado (el schema `identity` debe existir en PostgreSQL).
> 5A es recomendable pero no estrictamente necesario para 5B-1.

### Motivacion

Actualmente el login esta implementado como rutas API de Next.js que leen/escriben
`data/users.json` dentro del contenedor frontend. Esto impide:
1. Compartir la gestion de usuarios con otras apps del ecosistema
2. Escalar el frontend horizontalmente (cada replica tiene su propio users.json)
3. Integrar Keycloak como proveedor de identidad cuando sea necesario

### Estrategia incremental

```
Iteracion 5B-1 (inmediata): migrar user store de JSON a PostgreSQL (schema identity)
  -- Las rutas API de Next.js siguen siendo el punto de entrada del login
  -- Elimina el users.json del volumen nextjs-data
  -- Habilita multiples replicas del frontend sin estado local

Iteracion 5B-2 (near-term): crear bhm-identity service (FastAPI)
  -- Expone los mismos endpoints que las rutas API de Next.js actualmente sirven
  -- Next.js lo llama via HTTP en lugar de usar funciones locales
  -- Permite compartir la identidad con otras apps del ecosistema

Iteracion 5B-3 (futuro): integracion Keycloak
  -- bhm-identity se retira o se convierte en proxy/adapter
  -- Next.js usa next-auth con provider OIDC apuntando a Keycloak
  -- La cookie JWT pasa a ser el token Keycloak (mismo secreto, diferente emisor)
```

### Analisis de la autenticacion actual

```
Next.js API route: /api/auth/login (POST)
  -> lib/users.ts: findUserByEmail() -- lee data/users.json del disco
  -> lib/users.ts: verifyPassword()  -- bcrypt compare
  -> lib/auth.ts: signToken()        -- genera JWT con AUTH_SECRET
  -> response.cookies.set(COOKIE_NAME, token)

Next.js middleware.ts:
  -> jwtVerify(token, AUTH_SECRET)   -- valida en cada request
  -> payload.role -> control de acceso (admin / user)
```

El backend FastAPI NO participa en el flujo de autenticacion de usuarios. Solo valida
`X-API-Key` para sus propias rutas. Esta separacion se mantiene en 5B.

### Sub-tarea 5B-1: User store a PostgreSQL

#### Checklist 5B-1

**ORM en backend FastAPI (schema identity)**

- [ ] Crear modelo ORM `BhmUser` en `bunkerm-source/backend/app/models/orm.py`:
  ```python
  class BhmUser(Base):
      __tablename__ = "bhm_users"
      __table_args__ = {"schema": "identity"}
      id: Mapped[str]        # UUID
      email: Mapped[str]     # unique, indexed
      password_hash: Mapped[str]
      first_name: Mapped[str]
      last_name: Mapped[str]
      role: Mapped[str]      # 'admin' | 'user'
      created_at: Mapped[datetime]
  ```
- [ ] Crear revision Alembic que crea la tabla `identity.bhm_users`
- [ ] Crear endpoint FastAPI en nuevo router `routers/identity.py`:
  - `POST /api/v1/identity/verify` — recibe `{email, password}`, devuelve `{id, email, role, ...}` o 401
  - `GET  /api/v1/identity/users` — lista usuarios (requiere X-API-Key)
  - `POST /api/v1/identity/users` — crear usuario (requiere X-API-Key)
  - `PUT  /api/v1/identity/users/{id}` — actualizar (requiere X-API-Key)
  - `DELETE /api/v1/identity/users/{id}` — eliminar (requiere X-API-Key)
  - `POST /api/v1/identity/users/{id}/change-password` — cambio de password (requiere X-API-Key)
- [ ] Incluir `identity_router` en `main.py`
- [ ] Script de migracion de datos: `scripts/migrate-users-json-to-postgres.py`
  - Lee `data/users.json` del volumen nextjs-data (o de un path pasado como argumento)
  - Inserta los usuarios en `identity.bhm_users`
  - No elimina el JSON automaticamente — dejar como backup hasta validacion

**Next.js: actualizar lib/users.ts**

- [ ] Crear `frontend/lib/users-api.ts` que llama a la API FastAPI:
  ```typescript
  // Reemplaza las funciones sync de users.ts con llamadas HTTP al backend
  export async function findUserByEmail(email: string): Promise<UserWithHash | null>
  export async function verifyUserPassword(email: string, password: string): Promise<User | null>
  ```
  - La URL del backend viene de `IDENTITY_API_URL` (env var del contenedor frontend)
  - En Compose: `http://bunkerm-api:9001`; en K8s: `http://bunkerm-api:9001`
- [ ] Actualizar `frontend/app/api/auth/login/route.ts` para usar `users-api.ts`
- [ ] Actualizar `frontend/app/api/auth/me/route.ts` — solo verifica JWT, no cambia
- [ ] Actualizar `frontend/app/api/auth/users/route.ts` para llamar a la API del backend
- [ ] Actualizar `frontend/app/api/auth/change-password/route.ts`
- [ ] Mantener `AUTH_SECRET` en Next.js: sigue siendo el secreto para firmar la cookie JWT

**Variables de entorno nuevas**

- [ ] Agregar `IDENTITY_API_URL` a `docker-compose.dev.yml` para el servicio frontend:
  - `IDENTITY_API_URL=http://bunkerm-api:9001` (en Compose)
- [ ] Agregar `IDENTITY_API_URL` al ConfigMap `bhm-k8s-config` con valor `http://bunkerm-api:9001`
- [ ] Agregar `IDENTITY_API_KEY` (mismo valor que `API_KEY`) para que Next.js autentique
  sus llamadas al endpoint `/api/v1/identity/verify`

#### Validacion 5B-1

- [ ] `psql bunkerm_db -c 'SELECT email, role FROM identity.bhm_users'` lista los usuarios migrados
- [ ] Login en la UI funciona con las credenciales migradas
- [ ] `POST /api/v1/identity/verify` con credenciales incorrectas devuelve 401
- [ ] `data/users.json` puede eliminarse del volumen sin afectar el login
- [ ] Multiples replicas del frontend (scale=2 en Compose) comparten el mismo estado de usuarios

### Sub-tarea 5B-2: bhm-identity service (standalone)

> Esta iteracion convierte el router `identity.py` en un microservicio independiente.
> Pre-condicion: 5B-1 completado y estable.

#### Decision de diseno: interfaz compatible con OIDC basico

El servicio expone endpoints que pueden ser reemplazados por Keycloak en el futuro:

```
POST /protocol/openid-connect/token        -- login (grant_type=password)
GET  /.well-known/openid-configuration     -- discovery document (stub)
GET  /userinfo                             -- perfil del usuario autenticado
POST /api/v1/identity/users                -- admin CRUD
```

Nota: NO se implementa un OIDC completo. Solo se expone la interfaz de forma que el
cliente (Next.js) pueda hacer el swap por Keycloak sin cambiar su codigo de llamada.

#### Checklist 5B-2

- [ ] Crear `bunkerm-source/Dockerfile.identity`:
  - Base Python 3.12-slim
  - Copia solo los modulos necesarios: `models/`, `core/database.py`, `core/config.py`,
    nuevo `identity_service.py`, nuevo `identity_main.py`
  - Puerto: 8080 (diferente a 9001 para no colisionar si corren en el mismo host)
- [ ] Crear `identity_main.py` con la aplicacion FastAPI minima (sin todos los routers del backend)
- [ ] Agregar servicio `bhm-identity` en `docker-compose.dev.yml`
- [ ] Crear `k8s/base/identity.yaml` — Deployment + Service ClusterIP
- [ ] Actualizar `k8s/base/kustomization.yaml` — agregar `identity.yaml` a resources
- [ ] Actualizar Next.js: `IDENTITY_API_URL` apunta a `http://bhm-identity:8080` en lugar de `bunkerm-api:9001`
- [ ] Mover el router `identity.py` fuera de `bunkerm-api/main.py` (ya no lo sirve el backend principal)
- [ ] Documentar en `docs/adr/` el ADR de extraccion del servicio de identidad

#### Validacion 5B-2

- [ ] `kubectl get pods -n bhm-lab | grep identity` muestra `bhm-identity-*` Running
- [ ] Login en la UI usa el nuevo servicio: logs de `bhm-identity` muestran la llamada
- [ ] `bunkerm-api` no tiene el router `/api/v1/identity/verify` (fue removido)
- [ ] Keycloak puede reemplazarse en un futuro: cambiar `IDENTITY_API_URL` y el `signToken`
  en Next.js al OIDC token del Keycloak sin cambiar la logica de negocio

---

## Frente 5D — Migracion nginx in-pod a K8s Ingress

> Pre-condicion: 5A completado.
> Nota: para el lab kind actual, esta migracion es OPCIONAL. El NodePort :32000 es suficiente
> para el lab. Esta migracion aplica cuando se quiera exponer el cluster a una red real.

### Motivacion

El nginx in-pod (en el contenedor frontend) hace dos cosas:
1. Serve reverse proxy de la API (`/api/*` -> bunkerm-api)
2. Serve el frontend Next.js como static/SSR

En un entorno K8s maduro, el edge routing lo hace el Ingress controller. Esto permite:
- TLS centralizado (cert-manager)
- Rate limiting a nivel cluster
- Routing basado en Host header (multi-tenant)
- Observabilidad centralizada de trafico HTTP

### Opciones

| Opcion | Descripcion | Cuando usar |
|--------|-------------|-------------|
| A | Mantener nginx in-pod (actual) | Lab kind, single-node |
| B | nginx-ingress-controller + Ingress resource | Cluster multi-nodo o expuesto |
| C | Traefik Ingress | Si ya se usa Traefik en el cluster |

**Recomendacion para el lab kind actual**: Opcion A, con el siguiente cambio: nginx deja
de hacer proxy de la API y pasa esa responsabilidad al Ingress cuando llegue la migracion.

### Checklist 5D (para cuando se active)

#### Instalar nginx-ingress-controller en kind

- [ ] Agregar al `k8s/kind/kind-config.yaml` la seccion de extraPortMappings si no existe:
  ```yaml
  extraPortMappings:
    - containerPort: 80
      hostPort: 80
    - containerPort: 443
      hostPort: 443
  ```
- [ ] Aplicar el manifiesto del nginx-ingress-controller para kind:
  ```
  kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
  ```
- [ ] Esperar a que el pod `ingress-nginx-controller` este Ready

#### Crear Ingress resource

- [ ] Crear `k8s/base/ingress.yaml`:
  ```yaml
  apiVersion: networking.k8s.io/v1
  kind: Ingress
  metadata:
    name: bhm-ingress
    annotations:
      nginx.ingress.kubernetes.io/proxy-body-size: "10m"
      nginx.ingress.kubernetes.io/proxy-read-timeout: "180"
      nginx.ingress.kubernetes.io/proxy-send-timeout: "180"
  spec:
    ingressClassName: nginx
    rules:
      - host: bhm.local  # override en kind overlay
        http:
          paths:
            - path: /api/
              pathType: Prefix
              backend:
                service:
                  name: bunkerm-api
                  port:
                    number: 9001
            - path: /
              pathType: Prefix
              backend:
                service:
                  name: bunkerm-frontend
                  port:
                    number: 3000  # Next.js directo, nginx se elimina del frontend
  ```
- [ ] Actualizar `bunkerm-frontend`: cuando se usa Ingress, nginx puede eliminarse y
  Next.js puede servir en el puerto 3000 directamente (simplifica la imagen)
- [ ] Cambiar Service `bunkerm-frontend` de NodePort a ClusterIP
- [ ] Cambiar Service `bunkerm-api` a ClusterIP (ya lo es)

#### Politicas de Ingress y balanceo de carga

- [ ] Agregar anotaciones de rate limiting a nivel Ingress:
  ```yaml
  nginx.ingress.kubernetes.io/limit-rps: "20"
  nginx.ingress.kubernetes.io/limit-connections: "10"
  ```
- [ ] Para multi-replica de bunkerm-api: el Ingress balancea automaticamente via el Service
  K8s (round-robin por defecto). No requiere configuracion adicional.
- [ ] Para sesiones stateful (si Next.js usa sesiones server-side en el futuro):
  agregar `nginx.ingress.kubernetes.io/affinity: cookie`

#### Validacion 5D

- [ ] `kubectl get ingress -n bhm-lab` muestra ADDRESS asignada
- [ ] `curl -H "Host: bhm.local" http://localhost/api/monitor/health` -> 200
- [ ] `curl -H "Host: bhm.local" http://localhost/` -> frontend Next.js
- [ ] Rate limiting: 25+ requests rapidos al mismo endpoint -> algunos devuelven 429

---

## Dependencias entre frentes

```
5C (schemas PostgreSQL)
  |
  +-> 5A (image split)          -- independiente pero 5A facilita 5B
  |     |
  |     +-> 5D (K8s Ingress)    -- post 5A
  |
  +-> 5B-1 (user store -> PG)   -- requiere schema identity de 5C
        |
        +-> 5B-2 (bhm-identity) -- requiere 5B-1
              |
              +-> 5B-3 (Keycloak) -- futuro, fuera del scope de este plan
```

### Secuencia recomendada de iteraciones

| Iteracion | Frente(s) | Duracion estimada | Entregable |
|-----------|-----------|-------------------|------------|
| Sprint 1 | 5C | 1-2 dias | Schemas PostgreSQL, Alembic migrations |
| Sprint 2 | 5A | 2-3 dias | Dos imagenes, Compose + K8s actualizados |
| Sprint 3 | 5B-1 | 2-3 dias | User store en PG, Next.js llama al backend |
| Sprint 4 | 5B-2 | 3-4 dias | bhm-identity service standalone |
| Sprint 5 (op) | 5D | 1-2 dias | nginx-ingress, Ingress resource |

---

## Registro de decisiones

### ADR-5A-001: Dos Dockerfiles en lugar de multi-stage unico

**Decision**: crear `Dockerfile.frontend` y `Dockerfile.api` como archivos independientes.
**Razon**: los tiempos de build son dominados por el install de Node.js y Python respectivamente.
Separar evita invalidar el cache de Node por cambios Python y viceversa.
**Consecuencia**: `deploy.ps1` debe buildear y taggear dos imagenes.

### ADR-5B-001: Next.js sigue siendo el BFF (Backend for Frontend)

**Decision**: Next.js mantiene la gestion de cookies y sesiones JWT. El nuevo servicio
bhm-identity NO emite la cookie — solo valida credenciales y devuelve datos del usuario.
**Razon**: El patron BFF es el correcto para SSR. La cookie httpOnly la debe emitir el
servidor que esta en el mismo origen que el cliente (Next.js en :2000).
**Consecuencia para Keycloak**: cuando se integre Keycloak, el flujo sera Authorization Code
Flow entre Next.js (usando next-auth con provider OIDC) y Keycloak. La cookie `bunkerm_token`
pasara a ser el access token de Keycloak (o un token proxy generado por next-auth).

### ADR-5B-002: No usar NextAuth.js en la iteracion 5B-1

**Decision**: mantener el sistema JWT custom de `lib/auth.ts` y `middleware.ts` en la
iteracion 5B-1. Migrar a NextAuth.js (Auth.js v5) se reserva para la iteracion 5B-2 o 5B-3.
**Razon**: next-auth tiene soporte nativo para providers OIDC (incluyendo Keycloak) pero
introduce dependencias adicionales y un cambio mayor en el flujo de sesion. El riesgo es
alto para una iteracion de bajo impacto como 5B-1.
**Prerequisito para Keycloak**: cuando llegue la integracion, si se usa next-auth, el
`NEXTAUTH_URL` ya esta en el ConfigMap K8s y solo requiere agregar el provider OIDC.

### ADR-5D-001: nginx in-pod se mantiene hasta 5D

**Decision**: no eliminar nginx del contenedor frontend en el sprint 5A. nginx se mantiene
como reverse proxy in-pod hasta que se adopte K8s Ingress en 5D.
**Razon**: eliminar nginx requeriria que Next.js sirva la API directamente (no es su
responsabilidad) o que el Ingress este disponible antes de que se quite nginx.
**Consecuencia**: el contenedor frontend sigue usando supervisord con nginx + nextjs.

### ADR-5C-001: Un solo servidor PostgreSQL, schemas multiples

**Decision**: mantener una instancia PostgreSQL (`postgres:5432`) con schemas separados
por dominio en vez de crear multiples instancias.
**Razon**: overhead operacional de multiples instancias no esta justificado para el
volumen actual de datos. La separacion por schemas da suficiente aislamiento logico y
simplifica el backup (un solo pg_dump).
**Prerequisito para ecosistema compartido**: cuando el servicio externo de datos de topics
necesite compartir la misma identidad, se le otorga acceso al schema `identity` con un
usuario PostgreSQL de solo lectura. La conexion es via el mismo Service `postgres:5432`.

---

## Checklist de cierre de Phase 5

- [ ] 5C — Schemas PostgreSQL creados y Alembic migrations aplicadas
- [ ] 5A — `Dockerfile.frontend` y `Dockerfile.api` en bunkerm-source/
- [ ] 5A — `docker-compose.dev.yml` tiene `bunkerm-frontend` y `bunkerm-api` separados
- [ ] 5A — `k8s/base/bunkerm-frontend.yaml` y `k8s/base/bunkerm-api.yaml` en k8s/base/
- [ ] 5A — `deploy.ps1` builda dos imagenes
- [ ] 5B-1 — `identity.bhm_users` tabla en PostgreSQL con usuarios migrados
- [ ] 5B-1 — Next.js no lee `users.json` del disco; llama al backend para autenticacion
- [ ] 5B-2 — `bhm-identity` service desplegado como Deployment K8s independiente
- [ ] 5D (opcional) — Ingress resource creado y nginx-ingress-controller instalado en kind
- [ ] Smoke test pasa en ambos runtimes: `.\deploy.ps1 -Action smoke`
- [ ] Documentar cambios en ARCHITECTURE.md
