# BHM - Contrato Técnico de Delivery de Alertas

> Estado: Acordado para Fase 5
> Fecha: 2026-04-16
> Alcance: alertas técnicas emitidas por BHM hacia canales externos

---

## Propósito

Este documento fija el contrato técnico para el delivery de alertas externas de BHM sin acoplar el motor de detección al canal de envío ni al filesystem local.

El objetivo es permitir que:

- `bhm-api` siga detectando y exponiendo alertas técnicas del broker
- un worker dedicado asuma reintentos, idempotencia y auditoría de delivery
- frontend y producto puedan avanzar sobre payloads y estados estables sin esperar toda la implementación de canales

---

## Decisiones de arquitectura

### Ownership

- `bhm-api` y el monitor siguen siendo owners de la detección y del cambio de estado de la alerta.
- El intento de delivery externo no ocurre en el hilo síncrono que evalúa la alerta.
- El ownership de entrega vive en un worker dedicado `bhm-alert-delivery`.
- En Compose-first, `bhm-alert-delivery` puede reutilizar la imagen actual igual que `bhm-reconciler` y `bhm-broker-observability`.
- En Kubernetes, el mismo rol traduce a un `Deployment` o `Job` especializado con consumo de outbox persistido en PostgreSQL.

### Modelo operativo

- Cuando una alerta cambia a estado `raised`, `bhm-api` genera un evento canónico de alertas.
- Ese evento se persiste en PostgreSQL como outbox auditable antes de cualquier intento de envío.
- `bhm-alert-delivery` consume el outbox, resuelve canales habilitados y registra cada intento de entrega por separado.
- Los canales iniciales de Fase 5 son `email` y `webhook` genérico.
- Integraciones como Slack, Teams, Discord o Telegram entran como adaptadores sobre `webhook`, no como contratos de dominio distintos.
- SMS queda fuera del primer corte operativo salvo que exista una necesidad explícita posterior.

---

## Payload canónico

Cada alerta externa se modela como un `alert delivery event` con este payload lógico:

```json
{
  "eventId": "uuid",
  "alertId": "string",
  "dedupeKey": "string",
  "transition": "raised|updated|acknowledged|resolved",
  "status": "active|acknowledged|resolved",
  "type": "broker_down|client_capacity|reconnect_loop|auth_failures",
  "severity": "critical|high|medium|low",
  "title": "string",
  "description": "string",
  "impact": "string",
  "source": {
    "service": "bhm-api",
    "component": "monitor.alert-engine",
    "broker": "bhm-broker"
  },
  "timestamps": {
    "observedAt": "2026-04-16T08:45:00Z",
    "raisedAt": "2026-04-16T08:45:00Z",
    "resolvedAt": null
  },
  "metrics": {
    "clientCapacityPct": 91.2,
    "reconnectCount": null,
    "authFailCount": null
  },
  "links": {
    "monitor": "/api/v1/monitor/alerts/broker",
    "alert": "/api/v1/monitor/alerts/broker/{alertId}"
  },
  "routing": {
    "channelPolicyId": "uuid",
    "channelCount": 2
  }
}
```

### Reglas de payload

- `eventId` identifica una transición concreta de delivery, no la alerta entera.
- `alertId` identifica la alerta funcional que el frontend ya usa.
- `dedupeKey` debe ser estable por `alertId + transition + channelPolicyVersion`.
- `transition=updated` solo se emite cuando cambian severidad, descripción o facts relevantes, no por cada reevaluación de cooldown.
- `links` conserva contratos HTTP existentes; no obliga a B a rediseñar navegación o drill-down.

---

## Persistencia mínima

El contrato requiere tres entidades persistidas en PostgreSQL:

### `alert_delivery_channel`

- configuración de un canal concreto
- tipo: `email` o `webhook`
- payload no sensible visible para frontend
- secretos y tokens solo como referencias u objetos redacted
- campo `enabled`
- metadatos de auditoría y ownership

### `alert_delivery_event`

