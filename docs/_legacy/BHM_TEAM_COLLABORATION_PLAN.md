# BHM - Plan de Trabajo Colaborativo

> Proyecto: BHM (Broker Health Manager)
> Objetivo: Coordinar el trabajo paralelo de dos compañeros sin solapamientos, reduciendo conflictos de merge y evitando trabajo duplicado.
> Tipo de documento: Archivo vivo de coordinación
> Última actualización: 2026-04-20

---

## Propósito

Este documento organiza el trabajo en paralelo de dos responsables:

- Compañero A: migración a microservicios, arquitectura objetivo, evolución de persistencia y contratos entre frontend y backend.
- Compañero B: funcionalidades de producto, refinamiento funcional, historial, alertas, logs, estilos y UI.

El objetivo principal es que ambos puedan trabajar en paralelo con un criterio claro de ownership, dependencias y puntos de integración, usando este archivo como referencia compartida y como contexto para sus respectivos agentes.

---

## Estado tras el cierre de Fases 7, 8 y 9

Conclusión operativa actual:

- A ya cerró Fase 7 con baseline de hardening, resiliencia y rollback por capability documentado y validado.
- A ya cerró Fase 8 con inventario Compose -> Kubernetes, estrategia de empaquetado por tags y verificación del reconciliador como control loop broker-owned.
- A ya cerró Fase 9 para el alcance actual con un baseline `kind` ejecutable que despliega `postgres`, `mosquitto`, sidecars broker-owned, `bunkerm-platform` y `bhm-alert-delivery`, dejando `greenhouse-simulator` como herramienta externa fuera del baseline persistente.
- B puede trabajar sobre frontend, UX y refinamiento funcional usando los contratos HTTP actuales sin reabrir persistencia, control-plane ni manifests de Kubernetes.
- El principal punto todavia delicado para no pisarse es whitelist por IP: B puede trabajar UX y contrato funcional; A sigue siendo owner del enforcement broker-facing y de cualquier cambio estructural de despliegue o seguridad de plataforma.

El motivo principal de este corte es que el proyecto ya no esta solo en un baseline PostgreSQL Compose-first. Ahora existe tambien una topologia Kubernetes real, por lo que este documento debe coordinar trabajo funcional sobre contratos estabilizados y evitar que B toque por accidente el carril de plataforma que A ya materializo.

---

## Reglas transversales obligatorias

Estas reglas aplican a ambos compañeros y a cualquier agente que trabaje sobre el repositorio.

- [ ] Mantener buenas prácticas de arquitectura, diseño y revisión de cambios.
- [ ] Escribir el código en inglés.
- [ ] Escribir comentarios, documentación técnica y notas operativas en español.
- [ ] No usar emojis en código, comentarios ni mensajes técnicos persistidos, de preferencia a inicio de archivo o bloque de código.
- [ ] No reintroducir acoplamientos que contradigan el plan de migración a microservicios.
- [ ] Mantener la comunicación frontend-backend mediante APIs y contratos claros.
- [ ] Evitar cambios oportunistas en áreas ajenas sin coordinación previa.
- [ ] Actualizar este archivo cuando una tarea cambie de estado, se desbloquee o cambie de dependencia.

---

## Principio de no solapamiento

Para no pisarnos los pies, el criterio principal es este:

- El Compañero A tiene ownership sobre arquitectura, persistencia, contratos backend/frontend y topología de despliegue de la migración.
- El Compañero B tiene ownership sobre funcionalidades del producto, experiencia de usuario y refinamiento funcional.
- Si una funcionalidad depende de cambios estructurales de A, B debe evitar implementar una solución definitiva que quede obsoleta al migrar.
- Si B necesita avanzar antes de que A termine una dependencia, debe limitarse a trabajo seguro: UI desacoplada, contratos provisionales acordados, mocks locales o refinamientos que no comprometan la arquitectura final.

---

## Ownership por compañero

### Compañero A - Arquitectura y plataforma

Responsabilidades principales:

- arquitectura de microservicios
- separación de responsabilidades backend, reconciliación, persistencia y despliegue
- migración de lógica de base de datos de SQLite a PostgreSQL
- definición e implementación de APIs entre frontend y backend
- evolución Compose-first conforme al plan de microservicios
- decisiones técnicas que afecten ownership de datos y contratos de integración
- control-plane del broker y futura reconciliación

Áreas del repo donde A tiene prioridad:

- `docker-compose.dev.yml`
- `deploy.ps1`
- `config/`
- `scripts/migrate-to-postgres.py`
- `bunkerm-source/backend/app/core/`
- `bunkerm-source/backend/app/models/`
- `bunkerm-source/backend/app/routers/`
- `bunkerm-source/backend/app/services/` cuando afecte persistencia, integración o arquitectura
- `docs/adr/`
- `docs/BHM_TARGET_ARCHITECTURE.md`
- `BHM_MICROSERVICES_MIGRATION_PLAN.md`

### Compañero B - Funcionalidades de producto

Responsabilidades principales:

- whitelist por IP
- refinamiento del histórico de actividades de clientes
- historial para dashboard
- historial de topics
- alertas por correo y redes
- histórico de logs de broker y clientes
- estilos y UI
- experiencia de usuario y mejoras visuales

Áreas del repo donde B tiene prioridad:

- `bunkerm-source/frontend/`
- `bunkerm-source/backend/app/routers/` cuando el cambio sea funcional y no estructural
- `bunkerm-source/backend/app/services/` cuando el cambio sea funcional y no arquitectónico
- `bunkerm-source/backend/app/tests/` en cobertura funcional
- documentación de uso, funcionalidad y UI

