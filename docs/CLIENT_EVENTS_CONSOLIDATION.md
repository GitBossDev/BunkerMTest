# Consolidación de tablas de eventos de cliente MQTT

**Fecha:** 2026-04-29  
**Decisión:** Opción B — tabla única `client_mqtt_events` como event store canónico

---

## Contexto y motivación

### Problema detectado

Al analizar la base de datos PostgreSQL se identificaron dos tablas con información altamente solapada:

| Tabla | DB | Tipo de evento almacenado |
|---|---|---|
| `client_mqtt_events` | control-plane | Todos: conexiones, desconexiones, auth failures, publishes, subscribes |
| `client_session_events` | history | Solo: conexiones, desconexiones, auth failures |
| `client_topic_events` | history | Solo: publishes y subscribes |

Por cada evento procesado en el broker, el servicio llamaba en serie:
```python
client_activity_storage.record_event(event)   # → client_session_events + client_topic_events
persist_mqtt_event(event)                      # → client_mqtt_events
```

Esto generaba:
- **2× el almacenamiento** necesario para los mismos datos
- **Violación 2FN**: misma dependencia funcional almacenada en dos lugares
- **Dos fuentes de verdad** para microservicios externos que comparten el mismo PostgreSQL
- Un **bug silencioso** donde `reason_code` se guardaba en BD pero nunca llegaba a la API
- **Inconsistencia de casing** en `event_type`: `"Publish"` en `client_mqtt_events` vs `"publish"` en `client_topic_events`

### Por qué Opción B (no Opción A — CQRS dual write)

La Opción A (aceptar doble escritura como patrón CQRS) no reduciría el tamaño de ninguna tabla. Ambas seguirían creciendo al mismo ritmo, manteniendo ≈2× del almacenamiento. Para un PostgreSQL compartido entre verticales y microservicios del cluster, dos fuentes parciales obligan a los servicios externos a conocer la lógica interna de qué tabla consultar para cada tipo de evento.

`client_mqtt_events` es la tabla más completa — tiene `event_id` (UUID de deduplicación), `status`, `details`, y `reason_code`. Es la estructura exacta para la futura vista de auditoría por cliente.

---

## Tablas eliminadas

| Tabla | Motivo |
|---|---|
| `client_session_events` | Subconjunto estricto de `client_mqtt_events` |
| `client_topic_events` | Subconjunto estricto de `client_mqtt_events` |
| `HistoricalTick` (ORM) | Modelo muerto, sin migración activa, sin lectores ni escritores |

## Tablas conservadas (no redundantes)

| Tabla | Rol |
|---|---|
| `client_mqtt_events` | Event store canónico — movida de control-plane → history DB |
| `client_registry` | Catálogo de clientes sincronizado desde DynSec |
| `client_subscription_state` | Estado de suscripción activa por usuario+topic (upsert) |
| `client_daily_summary` | Rollup diario para reportes (derivado) |
| `client_daily_distinct_topics` | Topics distintos por día para reportes (derivado) |

---

## Correcciones de schema en `client_mqtt_events`

| Campo | Antes | Después | Motivo |
|---|---|---|---|
| columna timestamp | `timestamp` | `event_ts` | Consistencia con todas las demás event tables del proyecto |
| `event_type` al escribir | `"Publish"`, `"Subscribe"` | `"publish"`, `"subscribe"` | Consistencia con `client_topic_events` histórico y con `client_daily_summary` aggregations |
| `reason_code` en Pydantic | ausente | `Optional[str] = None` | Bug: se guardaba en BD pero el modelo lo ignoraba; nunca llegaba a la API |

---

## Plan de implementación

### Fase 1 — Limpieza Alembic

**1.1** Eliminar `005_client_mqtt_events.py`  
→ Archivo: `backend/app/alembic/versions/005_client_mqtt_events.py`  
→ Razón: rama muerta del DAG de Alembic. El slot `005` ya está ocupado por `005_schema_control_plane`. Esta revisión nunca puede ejecutarse en el flujo normal y puede causar `MultipleHeads`.

