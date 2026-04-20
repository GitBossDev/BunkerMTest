# ADR-0008 - Modelo de identidades y secretos para Fase 6

## Estado

Aprobado

## Contexto

Tras cerrar Fase 5, BHM ya dispone de control-plane, observabilidad broker-owned, read models persistidos y contrato estable para alertas. El siguiente riesgo estructural no está en observabilidad sino en mezclar identidades y credenciales con responsabilidades distintas.

En el baseline actual conviven varios mecanismos:

- sesión humana de la UI web;
- autenticación service-to-service para la API de gestión;
- credenciales MQTT para clientes y operaciones broker-facing;
- referencias a secretos externos usadas por `bhm-alert-delivery`;
- material sensible broker-facing (`mosquitto_passwd`, TLS, DynSec`) con traducción Compose-first y proyección posterior a Kubernetes.

Sin una decisión explícita, frontend, backend y operaciones podrían seguir reutilizando secretos de forma ambigua o bloquear una futura integración con un IdP externo.

## Decisión

Se fija el siguiente modelo de identidades y ownership:

1. La identidad humana de gestión vive en la sesión web (`AUTH_SECRET`, `NEXTAUTH_SECRET`, bootstrap `ADMIN_INITIAL_*`) y no se reutiliza para llamadas internas entre servicios ni para autenticación MQTT.
2. La identidad service-to-service del baseline Compose-first sigue siendo `API_KEY` por cabecera `X-API-Key` para routers internos/administrativos de FastAPI. Es un mecanismo transicional aceptado de Fase 6, no el contrato final de federación.
3. Las credenciales MQTT son un dominio aparte: DynSec para clientes/dispositivos y credenciales broker-facing específicas cuando una capability técnica las requiera. No se derivan ni de la sesión web ni del `API_KEY`.
4. Los secretos de delivery externo no se almacenan completos en read models ni payloads de auditoría. La persistencia funcional solo conserva metadata redactada y `secretRef`; la materialización efectiva ocurre por variables de entorno del worker o por el backend broker-facing correspondiente.
5. El secreto efímero de creación de clientes DynSec pertenece al control-plane y se stagea en PostgreSQL (`broker_reconcile_secret`) con TTL, nunca en el desired state funcional ni en payloads de auditoría.

## Ownership de secretos en Compose-first

### Sesión humana

- `AUTH_SECRET` y `NEXTAUTH_SECRET` firman y validan la sesión web.
- `ADMIN_INITIAL_EMAIL` y `ADMIN_INITIAL_PASSWORD` solo bootstrappean la identidad inicial de administración.

### Service-to-service

- `API_KEY` protege la superficie administrativa `/api/v1/*` que no pasa por sesión de usuario.
- Next.js puede propagarla hacia el backend en el baseline actual, pero ese uso se considera compatibilidad transicional y deberá reducirse cuando exista una identidad técnica más granular.

### MQTT y broker-facing

- `MQTT_USERNAME` y `MQTT_PASSWORD` pertenecen al broker y a clientes MQTT, no a la UI.
- DynSec gestiona usuarios/permisos MQTT del plano de datos.
- `mosquitto_passwd`, TLS y `dynamic-security.json` mantienen ownership broker-facing.

### Alert delivery

- `secretRef` y la configuración redacted de canales viven en PostgreSQL como metadata.
- El secreto material real se resuelve desde entorno o secret store del worker `bhm-alert-delivery`.

## Ruta de endurecimiento aceptada

Se acepta mantener temporalmente el mecanismo actual mientras se cumplan estos límites:

- no introducir nuevos secretos hardcoded en código ni en imágenes;
- no devolver secretos completos por API;
- no mezclar `API_KEY`, sesión web y credenciales MQTT en un mismo flujo;
- añadir regresiones de auth en cada nuevo router administrativo relevante.

## Extensión futura hacia OAuth2/OIDC

BHM no queda bloqueado por no integrar todavía un IdP externo. La evolución prevista es:

1. mantener la sesión humana actual como baseline funcional;
2. encapsular autenticación humana detrás de una interfaz compatible con claims/roles externos;
3. introducir posteriormente un proveedor OAuth2/OIDC para la UI sin alterar DynSec ni las credenciales MQTT;
4. tratar la identidad service-to-service como capability distinta, potencialmente con tokens dedicados o mTLS, sin reciclar la sesión humana.

## Evolución a Kubernetes

- `AUTH_SECRET`, `NEXTAUTH_SECRET`, `API_KEY`, SMTP/webhook secrets y material TLS se proyectan a `Secret`.
- `mosquitto_passwd` y TLS broker-facing siguen la ruta ya fijada de bootstrap/secret dedicado.
- `broker_reconcile_secret` permanece como secreto efímero del control-plane persistido con TTL en PostgreSQL y no requiere volver a volúmenes compartidos.
- La rotación nativa sobre objetos `Secret` queda como siguiente corte, pero el ownership ya queda separado por dominio.

## Consecuencias

### Positivas

- frontend, backend y broker dejan de compartir implícitamente la misma noción de identidad;
- Fase 6 puede endurecer auth sin reabrir Fase 5;
- la futura integración con OAuth2/OIDC no obliga a rediseñar MQTT ni alert delivery;
- el manejo de secretos en Compose y Kubernetes queda modelado por dominio.

### Pendientes deliberados

- la whitelist por IP sigue siendo una decisión aparte de authorization/policy broker-facing;
- no se introduce todavía RBAC fino ni tokens service-to-service dedicados;
- la rotación automática de secretos queda fuera de este corte inicial.