---

## Reglas prácticas para evitar conflictos de merge

- [ ] No editar simultáneamente el mismo archivo sin avisar.
- [ ] Si un cambio afecta contratos API o esquema de datos, A debe anunciarlo antes de que B lo consuma.
- [ ] Si B necesita un endpoint nuevo, debe acordar primero contrato, payload y naming con A.
- [ ] Si A cambia una respuesta API, debe notificar qué frontend queda afectado y si habrá compatibilidad temporal.
- [ ] Si B toca backend, debe evitar refactors estructurales fuera de su alcance funcional.
- [ ] Si A toca frontend, debe limitarse a lo necesario para soportar contratos o integración.
- [ ] Cada PR o bloque de trabajo debe indicar explícitamente si introduce dependencia para el otro compañero.

---

## Dependencias importantes entre A y B

Esta sección es la más importante para evitar doble trabajo.

### Dependencias críticas actuales

#### 1. Migración SQLite -> PostgreSQL

Impacta a B en:

- histórico de logs de broker y clientes
- alertas si persisten configuración, historial o entregas

Regla:

- B ya puede asumir PostgreSQL como backend operativo para histórico de actividades de clientes, historial de dashboard, historia de topics y reporting técnico asociado dentro del baseline actual.
- B no debe reintroducir almacenamiento nuevo en SQLite ni cambiar seams de persistencia; si necesita nuevos datos o filtros, debe pedir contrato o endpoint sobre la base PostgreSQL ya consolidada.

#### 2. APIs frontend-backend

Impacta a B en:

- todas las funcionalidades nuevas que necesiten datos o acciones persistentes

Regla:

- B puede avanzar en UI usando contratos acordados o mocks temporales.
- La implementación definitiva del endpoint, shape de respuesta y compatibilidad de contratos la lidera A cuando afecta arquitectura o persistencia.

#### 3. Arquitectura Compose-first y separación de servicios

Impacta a B en:

- alertas por correo y redes si requieren workers o servicios auxiliares
- logs históricos si cambian fuentes de observabilidad
- cualquier funcionalidad que dependa del acceso directo a archivos del broker

Regla:

- B debe evitar implementar soluciones que dependan de shared volumes como contrato final.
- Si necesita una solución temporal, debe dejarla claramente marcada como transicional y validada con A.
- La observabilidad desacoplada ya quedó cerrada en backend; B debe consumir contratos HTTP y `source-status`, no asumir acceso a logs o archivos del broker.

#### 4. Control-plane del broker

Impacta a B en:

- whitelist por IP si se implementa como configuración de broker o política asociada
- configuraciones futuras que toquen ACLs, DynSec o parámetros efectivos del broker

Regla:

- B no debe implementar enforcement directo ni en broker ni en manifests de Kubernetes.
- `api_admin` ya tiene contrato HTTP estable para avanzar en UX y modelado funcional.
- `mqtt_clients` sigue siendo carril broker-facing de A; cualquier enforcement real sobre Mosquitto, DynSec o policy runtime debe coordinarse antes.

---

## Estado de dependencias para el Compañero B

### Puede completar ya sin bloqueo estructural

- [x] Refinamiento del histórico de actividades de clientes.
- [x] Refinar o ampliar historial para dashboard.
- [x] Refinar o ampliar historia de topics.
- [x] UX y pantallas de whitelist por IP sobre el contrato funcional actual `GET/PUT /api/v1/security/ip-whitelist` y `GET /api/v1/security/ip-whitelist/status`.
- [x] UX y administración de alertas sobre `notifications`, canales, eventos, intentos y exportaciones.
- [x] Refinamiento funcional del histórico de logs apoyándose en `clientlogs`, `reports` y endpoints de `source-status` ya desacoplados del filesystem del broker.
- [x] Diseño UI de pantallas nuevas y refinamiento visual de dashboard y vistas existentes.
- [x] Composición de tablas, filtros, navegación, estados vacíos/error/loading y tests funcionales sobre históricos ya soportados por el baseline PostgreSQL actual.
- [x] Documentación funcional y de uso para las features históricas y de reporting técnico ya estabilizadas.
- [x] Mejoras de estilos y UI donde aplique.

### Puede avanzar, pero coordinando contrato con A

- [ ] Nuevos filtros, agregaciones o exportaciones que no estén ya cubiertos por `clientlogs`, `reports`, `monitor` o `notifications`.
- [ ] UX de whitelist que requiera campos nuevos en payload, nuevos scopes o semántica adicional no incluida en `docs/BHM_IP_WHITELIST_CONTRACT.md`.
- [ ] Alertas por redes o webhooks si B necesita extender el contrato actual de canales mas alla de `email` y `webhook`.

### Debe esperar definición o implementación previa de A

- [x] La persistencia definitiva de las features históricas priorizadas en PostgreSQL ya no bloquea a B en el baseline actual.
- [ ] Enforcement final de whitelist para `mqtt_clients` si requiere tocar configuración efectiva del broker o policy broker-facing.
- [x] Contrato final de delivery para alertas por correo, redes o webhooks si implica workers, credenciales o servicios auxiliares. Queda fijado en `docs/BHM_ALERT_DELIVERY_CONTRACT.md`, con payload canónico y separación `bhm-api` -> `bhm-alert-delivery`.
- [x] Definición final de la fuente de observabilidad para el histórico de logs de broker y clientes dentro de Fase 5. Queda fijada en `docs/adr/0007-phase5-observability-pipeline.md` como pipeline broker-owned + eventos técnicos estructurados + read models persistidos.

