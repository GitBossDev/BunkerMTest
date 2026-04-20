# BHM - Estrategia de Feature Flags, Rollout y Rollback de Fase 7

Este documento cierra la deuda operativa restante de Fase 7: hacer explicita la estrategia de activacion gradual, validacion y reversibilidad por capability sin inventar un framework nuevo ni introducir flags artificiales que el producto no use hoy.

## Principio

En el baseline actual de BHM, un "feature flag" de plataforma no siempre es un booleano dedicado en frontend. En muchos casos el flag real ya existe como:

- variable de entorno que habilita o deshabilita una capability
- modo de reconciliacion (`daemon`, `disabled`, etc.)
- despliegue o no de un worker auxiliar
- inclusion o no de una ruta de medicion en el harness de Fase 7

La estrategia aceptada para Fase 7 es usar esos toggles reales como mecanismo de rollout, con smoke, baseline y rollback explicitamente ligados a cada capability.

## Matriz de activacion por capability

| Capability | Toggle/flag operativo | Estado objetivo Fase 7 | Validacion minima | Rollback inmediato |
| --- | --- | --- | --- | --- |
| Reconciliacion broker-facing | `BROKER_RECONCILE_MODE=daemon` | Activo en Compose y `kind` | smoke, drift/applied, churn DynSec | volver a imagen previa o desactivar reconciliacion y mantener backend solo lectura |
| Observabilidad broker-owned | `BROKER_OBSERVABILITY_ENABLED=true` | Activo | `monitor/health`, `clientlogs`, `reports`, source-status | volver a imagen previa o desactivar fuente degradando reporting tecnico |
| Lectura incremental de logs | `BROKER_LOG_READ_ENABLED=true` | Activo | baseline/reporting, regresion de logs | degradacion controlada de historico tecnico |
| Resource stats broker-owned | `BROKER_RESOURCE_STATS_FILE_ENABLED=true` | Activo | snapshot de recursos, fallback `crictl` en `kind` | degradar a snapshot sin CPU/memoria reales |
| Delivery externo de alertas | `ALERT_NOTIFY_ENABLED=true` | Activo bajo worker dedicado | endpoints `notifications`, worker, outbox | poner `ALERT_NOTIFY_ENABLED=false` o escalar worker a `0` |
| Inline alert delivery legacy | `ALERT_NOTIFY_INLINE_DELIVERY_ENABLED=false` | Desactivado por defecto | no interferencia con outbox | mantener en `false`; si se activa puntualmente, revertir a `false` |
| Baseline host-facing con reporting | inclusion de probe `reporting` en `phase7_baseline.py` | Activo y verde | `overallStatus=ok` con `/api/proxy/reports/...` | retirar probe del baseline publicado si el carril host deja de ser estable |

## Estrategia de rollout

### 1. Cambios aditivos primero

- Introducir primero esquemas, tablas, payloads o sidecars/workers sin cambiar todavia el comportamiento principal.
- Confirmar compatibilidad con smoke y healthchecks antes de consumir el nuevo carril.

### 2. Activar lectura antes que escritura

- Cuando una capability tiene read-model o observabilidad asociada, validar primero el carril de lectura.
- Solo despues activar el cambio write-path, reconciliacion o entrega externa.

### 3. Medir inmediatamente despues del cambio

- Ejecutar smoke.
- Capturar baseline o prueba focalizada de la capability.
- Si la capability es broker-facing, validar `desired/applied/observed` o equivalente.

### 4. Mantener rollout por capability, no por fase completa

- No se hace rollout de "toda Fase 7" en bloque.
- Cada capability queda activada solo si:
  - smoke sigue verde
  - la prueba focalizada de la capability sigue verde
  - existe rollback inmediato y entendible

## Estrategia de rollback

### Broker-facing

- Primer rollback: volver a la imagen previa del backend/reconciler si el cambio afecta semantica de reconciliacion.
- Segundo rollback: restaurar backup o estado previo del artefacto broker-facing (`mosquitto.conf`, passwd, DynSec, TLS) cuando la capability ya lo soporte.
- Señal de error aceptable: `status=error` o `status=drift` auditable mientras se revierte el despliegue.

### Read-model y reporting tecnico

- Si falla la nueva fuente, degradar el endpoint o retirar la ruta del baseline publicado sin romper el resto del runtime.
- Las migraciones de esquema de PostgreSQL se asumen aditivas; el rollback principal es de imagen/codigo, no de downgrade agresivo de base de datos.

### Workers auxiliares

- El rollback principal del worker es operacional:
  - escalar a `0`
  - desactivar `ALERT_NOTIFY_ENABLED`
  - mantener persistido el outbox para no perder trazabilidad

## Secuencia operativa recomendada

1. `build` o imagen local actualizada.
2. `restart` del runtime objetivo (`Compose` o `kind`).
3. `smoke`.
4. Prueba focalizada de la capability nueva.
5. Baseline/recurso/resiliencia si el cambio toca Fase 7.
6. Solo entonces actualizar el plan y considerar la capability como verde.

## Evidencia de cierre de Fase 7

La estrategia anterior ya quedó validada en el baseline actual:

- rollout de imagen reconstruida en `kind` con smoke `5/5 OK`
- baseline host-facing en verde con reporting tecnico
- snapshot de recursos con fallback `crictl`
- recovery tras restart completo y tras reemplazo parcial del pod principal
- churn DynSec `create -> role -> delete` convergiendo a `applied` sin drift falso

Con esto, Fase 7 deja de tener deuda abierta de rollout/rollback: la activacion gradual y la reversibilidad quedan definidas por capability usando los toggles y carriles reales ya existentes.