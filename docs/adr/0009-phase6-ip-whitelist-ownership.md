# ADR-0009 - Ownership y modelo final de whitelist por IP para Fase 6

## Estado

Aprobado

## Contexto

Fase 6 todavía tenía una decisión estructural pendiente: cómo modelar la whitelist por IP sin contradecir el control-plane, sin mezclarla con DynSec/ACL y sin bloquear a frontend.

La ambigüedad era real porque una "whitelist por IP" puede significar cosas distintas según el plano:

- acceso humano o service-to-service al plano HTTP administrativo;
- acceso MQTT de clientes/dispositivos al broker;
- confianza en proxies o saltos intermedios para extraer la IP real;
- trazabilidad de denegaciones y estado aplicado/observado.

Si se resolvía solo como regla de aplicación, BHM no podría proteger el plano MQTT. Si se resolvía solo como capability broker-facing, la UI/API de administración quedaría fuera. Además, DynSec/ACL gestiona identidad y permisos MQTT, pero no ownership de origen de red.

## Decisión

La whitelist por IP se modela como una política unificada con enforcement híbrido por scope:

1. `api_admin` se aplica en el plano HTTP/ingress de BHM para proteger la UI y los endpoints administrativos.
2. `mqtt_clients` se aplica como capability broker-facing del control-plane para proteger conexiones MQTT al broker.
3. Ambos scopes se administran como una única política funcional para producto/frontend, pero cada uno se aplica en su enforcement point correcto.

## Reglas de ownership

### Scope `api_admin`

- Ownership: capa HTTP de BHM.
- Enforcement point: nginx/app backend trust chain.
- Objetivo: limitar acceso a la superficie administrativa y a llamadas API humanas o service-to-service expuestas por HTTP.
- Observabilidad: eventos de acceso denegado y configuración efectiva en el dominio de seguridad del producto.

### Scope `mqtt_clients`

- Ownership: control-plane broker-facing.
- Enforcement point: configuración efectiva del broker.
- Objetivo: limitar qué orígenes IP pueden establecer conexiones MQTT, independientemente de DynSec/ACL.
- Observabilidad: estado deseado/aplicado/observado y auditoría de reconciliación como el resto de capabilities broker-facing.

## Relación con DynSec/ACL y autorización técnica

- DynSec/ACL sigue siendo el mecanismo de identidad y autorización MQTT por usuario, grupo, rol y topic.
- La whitelist por IP no sustituye DynSec/ACL; opera antes o al lado del plano de identidad como guardia de origen.
- La autorización HTTP actual sigue siendo coarse-grained por `API_KEY`/sesión; la whitelist `api_admin` añade restricción por origen, no RBAC fino.

## Modelo funcional unificado

La política funcional se expresa como un documento con:

- `mode`: `disabled`, `audit`, `enforce`;
- `trustedProxies`: CIDRs o IPs desde las que se acepta `X-Forwarded-For`;
- `entries`: lista de reglas con `cidr`, `scope`, `description`, `enabled`;
- `defaultAction`: `allow` o `deny` por scope cuando no hay match;
- `lastUpdatedBy`, `lastUpdatedAt`, `version` y campos de auditoría.

## Contrato para frontend

Frontend no debe modelar whitelists separadas e incompatibles. La UX consume una política unificada con scopes y source-status por enforcement point.

El contrato funcional queda descrito en `docs/BHM_IP_WHITELIST_CONTRACT.md`.

## Consecuencias

### Positivas

- B puede diseñar una única UX coherente para whitelist.
- El backend no mezcla una regla de red HTTP con DynSec/ACL ni la empuja artificialmente a un solo componente.
- La migración futura a Kubernetes mantiene semántica clara: ingress/network policy para `api_admin`, capability reconciliada broker-facing para `mqtt_clients`.

### Limitaciones aceptadas

- La decisión fija el ownership y el contrato antes de cerrar la implementación completa.
- La enforcement real de `mqtt_clients` queda como siguiente slice técnico; este ADR no implica que el broker ya esté aplicando esa política hoy.
- No introduce RBAC fino; solo aclara el dominio correcto de la whitelist.