## Endpoints y contratos ya disponibles para B

### Whitelist por IP

- `GET /api/v1/security/ip-whitelist`
- `PUT /api/v1/security/ip-whitelist`
- `GET /api/v1/security/ip-whitelist/status`
- Contrato funcional base: `docs/BHM_IP_WHITELIST_CONTRACT.md`
- Regla: B puede trabajar la UX completa del documento y del estado; A mantiene ownership del enforcement broker-facing y de cualquier traduccion a plataforma.

### Alertas y delivery

- `GET /api/v1/monitor/alerts/config`
- `PUT /api/v1/monitor/alerts/config`
- `GET /api/v1/notifications/channels`
- `POST /api/v1/notifications/channels`
- `GET /api/v1/notifications/events`
- `GET /api/v1/notifications/attempts`
- `GET /api/v1/notifications/export/events`
- `GET /api/v1/notifications/export/attempts`
- Contrato tecnico base: `docs/BHM_ALERT_DELIVERY_CONTRACT.md`
- Regla: B puede construir pantallas, formularios, filtros y exportaciones sin tocar secretos, worker ni politicas de reintento.

### Historicos y reporting tecnico

- `GET /api/v1/clientlogs/events`
- `GET /api/v1/clientlogs/connected-clients`
- `GET /api/v1/clientlogs/last-connection`
- `GET /api/v1/clientlogs/top-subscribed`
- `GET /api/v1/clientlogs/activity-summary`
- `GET /api/v1/clientlogs/source-status`
- `GET /api/v1/clientlogs/activity/{username}`
- `GET /api/v1/reports/broker/daily`
- `GET /api/v1/reports/broker/weekly`
- `GET /api/v1/reports/clients/{username}/timeline`
- `GET /api/v1/reports/incidents/clients`
- `GET /api/v1/reports/export/broker`
- `GET /api/v1/reports/export/client-activity/{username}`
- `GET /api/v1/reports/retention/status`
- Regla: B puede consumir estos endpoints para UX, filtros y estados de fuente; no debe tocar storages ni migraciones.

### Observabilidad tecnica y estados utiles para UI avanzada

- `GET /api/v1/monitor/stats/resources/source-status`
- `GET /api/v1/config/broker/source-status`
- `GET /api/v1/dynsec/default-acl/status`
- `GET /api/v1/dynsec/clients/{username}/status`
- `GET /api/v1/dynsec/roles/{role_name}/status`
- `GET /api/v1/dynsec/groups/{group_name}/status`
- `GET /api/v1/config/mosquitto-config/status`
- `GET /api/v1/config/dynsec-json/status`
- `GET /api/v1/dynsec/password-file-status`
- Regla: estos endpoints sirven para UI tecnica, debugging y estados de reconciliacion; cualquier pantalla que implique mutacion de broker debe coordinarse con A.

---

## Checklist de trabajo - Compañero A

### Arquitectura y migración

- [ ] Mantener actualizado `BHM_MICROSERVICES_MIGRATION_PLAN.md`.
- [ ] Mantener actualizada la arquitectura objetivo en `docs/BHM_TARGET_ARCHITECTURE.md`.
- [x] Definir la topología inicial Compose-first que se implementará primero.
- [x] Diseñar el recorte entre `bhm-api` y `bhm-reconciler` mediante una costura explícita de reconciliación broker-facing dentro del proceso actual.
- [x] Evaluar si conviene introducir un laboratorio local de Kubernetes durante Fase 3.
- [x] Extender el primer corte de control-plane a clientes DynSec, enable/disable y asignación de roles.
- [x] Extender el patrón de control-plane al resto de entidades principales de DynSec: delete client, roles, ACLs, grupos y memberships.
- [x] Extender el patrón de control-plane a `mosquitto.conf`, incluyendo save/reset/remove listener y estado auditable.
- [x] Extraer un reconciliador explícito broker-facing y mover allí la aplicación efectiva de `defaultACLAccess`, `roles`, `groups`, `mosquitto.conf` y cert store TLS.
- [x] Mover también el lifecycle principal de clientes DynSec al reconciliador explícito broker-facing sin persistir passwords de creación en el desired state.
- [x] Mover también las memberships `group-client` DynSec al reconciliador explícito broker-facing, persistiendo además su prioridad en el estado deseado/observado.
- [x] Introducir un adapter local de runtime broker-facing para preparar el recorte futuro entre `bhm-api` y `bhm-reconciler`.
- [x] Revisar `docker-compose.dev.yml` según la arquitectura objetivo.
- [x] Cerrar Fase 7 con baseline de rendimiento, resiliencia, churn, burst y estrategia de rollout/rollback documentada.
- [x] Materializar y validar el baseline Kubernetes en `kind` para `postgres`, `bunkerm-platform` y `mosquitto` con sidecars broker-owned.
- [x] Traducir `bhm-alert-delivery` a `Deployment` separado y endurecer probes/recursos en el laboratorio Kubernetes.
- [x] Retirar `water-plant-simulator` del baseline activo y dejar la simulación en `greenhouse-simulator` como herramienta externa MQTT diferenciada del despliegue persistente.
- [x] Documentar topologia final, portabilidad Compose -> Kubernetes y estrategia de empaquetado por tags explicitos.

### Baseline Compose-first

