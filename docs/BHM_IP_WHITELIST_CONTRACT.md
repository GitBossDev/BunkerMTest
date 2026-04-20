# Contrato técnico - Whitelist por IP de BHM

## Objetivo

Definir un contrato funcional estable para que frontend y backend hablen de la misma capability de whitelist por IP durante Fase 6, aunque la implementación efectiva se entregue en slices posteriores.

## Alcance

La capability cubre dos scopes:

- `api_admin`: acceso HTTP administrativo a BHM.
- `mqtt_clients`: conexiones MQTT al broker.

## Modelo funcional

```json
{
  "policy": {
    "mode": "audit",
    "trustedProxies": ["10.0.0.0/24"],
    "defaultAction": {
      "api_admin": "allow",
      "mqtt_clients": "allow"
    },
    "entries": [
      {
        "id": "office-vpn",
        "cidr": "203.0.113.0/24",
        "scope": "api_admin",
        "description": "VPN corporativa",
        "enabled": true
      },
      {
        "id": "plant-gateway",
        "cidr": "198.51.100.12/32",
        "scope": "mqtt_clients",
        "description": "Gateway principal de planta",
        "enabled": true
      }
    ],
    "version": 3,
    "lastUpdatedAt": "2026-04-20T14:00:00Z",
    "lastUpdatedBy": {
      "type": "human",
      "id": "admin@bhm.local"
    }
  },
  "status": {
    "apiAdmin": {
      "mode": "audit",
      "enforcementPoint": "http-ingress",
      "configuredEntries": 1,
      "lastDecisionAt": null,
      "lastError": null
    },
    "mqttClients": {
      "mode": "audit",
      "enforcementPoint": "broker-control-plane",
      "configuredEntries": 1,
      "desiredVersion": 3,
      "appliedVersion": 3,
      "observedVersion": 3,
      "driftDetected": false,
      "lastError": null
    }
  }
}
```

## Endpoints previstos

### `GET /api/v1/security/ip-whitelist`

Devuelve el documento funcional completo y el estado por scope.

### `PUT /api/v1/security/ip-whitelist`

Actualiza la política funcional.

Reglas mínimas de validación:

- `mode` válido: `disabled`, `audit`, `enforce`.
- `scope` válido: `api_admin`, `mqtt_clients`.
- `cidr` debe ser una IP o CIDR válida.
- `entries[].id` único dentro de la política.

### `GET /api/v1/security/ip-whitelist/status`

Devuelve solo estado de enforcement y reconciliación por scope.

## Semántica operativa

- `disabled`: no aplica bloqueo ni auditoría activa.
- `audit`: registra coincidencias/no coincidencias sin bloquear.
- `enforce`: deniega accesos fuera de whitelist según el scope.

## Relación con seguridad existente

- `api_admin` complementa la sesión web y `API_KEY`; no los reemplaza.
- `mqtt_clients` complementa DynSec/ACL; no los reemplaza.
- Los payloads de whitelist no deben incluir secretos.

## Requisitos de auditoría

- Cada cambio de política debe dejar rastro de `lastUpdatedBy`, `lastUpdatedAt` y `version`.
- Cada denegación en modo `enforce` debe ser auditable al menos con `scope`, IP evaluada, resultado y timestamp.
- El scope `mqtt_clients` debe exponer estado `desired/applied/observed` una vez entre al control-plane broker-facing.