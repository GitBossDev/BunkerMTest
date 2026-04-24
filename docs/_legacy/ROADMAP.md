# ROADMAP: Plataforma de Gestión MQTT - BHM

**Proyecto**: BHM (Broker Health Manager), basado en un fork de BunkerM con funcionalidades empresariales propias  
**Fecha de creación**: 25 de marzo de 2026  
**Licencia**: Apache 2.0  
**Objetivo**: Plataforma de gestión avanzada de broker MQTT con simulación industrial realista

---

## Convenciones de Código

**IMPORTANTE**: Estas convenciones deben aplicarse en TODO el código del proyecto.

### 1. Nombres de Variables, Funciones y Clases
- **SIEMPRE en inglés**: Todos los identificadores (variables, funciones, clases, constantes) deben estar en inglés
- Ejemplos CORRECTOS: `user_name`, `get_connection()`, `DatabaseConfig`, `MAX_RETRIES`
- Ejemplos INCORRECTOS: `nombre_usuario`, `obtener_conexion()`, `ConfiguracionBD`

### 2. Comentarios y Documentación
- **SIEMPRE en español**: Todos los comentarios de código, docstrings y documentación deben estar en español
- Ejemplos CORRECTOS:
  ```python
  # Conectar a la base de datos PostgreSQL
  def connect_database():
      """
      Establece una conexión con PostgreSQL usando las credenciales del entorno.
      
      Returns:
          connection: Objeto de conexión a la base de datos
      """
      pass
  ```

### 3. Sin Emojis
- **PROHIBIDO** el uso de emojis en código, comentarios, documentación o nombres de archivos
- Usar texto plano descriptivo en su lugar
- Ejemplos:
  - NO: `# ✅ Conexión exitosa`
  - SÍ: `# [OK] Conexión exitosa` o `# Conexión exitosa`

### 4. Mensajes de Log y Salida de Usuario
- En español para proyecto local/corporativo
- Usar prefijos claros: `[INFO]`, `[WARNING]`, `[ERROR]`, `[OK]`

### 5. Archivos de Configuración
- Nombres de archivos en inglés: `config.yaml`, `database.json`
- Claves de configuración en inglés: `database_url`, `max_connections`
- Comentarios en español

### 6. Convenciones de Estilo por Lenguaje
- **Python**: PEP 8 (snake_case para funciones/variables, PascalCase para clases)
- **JavaScript/TypeScript**: Airbnb Style Guide (camelCase para funciones/variables, PascalCase para clases/componentes)
- **SQL**: UPPERCASE para palabras clave, snake_case para nombres de tablas/columnas

Estas convenciones aseguran consistencia, mantenibilidad y facilitan la colaboración en el proyecto.

---

## Resumen Ejecutivo