- [x] Crear `docs/BHM_COMPOSE_FIRST_BASELINE.md`.
- [x] Alinear aliases lógicos de servicio en `docker-compose.dev.yml`.
- [x] Validar estáticamente el compose con `podman compose ... config`.
- [x] Ejecutar validación runtime del baseline Compose-first.
- [x] Validar flujo operativo `stop/start/restart` con `deploy.ps1`.
- [x] Validar el paso `build` del ciclo de vida con `deploy.ps1`.
- [x] Validar login y navegación autenticada principal sobre el baseline local.
- [x] Resolver la mutación de `dynamic-security.json` en cada reinicio antes de cerrar el test de reinicio sin corrupción de estado.

### Persistencia y base de datos

- [x] Alinear el alcance y el orden recomendado de Fase 4 en `BHM_MICROSERVICES_MIGRATION_PLAN.md`.
- [x] Diseñar la estrategia de migración incremental de SQLite a PostgreSQL por capability o agregado.
- [x] Definir el esquema PostgreSQL inicial del bounded context de BHM, empezando por control-plane, auditoría y reconciliación.
- [x] Definir estrategia de compatibilidad temporal acotada para features ya persistidas en SQLite, evitando doble escritura estructural.
- [x] Implementar la capa de persistencia portable o repositorios de transición. El baseline actual ya opera con factorías y backends SQLAlchemy reales para control-plane, históricos y reporting técnico sobre PostgreSQL.
- [x] Ejecutar el primer corte operativo: mover a PostgreSQL el estado durable del control-plane (`broker_desired_state` y auditoría asociada).
- [x] Ejecutar el segundo corte operativo: mover broker history, topic history y client activity a PostgreSQL.
- [x] Coordinar con B qué carriles quedaron desbloqueados tras la migración: históricos principales, reporting técnico y contratos HTTP revalidados de monitor, clientlogs y reports ya pueden consumirse sin reabrir la capa de persistencia.

### APIs y contratos

- [~] Definir contratos API para features que B necesita implementar o refinar. Los contratos de históricos/reporting técnico, alertas y logs desacoplados ya tienen baseline estable; sigue pendiente principalmente whitelist.
- [~] Implementar o adaptar endpoints backend necesarios para frontend. El backend ya cubre los contratos actuales revalidados de históricos/reporting, `notifications` y logs desacoplados; pueden seguir apareciendo endpoints nuevos sobre whitelist o refinamientos funcionales menores.
- [x] Documentar breaking changes o compatibilidad temporal del cierre de Fase 4 y del baseline PostgreSQL actual.
- [x] Mantener tests de integración para endpoints afectados. La regresión ampliada cerró con `40 passed` sobre `monitor`, `clientlogs`, `reports` y la suite enfocada de Fase 4.

Estado actual ya disponible para coordinación con B:

