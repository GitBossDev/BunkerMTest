# ADR-0007 - Pipeline de observabilidad técnica para Fase 5

## Estado

Aprobado

## Contexto

Tras el cierre de Fase 4, BHM ya no depende de mounts de logs en el proceso web principal, pero Fase 5 seguía teniendo una decisión pendiente: cómo debe modelarse la observabilidad técnica para logs, incidentes y reporting operativo sin recaer en `tail -f` acoplado ni bloquear a frontend.

La solución debía cumplir simultáneamente estos requisitos:

- mantener `bhm-api` fuera del ownership directo del filesystem del broker;
- permitir compatibilidad Compose-first hoy y evolución posterior a Kubernetes;
- sostener reporting técnico e historial de incidentes con datos persistidos en PostgreSQL;
- dar a frontend un contrato HTTP estable para tablas, filtros, exports y drill-down;
- evitar que la validación end-to-end del delivery o del laboratorio de integración bloquee el refinamiento funcional.

## Decisión

Se adopta un pipeline observacional híbrido y explícito:

1. `bhm-broker-observability` es el único componente broker-owned autorizado para leer artefactos observacionales compartidos del broker.
2. La lectura de `mosquitto.log`, `broker-resource-stats.json`, `dynamic-security.json`, `mosquitto.conf`, `mosquitto_passwd` y cert store se sirve por HTTP interno broker-owned con `source-status` explícito.
3. `bhm-api` consume esa observabilidad vía cliente HTTP interno, nunca mediante lectura directa del filesystem del broker.
4. `clientlogs_service` transforma snapshots broker-owned en eventos técnicos estructurados (`Client Connection`, `Client Disconnection`, `Auth Failure`, `Subscribe`, `Publish`) y persiste la actividad útil en PostgreSQL.
5. `monitor_service` transforma métricas `$SYS` y publishes broker-observed en estado operativo y series históricas persistidas en PostgreSQL.
6. `reporting` consume exclusivamente read models persistidos de monitor/client activity/topic history para timeline, incidentes, reporting diario/semanal, retención y exports.

## Consecuencias

### Positivas

- Se elimina `tail -f` como contrato arquitectónico del producto, aunque la fuente primaria siga siendo el log del broker dentro del componente broker-owned.
- Frontend y UX pueden trabajar con contratos estables (`monitor`, `clientlogs`, `reports`, `notifications`) sin acoplarse al origen físico del dato.
- El pipeline ya es portable a Kubernetes: `bhm-broker-observability` traduce a sidecar, deployment broker-owned o componente equivalente sin volver a meter mounts en el pod web.
- La degradación queda auditable: cada fuente expone `enabled`, `available`, `mode`, `lastError` y, cuando aplica, offsets/replay.

### Limitaciones aceptadas

- Mientras Mosquitto siga siendo la fuente primaria de verdad para ciertos eventos de sesión, `bhm-broker-observability` continúa leyendo artefactos broker-owned; el cambio es de ownership y contrato, no de desaparición absoluta del log.
- La validación end-to-end de servicios auxiliares como `bhm-alert-delivery` sigue fuera de este ADR y se resuelve en el plan de integración.

## Eventos técnicos mínimos por servicio

### `bhm-broker-observability`

- snapshots incrementales de logs con `offset`, `next_offset`, `has_more`, `rewound`;
- snapshots de resource stats;
- estado observado de DynSec, configuración Mosquitto, passwd y cert store;
- `source-status` por artefacto broker-owned.

### `bhm-api` / `clientlogs_service`

- `Client Connection`;
- `Client Disconnection`;
- `Auth Failure`;
- `Subscribe`;
- `Publish`;
- `source-status` para `logTail` y `mqttPublish`.

### `bhm-api` / `monitor_service`

- métricas `$SYS` normalizadas del broker;
- publishes broker-observed reflejados en topic history y contadores del monitor;
- alertas técnicas activas e históricas;
- estado de fuente para observabilidad de resource stats.

### `reporting`

- reportes diarios y semanales del broker;
- timeline por cliente;
- incidentes derivados (`ungraceful_disconnect`, `auth_failure`, `reconnect_loop`);
- purge y estado de retención;
- exports CSV/JSON cuando el contrato HTTP los exponga.

## Impacto en el trabajo de B

- B puede considerar estable el carril HTTP de `monitor`, `clientlogs`, `reports` y `notifications` para UX, filtros, tablas y exports.
- El histórico final de logs ya no depende de una futura lectura directa desde frontend o web container, sino del pipeline broker-owned más read models persistidos.
- Si B necesita nuevas vistas sobre logs/incidentes, debe pedir extensión de contratos HTTP o read models, no reutilizar mounts ni parseo local del broker.

## Alternativas descartadas

### Mantener `tail -f` en el proceso web principal

Descartado porque reintroduce acoplamiento al broker y rompe el criterio Compose-first/Kubernetes-ready.

### Mover todo directamente a un stack externo de observabilidad

Descartado para Fase 5 porque añade demasiada complejidad operativa y no resuelve antes el ownership interno ni la estabilización de contratos HTTP del producto.