Desarrollo de BHM, una plataforma de gestión de broker MQTT basada en un fork de BunkerM (https://github.com/bunkeriot/BunkerM), extendida con funcionalidades propias de valor empresarial y una simulación completa de planta de tratamiento de aguas para pruebas realistas.

### Stack Tecnológico

| Componente | Tecnología | Versión |
|------------|-----------|---------|
| **Backend** | Python/FastAPI | 3.12+ |
| **Frontend** | Next.js + shadcn/ui | Latest |
| **Broker MQTT** | Eclipse Mosquitto | Latest |
| **Base de datos** | PostgreSQL | 16+ |
| **Despliegue** | Docker Compose | Latest |
| **Simulación** | Python + paho-mqtt | 3.12+ |

### Arquitectura de Servicios

> Nota: el diagrama siguiente refleja la topologia real actual (Fases 1-9 completadas).
> El estado historico con multiples puertos y SQLite queda documentado en _legacy/.

```
                          Host (localhost)
                               |
              :2000 HTTP    :1900 MQTT (TCP)
                  |               |
  +---------------+---------------+------------------------------------------+
  |  bunkerm-network (Docker/Podman bridge)                                    |
  |                                                                            |
  |  +------------------------------+    +-------------------------------+    |
  |  |  bunkerm-platform            |    |  bunkerm-mosquitto             |    |
  |  |  nginx :2000                 |    |  Mosquitto broker             |    |
  |  |    /api/v1/* -> uvicorn:9001 |    |  :1900 MQTT (TCP)             |    |
  |  |    /* -> Next.js :3000       |    |  :9001 MQTT-WS (opcional)     |    |
  |  |                              |    +-------------------------------+    |
  |  |  uvicorn :9001 (FastAPI)     |                                        |
  |  |    dynsec | monitor          |    +-------------------------------+    |
  |  |    config | clientlogs       |    |  bunkerm-reconciler            |    |
  |  |    bridges | reporting       |    |  broker_reconcile_daemon       |    |
  |  +------------------------------+    +-------------------------------+    |
  |                                                                            |
  |  +------------------------------+    +-------------------------------+    |
  |  |  postgres                    |    |  bhm-broker-observability      |    |
  |  |  PostgreSQL :5432            |    |  broker_observability_api      |    |
  |  |  (persistencia principal)    |    |  :9102 (interno)               |    |
  |  +------------------------------+    +-------------------------------+    |
  |                                                                            |
  |  +------------------------------+                                        |
  |  |  bhm-alert-delivery          |                                        |
  |  |  alert_delivery_daemon       |                                        |
  |  +------------------------------+                                        |
  +----------------------------------------------------------------------------+
```

---

## Funcionalidades Propias (Valor Agregado)

### Implementadas (Mejoras al panel base)

| # | Funcionalidad | Estado | Descripcion |
|---|---------------|--------|-------------|
| A | **Panel Users + Roles** | [x] COMPLETO | Admin/user con JWT, gestion de usuarios |
| B | **Client Logs mejorados** | [x] COMPLETO | Subscribe/Publish/AuthFailure, filtros |
| C | **Connected Clients correcto** | [x] COMPLETO | Reconstruccion desde logs, sin ruido interno |
| D | **Broker Config UI** | [x] COMPLETO | Listeners, websocket, inflight, queued |
| E | **ACL Test con wildcards** | [x] COMPLETO | Test topic + wildcards MQTT |

### Pendientes (Fase 4)

| # | Funcionalidad | Puerto | Valor de Negocio |
|---|---------------|--------|------------------|
| 1 | **Dashboards Personalizables** | 1006 | Diferenciador visual, widgets drag-and-drop |
| 2 | **Alertas Avanzadas** | 8100 | Email, Webhooks, cooldown inteligente |
| 3 | **Multi-tenancy Mejorado** | Transversal | Modelo SaaS, aislamiento completo |
| 4 | **Backup/Restore Automático** | 1007 | Confiabilidad, compliance, recuperación |
| 5 | **Versionado de ACL** | 1000 | Auditoría, rollback, trazabilidad |
| 6 | **Simulador de Carga** | 1008 | Testing, benchmarking, demostración |



## Estado Actual del Proyecto

- [x] Investigación y análisis del proyecto base BunkerM
- [x] Diseño de arquitectura extendida
- [x] Selección de industria para simulación (Planta de Tratamiento de Aguas)
- [x] **FASE 1**: Preparación del Entorno Base [COMPLETO]
- [x] **FASE 2**: Simulación Industrial [COMPLETO]
- [x] **Mejoras propias del panel** [COMPLETO]
- [ ] **FASE 3**: Integración y Pruebas
- [ ] **FASE 4**: Funcionalidades Propias

---

## FASE 1: Preparación del Entorno Base

**Duración estimada**: 1-2 días  
**Estado**: [OK] COMPLETO

### Objetivos
- [x] Fork de BunkerM clonado localmente
- [x] Fork de BunkerM integrado en repositorio propio (GitBossDev/BunkerMTest)
- [x] Docker Compose configurado (Podman compatible, PostgreSQL integrado en el baseline Compose-first)
- [x] Arquitectura monolitica: todo en bunkerm-platform con SQLite
- [x] Entorno desplegado y funcionando en localhost:2000
- [x] Script de gestión automatizado (deploy.ps1) con hot-patch
- [x] Generación de secrets automatizada (generate-secrets.py)
- [x] Configuración de variables de entorno (.env.dev)

### Tareas Detalladas

#### 1.1 Estructura de Directorios
```
BunkerMTest/
├── ROADMAP.md                     # Este archivo
├── DEPLOYMENT.md                  # Guía de despliegue
├── docker-compose.dev.yml         # Composición de servicios
├── .env.dev                       # Variables de entorno
├── .gitignore                     # Ignorar datos sensibles
├── data/                          # Volúmenes persistentes
│   ├── mosquitto/                 # Datos de Mosquitto
│   ├── postgres/                  # Datos de PostgreSQL
│   ├── logs/                      # Logs de servicios
│   └── backups/                   # Backups automáticos
├── config/                        # Configuraciones
│   ├── mosquitto/                 # Mosquitto configs
│   │   ├── mosquitto.conf
│   │   └── dynamic-security.json
│   ├── postgres/                  # PostgreSQL init scripts
│   │   └── init.sql
│   └── nginx/                     # Nginx configs
│       └── nginx.conf
├── scripts/                       # Scripts de utilidad
│   ├── migrate-to-postgres.py    # Migración SQLite → PostgreSQL
│   ├── setup-initial-users.sh    # Usuarios MQTT iniciales
│   └── check-health.sh            # Health check de servicios
└── greenhouse-simulator/          # [FASE 2] Simulador MQTT de invernadero
```

#### 1.2 Servicios Docker Compose

| Servicio | Imagen | Puerto(s) | Proposito |
|----------|--------|-----------|-----------|
| **bunkerm** | Build from source | 2000 | Plataforma BHM: nginx + Next.js + FastAPI unificado en puerto 9001 |
| **mosquitto** | Build from source | 1900, 9001 | Broker MQTT standalone con ciclo de vida independiente |
| **bhm-reconciler** | Build from source | (sin puerto) | Daemon de reconciliacion broker-facing |
| **bhm-broker-observability** | Build from source | 9102 (interno) | API de observabilidad read-only del broker |
| **bhm-alert-delivery** | Build from source | (sin puerto) | Daemon de entrega de alertas via outbox |
| **postgres** | postgres:16-alpine | 5432 | Persistencia principal (PostgreSQL, activo en todas las fases) |
| **pgadmin** (opcional) | dpage/pgadmin4 | 5050 | Admin de PostgreSQL levantado manualmente con perfil `tools` |

#### 1.3 Variables de Entorno (.env.dev)

```env
# Mosquitto (broker MQTT interno)
MQTT_USERNAME=bunker
MQTT_PASSWORD=<GENERADO_POR_SETUP>

# BHM Backend
API_KEY=<GENERAR_UUID_ALEATORIO>
JWT_SECRET=<GENERAR_SECRET_ALEATORIO>
AUTH_SECRET=<GENERAR_SECRET_ALEATORIO>
DYSEC_PATH=/var/lib/mosquitto/dynamic-security.json

# Timezone
TZ=Europe/Madrid

# PostgreSQL (baseline activo del stack)
POSTGRES_USER=bunkerm
POSTGRES_PASSWORD=<CAMBIAR_EN_PRODUCCION>
POSTGRES_DB=bunkerm_db
PGADMIN_DEFAULT_EMAIL=admin@bunkerm.local
PGADMIN_DEFAULT_PASSWORD=<CAMBIAR_EN_PRODUCCION>
```

#### 1.4 Migración SQLite → PostgreSQL

**Archivos afectados**:
- `smart-anomaly/app/database.py`
- `smart-anomaly/app/alembic.ini`
- `smart-anomaly/alembic/env.py`

**Cambios necesarios**:
1. Actualizar `SQLALCHEMY_DATABASE_URL` para usar `DATABASE_URL` de env
2. Cambiar driver de `sqlite+aiosqlite` a `postgresql+asyncpg`
3. Instalar dependencias: `asyncpg`, `psycopg2-binary`
4. Ejecutar migraciones Alembic contra PostgreSQL

**Tablas a crear**:
- `tenants` - Multi-tenancy
- `message_metadata` - Metadata de mensajes MQTT
- `metrics_aggregates` - Agregaciones de métricas
- `anomalies` - Anomalías detectadas
- `alerts` - Alertas generadas

#### 1.5 Comandos de Despliegue

```powershell
# 1. Generar secrets
.\deploy.ps1 -Action setup

# 2. Construir imagen
.\deploy.ps1 -Action build

# 3. Levantar servicios
.\deploy.ps1 -Action start

# 4. Verificar estado
.\deploy.ps1 -Action status

# pgAdmin opcional, fuera del flujo normal de deploy
docker compose --env-file .env.dev -f docker-compose.dev.yml --profile tools up -d pgadmin
```

#### 1.6 Criterios de Éxito Fase 1

- [x] `podman ps` muestra bunkerm-platform en estado "Up"
- [x] BHM UI accesible en http://localhost:2000
- [x] Mosquitto funcionando en puerto 1901 (externo)
- [x] Nginx proxy en puerto 2000
- [x] Script deploy.ps1 con acciones: setup, build, start, stop, restart, status, logs, clean, patch-backend, patch-frontend
- [x] Script generate-secrets.py genera .env.dev automáticamente
- [x] Login con admin@bhm.local / Usuario@1
- [x] Logs de servicios sin errores críticos

---

## FASE 2: Simulación MQTT de Invernadero

**Duración**: [OK] COMPLETO

### Objetivos
- [x] Simulador activo consolidado en `greenhouse-simulator`
- [x] Generación de carga MQTT desacoplada para validar broker, ACLs y churn de clientes
- [x] Ejecución soportada desde Windows o desde contenedor Podman contra el baseline `kind`
- [x] Wrapper operativo unificado en `simulator.ps1`
- [x] Compose auxiliar actualizado en `docker-compose.simulator.yml`
- [x] Runbook operativo disponible en `greenhouse-simulator/STRESSER_RUNBOOK.md`

### 2.1 Arquitectura del simulador activo

El simulador vigente no modela una planta de agua ni forma parte del baseline persistente de Kubernetes. El componente activo es un MQTT stresser de invernadero que vive fuera del cluster estable y se usa para:

- generar carga MQTT concurrente
- validar credenciales DynSec por cliente o credenciales compartidas
- comprobar conectividad contra `localhost:21900` o contra el `NodePort` del broker en `kind`

### 2.2 Variables principales del stresser

```env
MQTT_HOST=localhost
MQTT_PORT=21900
MQTT_AUTH_MODE=per-client
MQTT_CLIENT_PASSWORD=123456
CLIENTS=50
TIMEUNIT=3
TIME=10
MSGS=100
QOS=0
RETAIN=false
```

### 2.3 Estructura del simulador

```
greenhouse-simulator/
├── STRESSER_RUNBOOK.md
├── mosquitto/
└── src/
    ├── Greenhouse.Sensors/
    │   ├── Dockerfile
    │   ├── Program.cs
    │   ├── mqtt-stresser.env.example
    │   └── mqtt-stresser.kind.env
    ├── Greenhouse.Controller/
    ├── Greenhouse.ClientCreator/
    └── Greenhouse.Shared/
```

### 2.4 Criterios de éxito

- [x] `greenhouse-simulator` sustituye al simulador de agua como única referencia activa de simulación
- [x] `.\simulator.ps1 start` ejecuta el stresser de invernadero
- [x] `docker-compose.simulator.yml` ya no depende de `water-plant-simulator`
- [x] El simulador legado de agua queda movido a `_legacy/water-plant-simulator`
- [x] El baseline `kind` arranca sin requerir manifiestos ni imágenes del simulador de agua

---

## Mejoras Propias del Panel [COMPLETO]

**Estado**: [OK] COMPLETO

Extensiones propias implementadas sobre la base de BunkerM:

### Autenticación y Roles del Panel

- [x] Sistema de usuarios del panel con roles `admin` y `user` (solo lectura)
- [x] JWT con rol incluido en payload, cookies HTTP-only
- [x] Nuevo default admin: `admin@bhm.local` / `Usuario@1`
- [x] Gestion de usuarios en **Settings > Panel Users** (solo admin)
- [x] Registro publico deshabilitado
- [x] Middleware Next.js bloquea mutaciones para rol `user`

### Client Logs

- [x] Nuevos tipos de eventos: Subscribe, Publish, Auth Failure
- [x] Manejo correcto de timezone UTC/Z
- [x] Replay de logs al inicio (solo events recientes, no historial completo)
- [x] Filtrado de conexiones internas auto-UUID de mosquitto_ctrl
- [x] Auth Failure muestra username `unknown` (no datos previos relacionados)
- [x] Chips de filtro en UI por tipo de evento

### Connected Clients

- [x] Reconstruccion correcta del estado desde logs del broker
- [x] Clientes externos visibles (MQTT Explorer, bunker admin)
- [x] Conexiones internas auto-generadas no contaminan la lista

### Broker Configuration

- [x] Formulario estructurado (reemplaza editor JSON)
- [x] Soporte para listeners con proto tipo (mqtt / websocket)
- [x] Parametros: `max_inflight_messages`, `max_queued_messages`
- [x] Backend API actualizado en config service (puerto 1005)

### ACL Management

- [x] Test de acceso a topics desde el dialogo de ACL
- [x] Soporte de wildcards MQTT (`+` y `#`)
- [x] Respuesta estructurada: `allowed`, `reason`, `matchedRule`

### Repositorio

- [x] Codigo fuente unificado en repositorio propio (GitBossDev/BunkerMTest)
- [x] bunkerm-source integrado como codigo propio (no submodulo)
- [x] Metadatos UI alineados con Broker Health Manager

---

## FASE 3: Integración y Pruebas

**Duración estimada**: 1-2 días  
**Estado**: ⏸️ Pendiente

### Objetivos
- [ ] Todos los servicios integrados correctamente
- [ ] Pruebas de control manual exitosas
- [ ] Detección de anomalías validada
- [ ] Agentes (Schedulers/Watchers) funcionando
- [ ] Stress testing completado con métricas

### 3.1 Suite de Pruebas

#### Prueba 1: Verificación de Conectividad
```bash
# Levantar todos los servicios
docker-compose -f docker-compose.dev.yml -f docker-compose.simulator.yml up -d

# Verificar en BunkerM UI (localhost:2000):
# [OK] Dashboard muestra dispositivos conectados
# [OK] MQTT Explorer muestra topics de sensores actualizándose
# [OK] Tasas de publicación consistentes
```

#### Prueba 2: Control Manual de Actuadores
```bash
# Desde BunkerM MQTT Explorer, publicar:
Topic: actuators/pump1/command
Payload: {"action": "start", "speed": 70}

# Verificar:
# [OK] Simulador responde publicando a actuators/pump1/status
# [OK] Estado del actuador cambia en UI
```

#### Prueba 3: Validación de ACL
```bash
# Intentar publicar con credenciales de sensor a topic de actuador
mosquitto_pub -h localhost -p 1900 -u simulator_sensors -P <pass> \
  -t actuators/pump1/command -m '{"action":"start"}'

# Debe fallar con error de permisos
```

#### Prueba 4: Detección de Anomalías
```bash
# Activar generador de anomalías en simulador
curl -X POST http://localhost:8080/simulator/anomalies/enable

# Generar anomalía tipo Freeze en sensor pH
curl -X POST http://localhost:8080/simulator/anomalies/freeze \
  -d '{"sensor": "sensors/tank1/ph", "duration": 300}'

# Verificar en BunkerM Smart-Anomaly:
# [OK] Anomalía detectada con tipo "Silence"
# [OK] Severidad asignada correctamente
# [OK] Alerta generada automáticamente
```

#### Prueba 5: Agentes BunkerM

**Scheduler:**
```yaml
Name: Status Report
Cron: */15 * * * *
Topic: control/commands
Payload: {"command": "status_report", "timestamp": "{{timestamp}}"}
```
**Verificar**: Mensaje publicado cada 15 minutos

**Watcher:**
```yaml
Name: Low Level Alert
Topic: sensors/tank1/level
Condition: value < 25
Response Topic: control/alerts
Response Payload: {"alert": "Low water level", "value": {{value}}}
```
**Verificar**: Alerta se dispara cuando nivel < 25%

#### Prueba 6: Stress Testing

| Escenario | Dispositivos | Msg/s | Duración | Métrica Esperada |
|-----------|--------------|-------|----------|------------------|
| Bajo | 10 | 10 | 5 min | Latencia < 100ms |
| Medio | 50 | 50 | 10 min | Latencia < 500ms |
| Alto | 100 | 100 | 15 min | Latencia < 1s |
| Extremo | 500 | 500 | 5 min | Identificar límites |

**Comandos:**
```bash
# Escalar dispositivos en simulador
docker-compose -f docker-compose.simulator.yml up -d --scale simulator=10

# Monitorear recursos
docker stats

# Medir en BunkerM Dashboard:
# • Throughput (msg/s, KB/s)
# • Conexiones concurrentes
# • Uso de CPU/Memoria de Mosquitto
```

### 3.2 Criterios de Éxito Fase 3

- [ ] Control manual funciona bidireccional
- [ ] ACL previene accesos no autorizados correctamente
- [ ] 4 tipos de anomalías detectadas (Z-score, EWMA, Spike, Silence)
- [ ] Scheduler ejecuta cada 15 minutos sin fallos
- [ ] Watcher se dispara cuando condición se cumple
- [ ] Stress testing con 100 dispositivos: latencia < 1s
- [ ] Documentados límites de capacidad del sistema

---

## FASE 4: Funcionalidades Propias

**Duración estimada**: 8-12 días  
**Estado**: ⏸️ Pendiente

### 4.1 Dashboards Personalizables (2-3 días)

**Backend**:
- Nuevo servicio: `dashboard-service` (puerto 1006)
- Endpoints:
  - `GET /api/v1/dashboards` - Listar dashboards
  - `POST /api/v1/dashboards` - Crear dashboard
  - `PUT /api/v1/dashboards/{id}` - Actualizar
  - `DELETE /api/v1/dashboards/{id}` - Eliminar
  - `GET /api/v1/widgets/types` - Tipos disponibles

**PostgreSQL**:
```sql
CREATE TABLE dashboards (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  user_id UUID NOT NULL,
  name VARCHAR(255) NOT NULL,
  layout_json JSONB NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE widgets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dashboard_id UUID REFERENCES dashboards(id) ON DELETE CASCADE,
  type VARCHAR(50) NOT NULL,
  config_json JSONB NOT NULL,
  position_json JSONB NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);
```

**Frontend**:
- Librería: `react-grid-layout`
- Tipos de widgets:
  1. **LineChartWidget** - Gráfico temporal
  2. **GaugeWidget** - Medidor en tiempo real
  3. **TableWidget** - Últimos valores
  4. **MapWidget** - Mapa de dispositivos
  5. **AlertsWidget** - Alertas activas
  6. **StatusWidget** - Estado online/offline

**Criterios de éxito**:
- [ ] Dashboard creado desde UI con 3+ widgets
- [ ] Widgets se actualizan en tiempo real vía SSE
- [ ] Drag-and-drop funciona correctamente
- [ ] Configuración persiste en PostgreSQL
- [ ] Multi-tenancy: cada tenant ve solo sus dashboards

---

### 4.2 Sistema de Alertas Avanzado (2 días)

**Backend**:
- Extender servicio `smart-anomaly` (puerto 8100)
- Módulo `notification_engine`:
  - `EmailNotifier` (SMTP)
  - `SMSNotifier` (Twilio API)
  - `WebhookNotifier` (HTTP POST)

**PostgreSQL**:
```sql
CREATE TABLE notification_channels (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  type VARCHAR(20) NOT NULL, -- email, sms, webhook
  config_json JSONB NOT NULL,
  enabled BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE notification_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  trigger_type VARCHAR(50) NOT NULL,
  conditions_json JSONB NOT NULL,
  channel_ids JSONB NOT NULL, -- array of channel IDs
  cooldown_seconds INTEGER DEFAULT 300,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE notification_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_id UUID REFERENCES notification_rules(id),
  channel_id UUID REFERENCES notification_channels(id),
  sent_at TIMESTAMP DEFAULT NOW(),
  status VARCHAR(20) NOT NULL, -- success, failed
  error_message TEXT
);
```

**Endpoints**:
- `POST /api/v1/notifications/channels` - Configurar canal
- `GET /api/v1/notifications/channels` - Listar canales
- `POST /api/v1/notifications/rules` - Crear regla
- `GET /api/v1/notifications/history` - Historial

**Frontend**:
- Formulario de canales (SMTP, Twilio, Webhook)
- Formulario de reglas (trigger, condiciones, canales)
- Tabla de historial con filtros

**Criterios de éxito**:
- [ ] Canal de email configurado y probado
- [ ] Canal de SMS configurado (Twilio sandbox)
- [ ] Canal de webhook configurado
- [ ] Regla creada: pH < 6.0 → enviar email
- [ ] Notificación enviada cuando regla se dispara
- [ ] Historial muestra envío exitoso
- [ ] Cooldown previene spam (no más de 1 cada 5 min)

---

### 4.3 Multi-tenancy Mejorado (2-3 días)

**Backend**:
- Refactor transversal en todos los servicios
- Middleware de FastAPI para inyectar `tenant_id`
- Filtrado automático en queries SQL

**PostgreSQL**:
```sql
CREATE TABLE tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  domain VARCHAR(255) UNIQUE,
  created_at TIMESTAMP DEFAULT NOW(),
  limits_json JSONB,
  active BOOLEAN DEFAULT true
);

ALTER TABLE users ADD COLUMN tenant_id UUID REFERENCES tenants(id);
ALTER TABLE users ADD COLUMN role VARCHAR(50) DEFAULT 'tenant_user';
-- Roles: super_admin, tenant_admin, tenant_user

-- Agregar tenant_id a todas las tablas relevantes
ALTER TABLE dashboards ADD COLUMN tenant_id UUID REFERENCES tenants(id);
ALTER TABLE notification_channels ADD COLUMN tenant_id UUID REFERENCES tenants(id);
-- ... etc
```

**Endpoints (solo super_admin)**:
- `POST /api/v1/tenants` - Crear tenant
- `GET /api/v1/tenants` - Listar tenants
- `PUT /api/v1/tenants/{id}` - Actualizar tenant
- `DELETE /api/v1/tenants/{id}` - Eliminar tenant

**Frontend**:
- Panel de gestión de tenants (super-admin)
- Selector de tenant en login
- Indicador visual del tenant actual

**Criterios de éxito**:
- [ ] 2 tenants creados (Tenant A, Tenant B)
- [ ] Usuario de Tenant A no ve datos de Tenant B
- [ ] Super-admin puede acceder a todos los tenants
- [ ] Límites por tenant enforcement (max dispositivos, etc.)
- [ ] MQTT topics prefijados con tenant_id (opcional)

---

### 4.4 Backup y Restore Automático (1-2 días)

**Backend**:
- Nuevo servicio: `backup-service` (puerto 1007)
- Scheduler con APScheduler

**PostgreSQL**:
```sql
CREATE TABLE backups (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID,
  created_at TIMESTAMP DEFAULT NOW(),
  type VARCHAR(20) NOT NULL, -- manual, automatic
  size_bytes BIGINT,
  status VARCHAR(20) NOT NULL, -- pending, completed, failed
  file_path VARCHAR(500) NOT NULL
);
```

**Endpoints**:
- `POST /api/v1/backups/create` - Crear backup manual
- `GET /api/v1/backups` - Listar backups
- `GET /api/v1/backups/{id}/download` - Descargar ZIP
- `POST /api/v1/backups/{id}/restore` - Restaurar
- `PUT /api/v1/backups/schedule` - Configurar automático
- `GET /api/v1/backups/schedule` - Ver configuración

**Contenido del backup** (ZIP):
- `dynamic-security.json`
- `users.json`, `passwords.json`
- `postgres_dump.sql` (tablas: dashboards, widgets, notification_channels, rules)
- `metadata.json` (timestamp, versión de BunkerM, checksums)

**Frontend**:
- Botón "Create Backup Now"
- Tabla de backups con acciones (download, restore, delete)
- Formulario de configuración automática (daily/weekly, hora, retención)

**Criterios de éxito**:
- [ ] Backup manual creado exitosamente
- [ ] ZIP descargado y verificado (contiene todos los archivos)
- [ ] Restore ejecutado sin errores
- [ ] Configuración guardada (backup diario a 2:00 AM)
- [ ] Backup automático ejecuta según schedule
- [ ] Retención funciona (mantiene últimos 7 días)

---

### 4.5 Versionado de Configuraciones ACL (1 día)

**Backend**:
- Interceptor en servicio `dynsec` (puerto 1000)
- Snapshot pre-modificación

**PostgreSQL**:
```sql
CREATE TABLE acl_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID,
  version_number INTEGER NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  created_by_user_id UUID,
  change_description TEXT,
  acl_json JSONB NOT NULL,
  file_hash VARCHAR(64) NOT NULL -- SHA256
);
```

**Endpoints**:
- `GET /api/v1/acl/versions` - Listar versiones
- `GET /api/v1/acl/versions/{id}` - Ver contenido
- `GET /api/v1/acl/versions/{id}/diff` - Diff vs versión anterior
- `POST /api/v1/acl/versions/{id}/rollback` - Rollback

**Frontend**:
- Timeline de versiones (fecha, usuario, descripción)
- Vista de JSON de una versión
- Diff visual entre 2 versiones (colores: verde añadido, rojo eliminado)
- Botón "Rollback" con confirmación

**Criterios de éxito**:
- [ ] Modificación de ACL crea versión automáticamente
- [ ] Historial muestra última 10 versiones
- [ ] Diff visual funciona correctamente
- [ ] Rollback restaura versión anterior sin errores
- [ ] Campo "Change Description" guardado con cada cambio

---

### 4.6 Simulador de Carga Integrado (1-2 días)

**Backend**:
- Nuevo servicio: `load-simulator` (puerto 1008)
- Generador de clientes MQTT concurrentes

**PostgreSQL**:
```sql
CREATE TABLE load_tests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID,
  created_at TIMESTAMP DEFAULT NOW(),
  config_json JSONB NOT NULL,
  status VARCHAR(20) NOT NULL, -- pending, running, completed, failed
  results_json JSONB
);
```

**Endpoints**:
- `POST /api/v1/load-tests` - Crear y ejecutar test
- `GET /api/v1/load-tests` - Listar tests
- `GET /api/v1/load-tests/{id}` - Ver resultados
- `DELETE /api/v1/load-tests/{id}` - Eliminar test
- `POST /api/v1/load-tests/{id}/stop` - Detener en ejecución

**Parámetros de configuración**:
```json
{
  "name": "Stress Test 100 devices",
  "num_clients": 100,
  "publish_rate": 10,
  "message_size": 512,
  "duration": 600,
  "qos": 1,
  "topics": ["test/device{id}/data"],
  "connection_pattern": "gradual"
}
```

**Métricas recopiladas**:
- Latencia (p50, p95, p99)
- Throughput (msg/s, KB/s)
- Pérdida de mensajes (%)
- Errores de conexión
- Timeline de latencia

**Frontend**:
- Formulario de configuración con validaciones
- Progress bar durante ejecución
- Gráficos de resultados:
  - Line chart: Latency over time
  - Line chart: Throughput over time
  - Histogram: Latency distribution
  - Gauge: Error rate
- Comparación de múltiples tests (overlay)

**Criterios de éxito**:
- [ ] Test ejecutado con 100 clientes durante 5 min
- [ ] Resultados guardados en PostgreSQL
- [ ] Gráficos muestran datos correctamente
- [ ] P95 latency < 1s para 100 clientes
- [ ] Error rate < 1%
- [ ] Comparación visual entre 2 tests funciona

---

## Métricas de Éxito Global

### Métricas Técnicas
- [ ] **Uptime**: Servicios corriendo sin interrupción > 99%
- [ ] **Latencia MQTT**: P95 < 500ms con 100 dispositivos
- [ ] **Throughput**: > 1000 msg/s sin degradación
- [ ] **Cobertura de pruebas**: > 80% del código crítico
- [ ] **Tiempo de recuperación**: < 5 min con backup/restore

### Métricas de Funcionalidad
- [ ] **Dashboards**: Usuario puede crear dashboard en < 5 min
- [ ] **Alertas**: Notificación enviada en < 30s tras trigger
- [ ] **Multi-tenancy**: Aislamiento 100% verificado
- [ ] **Backup**: Backup completo < 2 min para 10K mensajes
- [ ] **ACL Versioning**: Rollback en < 1 min

### Métricas de Negocio
- [ ] **Diferenciación**: 6 features propias vs BunkerM base
- [ ] **Usabilidad**: Usuario no técnico puede configurar alertas
- [ ] **Escalabilidad**: Soporta 500 dispositivos simultáneos
- [ ] **Confiabilidad**: Backup automático diario funcionando

---

## Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| **PostgreSQL lento con alta concurrencia** | Media | Alto | Indexación adecuada, connection pooling, migrar a TimescaleDB si es necesario |
| **Mosquitto alcanza límites** | Media | Alto | Tunning de configs, considerar clustering en futuro |
| **Fronteras de multi-tenancy violadas** | Baja | Crítico | Tests exhaustivos, code review, auditoría |
| **Backups corruptos** | Baja | Alto | Checksums SHA256, validación en restore, backups redundantes |
| **Integración Twilio falla** | Media | Medio | Usar sandbox para desarrollo, fallback a email |
| **Drift del fork de BunkerM upstream** | Alta | Medio | No modificar core, nuevas features como servicios separados |

---

## Dependencias Externas

### Librerías Python (Backend)
```txt
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
sqlalchemy[asyncio]>=2.0.25
asyncpg>=0.29.0
psycopg2-binary>=2.9.9
alembic>=1.13.1
paho-mqtt>=1.6.1
pydantic>=2.5.3
python-jose[cryptography]>=3.3.0
bcrypt>=4.1.2
fastapi-mail>=1.4.1
twilio>=8.10.0
httpx>=0.26.0
apscheduler>=3.10.4
deepdiff>=6.7.1
numpy>=1.26.3
schedule>=1.2.1
```

### Librerías Node.js (Frontend)
```json
{
  "dependencies": {
    "next": "^14.0.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-grid-layout": "^1.4.4",
    "recharts": "^2.10.0",
    "@tanstack/react-query": "^5.17.0",
    "axios": "^1.6.5",
    "zustand": "^4.4.7",
    "tailwindcss": "^3.4.0",
    "@shadcn/ui": "latest"
  }
}
```

### Servicios Externos
- **Twilio**: SMS notifications (cuenta gratuita para desarrollo)
- **SMTP Server**: Email notifications (puede usar Gmail SMTP o servidor local)

---

## Documentación Adicional

### Archivos de Referencia
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Guía de despliegue detallada
- [ARCHITECTURE.md](./ARCHITECTURE.md) - Diagramas de arquitectura (por crear)
- [API.md](./API.md) - Documentación de APIs (por crear)
- [TESTING.md](./TESTING.md) - Suite de pruebas y casos (por crear)

### BunkerM Original
- Repositorio: https://github.com/bunkeriot/BunkerM
- Documentación: https://docs.bunkerm.io
- Licencia: Apache 2.0

### Recursos Útiles
- Eclipse Mosquitto: https://mosquitto.org/documentation/
- PostgreSQL: https://www.postgresql.org/docs/
- FastAPI: https://fastapi.tiangolo.com/
- Next.js: https://nextjs.org/docs
- Paho MQTT Python: https://www.eclipse.org/paho/index.php?page=clients/python/docs/index.php

---

## Cronograma Estimado

```gantt
FASE 1 (Entorno Base)         [====]                     1-2 días
FASE 2 (Simulación)                 [=======]            2-3 días
FASE 3 (Pruebas)                           [====]        1-2 días
FASE 4.1 (Dashboards)                           [=====]  2-3 días
FASE 4.2 (Alertas)                                [===]  2 días
FASE 4.3 (Multi-tenancy)                            [====] 2-3 días
FASE 4.4 (Backup)                                      [==] 1-2 días
FASE 4.5 (ACL Versioning)                                [=] 1 día
FASE 4.6 (Load Simulator)                                 [==] 1-2 días
──────────────────────────────────────────────────────────────────
Total: 12-19 días (full-time)
```

---

## Aprendizajes y Notas

### Decisiones de Diseño

1. **¿Por qué Python para todas las extensiones?**
   - Coherencia con código base de BunkerM
   - Facilita mantenimiento y debugging
   - FastAPI ya establecido como estándar

2. **¿Por qué PostgreSQL y no SQLite?**
   - Mejor soporte de concurrencia
   - Preparado para multi-tenancy
   - Auditoría y reporting más robustos

3. **¿Por qué servicios separados (puertos 1006-1008)?**
   - No modificar core de BunkerM
   - Fork limpio permite pull de updates upstream
   - Menor riesgo de romper funcionalidad existente

4. **¿Por qué simulación de planta de tratamiento de aguas?**
   - Industria realista con sensores/actuadores comunes
   - Complejidad media ideal para pruebas
   - Escalable: fácil agregar más componentes

### Lecciones del Análisis de BunkerM

- BunkerM tiene arquitectura de microservicios bien modular
- Dynamic Security Plugin de Mosquitto es potente para ACL runtime
- Smart-Anomaly ya tiene estructura sólida para extender
- Frontend dual (Vue + Next.js) puede causar confusión, usar solo Next.js
- Community tier tiene muchas limitaciones, usar `TIER=enterprise` en desarrollo

---

## Changelog

| Fecha | Versión | Cambios |
|-------|---------|---------|
| 2026-03-25 | 0.1.0 | Creación inicial del roadmap. Fase 1 en progreso. |

---

## Contribuyentes

- **Desarrollador Principal**: [Tu nombre]
- **Proyecto Base**: BunkerM (https://github.com/bunkeriot/BunkerM)

---

## Licencia

Este proyecto es un fork de BunkerM y mantiene la licencia **Apache 2.0**.

```
Copyright 2026 [Tu organización]

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

---

**Estado del Proyecto**: En Desarrollo Activo

**Última actualización**: 25 de marzo de 2026