- `GET /api/v1/dynsec/default-acl/status` expone estado deseado/aplicado/observado del primer slice de control-plane.
- `GET /api/v1/dynsec/clients/{username}/status` expone estado deseado/aplicado/observado por cliente DynSec.
- Las operaciones de create client, enable/disable y roles de cliente ya no dual-escriben el JSON desde el router.
- La aplicación broker-facing de create/enable/disable/delete/roles de cliente ya pasa por `services/broker_reconciler.py`; el password de creación se usa solo como dato efímero de reconciliación.
- Las memberships `group-client` DynSec también ya delegan `addGroupClient/removeGroupClient` al reconciliador explícito en vez de ejecutarlo desde HTTP, y su prioridad ya forma parte del estado deseado/observado normalizado.
- `GET /api/v1/dynsec/roles/{role_name}/status` y `GET /api/v1/dynsec/groups/{group_name}/status` ya exponen estado deseado/aplicado/observado por entidad.
- La gestión principal de roles, ACLs, grupos y memberships DynSec ya no muta `dynamic-security.json` directamente desde la capa HTTP.
- `GET /api/v1/config/mosquitto-config/status` ya expone estado deseado/aplicado/observado del archivo base de configuración del broker.
- `GET /api/v1/dynsec/password-file-status` ya expone estado deseado/aplicado/observado del nuevo scope `broker.mosquitto_passwd`, además de los metadatos legacy del fichero.
- `GET /api/v1/config/dynsec-json/status` ya expone estado deseado/aplicado/observado del documento DynSec completo.
- `POST /api/v1/config/mosquitto-config`, `POST /api/v1/config/reset-mosquitto-config` y `POST /api/v1/config/remove-mosquitto-listener` ya usan control-plane transicional en vez de escritura directa desde el router.
- `POST /api/v1/config/import-dynsec-json`, `POST /api/v1/config/import-acl` y `POST /api/v1/config/reset-dynsec-json` ya usan también control-plane transicional en vez de escritura directa de `dynamic-security.json` desde el router.
- `POST /api/v1/dynsec/import-password-file` ya deja dos rastros auditables: el del passwd como capability propia y el del documento DynSec proyectado desde ese import.
- `services/broker_runtime.py` y `services/broker_reconciler.py` ya definen una costura explícita broker-facing para seguir separando `bhm-api` del reconciliador futuro sin cambiar todavía de proceso.
- `services/broker_reconcile_runner.py` ya permite ejecutar reconciliaciones broker-facing por scope fuera del proceso HTTP, preparando la futura separación a un servicio/worker dedicado.
- `docker-compose.dev.yml` ya incluye `bhm-reconciler` como servicio transicional dedicado para esa costura broker-facing, ejecutando `services.broker_reconcile_daemon` fuera del proceso web.
- `bunkerm-platform` ya corre en `BROKER_RECONCILE_MODE=daemon` para los slices de `mosquitto.conf`, TLS, documento DynSec completo y `mosquitto_passwd`, esperando settlement reconciliado en lugar de aplicar esos cambios inline desde HTTP.
- `docker-compose.dev.yml` ya monta `mosquitto-data`, `mosquitto-conf` y `mosquitto-log` en solo lectura dentro de `bunkerm-platform`; la señal manual de reload también quedó movida al control-plane broker-facing.
- `docker-compose.dev.yml` ya incluye `bhm-broker-observability` como servicio interno broker-owned para servir `mosquitto.log` y `broker-resource-stats.json` por HTTP interno, evitando que `config` y `monitor` sigan leyendo esos ficheros directamente desde `bunkerm-platform`.
- La superficie activa de `config`, `monitor` y `clientlogs` ya quedó desacoplada del filesystem observacional del broker; `bunkerm-platform` ya no monta `mosquitto-log` y la deuda residual de Fase 3 pasa a validación runtime ampliada y equivalencia conceptual hacia Kubernetes.
- El placeholder `broker.bridge_bundle` ya existe como scope transicional diferido para bridges futuros, de modo que cualquier reintroducción funcional deberá alinearse al control-plane y no a writers directos o volúmenes compartidos.
- `POST /api/v1/dynsec/clients` ya puede operar también en modo daemon sin persistir passwords en SQLite: el web stagea un secreto efímero cifrado en `/nextjs/data/reconcile-secrets` y `bhm-reconciler` lo consume por `scope + version` al crear el cliente real.
- Las rutas principales de `routers/dynsec.py` para `defaultACLAccess`, enable/disable/delete de cliente, roles, grupos y memberships ya usan también espera por settlement daemon en lugar de reconciliación inline cuando el runtime está en modo daemon.
- `POST /api/v1/config/restart-mosquitto` y `POST /api/v1/dynsec/restart-mosquitto` ya delegan la recarga manual del broker al nuevo scope `broker.reload_signal`, en vez de escribir `.reload` desde la capa HTTP.
- El build local del runtime `bunkerm-platform` ya volvió a ser reproducible en Windows + Podman tras excluir `frontend/node_modules` del contexto de imagen.
- La integración real de cliente DynSec ya valida tanto el `status` auditable del control-plane como el `dynamic-security.json` efectivo del broker sobre el stack activo.
- Las rutas DynSec de `roles` y `groups` ya no ejecutan comandos broker-facing directamente desde el router; delegan al reconciliador explícito y elevan error HTTP si la reconciliación falla.
- Existe una prueba de integración ligera en `tests/test_broker_reconciler_integration.py` para validar la costura broker-facing con filesystem temporal y comandos DynSec simulados.
- Existe también una prueba de integración real en `tests/test_broker_reconciler_real_integration.py` para validar create/disable/delete de cliente contra el stack Podman activo y el broker real.
- El flujo de importación/sync de `mosquitto_passwd` ya no escribe `dynamic-security.json` directamente; ahora genera desired state del documento DynSec completo y lo delega al reconciliador explícito.
- La integración real sobre el stack Podman activo ya cubre también import/reset del documento DynSec, `import-password-file` y el sync desde `mosquitto_passwd`, no solo el lifecycle principal de clientes.
- El baseline local ya fue revalidado en runtime real tras ese recorte: `podman compose ... up -d mosquitto bunkerm bhm-reconciler` recreó el stack y `deploy.ps1 -Action smoke` cerró en `5/5 OK`.
- Fase 3 puede considerarse cerrada: el runtime HTTP ya no depende de mounts broker-facing para escrituras ni lecturas activas, y el siguiente carril estructural pasa a ser PostgreSQL.
- Fase 4 ya quedó ordenada en tres cortes para coordinación: primero control-plane durable y auditoría, después broker history/topic history/client activity, y por último read models o tablas auxiliares que sigan en SQLite.
- Mientras A no cierre un dominio en PostgreSQL, B debe evitar consolidar almacenamiento definitivo nuevo en SQLite para históricos o reporting técnico; puede seguir avanzando en UX, filtros, tablas, payloads esperados y contratos provisionales.
- A ya implementó el tramo actual de Fase 4 en código: URLs de base por dominio, engine del control-plane separable, normalización automática de dialectos async/sync para PostgreSQL, migrador seguro de `broker_desired_state` + `broker_desired_state_audit`, Alembic propio para el control-plane con adopción segura del esquema inicial y backends SQLAlchemy para históricos/reporting detrás de las factorías existentes.
- La capa HTTP y los servicios de monitor, clientlogs y reporting ya dejaron de depender de imports SQLite concretos para esos dominios; esto reduce el riesgo de merge cuando llegue la activación operativa de PostgreSQL.
- La validación enfocada del estado actual de Fase 4 ya pasó con `36 passed, 1 warning`, así que B puede seguir trabajando sobre contratos/UI de históricos y reporting sin tocar de nuevo la capa de persistencia ni asumir imports directos a SQLite.
- La validación real sobre PostgreSQL ya cubre dos carriles separados de Fase 4: control-plane durable y storages del segundo corte (`broker history`, `topic history`, `client activity`), ambos sobre el stack Compose-first.
- La validación real sobre PostgreSQL ya cubre también reporting técnico (`daily/weekly report`, `timeline`, `incidents`, `retention purge`) y existe ya un migrador operativo `scripts/migrate-history-reporting-state.py` para mover las tablas legacy de SQLite al datastore compartido de history/reporting.
- Alembic no queda como artefacto temporal de transición: pasa a ser la vía formal de versionado del esquema PostgreSQL del control-plane. Lo que sigue transicional es SQLite como origen legacy y el hecho de que reporting todavía comparte datastore/fallback con history.
- `deploy.ps1` ya detecta cuándo `.env.dev` activa PostgreSQL como datastore operativo, arranca `postgres` sin depender de `pgadmin`, usa `psycopg` como driver sync para seams/migraciones y extiende el smoke a comprobaciones de conectividad real desde `bunkerm-platform` y `bhm-reconciler`.
- La corrida runtime Compose-first sobre PostgreSQL ya quedó validada de punta a punta en Podman/Compose tras reconstruir la imagen base y recrear el stack: smoke `7/7 OK` con `bhm-api` y `bhm-reconciler` conectando al control-plane PostgreSQL.
- El baseline Compose-first sigue siendo la referencia de despliegue: la integración enfocada del control-plane con PostgreSQL se validó sobre Podman/Compose y no implica adelantar una migración a Kubernetes.

