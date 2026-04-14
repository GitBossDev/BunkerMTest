# BHM - Compose-First Baseline

> Estado: Base operativa de Fase 2
> Fecha: 2026-04-14
> Objetivo: Aterrizar decisiones de Compose-first compatibles con una futura migracion a Kubernetes sin romper el stack actual.

---

## Proposito

Este documento define el baseline operativo de BHM para la Fase 2 del plan de microservicios.

No introduce aun la separacion completa de servicios objetivo, pero fija decisiones de transicion que permiten evolucionar el `docker-compose.dev.yml` sin consolidar atajos incompatibles con Kubernetes.

---

## Objetivos de esta base

- mantener el stack actual operativo
- preparar nombres logicos de servicio estables
- documentar roles transicionales por servicio
- revisar healthchecks y orden de arranque actuales
- dejar claro que PostgreSQL ya forma parte del baseline objetivo, aunque la adopcion funcional sea progresiva
- evitar nuevas dependencias de shared volumes como contrato arquitectonico

---

## Estado actual del baseline

La topologia actual sigue siendo transicional:

- `bunkerm` actua como plataforma consolidada y contiene UI + API
- `mosquitto` sigue separado y mantiene ciclo de vida propio
- `postgres` existe ya en Compose, aunque la aplicacion todavia no lo usa como datastore principal
- `pgadmin` sigue siendo utilitario opcional

Esta topologia sigue siendo valida para Fase 2 siempre que se trate como paso de transicion y no como arquitectura final.

---

## Decisiones operativas de Fase 2

### 1. Nombres logicos estables para futura separacion

Se introducen aliases de red para desacoplar el nombre tecnico actual del nombre logico futuro.

Mapeo acordado:

- `postgres` -> alias `bhm-postgres`
- `mosquitto` -> alias `bhm-broker`
- `bunkerm` -> aliases `bhm-platform`, `bhm-api`, `bhm-web`

Motivo:

- permite referenciar servicios con nombres mas cercanos a la arquitectura objetivo
- reduce el coste de cambio cuando se separen procesos o contenedores despues
- es compatible con una futura traduccion a nombres de Service en Kubernetes

### 2. Consolidacion temporal permitida de UI + API

`bunkerm` puede seguir agrupando `bhm-web` y `bhm-api` de manera temporal.

Condicion:

- esta consolidacion no debe usarse para justificar acceso directo a base de datos desde frontend ni ownership impropio sobre el broker.

### 3. PostgreSQL deja de considerarse solo herramienta auxiliar en el baseline objetivo

Aunque el consumo funcional todavia sea progresivo, PostgreSQL ya debe considerarse parte del baseline Compose-first de BHM.

Consecuencia:

- toda nueva decision de persistencia debe evaluarse pensando en PostgreSQL como destino principal.

### 4. El broker mantiene ciclo de vida independiente

Mosquitto sigue siendo un servicio separado con puertos y persistencia propios.

Condicion:

- no deben añadirse nuevas dependencias de control basadas en filesystem compartido.

### 5. Healthchecks y startup order revisados

Estado revisado:

- `postgres` dispone de healthcheck por `pg_isready`
- `mosquitto` dispone de healthcheck por socket TCP
- `bunkerm` dispone de healthcheck HTTP sobre `/api/monitor/health`
- `bunkerm` ya depende de `mosquitto` healthy

Decisiones:

- no forzar dependencia de `bunkerm` hacia `postgres` hasta que exista uso real obligatorio
- cuando `bhm-api` dependa funcionalmente de PostgreSQL, esa dependencia debe hacerse explicita en Compose
- el healthcheck de la plataforma debe usar una ruta realmente publica del stack y no una ruta interceptada por middleware de autenticacion

### 6. Persistencia y volumes

Se mantienen los volumes actuales porque el runtime aun los necesita.

Condicion:

- no se deben crear nuevos shared volumes de control entre backend y broker
- los volumes actuales se consideran deuda tecnica conocida de transicion hacia Fase 3

### 7. Validacion runtime ejecutada

Validaciones realizadas sobre el stack actual:

- `podman compose --env-file .env.dev -f docker-compose.dev.yml up -d` aplico la configuracion sin errores
- `bunkerm-mosquitto` quedo `healthy`
- `bunkerm-platform` paso a `healthy` despues de corregir el healthcheck hacia `/api/monitor/health`
- `GET /api/monitor/health` respondio `200 OK`
- `GET /api/auth/me` respondio `401 Unauthorized`, manteniendo el comportamiento esperado para rutas protegidas
- el alias `bhm-broker` resolvio correctamente desde `bunkerm-platform`
- `deploy.ps1 -Action stop`, `start` y `restart` ejecutaron correctamente el ciclo operativo del stack
- `deploy.ps1 -Action build` construyo correctamente las imagenes `bunkermtest-mosquitto:latest` y `bunkermtest-bunkerm:latest`
- `deploy.ps1 -Action smoke` termino en `5/5 OK` tras endurecer el check autenticado de DynSec
- `GET /login` respondio `200 OK` y sirvio la pantalla de autenticacion
- `POST /api/auth/login` dejo cookie de sesion reutilizable en el baseline local tras ajustar la politica `Secure` al esquema de `FRONTEND_URL`
- `GET /api/auth/me` respondio `200 OK` con sesion autenticada y `GET /dashboard` devolvio contenido autenticado
- la exposicion de puertos observada en runtime quedo limitada a `2000/tcp` para plataforma y `1900/tcp`, `9001/tcp` para broker
- dos reinicios controlados mantuvieron estable el hash de `dynamic-security.json`
- el broker registro `Credentials already synchronized for admin`, confirmando sincronizacion idempotente del entrypoint

Conclusiones:

- el baseline Compose-first queda validado a nivel runtime para la topologia actual
- el ajuste de healthcheck corrige una incompatibilidad real entre backend, nginx y middleware frontend
- la siguiente iteracion de Fase 2 debe centrarse en reducir dependencias de filesystem compartido y definir el primer recorte entre `bhm-api` y `bhm-reconciler`

Hallazgos pendientes antes de cerrar completamente la fase:

- el backend principal sigue dependiendo de acceso directo a `dynamic-security.json`, `mosquitto.conf` y logs compartidos; eso queda como deuda estructural para Fase 3

---

## Compatibilidad futura con Kubernetes

Estas decisiones se consideran compatibles con una migracion futura:

- aliases de red como aproximacion a nombres logicos de servicio
- healthchecks por servicio y no por proceso externo improvisado
- broker con ciclo de vida separado
- PostgreSQL con volumen propio y responsabilidad clara
- consolidacion temporal de `bhm-web` y `bhm-api` solo como paso de transicion

Estas decisiones no deben adoptarse a partir de ahora:

- nuevos shared volumes de control
- nuevas escrituras directas desde la plataforma al filesystem del broker como patron aceptado
- nuevas features persistidas solo en SQLite si su destino natural sera PostgreSQL

---

## Salida esperada de esta base

Con esta base de Fase 2 ya se puede:

- seguir trabajando sobre el stack actual sin romperlo
- preparar contratos y nombres lógicos para la separación futura
- empezar el recorte entre `bhm-api` y `bhm-reconciler`
- diseñar la migración de persistencia a PostgreSQL con un baseline Compose coherente

El siguiente paso lógico después de esta base es decidir el primer recorte técnico real del runtime actual.