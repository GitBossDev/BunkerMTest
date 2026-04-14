# BHM - Arquitectura Objetivo

> Estado: Borrador de trabajo para Fase 1
> Fecha: 2026-04-14
> Alcance inmediato: Arquitectura objetivo y traduccion operativa a Docker/Podman Compose

---

## Proposito

Este documento define la arquitectura objetivo de BHM para la Fase 1 de la migracion, separando el producto de gestion tecnica del broker de otros dominios y aterrizando esa arquitectura a una topologia Compose-first.

Su objetivo no es describir el estado actual, sino el estado deseado que guiara las siguientes fases del plan.

---

## Definicion formal del producto

BHM es el producto responsable de la gestion tecnica y operativa del broker MQTT.

Su responsabilidad principal es ofrecer una plataforma segura y auditable para:

- gestionar configuracion del broker
- gestionar clientes MQTT, DynSec, roles, grupos y ACLs
- observar salud y estado operativo del broker
- mantener auditoria y reporting tecnico de la plataforma
- exponer contratos tecnicos para integracion con otros productos

BHM no es el producto de reporting de negocio ni el producto de transformacion de datos. Esos dominios viven fuera de BHM y se integran con el a traves de APIs o eventos.

---

## Bounded contexts

### 1. Broker Management

Responsabilidad:

- configuracion deseada del broker
- listeners, TLS, bridges y parametros operativos
- solicitudes de cambio y validacion previa
- reconciliacion de configuracion hacia el broker

Datos propios:

- broker desired state
- broker generated state
- broker applied state
- broker observed state
- historial de cambios y rollback metadata

### 2. Identity and Access for MQTT

Responsabilidad:

- clientes MQTT
- credenciales MQTT administradas por la plataforma
- roles, grupos y ACLs
- politicas asociadas a DynSec

Datos propios:

- mqtt clients
- mqtt roles
- mqtt groups
- mqtt acl policies
- audit trail de cambios de acceso

### 3. Technical Observability

Responsabilidad:

- estado operativo del broker
- eventos tecnicos de clientes
- incidentes tecnicos
- metricas de runtime
- reporting tecnico propio de BHM

Datos propios:

- broker health metrics
- client activity timeline
- incidents
- technical reports
- retention metadata

### 4. Platform Management API

Responsabilidad:

- API consumida por frontend y otras integraciones tecnicas
- autenticacion y autorizacion de la plataforma
- orquestacion de casos de uso de gestion
- contratos API versionados

Datos propios:

- usuarios de plataforma
- sesiones o credenciales de gestion
- audit trail de acciones administrativas

### 5. External Reporting and Data Transformation Product

Responsabilidad:

- reporting de negocio
- transformacion avanzada de datos
- analitica transversal de uno o mas brokers
- procesamiento ajeno al ownership tecnico de BHM

Restriccion:

- no accede directamente a la base de datos interna de BHM
- consume datos solo por APIs o eventos publicados por BHM

---

## Ownership de datos

| Dominio | Owner | Persistencia | Exposicion externa |
|--------|-------|--------------|--------------------|
| Configuracion deseada del broker | BHM | PostgreSQL BHM | API y eventos tecnicos |
| Estado aplicado/observado del broker | BHM | PostgreSQL BHM | API y eventos tecnicos |
| Clientes MQTT, roles, grupos, ACLs | BHM | PostgreSQL BHM | API tecnica |
| Reporting tecnico e incidentes | BHM | PostgreSQL BHM | API tecnica |
| Reporting de negocio | Producto externo | Persistencia propia | Fuera de BHM |
| Transformacion avanzada de datos | Producto externo | Persistencia propia | Fuera de BHM |

---

## Contratos de integracion entre productos

### Contratos API iniciales

- API de estado del broker
- API de incidentes tecnicos
- API de reporting tecnico
- API de eventos o timeline por cliente MQTT
- API de configuraciones aplicadas y auditoria

### Contratos de eventos futuros

- broker degraded
- broker recovered
- config change requested
- config applied
- config drift detected
- mqtt auth failure
- mqtt reconnect loop detected
- client connected
- client disconnected

### Reglas de integracion

- No hay lectura directa de tablas entre productos.
- No hay lectura directa de archivos internos del broker desde productos externos.
- Los contratos deben versionarse.
- La exposicion inicial puede ser solo HTTP mientras la plataforma madura.

---

## Servicios objetivo

La arquitectura objetivo para Compose-first queda compuesta por los siguientes servicios.

### 1. `bhm-web`

Responsabilidad:

- servir la interfaz web
- consumir la API de gestion
- no acceder directamente a la base de datos

Notas:

- puede seguir estando integrado con nginx o evolucionar a separacion posterior si conviene

### 2. `bhm-api`

Responsabilidad:

- exponer la API principal de gestion
- aplicar reglas de autenticacion y autorizacion
- registrar solicitudes de cambio
- consultar estado tecnico y reporting operativo

### 3. `bhm-reconciler`

Responsabilidad:

- consumir el estado deseado persistido
- generar configuracion efectiva del broker
- aplicar cambios al broker segun la estrategia permitida por el entorno
- detectar drift
- registrar estado aplicado y observado

Estado actual del primer corte:

- el primer slice real de este rol ya empezo dentro del backend unificado para `defaultACLAccess` de DynSec
- el endpoint de gestion ya no dual-escribe directamente ese caso; primero persiste estado deseado y luego delega la reconciliacion al servicio de control-plane
- este primer corte sigue conviviendo en el mismo proceso que `bhm-api`, pero marca la separacion semantica que luego debe extraerse a un servicio dedicado

### 4. `bhm-postgres`

Responsabilidad:

- persistencia principal de BHM

### 5. `bunkerm-mosquitto`

Responsabilidad:

- seguir siendo el broker MQTT gestionado
- mantener un ciclo de vida independiente de la plataforma de gestion

### 6. `bhm-observability-collector` (opcional en Compose-first, recomendado como siguiente paso)

Responsabilidad:

- desacoplar la captura tecnica de logs, eventos o metricas
- alimentar reporting tecnico e incidentes sin `tail -f` desde `bhm-api`

---

## Topologia objetivo Compose-first

```
External users / systems
        |
        | HTTP/HTTPS
        v
  +-------------------+
  |      bhm-web      |
  +---------+---------+
            |
            | internal HTTP API
            v
  +-------------------+        +----------------------+
  |      bhm-api      |<------>|     bhm-postgres     |
  +---------+---------+        +----------------------+
            |
            | desired state / audit / read models
            v
  +-------------------+
  |   bhm-reconciler  |
  +---------+---------+
            |
            | broker apply / observe
            v
  +-------------------+
  | bunkerm-mosquitto |
  +-------------------+

Optional path:

  +---------------------------+
  | bhm-observability-collector |
  +---------------+-----------+
                  |
                  v
         technical events / logs / metrics
```

---

## Conversion de la arquitectura objetivo a Compose-first

### Principios de conversion

- Compose se usa como plataforma de despliegue inicial.
- Cada servicio debe tener responsabilidad unica y ownership claro.
- Los volumes compartidos no deben seguir usandose como mecanismo primario de control.
- PostgreSQL entra como datastore principal de BHM tan pronto como sea viable en la fase correspondiente.

### Mapeo de servicios a Compose

| Servicio objetivo | Implementacion inicial en Compose | Notas |
|------------------|-----------------------------------|-------|
| `bhm-web` | Puede seguir integrado temporalmente con `bhm-api` dentro de `bunkerm-platform` o separarse despues | En Compose-first se permite consolidacion temporal si no rompe ownership ni contratos |
| `bhm-api` | Evolucion del backend actual | Debe dejar de escribir directamente archivos del broker |
| `bhm-reconciler` | Nuevo servicio o proceso dedicado | Recomendado separarlo del API para marcar ownership operacional |
| `bhm-postgres` | Servicio `postgres` del compose | Pasara de opcional a componente central de BHM |
| `bunkerm-mosquitto` | Se mantiene | Su ciclo de vida sigue desacoplado de la plataforma |
| `bhm-observability-collector` | Servicio adicional posterior | Puede empezar como sidecar o collector simple |

### Redes

- Red interna unica en Compose para comunicacion privada entre servicios.
- Exposicion publica solo de los puntos de entrada necesarios.
- El broker puede seguir exponiendo MQTT al exterior.

### Persistencia

- PostgreSQL debe tener volumen propio y ownership exclusivo de sus datos.
- El broker mantiene su persistencia propia.
- BHM no debe depender de mounts compartidos con el broker para funcionar.

Nota de transicion ya implementada:

- mientras PostgreSQL aun no es el datastore operativo del control-plane, el primer slice de estado deseado usa persistencia transicional en SQLite mediante la tabla `broker_desired_state`
- esto no cambia el objetivo final de mover el ownership durable del control-plane a PostgreSQL en la fase correspondiente

### Configuracion y secretos

- Variables de entorno por servicio, limitadas a su responsabilidad.
- Secretos preparados para evolucion posterior a mecanismos mas robustos en Kubernetes.
- Evitar defaults inseguros como contrato final de arquitectura.

### Healthchecks y orden de arranque

- `bhm-api` depende de disponibilidad de PostgreSQL.
- `bhm-reconciler` depende de PostgreSQL y de conectividad hacia el broker.
- `bhm-web` depende de disponibilidad de `bhm-api`.
- El broker no debe depender del arranque del API para mantener conexiones MQTT.

---

## Acoplamientos actuales a eliminar

- shared volumes entre backend y broker para `mosquitto.conf`
- shared volumes entre backend y broker para `dynamic-security.json`
- lectura directa de logs del broker desde el backend via `tail -f`
- rutas hardcodeadas que asumen ownership compartido del filesystem del broker
- SQLite como soporte principal de estado durable para la nueva arquitectura objetivo

---

## Decisiones de transicion permitidas en Compose-first

Estas decisiones se permiten como paso intermedio mientras no contradigan la arquitectura objetivo:

- mantener frontend y API dentro de una misma imagen o contenedor si el contrato sigue siendo API-only
- mantener `bunkerm-mosquitto` como nombre tecnico del broker mientras no exista renombre operativo controlado
- mantener `postgres` como nombre de servicio de Compose aunque el dominio sea BHM
- alojar el primer slice de reconciliacion dentro del backend unificado mientras se define y extrae `bhm-reconciler` como proceso o servicio independiente

Estas decisiones no se permiten como estado final:

- seguir usando escritura cruzada como mecanismo primario de aplicacion de cambios
- seguir usando shared volumes de control como contrato arquitectonico
- seguir modelando PostgreSQL como herramienta opcional en la arquitectura objetivo

---

## Entregables de Fase 1 cubiertos por este documento

- definicion formal de BHM como producto de gestion del broker
- bounded contexts principales
- ownership de datos por producto
- contratos de integracion iniciales
- servicios objetivo
- topologia objetivo Compose-first
- lista de acoplamientos actuales a eliminar

---

## Salida esperada hacia Fase 2

Al cerrar Fase 1, el equipo debe poder:

- decidir la topologia inicial de Compose sin ambiguedad de responsabilidades
- identificar que servicios nuevos deben aparecer primero
- empezar a mover el backend actual hacia `bhm-api` y `bhm-reconciler`
- convertir `postgres` en componente estructural de BHM
- planificar la eliminacion progresiva de shared volumes de control