**1.2** Crear `008_remove_client_mqtt_events_from_control_plane.py`  
→ Árbol: control-plane alembic, `down_revision = "007_client_mqtt_events"`  
→ `upgrade()`: copia datos de `client_mqtt_events` a history DB si es posible, luego DROP con `checkfirst=True`  
→ `downgrade()`: recrear la tabla (para rollback)

**1.3** Actualizar `001_history_reporting_initial.py`  
→ Agregar `ClientMQTTEvent.__table__` a la lista `TABLES` (para fresh installs sin revisión previa)

**1.4** Crear `002_consolidate_client_events.py`  
→ Árbol: history_reporting_alembic, `down_revision = "001_history_reporting_initial"`  
→ `upgrade()`: DROP `client_session_events`, DROP `client_topic_events`, CREATE `client_mqtt_events` con schema corregido (`event_ts` en vez de `timestamp`)  
→ `downgrade()`: DROP `client_mqtt_events`, recrear `client_session_events` y `client_topic_events`

### Fase 2 — ORM y Pydantic

**2.1** `models/orm.py`  
- Eliminar clase `HistoricalTick`  
- Renombrar columna `timestamp` → `event_ts` en `ClientMQTTEvent`  
- Añadir `reason_code` a `ClientMQTTEvent` (ya existe en Alembic, solo faltaba en el ORM)

**2.2** `services/clientlogs_service.py`  
- Añadir `reason_code: Optional[str] = None` al modelo Pydantic `MQTTEvent`

### Fase 3 — Eliminar doble escritura

**3.1** `services/clientlogs_service.py` — `persist_mqtt_event()`  
- Cambiar `settings.resolved_control_plane_database_url` → `settings.resolved_history_database_url`  
- Normalizar `event_type` a `.lower()` al construir `ClientMQTTEvent`  
- Mapear `reason_code` desde el evento

**3.2** `clientlogs/sqlalchemy_activity_storage.py` — `record_event()`  
- Eliminar `session.add(ClientSessionEvent(...))` — ya no escribir sesiones  
- Eliminar `session.add(ClientTopicEvent(...))` — ya no escribir topics  
- Mantener escrituras a `client_subscription_state` y `client_daily_summary`  
- Eliminar `ClientSessionEvent`/`ClientTopicEvent` de `_prune_locked()`  
- Eliminar imports de `ClientSessionEvent`, `ClientTopicEvent`

**3.3** `clientlogs/sqlite_activity_storage.py`  
- Eliminar `CREATE TABLE client_session_events` del DDL  
- Eliminar `CREATE TABLE client_topic_events` del DDL  
- Eliminar `DELETE FROM client_session_events` de `_prune_locked()`  
- Eliminar `DELETE FROM client_topic_events` de `_prune_locked()`  
- Eliminar el bloque `INSERT INTO client_session_events` de `record_event()`  
- Eliminar el bloque `INSERT INTO client_topic_events` de `record_event()`  
- Mantener `client_subscription_state` y `client_daily_summary`

**3.4** `clientlogs/activity_storage.py`  
- Quitar `ClientSessionEvent` y `ClientTopicEvent` de la lista `ensure_tables`

### Fase 4 — Corregir lectura

**4.1** `clientlogs/sqlalchemy_activity_storage.py` — `get_client_activity()`  
- Reemplazar query a `ClientSessionEvent` → query a `ClientMQTTEvent` filtrada por `event_type IN ('client connection', 'client disconnection', 'auth failure')`  
- Reemplazar query a `ClientTopicEvent` → query a `ClientMQTTEvent` filtrada por `event_type IN ('subscribe', 'publish')`  
- Mapear campos de `ClientMQTTEvent` a la response shape existente (mantener compatibilidad con el frontend actual)

**4.2** `routers/clientlogs.py` — endpoint `GET /events`  
- Cambiar `settings.resolved_control_plane_database_url` → `settings.resolved_history_database_url`