- outbox de eventos canónicos listos para entregar
- relación con `alertId`
- `eventId`, `dedupeKey`, `transition`, `status`, `payload_json`
- estado global del evento: `pending`, `partially_delivered`, `delivered`, `dead_letter`

### `alert_delivery_attempt`

- un registro por intento y por canal
- `eventId`
- `channelId`
- `attemptNumber`
- estado: `pending`, `sent`, `failed`, `cancelled`
- `providerStatusCode`, `providerMessageId`, `errorClass`, `errorDetail`
- timestamps de programación, inicio y fin

---

## Idempotencia y reintentos

### Idempotencia

- `bhm-api` no debe insertar dos `alert_delivery_event` con el mismo `dedupeKey`.
- `bhm-alert-delivery` no debe ejecutar dos veces un mismo `attemptNumber` para el mismo `eventId + channelId`.
- Los webhooks deben incluir cabeceras:
  - `X-BHM-Event-Id`
  - `X-BHM-Alert-Id`
  - `X-BHM-Dedupe-Key`
  - `X-BHM-Signature` si el canal usa secreto compartido
- Email debe incluir `Message-ID` propio y `X-BHM-Event-Id`.

### Reintentos

- política base: backoff exponencial con jitter
- tiempos sugeridos: `30s`, `2m`, `10m`, `30m`, `2h`
- máximo inicial: `5` intentos por canal
- después del último fallo, el intento queda en `dead_letter`
- reintentos solo aplican a errores transitorios: timeout, `429`, `5xx`, problemas de DNS o TLS recuperables
- errores permanentes como `4xx` funcionales o configuración inválida cancelan nuevos intentos hasta corrección manual

---

## Canales y credenciales

### Email

- Configuración SMTP por canal o por perfil compartido
- secretos nunca devueltos completos por API
- frontend solo recibe campos redacted y flags de presencia
- soporte mínimo: `starttls`, `ssl`, usuario/password y lista de destinatarios

### Webhook

- método inicial: `POST`
- content-type: `application/json`
- timeout máximo: `15s`
- firma HMAC opcional con secreto por canal
- allowlist explícita de hosts si el despliegue lo requiere más adelante

### Manejo de secretos

- En Compose-first, los secretos de delivery viven en `.env.dev` o en referencias de canal persistidas como metadata redacted y materializadas por variables de entorno del worker.
- El payload canónico jamás incluye secretos.
- La API de lectura de canales devuelve secretos enmascarados o solo flags del tipo `hasSecret=true`.

---

## Contratos HTTP que B puede usar ya

El frontend puede trabajar desde ahora con este carril estable:

- `GET /api/v1/monitor/alerts/config`
- `PUT /api/v1/monitor/alerts/config`
- futuro `GET /api/v1/notifications/channels`
- futuro `POST /api/v1/notifications/channels`
- futuro `GET /api/v1/notifications/events`
- futuro `GET /api/v1/notifications/attempts`

### Garantías para B

- `alertId`, `severity`, `title`, `description`, `impact` y `status` se mantienen como campos funcionales estables.
- `channel type`, `enabled`, `lastDeliveryStatus`, `lastAttemptAt` y `retryPolicySummary` son campos seguros para UX y tablas de administración.
- La implementación interna del worker o del outbox no debe obligar a rehacer pantallas si se respeta este contrato.

---

## Reparto de trabajo A/B

### Carril de A

- tablas y migraciones del outbox de delivery
- worker `bhm-alert-delivery`
- adaptadores SMTP y webhook
- idempotencia, reintentos y auditoría

### Carril de B

- UX de canales y reglas
- copy funcional y estados de delivery
- tablas, filtros y exportaciones sobre historial de intentos
- validación de formularios y payloads esperados del frontend

---

## Criterio de cierre de este contrato

Este contrato se considera suficiente para Fase 5 cuando:

- el payload canónico está fijado
- el ownership del delivery está separado del motor de alertas
- existe un modelo explícito de outbox + attempts
- B puede implementar UX sin bloquearse por dudas de payload o ownership