### Coordinación

- [x] Notificar a B cuando una dependencia quede desbloqueada.
- [x] Marcar en este documento qué tareas ya pueden ejecutarse sin riesgo.

---

## Checklist de trabajo - Compañero B

### Funcionalidades pendientes

- [x] Implementar o diseñar whitelist por IP.
- [ ] Refinar el histórico de actividades de clientes.
- [x] Refinar o ampliar historia de topics.
- [x] Implementar alertas por correo.
- [ ] Refinar histórico de logs de clientes.
- [x] Mejorar estilos y UI donde aplique.

### Trabajo seguro sin bloquearse

- [x] Diseñar UX y estados UI para funcionalidades dependientes de nuevas APIs.
- [x] Definir con A los contratos de datos antes de consumirlos cuando el flujo ya tenga baseline estable en Fase 4.
- [x] Evitar fijar almacenamiento definitivo propio: PostgreSQL ya quedó cerrado para los históricos priorizados y B no debe tocar la capa de persistencia.
- [x] Añadir tests funcionales y de interfaz donde no haya dependencia estructural pendiente.

### Coordinación

- [ ] Notificar a A si una feature requiere endpoint nuevo o cambio de contrato.
- [ ] Marcar en este documento qué tareas quedaron bloqueadas por dependencia estructural.
- [ ] Evitar cambios de arquitectura o persistencia fuera del alcance funcional.

---

## Matriz rápida de dependencias por feature

| Feature | Responsable principal | Dependencia de A | Puede avanzar B ya | Nota |
|--------|------------------------|------------------|--------------------|------|
| Whitelist por IP | B | Media/Alta | Si, con coordinacion | El contrato HTTP ya existe para UX y estados; el enforcement final de `mqtt_clients` sigue siendo broker-facing y owned por A |
| Histórico actividad clientes | B | Baja | Sí | PostgreSQL ya es baseline operativo para este dominio; puede cerrarse funcionalmente sin tocar persistencia |
| Historial dashboard | B | Baja | Sí | Puede cerrarse sobre contratos HTTP actuales; coordinar solo si pide endpoints o filtros nuevos |
| Historia de topics | B | Baja | Sí | PostgreSQL ya cubre el dominio; no hace falta esperar más cambios estructurales para refinamiento funcional |
| Alertas por correo | B | Media | Si | El contrato de canales, eventos, intentos y exportaciones ya existe; A mantiene worker, secretos y retry policy |
| Alertas por redes/webhooks | B | Media | Si, con coordinacion | El canal `webhook` ya existe como baseline; extensiones de contrato o canales nuevos se coordinan con A |
| Histórico logs broker | B | Media | Si | Debe apoyarse en `clientlogs`, `reports` y `source-status`; no en mounts ni lectura directa del broker |
| Histórico logs clientes | B | Media | Si | Igual que broker logs: UX libre sobre contrato actual, persistencia y observabilidad siguen owned por A |
| Estilos y UI | B | Baja | Sí | Puede avanzar salvo pantallas atadas a contratos inestables |
| PostgreSQL migration | A | N/A | No | Ownership de A |
| APIs frontend-backend | A | N/A | No, salvo mocks | Ownership de A cuando el cambio es estructural |
| Compose-first / Kubernetes topology | A | N/A | No | Ownership de A |

---

## Criterios de coordinación antes de implementar una tarea

Antes de empezar una tarea, cada compañero debe responder:

- [ ] ¿La tarea toca persistencia, contratos API o despliegue?
- [ ] ¿La tarea modifica archivos con ownership principal del otro compañero?
- [ ] ¿La implementación definitiva depende de PostgreSQL o de la nueva arquitectura?
- [ ] ¿Se puede hacer una parte segura sin bloquear la implementación final?
- [ ] ¿Es necesario acordar un contrato o una estructura de datos primero?

Si cualquiera de esas respuestas implica dependencia fuerte, la tarea debe coordinarse antes de implementarse.

---

## Convenciones de trabajo, commits y PRs

Recomendado para ambos:

- Trabajar directamente sobre `main` manteniendo cambios pequeños y frecuentes.
- Evitar acumular grandes bloques de cambios sin sincronización.
- Mantener commits pequeños y orientados a una capacidad concreta.
- Indicar en cada commit o PR interno de seguimiento:
  - area tocada
  - dependencia generada
  - si rompe o cambia contratos
  - qué debe saber el otro compañero

---

## Estrategia para mantener este archivo vivo

La estrategia acordada es trabajar directamente sobre `main`.

