# Inventario de Portabilidad Compose -> Kubernetes

Este documento inicia el trabajo operativo de Fase 8 convirtiendo el baseline Compose-first en un inventario explicito de objetos, dependencias y gaps hacia Kubernetes.

## Objetivo

- identificar que piezas de `docker-compose.dev.yml` ya tienen traduccion valida en `k8s/base`
- hacer visible que dependencias siguen siendo transicionales
- dejar claro que objetos adicionales deberan existir cuando la migracion de plataforma se aborde por completo

## Mapping actual por servicio

| Servicio Compose | Estado actual en Kubernetes | Objeto actual | Dependencias principales | Gaps pendientes |
| --- | --- | --- | --- | --- |
| `postgres` | Traducido | `StatefulSet` + headless `Service` + PVC | secret `bhm-env`, init SQL, storage persistente | backup/restore automatizado, politicas de recursos |
| `bunkerm-platform` | Traducido | `Deployment` + `Service` | `bhm-env`, `bhm-k8s-config`, `postgres`, `mosquitto`, broker observability | `nextjs/data` sigue efimero, falta estrategia final de Ingress |
| `bhm-reconciler` | Traducido como sidecar broker-owned | contenedor sidecar en `StatefulSet/mosquitto` | `bhm-env`, PVC broker-local, control-plane PostgreSQL | futura evolucion a controller/Job/operator |
| `bhm-broker-observability` | Traducido como sidecar | sidecar + `Service` interno | acceso read-only a PVCs del broker | decidir si queda sidecar o collector/deployment dedicado |
| `mosquitto` | Traducido | `StatefulSet` + `Service` + PVCs | `Secret` bootstrap, PVCs data/conf/log | rotacion nativa de passwd/TLS, estrategia final de exposicion |
| `bhm-alert-delivery` | Traducido en este corte | `Deployment` | `bhm-env`, PostgreSQL, outbox persistido | politicas de escalado, readiness mas funcional |
| `water-plant-simulator` | Traducido en Fase 9 | `Deployment` | `ConfigMap` propio, MQTT interno, credenciales desde `bhm-env` | separar credenciales del simulador y decidir imagen final del producto externo |
| `pgadmin` | Fuera del baseline | sin objeto actual | solo herramienta operativa | mantener fuera del carril principal |

## Configuracion y secretos

### ConfigMap actuales

- `bhm-k8s-config`
- `postgres-init`

### Secret actuales

- `bhm-env`
- `mosquitto-passwd-bootstrap`
- `mosquitto-tls-bootstrap`

### Secret futuros o refinamientos evidentes

- separar `bhm-env` en secretos por dominio cuando se salga del laboratorio temprano:
  - sesion web
  - MQTT/broker-facing
  - PostgreSQL
  - SMTP/webhooks
- mover la rotacion de `mosquitto_passwd` y TLS desde seed inicial a reconciliacion/control-plane u objetos `Secret` gestionados

## Almacenamiento

| Path / dominio | Estado actual | Objeto Kubernetes | Comentario |
| --- | --- | --- | --- |
| PostgreSQL data | Persistente | PVC `postgres-data` | baseline correcto |
| Mosquitto data | Persistente | PVC `mosquitto-data` | incluye DynSec y backups broker-facing |
| Mosquitto conf | Persistente | PVC `mosquitto-conf` | transicional para no romper ownership broker-local |
| Mosquitto log | Persistente | PVC `mosquitto-log` | usado por observabilidad broker-owned |
| `/nextjs/data` | Efimero | `emptyDir` | gap visible: decidir si persiste o se vacia por completo del pod web |
| logs API/nginx | Efimeros | `emptyDir` | aceptable en laboratorio temprano |

## Red y exposicion

- El runtime de laboratorio usa `Service` internos para DNS y comunicacion intra-cluster.
- La exposicion al host ya no depende del baseline Compose, sino de `kubectl port-forward` gestionado por `deploy.ps1`.
- `NodePort` sigue presente en los manifests como ayuda de laboratorio y para validacion de reachability, pero no es el contrato final recomendado.

## Estrategia de imagenes y empaquetado

- Imagen de plataforma: `localhost/bunkermtest-bunkerm:latest`
- Imagen broker: `localhost/bunkermtest-mosquitto:latest`
- `kind` con Podman consume estas imagenes mediante `image-archive` y `imagePullPolicy: Never`.
- El laboratorio ya admite tags explicitos via `deploy.ps1 -ImageTag ...` y `k8s/scripts/bootstrap-kind.ps1`, sin editar manifests a mano.

Lineamiento actual:

- mientras el laboratorio sea local y efimero, se mantiene carga de imagen local reconstruida
- para un clúster posterior, el siguiente paso evidente es versionar tags por commit/corte y abandonar `latest`
- el lineamiento operativo detallado ya queda fijado en `k8s/IMAGE_PACKAGING.md`

## Dependencias criticas que ya no bloquean

- el secreto efimero de `create_client` ya no exige volumen compartido entre web y broker
- el broker-facing real ya esta acotado al `StatefulSet` del broker
- el worker `bhm-alert-delivery` ya puede vivir como `Deployment` separado porque consume outbox PostgreSQL y no depende del filesystem del broker

## Dependencias que siguen siendo transicionales

- reconciliador broker-facing acoplado a filesystem local del broker
- `mosquitto-conf` y `mosquitto_passwd` todavia materializados como archivos broker-locales
- `/nextjs/data` del proceso web aun sin decision final de persistencia o eliminacion total

## Evolucion del reconciliador

- la verificacion tecnica del paso sidecar -> control loop -> controlador queda documentada en `k8s/RECONCILER_CONTROL_LOOP_EVOLUTION.md`
- la conclusion actual es mantener sidecar broker-owned mientras la escritura real siga dependiendo del filesystem del broker, pero con semantica ya valida para `--once`, `Job` o controlador posterior

## Compatibilidad futura con la imagen del producto de transformacion de datos

La integracion futura no deberia entrar dentro del pod broker-owned ni del pod web principal. El punto de insercion razonable sigue siendo uno de estos carriles:

- `Deployment` separado que consuma datos o eventos del control-plane
- worker/consumer adicional desacoplado via PostgreSQL o cola futura
- servicio interno con contrato HTTP o mensajeria, no volumen compartido con broker

Eso deja la compatibilidad futura en estado revisado, aunque no implementado aun.