### Fase 5 — Tests

**5.1** `tests/test_history_postgres_integration.py`  
- Quitar imports de `ClientSessionEvent`, `ClientTopicEvent`  
- Quitar cleanup de esas tablas en teardown  
- Agregar assertions sobre `ClientMQTTEvent`

**5.2** `tests/test_reporting_postgres_integration.py`  
- Quitar imports y cleanup de `ClientSessionEvent`, `ClientTopicEvent`  
- Adaptar assertions de retention a `client_mqtt_events`

**5.3** `tests/test_history_reporting_alembic_migrations.py`  
- Cambiar assert `"client_session_events" in table_names` → `"client_mqtt_events" in table_names`  
- Verificar que `client_topic_events` ya no existe

**5.4** `tests/test_sqlalchemy_storage_backends.py`  
- Adaptar assertions de `rows_past_retention` para tablas post-consolidación

**5.5** `tests/test_reports.py`  
- Adaptar queries directas que referencian `client_topic_events`

---

## Archivos involucrados

| Archivo | Acción |
|---|---|
| `alembic/versions/005_client_mqtt_events.py` | **ELIMINAR** |
| `alembic/versions/008_remove_client_mqtt_events_from_control_plane.py` | **CREAR** |
| `history_reporting_alembic/versions/001_history_reporting_initial.py` | **MODIFICAR** — agregar ClientMQTTEvent |
| `history_reporting_alembic/versions/002_consolidate_client_events.py` | **CREAR** |
| `models/orm.py` | **MODIFICAR** — quitar HistoricalTick, corregir ClientMQTTEvent |
| `services/clientlogs_service.py` | **MODIFICAR** — MQTTEvent + persist_mqtt_event |
| `clientlogs/sqlalchemy_activity_storage.py` | **MODIFICAR** — record_event + get_client_activity |
| `clientlogs/sqlite_activity_storage.py` | **MODIFICAR** — DDL + record_event + _prune_locked |
| `clientlogs/activity_storage.py` | **MODIFICAR** — quitar tablas eliminadas de ensure_tables |
| `routers/clientlogs.py` | **MODIFICAR** — /events endpoint usa history DB |
| `tests/test_history_postgres_integration.py` | **MODIFICAR** |
| `tests/test_reporting_postgres_integration.py` | **MODIFICAR** |
| `tests/test_history_reporting_alembic_migrations.py` | **MODIFICAR** |
| `tests/test_sqlalchemy_storage_backends.py` | **MODIFICAR** |
| `tests/test_reports.py` | **MODIFICAR** |

---

## Criterios de verificación

1. `alembic heads` (control-plane) → único head `008_remove_client_mqtt_events_from_control_plane`
2. `alembic heads` (history_reporting) → único head `002_consolidate_client_events`
3. `pytest` sobre tests de history/reporting/clientlogs pasa sin errores
4. `GET /api/v1/clientlogs/events` devuelve eventos desde history DB, incluyendo `reason_code`
5. `GET /api/v1/clientlogs/activity/{username}` devuelve `session_events`, `topic_events`, `subscriptions`, `daily_summary` — misma shape, fuente consolidada
6. En PostgreSQL: `\dt` no muestra `client_session_events` ni `client_topic_events`; `client_mqtt_events` existe en history DB (public schema)

---

## Apunta hacia (futura fase, no en scope ahora)

`GET /api/v1/clientlogs/activity/{username}` pasará de devolver las últimas N entradas del feed global a una vista de auditoría por cliente con:
- Timeline de conexiones y desconexiones (con `reason_code`, `disconnect_kind`)
- Historial de suscripciones activas e históricas por topic
- Detalle de publicaciones por topic (payload_bytes, qos, retained)
- Resumen diario de actividad

La estructura de `client_mqtt_events` post-consolidación soporta directamente estas consultas via `WHERE username = ? AND event_type = ?`.