Esto se hace asi porque puede haber cambios implementados por uno de los compañeros que el otro necesite tener presentes inmediatamente, y se prioriza que este archivo y el estado general del proyecto reflejen siempre la situacion mas reciente.

### Flujo acordado

- Ambos compañeros trabajan sobre `main`.
- Los cambios deben ser pequeños, acotados y frecuentes.
- Si un cambio afecta coordinación, dependencias, bloqueos o desbloqueos, este archivo se actualiza en el mismo bloque de trabajo o inmediatamente después.
- Antes de empezar una tarea dependiente, revisar la última versión de este archivo.
- Si ambos necesitan tocar el mismo archivo técnico, deben coordinarse antes de editarlo.

### Ventajas de esta estrategia

- el archivo sigue realmente vivo en el estado más reciente del repositorio
- ambos ven inmediatamente cambios estructurales o funcionales del otro
- se evita olvidar sincronizaciones entre ramas

### Riesgos a controlar

- mayor riesgo de pisarse en archivos de código si no hay comunicación
- mayor necesidad de hacer commits pequeños y frecuentes
- mayor necesidad de respetar ownership y avisar antes de tocar áreas sensibles

### Regla práctica para esta modalidad

- [ ] No acumular cambios grandes sin compartirlos.
- [ ] Avisar antes de editar archivos con alta probabilidad de conflicto.
- [ ] Actualizar este archivo al cambiar una dependencia relevante.
- [ ] Priorizar commits pequeños y trazables.

---

## Uso de este archivo con agentes

### Contexto mínimo para el agente del Compañero A

- Trabajas en BHM.
- Tu ownership principal es arquitectura, migración a microservicios, PostgreSQL, Compose-first y contratos API.
- Debes evitar cambios funcionales que invadan el ownership del compañero B salvo que sean necesarios para habilitar una dependencia.
- El código va en inglés, comentarios y documentación técnica en español, y sin emojis en código.
- Antes de cambiar contratos o persistencia, revisa este archivo y actualiza dependencias si desbloqueas trabajo para B.
- Estás trabajando sobre `main`, por lo que debes extremar cuidado para no mezclar cambios innecesarios ni tocar áreas del compañero B sin coordinación.

### Contexto mínimo para el agente del Compañero B

- Trabajas en BHM.
- Tu ownership principal es funcionalidades de producto, históricos, alertas, logs, estilos y UI.
- Debes evitar refactors estructurales de arquitectura, persistencia o despliegue sin coordinación con A.
- Si una feature depende de PostgreSQL, APIs nuevas o cambios de arquitectura, debes dejar constancia aquí y evitar hacer trabajo definitivo duplicado.
- El código va en inglés, comentarios y documentación técnica en español, y sin emojis en código.
- Estás trabajando sobre `main`, por lo que debes extremar cuidado para no mezclar cambios innecesarios ni tocar áreas del compañero A sin coordinación.

---

## Bloqueos y decisiones pendientes

Usar esta sección como tablero rápido de coordinación.

### Bloqueos actuales

- [ ] Cerrar la estrategia final de enforcement para `mqtt_clients` dentro del control-plane broker-facing sin romper el contrato funcional actual.
- [x] Definir qué endpoints históricos pasarán primero a PostgreSQL.
- [x] Definir el contrato para alertas con canales externos.
- [x] Definir si el histórico de logs se alimentará de la fuente actual o de la futura capa de observabilidad.
- [ ] Reducir la dependencia operativa del laboratorio respecto a `kubectl port-forward` para exposición host-managed estable.

### Decisiones que deben tomarse con prioridad

- [x] Prioridad de features de B que necesitan soporte temprano de A. En el estado actual, la prioridad estructural pasa principalmente a enforcement final de whitelist y a cualquier extension de contrato fuera de los endpoints ya listados.
- [x] Compatibilidad temporal SQLite/PostgreSQL durante el trabajo paralelo.
- [~] Política de mocks o payloads de prueba para que B no quede bloqueado mientras A implementa backend. Ya no es bloqueo para historicos, alerts ni whitelist base; solo reaparece si B necesita campos nuevos.
- [x] Mantener cualquier laboratorio local de Kubernetes fuera del camino crítico de Fase 3; el laboratorio ya existe y debe usarse como carril de regresion de plataforma, no como espacio de cambios funcionales de B.

### Actualización operativa reciente

- A ya cerró Fase 7, Fase 8 y Fase 9 con evidencia real en el repo y en el laboratorio `kind`, de modo que la coordinacion ya no se limita a Compose-first.
- A ya dejó estabilizados para B los carriles HTTP de whitelist base, notifications, historicos, reporting tecnico y estados de observabilidad/reconciliacion.
- A ya materializó el baseline Kubernetes en `k8s/` con `postgres`, `bunkerm-platform`, `mosquitto` broker-owned con sidecars `reconciler` y `observability` y `bhm-alert-delivery`.
- A ya documentó el inventario de portabilidad, la topologia final y la estrategia de empaquetado de imagenes en `k8s/PORTABILITY_INVENTORY.md`, `k8s/FINAL_TOPOLOGY.md` y `k8s/IMAGE_PACKAGING.md`.
- A ya revalidó en Kubernetes el reconciliador con `--once --scope all`, cerrando con `RECONCILE_ONCE_OK`, y dejó al simulador externo conectado al broker interno por MQTT sin shared volumes.
- A ya dejó como deuda visible de plataforma la publicacion host-managed por `kubectl port-forward`; B no debe intentar resolver eso desde frontend ni desde manifests.

