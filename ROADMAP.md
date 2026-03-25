# ROADMAP: Plataforma de Gestión MQTT - BunkerM Extended

**Proyecto**: Fork de BunkerM con funcionalidades empresariales propias  
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

Desarrollo de una plataforma de gestión de broker MQTT basada en BunkerM (https://github.com/bunkeriot/BunkerM), extendida con 6 funcionalidades propias de valor empresarial y una simulación completa de planta de tratamiento de aguas para pruebas realistas.

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

```
┌─────────────────────────────────────────────────────────────┐
│                     Nginx Reverse Proxy                      │
│                        (puerto 2000)                         │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌────────────┐  ┌──────────────┐  ┌──────────────┐
│  Next.js   │  │   FastAPI    │  │  Mosquitto   │
│  Frontend  │  │   Backend    │  │  MQTT Broker │
│  (2000)    │  │ (1000-1008)  │  │   (1900)     │
└────────────┘  └──────┬───────┘  └──────────────┘
                       │
                       ▼
              ┌──────────────┐
              │  PostgreSQL  │
              │    (5432)    │
              └──────────────┘
```

---

## Funcionalidades Propias (Valor Agregado)

| # | Funcionalidad | Puerto | Valor de Negocio |
|---|---------------|--------|------------------|
| 1 | **Dashboards Personalizables** | 1006 | Diferenciador visual, widgets drag-and-drop |
| 2 | **Alertas Avanzadas** | 8100 | Email, SMS, Webhooks, cooldown inteligente |
| 3 | **Multi-tenancy Mejorado** | Transversal | Modelo SaaS, aislamiento completo |
| 4 | **Backup/Restore Automático** | 1007 | Confiabilidad, compliance, recuperación |
| 5 | **Versionado de ACL** | 1000 | Auditoría, rollback, trazabilidad |
| 6 | **Simulador de Carga** | 1008 | Testing, benchmarking, demostración |

---

## Estado Actual del Proyecto

- [x] Investigación y análisis de BunkerM
- [x] Diseño de arquitectura extendida
- [x] Selección de industria para simulación (Planta de Tratamiento de Aguas)
- [x] **FASE 1**: Preparación del Entorno Base [COMPLETO]
- [x] **FASE 2**: Simulación Industrial [COMPLETO]
- [ ] **FASE 3**: Integración y Pruebas
- [ ] **FASE 4**: Funcionalidades Propias

---

## FASE 1: Preparación del Entorno Base

**Duración estimada**: 1-2 días  
**Estado**: [OK] COMPLETO

### Objetivos
- [x] Fork de BunkerM clonado localmente
- [x] Docker Compose configurado con todos los servicios
- [x] Migración a PostgreSQL preparada (script migrate-to-postgres.py)
- [x] Entorno desplegado y funcionando en localhost
- [x] Script de gestión automatizado (deploy.ps1)
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
└── water-plant-simulator/         # [FASE 2] Simulador
```

#### 1.2 Servicios Docker Compose

| Servicio | Imagen | Puerto(s) | Volúmenes | Propósito |
|----------|--------|-----------|-----------|-----------|
| **postgres** | postgres:16-alpine | 5432 | `./data/postgres` | Base de datos principal |
| **mosquitto** | eclipse-mosquitto:latest | 1900, 9001 | `./data/mosquitto`, `./config/mosquitto` | Broker MQTT |
| **bunkerm-backend** | Build from source | 1000-1005, 8100 | `./data/logs` | Servicios Python/FastAPI |
| **bunkerm-frontend** | Build from source | 3000 | - | Next.js UI |
| **nginx** | nginx:alpine | 2000 | `./config/nginx` | Reverse proxy |
| **pgadmin** (opcional) | dpage/pgadmin4 | 5050 | - | Admin de PostgreSQL |

#### 1.3 Variables de Entorno (.env.dev)

```env
# PostgreSQL
POSTGRES_USER=bunkerm
POSTGRES_PASSWORD=<CAMBIAR_EN_PRODUCCION>
POSTGRES_DB=bunkerm_db
DATABASE_URL=postgresql://bunkerm:<CAMBIAR_EN_PRODUCCION>@postgres:5432/bunkerm_db

# Mosquitto
MQTT_BROKER=mosquitto
MQTT_PORT=1900
MQTT_USERNAME=admin
MQTT_PASSWORD=<CAMBIAR_EN_PRODUCCION>

# BunkerM Backend
API_KEY=<GENERAR_UUID_ALEATORIO>
JWT_SECRET=<GENERAR_SECRET_ALEATORIO>
AUTH_SECRET=<GENERAR_SECRET_ALEATORIO>
TIER=enterprise
DYNSEC_PATH=/var/lib/mosquitto/dynamic-security.json

# Puertos de servicios
DYNSEC_PORT=1000
MONITOR_PORT=1001
CLIENTLOGS_PORT=1002
AWS_BRIDGE_PORT=1003
AZURE_BRIDGE_PORT=1004
CONFIG_PORT=1005
SMART_ANOMALY_PORT=8100

# Nuevos servicios propios
DASHBOARD_SERVICE_PORT=1006
BACKUP_SERVICE_PORT=1007
LOAD_SIMULATOR_PORT=1008

# pgAdmin (opcional)
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

```bash
# 1. Generar secrets
python scripts/generate-secrets.py > .env.dev

# 2. Crear estructura de directorios
mkdir -p data/{mosquitto,postgres,logs,backups} config/{mosquitto,postgres,nginx}

# 3. Copiar configuraciones base
cp config/mosquitto/mosquitto.conf.example config/mosquitto/mosquitto.conf

# 4. Levantar servicios
docker-compose -f docker-compose.dev.yml up -d

# 5. Verificar logs
docker-compose -f docker-compose.dev.yml logs -f

# 6. Ejecutar migraciones
docker-compose -f docker-compose.dev.yml exec bunkerm-backend alembic upgrade head

# 7. Verificar salud
./scripts/check-health.sh
```

#### 1.6 Criterios de Éxito Fase 1

- [x] `docker-compose ps` muestra todos los servicios en estado "Up"
- [x] PostgreSQL conectado en puerto 5432
- [x] Mosquitto funcionando en puerto 1900
- [x] Nginx proxy en puerto 2000
- [x] Script deploy.ps1 con 7 acciones (setup, start, stop, restart, status, logs, clean)
- [x] Script generate-secrets.py genera .env.dev automáticamente
- [x] Archivo DEPLOYMENT.md con documentación completa
- [x] Logs de servicios sin errores críticos

---

## FASE 2: Simulación de Planta de Tratamiento de Aguas

**Duración e[OK] COMPLETO

### Objetivos
- [x] Simulador de planta implementado en Python
- [x] 8 sensores + 4 actuadores IoT publicando datos realistas
- [x] Controlador automático de planta implementado
- [x] Modelo físico con dinámica de tanques, flujos y presiones
- [x] Generador de anomalías operativo (freeze, spike, drift, disconnect)
- [x] Docker Compose configurado (docker-compose.simulator.yml)
- [x] Script de gestión automatizado (simulator.ps1)
- [x] Documentación completa (PHASE2_SIMULATOR.md)ficos
- [ ] Generador de anomalías operativo

### 2.1 Arquitectura de la Planta Simulada

```
┌─────────────────────────────────────────────────────────┐
│                  Planta de Tratamiento                   │
│                                                           │
│  ┌────────┐      ┌─────────┐      ┌────────┐           │
│  │ Tanque │──────│ Bomba 1 │──────│ Tanque │           │
│  │   1    │      │         │      │   2    │           │
│  │        │      └─────────┘      │        │           │
│  └────────┘                       └────────┘           │
│      │                                 │                │
│      │                                 │                │
│  ┌───▼───┐                        ┌───▼───┐           │
│  │Válvula│                        │Válvula│           │
│  │   1   │                        │   2   │           │
│  └───────┘                        └───────┘           │
│                                                         │
│  Sensores:                                              │
│  • Nivel (tank1, tank2)                                 │
│  • pH, Turbidez                                         │
│  • Caudal (inlet, outlet)                               │
│  • Presión (pump1, pump2)                               │
│  • Temperatura ambiente                                 │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Topics MQTT

**Sensores (Publishers):**
```
sensors/tank1/level         → float (0-100%)
sensors/tank1/ph            → float (6.0-8.5)
sensors/tank1/turbidity     → float (0-10 NTU)
sensors/flow/inlet          → float (0-500 L/min)
sensors/flow/outlet         → float (0-500 L/min)
sensors/pump1/pressure      → float (0-5 bar)
sensors/pump2/pressure      → float (0-5 bar)
sensors/ambient/temperature → float (15-35°C)
```

**Actuadores (Subscribers + Publishers):**
```
actuators/pump1/command     → JSON {"action": "start|stop", "speed": 0-100}
actuators/pump1/status      → JSON {"status": "running|stopped", "speed": int, ...}
actuators/pump2/command     → JSON
actuators/pump2/status      → JSON
actuators/valve1/command    → JSON {"action": "open|close", "position": 0-100}
actuators/valve1/status     → JSON {"position": int, ...}
actuators/valve2/command    → JSON
actuators/valve2/status     → JSON
```

**Control Central:**
```
control/plant/status        → JSON (estado general)
control/alerts              → JSON (alertas generadas)
control/commands            → JSON (comandos broadcast)
```

### 2.3 Formato de Mensajes

```json
// Sensor
{
  "timestamp": "2026-03-25T10:30:45Z",
  "device_id": "sensor_tank1_level",
  "value": 75.3,
  "unit": "%",
  "quality": "good"
}

// Actuator Status
{
  "timestamp": "2026-03-25T10:30:45Z",
  "device_id": "pump1",
  "status": "running",
  "speed": 85,
  "power_consumption": 2.3,
  "hours_operation": 1234.5
}
```

### 2.4 Lógica de Control Automático

```python
# Pseudocódigo del controlador
if tank1_level < 20%:
    start_pump1()
    send_alert("Low water level in tank1")

if tank1_level > 90%:
    stop_pump1()

if ph < 6.5 or ph > 8.0:
    send_alert("pH out of range")
    adjust_chemical_dosing()

if turbidity > 5:
    send_alert("High turbidity detected")
    increase_filtration()
```

### 2.5 Generador de Anomalías

| Tipo de Anomalía | Descripción | Detectable por |
|------------------|-------------|----------------|
| **Freeze** | Sensor congela valor durante 5+ min | Silence Detector |
| **Spike** | Valor aumenta >3× repentinamente | Spike Detector |
| **Drift** | Incremento gradual sostenido | EWMA Detector |
| **Desconexión** | Cliente MQTT se desconecta temporalmente | BunkerM Monitor |
| **Out of Range** | Valores fuera de rangos físicos posibles | Z-score Detector |

### 2.6 Configuración de ACL

**Usuarios MQTT:**
- `simulator_sensors` → role: `sensor_publisher`
- `simulator_actuators` → role: `actuator_full`
- `simulator_controller` → role: `controller_full`
- `admin_user` → role: `admin`

**ACL Rules:**
```json
{
  "roles": [
    {
      "rolename": "sensor_publisher",
      "acls": [
        {
          "acltype": "publishClientSend",
          "topic": "sensors/#",
          "allow": true
        },
        {
          "acltype": "subscribeLiteral",
          "topic": "control/commands",
          "allow": true
        }
      ]
    },
    {
      "rolename": "actuator_full",
      "acls": [
        {
          "acltype": "publishClientSend",
          "topic": "actuators/#",
          "allow": true
        },
        {
          "acltype": "subscribeLiteral",
          "topic": "actuators/+/command",
          "allow": true
        },
        {
          "acltype": "subscribeLiteral",
          "topic": "control/commands",
          "allow": true
        }
      ]
    },
    {
      "rolename": "controller_full",
      "acls": [
        {
          "acltype": "publishClientSend",
          "topic": "#",
          "allow": true
        },
        {
          "acltype": "subscribeLiteral",
          "topic": "#",
          "allow": true
        }
      ]
    }
  ]
}
```

### 2.7 Estructura del Simulador

```
water-plant-simulator/
├── Dockerfile
├── docker-compose.simulator.yml
├── requirements.txt
├── config/
│   └── plant_config.yaml
├── src/
│   ├── main.py
│   ├── devices/
│   │   ├── __init__.py
│   │   ├── base_device.py
│   │   ├── sensor.py
│   │   ├── actuator.py
│   │   └── controller.py
│   ├── simulation/
│   │   ├── __init__.py
│   │   ├── physics_model.py
│   │   └── anomaly_generator.py
│   └── mqtt_client.py
└── README.md
```
x] Simulador se levanta con `.\simulator.ps1 start`
- [x] 12 dispositivos (8 sensores + 4 actuadores) implementados
- [x] Sensores publican cada 5-10 segundos (configurable)
- [x] Actuadores responden a comandos MQTT (on, off, set_value, set_mode)
- [x] Controlador automático implementado con reglas de nivel, pH y turbidez
- [x] Modelo físico calcula dinámica de tanques, flujos y presiones
- [x] Generador de anomalías con 4 tipos (freeze, spike, drift, disconnect)
- [x] Docker Compose configurado con dependencia en red bunkerm-network
- [x] Script simulator.ps1 con 8 acciones (start, stop, restart, status, logs, anomalies, build, clean)
- [x] Documentación completa en PHASE2_SIMULATOR.md (400+ líneas)
- [x] Archivo plant_config.yaml con configuración completa (130+ líneas)
- [x] Dockerfile optimizado con usuario no privilegiadoonde correctamente)
- [ ] ACL funciona: intentos no autorizados fallan
- [ ] Controlador automático enciende bomba cuando nivel < 20%
- [ ] Anomalías generadas son visibles en logs

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