- A ya movió `defaultACLAccess` y el lifecycle básico de clientes DynSec al patrón de estado deseado + reconciliación.
- A ya movió también roles, ACLs, grupos y memberships DynSec al mismo patrón transicional.
- A ya movió también el archivo base `mosquitto.conf` al mismo patrón transicional para las operaciones principales de configuración.
- A ya introdujo un reconciliador explícito broker-facing y empezó a sacar del router la aplicación efectiva del broker para `roles` y `groups`.
- A ya movió también el lifecycle principal de clientes DynSec a ese reconciliador explícito, incluyendo `create` con password efímero no persistido y rollback básico sobre fallos de escritura del JSON.
- A ya movió además las memberships `group-client` al mismo reconciliador explícito, con prioridad persistida en el estado deseado/observado y reconciliación de drift cuando cambia.
- A ya dejó validadas tanto una integración ligera como una integración real sobre esa costura broker-facing, y además recuperó la reconstrucción reproducible del runtime local sobre Podman para seguir iterando Fase 3 sin depender de un stack viejo.
- A ya movió también import/reset del documento DynSec y el sync desde `mosquitto_passwd` al mismo patrón transicional, cerrando la escritura directa activa de `dynamic-security.json` desde la superficie HTTP del producto.
- A ya dejó validadas esas rutas también sobre el runtime real reconstruido, con restauración automática del documento DynSec y del `mosquitto_passwd` para no contaminar el stack activo.
- A ya movió además el propio `mosquitto_passwd` al control-plane transicional, con rollback básico y estado auditable separado del documento DynSec.
- A ya dejó una costura ejecutable por CLI para reconciliar scopes broker-facing sin depender del router HTTP como punto de aplicación efectiva.
- A ya materializó esa costura en Compose como `bhm-reconciler`, todavía transicional pero ya separado del proceso web como loop broker-facing dedicado.
- A ya amplió la integración real para cubrir también el import publicado de `mosquitto_passwd` contra el stack Podman activo.
- A ya hizo el primer recorte de ownership real sobre el filesystem del broker: `bunkerm-platform` quedó sin permisos de escritura sobre `/etc/mosquitto` y `/var/log/mosquitto` para los slices ya daemonizados.
- A ya eliminó también el bloqueo principal de `create_client` para modo daemon mediante un handoff efímero cifrado fuera de la base transicional y fuera del filesystem del broker.
- A ya cerró además el siguiente slice activo sobre `mosquitto-data`: el runtime HTTP dejó de escribir `.reload` y `bunkerm-platform` quedó completamente en solo lectura sobre los mounts broker-facing del baseline.
- A ya retiró también las superficies legacy ejecutables de `aws_bridge.py`, `azure_bridge.py`, `app/aws-bridge/main.py`, `app/azure-bridge/main.py` y `app/dynsec/main.py`; ya no quedan writers broker-facing alternativos en esos caminos históricos.
- A ya auditó también el mount `mosquitto-log`: sigue siendo necesario por `clientlogs`, por `GET /api/v1/config/broker` y por `broker-resource-stats.json`, así que el siguiente recorte no era quitar el volumen sino volver esa dependencia explícita y degradable.
- A ya hizo ese corte preparatorio en `clientlogs`: el tail del log puede deshabilitarse, la ausencia del fichero ya no se trata como supuesto implícito de arranque y existe un endpoint de estado de fuentes para debugging operativo.
- A ya cerró el remate pendiente de Fase 3: `bunkerm-platform` quedó sin mounts broker-facing sobre logs, data y config; esas lecturas viven ahora en `bhm-broker-observability` por HTTP interno.
- A ya dejó definida la secuencia recomendada de Fase 4: primero control-plane durable y auditoría en PostgreSQL, después históricos principales (`broker history`, `topic history`, `client activity`) y por último read models auxiliares.
- Durante Fase 4, la regla de compatibilidad temporal queda así: no habrá doble escritura generalizada SQLite/PostgreSQL; cada dominio debe tener un único writer y, si hace falta transición, se resolverá con migración de datos y lecturas/imports acotadas.
- A ya dejó además un seam explícito para históricos y reporting, de modo que el siguiente cambio estructural esperado será sustituir el backend de esos seams y no volver a tocar contratos HTTP por el simple hecho de cambiar de SQLite a PostgreSQL.
- B ya no debe considerar AWS/Azure Bridge ni el runtime standalone de DynSec como puntos reutilizables de implementación; cualquier trabajo futuro sobre esas capacidades deberá arrancar directamente desde el control-plane y no desde esos archivos legacy.
- B debe seguir considerando estos contratos como transicionales, pero ya puede apoyarse en endpoints de estado para UI técnica o debugging si los necesita.

---

## Definición de hecho compartida

Una tarea se considera realmente terminada cuando:

- [ ] respeta las convenciones del proyecto
- [ ] no invade ownership ajeno sin coordinación
- [ ] incluye validación o tests razonables si aplica
- [ ] actualiza documentación si cambia el comportamiento
- [ ] deja claro si habilita, bloquea o modifica trabajo del otro compañero

---

## Notas finales

La regla más importante de este documento es simple: B no debe cerrar soluciones definitivas en áreas cuya base estructural aún depende de A, y A debe exponer cuanto antes contratos y decisiones suficientes para que B no quede bloqueado innecesariamente.

Este archivo debe mantenerse vivo. Si cambia una dependencia, cambia el estado de una tarea o se redefine un ownership, se actualiza aquí antes de seguir acumulando trabajo paralelo.