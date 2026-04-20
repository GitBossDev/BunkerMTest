# BHM - Plan de Migración a Microservicios

> **Proyecto**: BHM (Broker Health Manager)
> **Objetivo**: Migrar la solución actual a una arquitectura de microservicios, operativa primero sobre Docker/Podman Compose y ya validada en un baseline Kubernetes de laboratorio coherente con la arquitectura objetivo.
> **Última actualización**: 2026-04-20

---

## Propósito

Este documento define las fases de trabajo, el orden recomendado de ejecución y el checklist operativo para migrar BHM hacia una arquitectura más desacoplada, portable y mantenible.

El objetivo inmediato fue estabilizar primero Docker/Podman Compose con límites claros entre servicios. Ese objetivo ya quedó cumplido y, tras la revisión general actual, el plan también deja registrado un baseline Kubernetes ejecutado y validado en `kind`, sin perder la trazabilidad de la secuencia Compose-first que permitió llegar a ese punto.

## Estado general tras la revisión actual

- [x] Las Fases 0 a 9 ya tienen evidencia operativa en el repositorio y las Fases 7, 8 y 9 quedaron cerradas con validación real.
- [x] Compose-first sigue siendo la base conceptual del plan, pero ya no es el único runtime validado: existe laboratorio Kubernetes funcional en `k8s/`.
- [x] La migración a Kubernetes dejó de ser solo una intención futura y pasó a tener topología mínima ejecutable con `postgres`, `mosquitto`, sidecars broker-owned, `bunkerm-platform`, `bhm-alert-delivery` y `water-plant-simulator`.
- [x] El principal gap operativo que sigue visible en el laboratorio es la publicación host-managed por `kubectl port-forward`; no bloquea la arquitectura ni el cierre de fase porque la validación final se hizo directamente sobre el clúster.

---

## Reglas transversales

Estas reglas aplican a todas las fases del plan.

- [ ] Mantener convenciones y buenas prácticas de arquitectura, código y despliegue.
- [ ] Escribir el código en inglés.
- [ ] Escribir comentarios, documentación técnica y notas operativas en español.
- [ ] Evitar soluciones temporales que vuelvan a acoplar el backend con el filesystem interno del broker.
- [ ] Mantener la comunicación frontend-backend únicamente vía APIs.
- [ ] Diseñar cada cambio de Docker/Podman Compose con una ruta clara de evolución a Kubernetes.
- [ ] Mantener criterios de rollback, smoke tests y validación técnica por fase.
- [ ] No romper las funcionalidades existentes mientras la migración sea incremental.

## ADRs base

Los ADRs definidos para iniciar la migración se encuentran en `docs/adr/`.

- [x] ADR-0001 - Identidad del producto y bounded contexts.
- [x] ADR-0002 - Compose-first con portabilidad a Kubernetes.
- [x] ADR-0003 - Control-plane del broker basado en estado deseado y reconciliación.
- [x] ADR-0004 - PostgreSQL separado por bounded context para BHM.
- [x] ADR-0005 - Topología de servicios objetivo para Compose-first.
- [x] ADR-0007 - Pipeline de observabilidad técnica para Fase 5.
- [x] ADR-0008 - Modelo de identidades y secretos para Fase 6.
- [x] ADR-0009 - Ownership y modelo final de whitelist por IP para Fase 6.

---

## Principios de diseño

- [ ] BHM es el producto de gestión técnica del broker, no el producto de reporting de negocio.
- [ ] El backend de gestión no debe escribir directamente archivos internos del contenedor del broker como mecanismo primario de operación.
- [ ] El estado durable debe vivir en servicios explícitos, principalmente PostgreSQL, no en estado local implícito del contenedor de aplicación.
- [ ] La aplicación de cambios al broker debe resolverse con un modelo de estado deseado + reconciliación.
- [ ] La solución inicial para Docker/Podman debe ser compatible conceptualmente con una implementación futura en Kubernetes.
- [ ] La observabilidad debe desacoplarse de `tail -f` y de mounts cruzados obligatorios.

---

## Orden de ejecución recomendado

| Fase | Nombre | Objetivo principal | Dependencia |
|------|--------|--------------------|-------------|
| 0 | Preparación y gobierno técnico | Alinear reglas, alcance y criterios de migración | Ninguna |
| 1 | Arquitectura objetivo y bounded contexts | Definir límites del producto y contratos | Fase 0 |
| 2 | Compose-first microservices baseline | Hacer que la topología de microservicios funcione bien en Docker/Podman | Fase 1 |
| 3 | Broker control-plane | Sustituir escritura directa por estado deseado + reconciliación | Fase 2 |
| 4 | Persistencia PostgreSQL | Mover estado operativo a PostgreSQL por bounded context | Fase 3 |
| 5 | Observabilidad y reporting técnico | Desacoplar logs, eventos y reporting operativo | Fase 4 |
| 6 | Seguridad e identidad técnica | Preparar autenticación y autorización para evolución futura | Fase 5 |
| 7 | Hardening, rendimiento y resiliencia | Consolidar comportamiento stateless y medir baseline | Fase 6 |
| 8 | Preparación para Kubernetes | Dejar lista la transición posterior a Kubernetes | Fase 7 |
| 9 | Implementación posterior en Kubernetes | Materializar un baseline Kubernetes ejecutable con el core BHM y el workload externo desacoplado | Fase 8 |

---

## Fase 0 - Preparación y gobierno técnico

**Objetivo**: Alinear el trabajo, el lenguaje común y las reglas de ejecución antes de tocar la arquitectura.

### Actividades

- [x] Confirmar que el nombre oficial del producto es BHM (Broker Health Manager) en la documentación nueva.
- [x] Identificar documentación vigente que siga describiendo el sistema con naming legado y marcarla para actualización progresiva.
- [x] Establecer el alcance del plan: microservicios sobre Docker/Podman ahora, Kubernetes después.
- [x] Definir qué componentes seguirán siendo stateful por naturaleza: broker, PostgreSQL y almacenamiento persistente explícito.
- [x] Definir qué componentes deben tender a stateless: frontend, backend de gestión, workers de reconciliación y servicios auxiliares.
- [x] Documentar las reglas transversales de código: code in English, comments in Spanish.
- [x] Acordar que toda fase debe cerrar con verificación y test aplicables.

### Inventario de identidad revisado

#### Documentación raíz ya alineada a BHM

- [x] `README.md`
- [x] `BHM_MICROSERVICES_MIGRATION_PLAN.md`
- [x] `ARCHITECTURE.md`
- [x] `ROADMAP.md`
- [x] `QUICKSTART.md`
- [x] `QUALITY_PLAN.md`
- [x] `WORK_PLAN.md`

#### Documentación marcada para actualización progresiva o conservación histórica

- [x] `bunkerm-source/README.md` - documentación upstream/base; no renombrar sin una fase controlada sobre assets, branding y referencias externas.
- [x] `bunkerm-source/SECURITY.md` - documento upstream; mantener trazabilidad histórica por ahora.
- [x] `bunkerm-source/docs/faq.md` - documentación upstream de producto base.
- [x] `bunkerm-source/ARCHITECTURE.md` - arquitectura histórica del código base integrado.
- [x] `bunkerm-source/RESTRUCTURE_PLAN.md` - documento histórico de la consolidación previa.
- [x] `water-plant-simulator/README.md` - referencia ya alineada al naming activo; conservar solo el contexto histórico que siga siendo útil.
- [x] `SQLITE_PERSISTENCE_PHASES.md` - documento técnico vigente; mantiene identificadores y rutas técnicas heredadas.

#### Identificadores técnicos que permanecen temporalmente

- [x] `bunkerm-source/`
- [x] `bunkerm-platform`
- [x] `bunkerm-mosquitto`
- [x] `bunkerm-network`
- [x] `bunkerm-*` volumes e imágenes
- [x] rutas y nombres técnicos heredados como `/nextjs/data/bunkerm.db`

### Verificaciones

- [x] El equipo comparte un único documento base de migración.
- [x] El alcance de Docker/Podman y Kubernetes posterior queda explícito.
- [x] Las convenciones de código y documentación quedan asentadas.

### Tests

- [x] Revisión documental de consistencia entre este plan y la arquitectura actual.
- [x] Revisión manual de nomenclatura para evitar seguir introduciendo el nombre anterior en documentos nuevos.

### Criterio de salida

- [x] Existe acuerdo sobre objetivos, alcance y convenciones antes de empezar la migración técnica.

---

## Fase 1 - Arquitectura objetivo y bounded contexts

**Objetivo**: Definir la arquitectura destino y separar claramente responsabilidades entre productos y servicios.

### Actividades

- [x] Definir formalmente que BHM es el producto de gestión del broker.
- [x] Definir el bounded context de BHM: configuración del broker, DynSec/ACL, estado operativo, reporting técnico, auditoría y salud del broker.
- [x] Definir el bounded context del producto externo de reporting/transformación de datos.
- [x] Documentar contratos de integración entre BHM y el otro producto vía APIs y, si aplica más adelante, eventos.
- [x] Decidir qué datos pertenecen solo a BHM y cuáles se expondrán al otro producto.
- [x] Definir los servicios iniciales de la topología Compose-first.
- [x] Identificar acoplamientos actuales que deben eliminarse: shared volumes de control, escrituras cruzadas, log tailing directo, rutas hardcodeadas.
- [x] Definir ADRs mínimos para decisiones críticas de arquitectura.

### Artefactos producidos

- [x] `docs/BHM_TARGET_ARCHITECTURE.md` como documento de arquitectura objetivo.
- [x] `docs/adr/0005-compose-first-service-topology.md` como decisión de topología de servicios para Compose-first.

### Verificaciones

- [x] Existe una definición clara de ownership de datos por producto.
- [x] Se evita el acceso directo del producto externo a la base de datos interna de BHM.
- [x] Los servicios candidatos a microservicio y sus responsabilidades están listados.

### Tests

- [x] Revisión técnica del diagrama objetivo.
- [x] Revisión de contratos API propuestos y su versionado.

### Criterio de salida

- [x] La arquitectura objetivo está documentada y sirve de referencia para las fases siguientes.

---

## Fase 2 - Compose-first microservices baseline

**Objetivo**: Tener una topología estable de microservicios sobre Docker/Podman Compose, funcional y verificable.

### Actividades

- [x] Diseñar la topología inicial de servicios desacoplados para Docker/Podman Compose.
- [x] Separar claramente frontend, backend de gestión, broker y persistencia.
- [x] Identificar si se necesita un servicio adicional de reconciliación desde esta fase o si entra en la siguiente.
- [x] Revisar variables de entorno y configuración para que cada servicio tenga responsabilidades claras.
- [x] Eliminar dependencias no necesarias entre contenedores.
- [x] Revisar healthchecks, readiness y orden de arranque.
- [x] Garantizar que la aplicación puede levantarse completa con un flujo reproducible de `build`, `start`, `stop` y `restart`.
- [x] Asegurar que la topología en Compose no introduzca decisiones incompatibles con una futura migración a Kubernetes.

### Artefactos producidos

- [x] `docs/BHM_COMPOSE_FIRST_BASELINE.md` como baseline operativo de Fase 2.
- [x] `docker-compose.dev.yml` alineado con nombres lógicos de servicio y comentarios de transición Compose-first.

### Verificaciones

- [x] `docker compose` o `podman compose` levantan todos los servicios requeridos.
- [x] Cada contenedor expone solo los puertos realmente necesarios.
- [x] El frontend funciona consumiendo exclusivamente la API.
- [x] El backend de gestión no depende de escribir directamente en archivos del broker para arrancar.

### Tests

- [x] Validación estática de Compose con `podman compose --env-file .env.dev -f docker-compose.dev.yml config`.
- [x] Smoke test de arranque completo del stack.
- [x] Smoke test de login y navegación principal.
- [x] Smoke test de endpoints críticos de gestión y monitoring.
- [x] Test de reinicio controlado de servicios sin corrupción de estado.

### Evidencia reciente

- [x] `podman compose --env-file .env.dev -f docker-compose.dev.yml up -d` recreó el stack sin errores.
- [x] `bunkerm-mosquitto` quedó `healthy` y `bunkerm-platform` pasó a `healthy` tras corregir el healthcheck hacia `/api/monitor/health`.
- [x] `GET /api/monitor/health` respondió `200 OK` en el runtime expuesto por nginx.
- [x] `GET /api/auth/me` mantuvo `401 Unauthorized`, confirmando que el ajuste del healthcheck no abrió rutas protegidas.
- [x] El alias lógico `bhm-broker` resolvió correctamente dentro del contenedor `bunkerm-platform`.
- [x] `deploy.ps1 -Action stop` y `deploy.ps1 -Action start` completaron correctamente y dejaron el stack operativo otra vez.
- [x] `deploy.ps1 -Action restart` reconstruyó el runtime y dejó `bunkerm-mosquitto` y `bunkerm-platform` en estado `healthy`.
- [x] `deploy.ps1 -Action build` construyó correctamente `bunkermtest-mosquitto:latest` y `bunkermtest-bunkerm:latest`.
- [x] `deploy.ps1 -Action start` reconstruyó el stack Compose-first usando la imagen reutilizable `bunkermtest-bunkerm:latest` para `bunkerm-platform`, `bhm-reconciler` y `bhm-broker-observability`, y el smoke automático volvió a cerrar en `5/5 OK`.
- [x] `deploy.ps1 -Action smoke` terminó en `5/5 OK` después de endurecer el check autenticado de DynSec frente a timing de arranque.
- [x] `GET /login` respondió `200 OK` y devolvió la pantalla de autenticación de Next.js.
- [x] `POST /api/auth/login` con las credenciales iniciales dejó una cookie de sesión reutilizable en `http://localhost:2000` tras ajustar la política `Secure` al esquema real de `FRONTEND_URL`.
- [x] `GET /api/auth/me` respondió `200 OK` con sesión autenticada y `GET /dashboard` devolvió contenido autenticado del dashboard.
- [x] El runtime activo expone `2000/tcp` para la plataforma y `1900/tcp`, `9001/tcp` para el broker.
- [x] Dos reinicios controlados mantuvieron estable el hash de `dynamic-security.json`, confirmando que el entrypoint del broker dejó de reescribir el archivo cuando no hay cambios efectivos de credenciales.
- [x] El broker registró `Credentials already synchronized for admin`, confirmando sincronización idempotente en arranque.
- [x] La inspección runtime confirmó que `bunkerm-platform` ya no monta `/var/log/mosquitto`, mientras que `bunkerm-broker-observability` sí mantiene ese mount en solo lectura como consumidor broker-owned.
- [x] Desde `bunkerm-platform` se validó por HTTP interno que `bhm-broker-observability` expone `source-status` disponible para `mosquitto.log` y `broker-resource-stats.json`, confirmando el nuevo camino runtime de observabilidad desacoplada del proceso web.
- [x] La validación final de runtime confirmó que `bunkerm-platform` ya no monta `/var/lib/mosquitto` ni `/etc/mosquitto`; sólo conserva mounts propios de plataforma, mientras `bhm-broker-observability` concentra `/var/log/mosquitto`, `/var/lib/mosquitto` y `/etc/mosquitto` en solo lectura.
- [x] Desde `bunkerm-platform` se validó por HTTP interno que `bhm-broker-observability` expone `source-status` operativo para `dynamic-security.json`, `mosquitto.conf`, `mosquitto_passwd` y el directorio de certificados, cerrando el último camino runtime que seguía dependiendo de mounts broker-facing en la plataforma.

### Hallazgos abiertos

- [x] La deuda original sobre arranque del backend quedó cerrada en Fase 3: el proceso web ya no necesita escribir directamente en archivos del broker para arrancar y la lectura observacional de logs/resource stats quedó desplazada a `bhm-broker-observability`; permanecen solo mounts de compatibilidad transicional en solo lectura para artefactos broker-facing aún gobernados por el control-plane.
- [x] El smoke test de `deploy.ps1` fue endurecido con reintentos en la llamada autenticada a DynSec porque el hot-patch posterior al arranque puede introducir una ventana corta de falso negativo.
- [x] La cookie de autenticación del frontend ya no fuerza `Secure` en el baseline HTTP local; se usa cookie segura automáticamente cuando `FRONTEND_URL` es `https`.

### Criterio de salida

- [x] BHM funciona correctamente como stack Compose-first y deja de depender de supuestos de despliegue monolítico.

---

## Fase 3 - Broker control-plane y aplicación de cambios

**Objetivo**: Sustituir la escritura directa sobre `mosquitto.conf`, `dynamic-security.json` y otros artefactos del broker por un flujo basado en estado deseado y reconciliación.

### Actividades

- [x] Diseñar el modelo de estado deseado para configuración del broker.
- [x] Diseñar el modelo de estado deseado para clientes, roles, grupos y ACLs.
- [x] Definir el servicio reconciliador responsable de aplicar cambios al broker dentro del proceso actual, dejando una costura explícita para su futura separación.
- [x] Separar configuración deseada, configuración generada, estado aplicado y estado observado.
- [x] Diseñar detección de drift entre el estado deseado y el estado real del broker.
- [x] Rediseñar los endpoints de gestión para que soliciten cambios en lugar de escribir archivos directamente.
- [x] Definir estrategia de aplicación de cambios en Docker/Podman Compose.
- [x] Definir equivalencia conceptual para Kubernetes, aunque la implementación llegue más adelante.
- [x] Evaluar si un laboratorio local de Kubernetes agrega valor en Fase 3 o si debe mantenerse fuera del camino crítico.
- [x] Replantear la gestión de bridges y certificados dentro del mismo modelo de reconciliación, excluyendo AWS/Azure del alcance funcional activo del producto.
- [x] Definir rollback para cambios fallidos al broker.

### Estado de avance reportable de Fase 3

- [x] Cortes implementados hasta ahora: 26 slices incrementales cerrados y validados localmente.
- [x] Modelo de estado deseado para configuración del broker: cubierto para `mosquitto.conf`, TLS, documento DynSec completo, `mosquitto_passwd`, `broker.reload_signal` y placeholder transicional `broker.bridge_bundle` para bridges futuros fuera de la superficie activa.
- [x] Modelo de estado deseado para clientes, roles, grupos y ACLs: cubierto en el baseline activo. Las entidades DynSec principales ya operan por desired state + reconciliación con estado auditable por entidad o capability.
- [x] Separación entre configuración deseada, generada, aplicada y observada: reportable. `desired`, `applied` y `observed` ya existen para las capabilities broker-facing; la dimensión `generated` queda explicitada como artefacto derivado o payload servido por el componente broker-owned cuando aplica.
- [x] Detección de drift: reportable para las capabilities del control-plane. La cobertura residual fuera de drift estricto queda acotada a observabilidad histórica (`clientlogs`) y no al núcleo de aplicación broker-facing.
- [x] Endpoints de gestión que solicitan cambios en vez de escribir al broker: cubierto para la superficie activa. `config`, `monitor` y `clientlogs` ya no dependen de lectura directa de `mosquitto.log` ni `broker-resource-stats.json` desde el proceso web principal.
- [x] Estrategia Compose-first de aplicación de cambios: avanzada y evidenciada. `bhm-reconciler` ejecuta el loop broker-facing fuera del proceso web y `bhm-broker-observability` centraliza la lectura observacional broker-owned para logs y resource stats.
- [x] Equivalencia conceptual para Kubernetes: cerrada a nivel conceptual para la salida de Fase 3. El baseline actual ya mapea config/secretos/estado deseado/observabilidad broker-owned a componentes portables y deja `bridge_bundle` como capability diferida sin bloquear la traducción posterior a Jobs, sidecars o controladores en Kubernetes.
- [x] Bridges y certificados en el modelo de reconciliación: reportable. TLS ya quedó absorbido por el control-plane y los bridges futuros tienen ahora placeholder explícito `broker.bridge_bundle` sin reactivar AWS/Azure Bridge.
- [x] Rollback por capability: reportable. Existe rollback o degradación controlada para las capabilities broker-facing activas y queda explícita la excepción de observabilidad histórica, que se mueve a Fase 5.
- [x] Deuda residual de Fase 3 cerrada. El runtime HTTP activo ya no mantiene mounts broker-facing sobre logs, data ni config; las lecturas observadas de `dynamic-security.json`, `mosquitto.conf`, `mosquitto_passwd` y certs quedaron desplazadas a `bhm-broker-observability` mediante HTTP interno broker-owned.

### Cortes restantes propuestos para cerrar Fase 3

- [x] Corte 21 implementado: `GET /api/v1/config/broker` quedó desacoplado del acceso directo a `mosquitto.log` en `bunkerm-platform` y ahora consume un servicio interno broker-owned de observabilidad.
- [x] Corte 22 implementado: `GET /api/v1/monitor/stats/resources` y su source-status ya consumen `broker-resource-stats.json` vía el mismo servicio interno broker-owned, sin lectura directa desde el proceso web principal.
- [x] Corte 23 implementado: se añadió el scope transicional `broker.bridge_bundle` para modelar bridges futuros como desired state diferido, sin reactivar AWS/Azure Bridge.
- [x] Corte 24 implementado: se documentó una matriz explícita de `desired/generated/applied/observed`, drift y rollback por capability para el baseline activo de Fase 3.
- [x] Corte 25 implementado: se cerró la validación reportable del criterio de salida de Fase 3, dejando evidencia de qué mounts broker-facing ya no son dependencia del backend principal y cuál deuda residual pasa a Fase 5.
- [x] Corte final implementado para cierre real de Fase 3: `mosquitto-data` y `mosquitto-conf` fueron retirados de `bunkerm-platform`; las lecturas activas de `dynamic-security.json`, `mosquitto.conf`, `mosquitto_passwd` y certs quedaron movidas a `bhm-broker-observability` y consumidas por HTTP interno u observed-state helpers.

### Matriz reportable de capacidades Fase 3

| Capability | Desired | Generated | Applied | Observed | Drift | Rollback/Degradación | Estado |
|------------|---------|-----------|---------|----------|-------|----------------------|--------|
| `broker.mosquitto_config` | `broker_desired_state` | contenido `mosquitto.conf` derivado | reconciliador broker-facing | parseo del fichero efectivo | Sí | backup + restore + reload | Activo |
| `broker.tls_certs` | `broker_desired_state` | archivos del cert store | reconciliador broker-facing | hash/metadata de ficheros | Sí | snapshot en memoria + restore | Activo |
| `broker.dynsec_config` | `broker_desired_state` | documento DynSec proyectado | reconciliador broker-facing | lectura normalizada del JSON efectivo | Sí | rollback broker-facing / error auditable | Activo |
| `broker.mosquitto_passwd` | `broker_desired_state` | fichero passwd derivado | reconciliador broker-facing | lectura del fichero efectivo | Sí | backup lateral + restore + reload | Activo |
| `broker.reload_signal` | `broker_desired_state` | payload de señal | reconciliador broker-facing | confirmación observada de señal | No estricto | reintento manual | Activo |
| `dynsec.client.*`, `dynsec.role.*`, `dynsec.group.*`, `dynsec.default_acl` | `broker_desired_state` | payload normalizado por entidad | reconciliador broker-facing | snapshot DynSec observado | Sí | rollback parcial / error auditable | Activo |
| `broker.bridge_bundle` | `broker_desired_state` | payload diferido documentado | no aplica aún | no aplica aún | No | no aplica | Diferido |
| `config/broker` observabilidad | no aplica | payload servido por `bhm-broker-observability` | servicio interno broker-owned | source-status HTTP | No | `503` explícito | Transicional |
| `monitor/stats/resources` observabilidad | no aplica | payload servido por `bhm-broker-observability` | servicio interno broker-owned | source-status HTTP | No | fallback-process / unavailable | Transicional |
| `clientlogs/logTail` observabilidad | no aplica | snapshot de logs servido por `bhm-broker-observability` | polling interno broker-owned | source-status HTTP | No | degradación explícita + reintento | Transicional |

### Evidencia final de cierre de Fase 3

- [x] Suite enfocada de regresión ejecutada tras el corte final: `79 passed, 4 warnings in 9.18s` sobre `test_architecture.py`, `test_config.py`, `test_dynsec.py`, `test_clientlogs.py`, `test_clientlogs_service.py` y `test_monitor.py`.
- [x] `deploy.ps1 -Action build` reconstruyó correctamente `bunkermtest-mosquitto:latest` y `bunkermtest-bunkerm:latest` con la nueva topología.
- [x] `deploy.ps1 -Action start` levantó `bunkerm-mosquitto`, `bunkerm-platform`, `bunkerm-reconciler` y `bunkerm-broker-observability`; el smoke automático volvió a cerrar en `5/5 OK`.
- [x] La inspección de mounts confirmó que `bunkerm-platform` quedó sin acceso directo a `/var/log/mosquitto`, `/var/lib/mosquitto` ni `/etc/mosquitto`, y que `bhm-broker-observability` asumió esos mounts en solo lectura.
- [x] La validación por HTTP interno confirmó disponibilidad runtime de los nuevos endpoints `source-status` para DynSec, configuración Mosquitto, passwd y certs.

- [x] El import de `dynamic-security.json` quedó endurecido con doble barrera broker-owned: el router rechaza documentos estructuralmente inválidos antes de persistir desired state y `bhm-reconciler` vuelve a validarlos antes de escribir/reiniciar, evitando que la UI pueda dejar muerto al broker con artefactos incompatibles y manteniendo el contrato portable hacia Kubernetes.

### Criterio de salida

- [x] Fase 3 queda cerrada: el control-plane broker-facing opera por desired state + reconciliación, y el runtime HTTP principal ya no depende del filesystem compartido del broker para escrituras ni lecturas activas.
- [x] Fase 4 puede iniciarse sobre un baseline Compose-first validado en runtime y con separación explícita entre plataforma web, reconciliador broker-facing y observabilidad broker-owned.

### Primer corte implementado

- [x] Se introdujo la tabla transicional `broker_desired_state` para persistir estado deseado/aplicado/observado del control-plane antes de la migración a PostgreSQL.
- [x] `PUT /api/v1/dynsec/default-acl` dejó de dual-escribir desde el router y ahora registra estado deseado antes de reconciliar.
- [x] Se implementó un primer reconciliador de aplicación para `defaultACLAccess`, encapsulado en servicio y con detección básica de drift.
- [x] Se añadió `GET /api/v1/dynsec/default-acl/status` para auditar `desired`, `applied`, `observed`, `status`, `version` y `lastError`.
- [x] El primer corte usa SQLite transicional como soporte de estado deseado; PostgreSQL sigue siendo el destino definitivo de Fase 4.

### Segundo corte implementado

- [x] `POST /api/v1/dynsec/clients` dejó de dual-escribir desde el router y ahora persiste desired state del cliente antes de reconciliar.
- [x] `PUT /api/v1/dynsec/clients/{username}/enable` y `PUT /api/v1/dynsec/clients/{username}/disable` ya aplican el patrón de desired state + reconciliación.
- [x] `POST /api/v1/dynsec/clients/{username}/roles` y `DELETE /api/v1/dynsec/clients/{username}/roles/{role_name}` ya no manipulan directamente `dynamic-security.json` desde el router.
- [x] Se añadió `GET /api/v1/dynsec/clients/{username}/status` para auditar estado deseado, aplicado y observado por cliente.
- [x] Este segundo corte sigue siendo transicional: la aplicación broker-facing del lifecycle principal de clientes ya pasa por el reconciliador explícito dentro de `bhm-api`, pero la separación a un proceso `bhm-reconciler` sigue pendiente.

### Tercer corte implementado

- [x] `DELETE /api/v1/dynsec/clients/{username}` ya no elimina directamente el cliente del JSON desde el router; ahora registra desired state borrado y reconcilia la ausencia observada.
- [x] `POST /api/v1/dynsec/roles`, `DELETE /api/v1/dynsec/roles/{role_name}` y la gestión de ACLs de rol ya usan el patrón de desired state + reconciliación.
- [x] `POST /api/v1/dynsec/groups`, `DELETE /api/v1/dynsec/groups/{group_name}`, asignación de roles y membresías de clientes a grupos ya no mutan `dynamic-security.json` directamente desde HTTP.
- [x] Se añadieron `GET /api/v1/dynsec/roles/{role_name}/status` y `GET /api/v1/dynsec/groups/{group_name}/status` para auditar `desired`, `applied`, `observed`, `status`, `version` y `lastError`.
- [x] La superficie principal de entidades DynSec ya quedó encapsulada en la capa transicional de control-plane, aunque la ejecución efectiva al broker siga ocurriendo todavía dentro de `bhm-api`.

### Cuarto corte implementado

- [x] `POST /api/v1/config/mosquitto-config` ya no escribe `mosquitto.conf` directamente desde el router; ahora registra desired state del archivo y reconcilia su contenido efectivo.
- [x] `POST /api/v1/config/reset-mosquitto-config` y `POST /api/v1/config/remove-mosquitto-listener` también pasan por la misma capa transicional de control-plane.
- [x] Se añadió `GET /api/v1/config/mosquitto-config/status` para auditar `desired`, `applied`, `observed`, `status`, `version` y `lastError` del archivo base del broker.
- [x] La reconciliación de `mosquitto.conf` ya incorpora backup previo y rollback básico cuando la escritura o la recarga fallan.
- [x] Este corte reduce otra parte del acoplamiento directo HTTP -> filesystem del broker, aunque bridges y certificados siguen pendientes del mismo patrón.

### Quinto corte implementado

- [x] `POST /api/v1/config/tls-certs/upload` ya no escribe certificados TLS directamente desde el router; ahora registra desired state del cert store y reconcilia el filesystem efectivo.
- [x] `DELETE /api/v1/config/tls-certs/{filename}` ya no elimina archivos directamente desde HTTP; ahora marca ausencia deseada y reconcilia el estado observado.
- [x] Se añadió `GET /api/v1/config/tls-certs/status` para auditar `desired`, `applied`, `observed`, `status`, `version` y `lastError` del almacén TLS del broker.
- [x] La reconciliación del cert store ya contempla drift detection por `sha256` y rollback básico en memoria sobre los archivos tocados durante la operación.
- [x] Este corte cubre los certificados TLS locales del broker y deja fuera del alcance activo los bridges AWS/Azure ya retirados de la superficie funcional del producto.

### Sexto corte implementado

- [x] Se añadió `services/broker_reconciler.py` como costura explícita para encapsular la mutación broker-facing del control-plane transicional.
- [x] `services/broker_desired_state_service.py` ahora delega en ese reconciliador la aplicación efectiva de `defaultACLAccess`, `mosquitto.conf`, cert store TLS y la mutación broker-facing de `roles` y `groups`.
- [x] Las rutas DynSec de `roles` y `groups` ya no disparan comandos broker-facing directamente desde el router; ahora solicitan desired state y elevan `500` si la reconciliación termina en `error`.
- [x] Se añadió `tests/test_broker_reconciler_integration.py` para validar integración ligera sobre la costura broker-facing del reconciliador.
- [x] Este corte sigue siendo transicional: el reconciliador explícito vive aún dentro de `bhm-api`, pero el recorte `bhm-api` -> `bhm-reconciler` ya quedó definido en código para futuras fases.

### Séptimo corte implementado

- [x] La reconciliación de clientes DynSec ahora delega en `services/broker_reconciler.py` la aplicación broker-facing de `create`, `enable`, `disable`, `delete` y diff de roles.
- [x] La reconciliación de grupos DynSec ahora delega también en esa costura la aplicación broker-facing de memberships `group-client`.
- [x] Las rutas DynSec de clientes ya no ejecutan comandos broker-facing directamente desde el router; solo registran desired state, solicitan reconciliación y elevan `500` si el estado final es `error`.
- [x] Las rutas DynSec de memberships `group-client` ya no ejecutan `addGroupClient/removeGroupClient` directamente desde el router; siguen el mismo flujo de desired state + reconciliación.
- [x] El caso sensible de `create client` quedó encapsulado sin persistir el password en `broker_desired_state`; la contraseña se usa solo como argumento efímero de reconciliación.
- [x] El reconciliador explícito añade rollback básico para cambios broker-facing de cliente cuando falla la escritura de `dynamic-security.json` después de aplicar el cambio efectivo.
- [x] Este corte sigue siendo transicional: la reconciliación de clientes continúa in-process, pero el router HTTP dejó de ser el punto de aplicación directa al broker.

### Octavo corte implementado

- [x] Se añadió `services/broker_runtime.py` como adapter local explícito del runtime broker-facing para separar la lógica de reconciliación de los detalles in-process de filesystem, locks y `mosquitto_ctrl`.
- [x] `services/broker_reconciler.py` ya consume esa costura de runtime por puerto, preparando el recorte futuro entre `bhm-api` y `bhm-reconciler` sin cambiar todavía de proceso.
- [x] La prioridad de memberships `group-client` dejó de ser solo dato efímero de aplicación: ahora forma parte del estado deseado y observado normalizado en el control-plane.
- [x] La reconciliación de memberships `group-client` ya detecta drift de prioridad y aplica `remove/add` cuando el valor efectivo cambia en el broker.
- [x] Se añadió `tests/test_broker_reconciler_real_integration.py` para validar un slice real contra el stack Compose-first activo, entrando por la superficie publicada del producto y verificando el `dynamic-security.json` del broker.

### Noveno corte implementado

- [x] `POST /api/v1/config/import-dynsec-json`, `POST /api/v1/config/import-acl` y `POST /api/v1/config/reset-dynsec-json` ya no escriben `dynamic-security.json` directamente desde el router; ahora registran desired state del documento DynSec completo y reconcilian su aplicación efectiva vía la costura broker-facing.
- [x] Se añadió `GET /api/v1/config/dynsec-json/status` para auditar `desired`, `applied`, `observed`, `status`, `version` y `lastError` del documento DynSec completo.
- [x] El flujo `dynsec/password_import.py` ya no escribe `dynamic-security.json` directamente; tras importar o sincronizar `mosquitto_passwd`, solicita un nuevo desired state del documento DynSec y delega la escritura efectiva al reconciliador explícito.
- [x] La aplicación efectiva del documento DynSec completo ya usa una señal explícita de reinicio/relectura del plugin (`.dynsec-reload`) encapsulada detrás del runtime broker-facing, igual que el resto de la costura transicional.
- [x] Se añadieron regresiones específicas para la reconciliación completa de DynSec, el status auditable del documento y el sync desde `mosquitto_passwd`.

### Décimo corte implementado

- [x] La integración real contra el stack Podman activo ya valida también `POST /api/v1/config/import-dynsec-json` y `POST /api/v1/config/reset-dynsec-json` entrando por la superficie publicada del producto y comprobando tanto el `status` auditable como el `dynamic-security.json` efectivo del broker.
- [x] La integración real contra el stack Podman activo ya valida `POST /api/v1/dynsec/sync-passwd-to-dynsec`, preparando un `mosquitto_passwd` temporal en el runtime y comprobando que el documento DynSec observado y el broker real incorporan el usuario sincronizado.
- [x] Las pruebas reales restauran después el documento DynSec y el fichero `mosquitto_passwd`, de modo que el stack activo queda limpio tras cada validación.

### Undécimo corte implementado

- [x] `mosquitto_passwd` ya forma parte del control-plane transicional como scope explícito `broker.mosquitto_passwd`, con `desired`, `applied`, `observed`, `status`, `version`, detección de drift y `lastError`.
- [x] `POST /api/v1/dynsec/import-password-file` ya no copia el archivo directamente como paso principal del router; ahora registra desired state del passwd, reconcilia su aplicación efectiva con rollback básico y luego proyecta los usuarios faltantes sobre el documento DynSec completo.
- [x] `POST /api/v1/dynsec/sync-passwd-to-dynsec` ahora deja auditado también el estado aplicado/observado del propio passwd antes de reconciliar DynSec.
- [x] `GET /api/v1/dynsec/password-file-status` ya expone metadatos legacy (`exists`, `size_bytes`, `user_count`) junto con el estado auditable del nuevo scope `broker.mosquitto_passwd`.
- [x] La costura broker-facing añade ahora aplicación efectiva de `mosquitto_passwd` con backup lateral, `chmod 0644`, señal de recarga y rollback básico si la escritura o la recarga fallan.

### Duodécimo corte implementado

- [x] Se añadió `services/broker_reconcile_runner.py` como runner CLI mínimo para reconciliar scopes broker-facing fuera del proceso HTTP (`python -m services.broker_reconcile_runner --scope ...`).
- [x] La estrategia Compose-first queda más explícita: la aplicación efectiva del broker ya no depende conceptualmente del router HTTP, sino de una costura invocable por scope que puede moverse después a un contenedor `bhm-reconciler` sin cambiar el contrato interno del control-plane.
- [x] Queda documentada la semántica transicional de rollback por capability: `mosquitto.conf` y `mosquitto_passwd` restauran contenido previo y relanzan recarga; TLS restaura snapshots de archivos; DynSec por entidad o documento completo se apoya en rollback broker-facing y/o detección de drift/estado de error si la reversión no es completa.
- [x] Queda también más clara la traducción conceptual a Kubernetes: `mosquitto.conf` se alinea con configuración tipo ConfigMap, `mosquitto_passwd` y TLS con material tipo Secret y `dynamic-security.json` con un artefacto privado reconciliado por el componente broker-facing, no por la capa HTTP.

### Decimotercer corte implementado

- [x] `docker-compose.dev.yml` ya incluye `bhm-reconciler` como servicio transicional dedicado para el loop broker-facing, reutilizando la imagen actual pero sin puertos web y con `command` específico hacia `services.broker_reconcile_daemon`.
- [x] Se añadió `services/broker_reconcile_daemon.py` para consumir de forma periódica el estado deseado pendiente/drift/error fuera del proceso HTTP.
- [x] `services/broker_reconcile_runner.py` ya resuelve también scopes dinámicos (`dynsec.default_acl`, `dynsec.client.*`, `dynsec.role.*`, `dynsec.group.*`) a partir de `broker_desired_state`, de modo que el servicio dedicado puede reconciliar trabajo real y no solo scopes fijos.
- [x] `deploy.ps1` ya reconoce también `bunkerm-reconciler` en el flujo de hot-patch backend y reinicia ese contenedor para no dejar el daemon con código desfasado durante desarrollo local.

### Decimocuarto corte implementado

- [x] La integración real contra el stack Podman activo ahora cubre también `POST /api/v1/dynsec/import-password-file`, no solo el sync desde `mosquitto_passwd`.
- [x] La validación real de ese flujo comprueba el rastro auditable del scope `broker.mosquitto_passwd`, el documento DynSec observado y el artefacto efectivo del broker tras el import.
- [x] La restauración del stack tras la prueba vuelve a dejar limpios tanto `dynamic-security.json` como `mosquitto_passwd`, manteniendo la misma disciplina de no contaminar el baseline activo.

### Decimoquinto corte implementado

- [x] Las rutas de `mosquitto.conf`, cert store TLS, import/reset del documento DynSec y `mosquitto_passwd` ya pueden operar en modo daemon broker-facing: registran el desired state y esperan el settlement reconciliado en vez de aplicar el cambio inline desde el proceso web cuando `BROKER_RECONCILE_MODE=daemon`.
- [x] `services/broker_desired_state_service.py` ahora centraliza ese patrón con espera auditable por scope/version, de modo que el router HTTP puede seguir respondiendo con estado consistente sin retomar ownership directo del filesystem del broker.
- [x] `docker-compose.dev.yml` ya arranca `bunkerm-platform` con `BROKER_RECONCILE_MODE=daemon`, `BROKER_RECONCILE_WAIT_TIMEOUT_SECONDS=12` y mounts `mosquitto-conf` y `mosquitto-log` en solo lectura.
- [x] El stack local quedó validado con runtime real: `podman compose ... up -d mosquitto bunkerm bhm-reconciler` recreó `bunkerm-platform` y `bunkerm-reconciler`, y `deploy.ps1 -Action smoke` terminó en `5/5 OK`.
- [x] El mount `mosquitto-data` sigue transicionalmente writable en `bunkerm-platform` porque el slice de `create_client` todavía depende de un password efímero no persistido en desired state y aún no puede migrarse completo al daemon sin rediseño adicional.

### Decimosexto corte implementado

- [x] Las rutas principales de entidades DynSec en `routers/dynsec.py` ya usan también el patrón daemon-aware `set desired state + wait for settlement` para `defaultACLAccess`, enable/disable/delete de cliente, roles de cliente, roles, ACLs, grupos y memberships, evitando seguir aplicando esos cambios inline desde el proceso web cuando `BROKER_RECONCILE_MODE=daemon`.
- [x] `POST /api/v1/dynsec/clients` ya resuelve el caso sensible de `create_client` sin persistir el password en `broker_desired_state`: el proceso web cifra un secreto efímero y lo stagea en `/nextjs/data/reconcile-secrets`, y el reconciliador dedicado lo consume por `scope + version` en el momento de aplicar la creación real.
- [x] El handoff efímero queda fuera del filesystem del broker y fuera de la base transicional: el password ya no necesita viajar ni en `desired`, ni en `applied`, ni en `observed`, y el artefacto staged se elimina tras una reconciliación exitosa.
- [x] Con este corte desaparece el bloqueo funcional que impedía daemonizar `create_client`; el motivo para mantener `mosquitto-data` writable en `bunkerm-platform` pasa a ser la existencia de superficies broker-facing legacy aún no recortadas por completo, no la creación principal de clientes DynSec.

### Decimoséptimo corte implementado

- [x] La auditoría de superficies activas confirmó que las escrituras directas restantes a `.reload` dentro de `routers/` ya no pertenecían a DynSec ni al config activo, sino a dos endpoints de recarga manual; las únicas escrituras directas restantes en routers quedaron acotadas a `aws_bridge.py` y `azure_bridge.py`, que no forman parte del runtime HTTP montado por `main.py`.
- [x] Se añadió el scope transicional `broker.reload_signal` al control-plane para modelar la señal manual de recarga de Mosquitto como capability broker-facing propia, aplicada por `bhm-reconciler` en vez de escribirse desde `bunkerm-platform` sobre `/var/lib/mosquitto/.reload`.
- [x] `POST /api/v1/config/restart-mosquitto` y `POST /api/v1/dynsec/restart-mosquitto` ya no escriben el marker `.reload` desde el proceso web; ahora registran desired state y esperan settlement reconciliado igual que el resto de capabilities ya daemonizadas.
- [x] `docker-compose.dev.yml` ya monta también `mosquitto-data` en solo lectura dentro de `bunkerm-platform`, de modo que el web container queda sin permisos de escritura sobre los tres mounts broker-facing del baseline (`mosquitto-data`, `mosquitto-conf`, `mosquitto-log`).

### Decimoctavo corte implementado

- [x] Las superficies legacy `routers/aws_bridge.py` y `routers/azure_bridge.py` ya no conservan lógica ejecutable de escritura directa sobre `conf.d`, certificados ni señales de recarga; quedaron convertidas en compatibilidad segura con respuesta `410 Gone` y mensaje explícito de reactivación futura solo vía control-plane.
- [x] Los microservicios standalone históricos `app/aws-bridge/main.py` y `app/azure-bridge/main.py` ya no pueden actuar como writers alternativos del broker si alguien los ejecuta por error; ambos quedaron reducidos a stubs `410 Gone` alineados con la retirada funcional de AWS/Azure Bridge.
- [x] `app/dynsec/main.py` dejó de contener un runtime legacy ejecutable con dual-write a `dynamic-security.json` y comandos directos `mosquitto_ctrl`; ahora es un stub de compatibilidad que redirige a la superficie unificada `/api/v1/dynsec`.
- [x] Se añadieron guardrails y tests específicos para evitar que estas superficies legacy vuelvan a introducir mutaciones broker-facing fuera del control-plane transicional.

### Decimonoveno corte implementado

- [x] La auditoría del mount `mosquitto-log` confirmó que sigue teniendo tres consumidores activos dentro del runtime unificado: `services/clientlogs_service.py` por `tail -f` y replay inicial, `routers/config_mosquitto.py` para `GET /api/v1/config/broker` y `services/monitor_service.py` para `broker-resource-stats.json`; por tanto, retirar hoy ese volumen del web container no sería todavía un corte limpio de Fase 3.
- [x] `services/clientlogs_service.py` ya no trata el log del broker como requisito implícito de arranque: el tail puede deshabilitarse por configuración, detecta ausencia del fichero sin quedarse en un loop ciego y publica estado operativo auditable de sus dos fuentes (`logTail`, `mqttPublish`).
- [x] `GET /api/v1/clientlogs/source-status` expone ahora el estado de esas fuentes para distinguir cuándo ClientLogs está alimentándose por tail de logs, cuándo solo por observación MQTT y cuándo el acoplamiento al mount falta o está degradado.
- [x] Este corte no elimina todavía `mosquitto-log` del baseline Compose-first porque el endpoint activo de lectura de logs y las métricas auxiliares del monitor siguen dependiendo de ese volumen; deja, eso sí, auditado y acotado el trabajo restante para la futura fase de observabilidad desacoplada.

### Vigésimo corte implementado

- [x] `GET /api/v1/config/broker` ya expone metadatos de fuente para la lectura de `mosquitto.log`, y `GET /api/v1/config/broker/source-status` deja auditado si esa dependencia compartida está disponible, deshabilitada o degradada.
- [x] `services/monitor_service.py` ya publica estado operativo de la fuente `broker-resource-stats.json`, y `GET /api/v1/monitor/stats/resources` junto con `GET /api/v1/monitor/stats/resources/source-status` distinguen entre lectura por fichero compartido, fallback local o indisponibilidad.
- [x] El cálculo de actividad derivada en `monitor/stats` ya degrada correctamente cuando el estado observado de DynSec no está disponible, evitando que la ausencia del artefacto broker-facing rompa endpoints de reporting operativo.
- [x] Este corte no elimina todavía `mosquitto-log` del baseline, pero cierra la auditoría de sus consumidores activos con contrato HTTP explícito y deja listo el siguiente recorte sobre las dos dependencias observacionales restantes.

### Vigésimo primer corte implementado

- [x] Se añadió `bhm-broker-observability` como servicio interno Compose-first, broker-owned y sin puertos públicos, para servir por HTTP interno las lecturas transicionales de `mosquitto.log`.
- [x] `GET /api/v1/config/broker` y `GET /api/v1/config/broker/source-status` ya no leen `mosquitto.log` directamente desde `bunkerm-platform`; ahora consumen `services/broker_observability_api.py` vía `broker_observability_client`.
- [x] Los guardrails de arquitectura ya protegen que este desacoplamiento no retroceda a lectura directa del fichero compartido desde el router de configuración.

### Vigésimo segundo corte implementado

- [x] `GET /api/v1/monitor/stats/resources` y `GET /api/v1/monitor/stats/resources/source-status` ya no leen `broker-resource-stats.json` directamente desde `bunkerm-platform`; ahora consumen la misma API interna broker-owned.
- [x] Cuando el servicio interno no está disponible, el monitor sigue degradando a `fallback-process` o `unavailable` con `lastError` explícito, en vez de asumir el mount como prerequisito silencioso.
- [x] Este corte deja a `config` y `monitor` fuera del ownership directo del filesystem observacional del broker, manteniendo la compatibilidad transicional del baseline Compose-first.

### Vigésimo tercer corte implementado

- [x] Se añadió el scope `broker.bridge_bundle` como placeholder de desired state para futuros bridges, con estado `deferred`, payload normalizado y status auditable.
- [x] El modelo deja explícito que la superficie AWS/Azure Bridge sigue retirada del producto activo, pero evita perder trazabilidad arquitectónica para una reintroducción posterior alineada al control-plane.

### Vigésimo cuarto corte implementado

- [x] La hoja de ruta de Fase 3 ya distingue de forma reportable qué capabilities tienen `desired`, `generated`, `applied` y `observed`, y cuáles son puramente observacionales o diferidas.
- [x] La cobertura de drift y rollback quedó consolidada en una matriz única para que el avance pueda reportarse sin depender de revisar slice por slice.

### Vigésimo quinto corte implementado

- [x] La validación final de Fase 3 deja explícito que `bunkerm-platform` ya no necesita leer directamente `mosquitto.log` ni `broker-resource-stats.json`; esas lecturas viven ahora detrás de `bhm-broker-observability`.
- [x] Los mounts broker-facing que siguen presentes en `bunkerm-platform` quedan acotados a compatibilidad transicional: `mosquitto-data` y `mosquitto-conf` en solo lectura para observación/control-plane ya recortado, y `mosquitto-log` pendiente solo por la funcionalidad histórica de `clientlogs`, que pasa a Fase 5 de observabilidad y reporting técnico.
- [x] Con esto, la deuda residual deja de ser un problema del núcleo de gestión broker-facing y queda explicitada como trabajo posterior de observabilidad desacoplada.

### Vigésimo sexto corte implementado

- [x] `services/clientlogs_service.py` ya no usa `tail -f` ni `grep` locales sobre `mosquitto.log`; ahora consume snapshots vía `broker_observability_client.fetch_broker_logs_sync()` y mantiene `source-status` auditable con degradación explícita y reintentos.
- [x] `services/monitor_service.py` dejó también de leer `broker-resource-stats.json` por filesystem local para los snapshots históricos persistidos; ese path ya consume el servicio interno `bhm-broker-observability` tanto en la capa HTTP como en la capa de storage histórico.
- [x] `docker-compose.dev.yml` ya no monta `mosquitto-log` dentro de `bunkerm-platform`; ese volumen queda acotado al broker y al servicio interno broker-owned de observabilidad.
- [x] Con este corte, el proceso web principal ya no mantiene accesos directos activos ni a `mosquitto.log` ni a `broker-resource-stats.json`, cerrando la deuda ejecutable detectada en la revisión general de los cortes de Fase 3.
- [x] La validación runtime ampliada sobre el stack activo confirmó además que `bunkerm-platform` consume `source-status` de logs y resource stats por HTTP interno contra `bhm-broker-observability`, y que el mount `/var/log/mosquitto` ya no existe en el contenedor web.
- [x] La revisión adicional del punto pendiente confirmó, sin embargo, que `bunkerm-platform` todavía necesita `mosquitto-data` y `mosquitto-conf` en solo lectura para rutas activas que leen `dynamic-security.json`, `mosquitto.conf`, `mosquitto_passwd` y certs del broker.

### Consideraciones Docker/Podman ahora

- [x] El primer reconciliador de `defaultACLAccess` es compatible con el runtime Compose-first actual.
- [x] El contexto de build de `bunkerm-platform` ya excluye explícitamente `frontend/node_modules` y artefactos locales de Next.js para evitar fallos de tar en Windows + Podman durante la reconstrucción del runtime.
- [x] Mientras siga existiendo volumen compartido en Compose, la aplicación efectiva del broker debe ejecutarse desde una costura invocable y testeable separada del router HTTP; el runner CLI actual cubre ese papel transicional.
- [x] El baseline Compose-first ya materializa esa costura en un servicio dedicado `bhm-reconciler`, aunque `bunkerm-platform` mantenga todavía mounts broker-facing por compatibilidad transicional.
- [x] `bunkerm-platform` ya no necesita escritura sobre `/etc/mosquitto` ni sobre los logs del broker para los slices de configuración de archivo, TLS, documento DynSec completo y `mosquitto_passwd`; esos mounts quedaron en solo lectura dentro del runtime local.
- [x] El handoff efímero de `create_client` ya usa un spool cifrado en `/nextjs/data/reconcile-secrets`, compartido entre `bunkerm-platform` y `bhm-reconciler`, en lugar de reutilizar el filesystem del broker o persistir el password en SQLite.
- [x] `bunkerm-platform` ya no necesita tampoco escritura sobre `/var/lib/mosquitto` para el runtime HTTP activo: la señal manual de recarga quedó encapsulada como capability broker-facing y las escrituras router-directas que siguen existiendo allí pertenecen solo a superficies legacy no montadas en `main.py`.
- [x] Las superficies legacy históricas de AWS/Azure Bridge y el runtime standalone de DynSec ya no son ejecutables como writers alternativos del broker; quedaron explicitadas como compatibilidad retirada con respuesta `410 Gone` hasta que exista una migración real al control-plane.
- [x] `bunkerm-platform` ya no monta `mosquitto-log`; la observabilidad de logs y resource stats del broker quedó trasladada a `bhm-broker-observability`, que es ahora el único consumidor broker-owned de ese volumen compartido.
- [x] `clientlogs`, `config` y `monitor` ya consumen observabilidad broker-owned por HTTP interno y exponen estado de fuente explícito, de modo que el acoplamiento observacional residual dejó de vivir dentro del proceso web principal.
- [~] La solución ya no depende de que el backend principal comparta ownership de escritura del filesystem del broker, pero el web sigue dependiendo de mounts read-only sobre `mosquitto-data` y `mosquitto-conf` para parte del estado observado/configuración activa.
- [~] Si existe un volumen persistente del broker, su manipulación efectiva de escritura ya queda encapsulada en componentes broker-owned (`bhm-reconciler` y `bhm-broker-observability`), aunque la lectura de ciertos artefactos sigue residiendo parcialmente en el proceso web.
- [x] Las capacidades AWS/Azure Bridge quedaron fuera de la superficie activa del producto y no deben considerarse parte del baseline funcional de Fase 3.

### Consideraciones Kubernetes después

- [x] El modelo de estado deseado ya tiene una traducción conceptual inicial a objetos de plataforma: `mosquitto.conf` como configuración, `mosquitto_passwd` y TLS como secretos/material sensible y `dynamic-security.json` como artefacto privado reconciliado.
- [x] La semántica de reconciliación ya no depende de comandos ad hoc como contrato de arquitectura: los detalles de ejecución quedan encapsulados detrás de capabilities de desired state y de componentes broker-owned, lo que permite traducirlos después a Jobs, sidecars o controladores en Kubernetes.
- [x] La aplicación de certificados y bridges ya puede evolucionar a secretos gestionados por la plataforma: TLS quedó modelado como capability reconciliada y los bridges futuros se representan mediante `broker.bridge_bundle`, listo para proyectarse luego sobre Secrets/ConfigMaps o recursos equivalentes.
- [x] Se documentó que un clúster local de Kubernetes puede usarse más adelante como carril opcional de validación, pero no como baseline obligatorio de Fase 3.

### Decisión aplicada en esta fase

- [x] Se evaluó el uso de un clúster local de Kubernetes sobre Docker/Podman.
- [x] Se decidió no incorporarlo ahora como entorno principal porque no resuelve la deuda del control-plane y añade complejidad operativa en Windows + Podman remoto.
- [x] Si se habilita una validación temprana de Kubernetes antes de Fase 8, la opción preferida será `kind` como laboratorio efímero y no `minikube` con driver Podman.

### Verificaciones

- [x] Un cambio de configuración puede solicitarse desde la API sin escritura directa del backend sobre rutas internas del broker para el caso de `defaultACLAccess`.
- [x] El estado aplicado y el estado observado pueden auditarse para `defaultACLAccess` mediante `GET /api/v1/dynsec/default-acl/status`.
- [x] La creación y administración básica de clientes DynSec ya puede solicitarse sin dual-write directo desde el router.
- [x] El estado aplicado y observado de clientes DynSec ya puede auditarse mediante `GET /api/v1/dynsec/clients/{username}/status`.
- [x] La aplicación broker-facing del lifecycle principal de clientes DynSec ya pasa por la costura explícita de reconciliación y no por ejecución directa desde el router.
- [x] El slice real de cliente DynSec ya quedó validado tanto por el estado auditable (`status`) como por el `dynamic-security.json` efectivo del broker sobre el stack Podman activo.
- [x] El documento DynSec completo ya puede importarse, resetearse y sincronizarse desde `mosquitto_passwd` sin escritura directa desde la capa HTTP.
- [x] El estado aplicado y observado del documento DynSec completo ya puede auditarse mediante `GET /api/v1/config/dynsec-json/status`.
- [x] El slice real de documento DynSec completo y el sync desde `mosquitto_passwd` ya quedaron validados también contra el stack Podman activo, no solo por suite local.
- [x] El archivo `mosquitto_passwd` ya puede solicitarse y auditarse como capability propia del control-plane mediante `POST /api/v1/dynsec/import-password-file` y `GET /api/v1/dynsec/password-file-status`.
- [x] El baseline Compose-first ya puede ejecutar reconciliación broker-facing fuera del proceso web mediante el servicio `bhm-reconciler`.
- [x] Las entidades de roles y grupos DynSec ya pueden solicitar cambios sin mutación directa del JSON desde la capa HTTP.
- [x] El estado aplicado y observado de roles y grupos DynSec ya puede auditarse mediante endpoints de estado por entidad.
- [x] Las memberships `group-client` DynSec ya pasan también por la costura explícita broker-facing y no por ejecución directa desde el router.
- [x] La prioridad de memberships `group-client` ya queda reflejada en `desired` y `observed`, evitando perder semántica de reconciliación en ese slice.
- [x] La aplicación broker-facing de `roles` y `groups` ya pasa por una costura explícita de reconciliación y no por ejecución directa desde el router.
- [x] La configuración base de `mosquitto.conf` ya puede solicitarse sin escritura directa desde la capa HTTP.
- [x] El estado aplicado y observado del archivo base del broker ya puede auditarse mediante `GET /api/v1/config/mosquitto-config/status`.
- [x] Los certificados TLS locales del broker ya pueden solicitar cambios sin escritura directa desde la capa HTTP.
- [x] El estado aplicado y observado del cert store TLS ya puede auditarse mediante `GET /api/v1/config/tls-certs/status`.
- [x] Existe rollback básico al menos para la reconciliación transicional de `mosquitto.conf`.
- [x] El baseline Compose-first ya ejecuta en runtime real los slices anteriores con `bunkerm-platform` en modo daemon y con `/etc/mosquitto` y `/var/log/mosquitto` montados en solo lectura.
- [x] El lifecycle principal de clientes DynSec ya puede solicitarse también en modo daemon sin persistir su password de creación en el control-plane durable.
- [x] El baseline Compose-first ya puede ejecutar también la recarga manual de Mosquitto sin escritura directa desde la capa HTTP sobre `/var/lib/mosquitto/.reload`.
- [x] No quedan superficies legacy ejecutables en el repositorio que sigan publicando rutas activas con lógica broker-facing directa para AWS/Azure Bridge o para el antiguo runtime standalone de DynSec.
- [x] El proceso web principal ya no mantiene lectura directa activa de `mosquitto.log` ni de `broker-resource-stats.json`; esos artefactos quedaron encapsulados detrás de `bhm-broker-observability`.
- [x] `clientlogs` conserva trazabilidad operativa mediante polling HTTP interno y `source-status`, sin requerir el mount de logs en `bunkerm-platform`.
- [x] El stack runtime validado con `deploy.ps1 -Action start` ya incluye `bunkerm-mosquitto`, `bunkerm-reconciler`, `bunkerm-broker-observability` y `bunkerm-platform` operativos en la misma red Compose-first, con smoke `5/5 OK` posterior al arranque.
- [x] La validación interna desde `bunkerm-platform` confirmó `source-status.available=true` para logs y resource stats en `bhm-broker-observability`, reforzando que la observabilidad broker-owned ya no depende del filesystem local del proceso web.
- [x] El runtime HTTP ya puede prescindir de `mosquitto-data` y `mosquitto-conf`: las lecturas activas de `dynamic-security.json`, `mosquitto.conf`, `mosquitto_passwd` y certs quedaron movidas a `bhm-broker-observability` y a observed-state helpers consumidos por HTTP interno.

### Tests

- [x] Test unitario del modelo de estado deseado para `defaultACLAccess`.
- [x] Test unitario del reconciliador de `defaultACLAccess`.
- [x] `pytest tests/test_config.py tests/test_dynsec.py tests/test_architecture.py` pasó con `49 passed` tras introducir el modo daemon broker-facing para rutas elegibles.
- [x] `deploy.ps1 -Action smoke` pasó con `5/5 OK` sobre el stack recompuesto con `bunkerm-platform` y `bhm-reconciler` activos.
- [x] `pytest tests/test_dynsec.py tests/test_broker_reconcile_runner.py tests/test_architecture.py` pasó con `39 passed` tras daemonizar también las rutas principales de `routers/dynsec.py` y añadir el handoff efímero cifrado de `create_client`.
- [x] `pytest tests/test_config.py tests/test_dynsec.py tests/test_broker_reconcile_runner.py tests/test_architecture.py` pasó con `58 passed` tras mover también la señal manual de reload al control-plane y endurecer `mosquitto-data` a solo lectura en el web container.
- [x] `pytest tests/test_bridges.py tests/test_legacy_surfaces.py tests/test_architecture.py -q` pasó con `15 passed` y protege la retirada segura de superficies legacy broker-facing para que no vuelvan a introducir escrituras directas fuera del control-plane.
- [x] `pytest tests/test_clientlogs.py tests/test_architecture.py -q` pasó con `13 passed` tras hacer auditable y opcional la dependencia de `clientlogs` respecto a `mosquitto-log`.
- [x] `pytest tests/test_config.py tests/test_monitor.py tests/test_clientlogs.py tests/test_architecture.py -q` pasó con `44 passed` tras volver explícitos y auditables los consumidores restantes de `mosquitto-log` y `broker-resource-stats.json`.
- [x] `pytest tests/test_clientlogs.py tests/test_clientlogs_service.py tests/test_monitor.py tests/test_architecture.py tests/test_config.py -q` pasó con `49 passed` tras mover `clientlogs` y los snapshots históricos del monitor a `bhm-broker-observability` y retirar `mosquitto-log` de `bunkerm-platform`.
- [x] Test unitario del modelo de estado deseado para clientes DynSec y asignación de roles.
- [x] Test unitario del reconciliador de clientes DynSec para create/enable-disable/roles.
- [x] Tests de regresión para import/sync/status de `mosquitto_passwd` como scope propio del control-plane.
- [x] Test de integración ligera del reconciliador broker-facing para la aplicación efectiva de `mosquitto_passwd`.
- [x] Test unitario del runner CLI de reconciliación por scope.
- [x] Test de guardrail arquitectónico para asegurar que `docker-compose.dev.yml` mantiene el servicio `bhm-reconciler` en el baseline Compose-first.
- [x] Test unitario del modelo de estado deseado para roles, ACLs, grupos y memberships.
- [x] Test unitario del reconciliador de roles, ACLs y grupos DynSec.
- [x] Test unitario del modelo de estado deseado para `mosquitto.conf`.
- [x] Test unitario del reconciliador transicional de `mosquitto.conf` para save/reset/remove listener.
- [x] Test unitario del modelo de estado deseado para certificados TLS del broker.
- [x] Test unitario del reconciliador transicional del cert store TLS para upload/delete.
- [x] Test de integración de aplicación de cambios al broker.
- [x] Test de integración ligero sobre la costura broker-facing del reconciliador para `mosquitto.conf` y `defaultACLAccess`.
- [x] Test de rollback cuando la reconciliación falla para `mosquitto.conf` y cert store TLS.
- [x] Test de drift detection para `defaultACLAccess`.
- [x] Test de drift detection y estado observado para clientes DynSec.
- [x] Test de drift detection y estado observado para roles y grupos DynSec.
- [x] Test de drift detection y estado observado para `mosquitto.conf`.
- [x] Test de drift detection y estado observado para certificados TLS del broker.
- [ ] La integración real `tests/test_broker_reconciler_real_integration.py` quedó preparada para este corte, pero en esta ejecución local terminó en `skipped` por precondiciones del entorno activo y no aportó una validación adicional del nuevo handoff efímero.
- [x] `deploy.ps1 -Action smoke` volvió a cerrar en `5/5 OK` tras recrear `bunkerm-platform` con `mosquitto-data`, `mosquitto-conf` y `mosquitto-log` en solo lectura.

### Evidencia reciente

- [x] Se añadió `services/broker_desired_state_service.py` como primer servicio transicional de control-plane.
- [x] Se añadió el modelo ORM `BrokerDesiredState` en el backend unificado.
- [x] Se amplió el servicio transicional para desired state y reconciliación de clientes DynSec.
- [x] Se añadieron los endpoints de estado `GET /api/v1/dynsec/default-acl/status` y `GET /api/v1/dynsec/clients/{username}/status`.
- [x] Se amplió el servicio transicional para deleted clients, roles, ACLs, grupos y memberships de DynSec.
- [x] Se añadieron los endpoints de estado `GET /api/v1/dynsec/roles/{role_name}/status` y `GET /api/v1/dynsec/groups/{group_name}/status`.
- [x] Se amplió el servicio transicional para desired state, drift detection y rollback básico de `mosquitto.conf`.
- [x] Se añadió el endpoint de estado `GET /api/v1/config/mosquitto-config/status`.
- [x] Las rutas y pantallas de AWS/Azure Bridge fueron retiradas de la superficie activa del backend unificado y de la navegación del frontend.
- [x] Se amplió el servicio transicional para desired state, drift detection y reconciliación del cert store TLS local.
- [x] Se añadió el endpoint de estado `GET /api/v1/config/tls-certs/status`.
- [x] Las rutas de configuración endurecieron su contrato HTTP para devolver `500` cuando la reconciliación termina en `error` y evitar falsos éxitos silenciosos.
- [x] Se añadieron pruebas explícitas de rollback para fallo de recarga de `mosquitto.conf` y para fallo de reconciliación del cert store TLS.
- [x] Se añadió `services/broker_reconciler.py` como reconciliador explícito broker-facing y se movió a esa costura la ejecución efectiva de `defaultACLAccess`, `roles`, `groups`, `mosquitto.conf` y cert store TLS.
- [x] Se amplió `services/broker_reconciler.py` para asumir también la aplicación efectiva del lifecycle principal de clientes DynSec sin persistir el password de creación en el desired state.
- [x] Se añadió `services/broker_runtime.py` como adapter local explícito para desacoplar la lógica del reconciliador de los detalles in-process del runtime broker-facing.
- [x] Se amplió además la reconciliación broker-facing de grupos para cubrir memberships `group-client` y su prioridad desde el mismo seam explícito.
- [x] Se amplió la costura broker-facing para cubrir también el documento DynSec completo y encapsular la señal `.dynsec-reload` detrás del runtime local.
- [x] Se añadió `services/broker_reconcile_daemon.py` y el servicio Compose `bhm-reconciler` para empezar a ejecutar el control-loop broker-facing fuera del proceso web.
- [x] Se añadió el polling HTTP interno broker-owned para `clientlogs` y para los snapshots históricos de resource stats del monitor, permitiendo retirar `mosquitto-log` del contenedor web principal.
- [x] Se añadió `tests/test_broker_reconciler_integration.py` para validar la costura broker-facing con filesystem temporal y comandos DynSec simulados.
- [x] Se ajustó `.dockerignore` del runtime `bunkerm-platform` para excluir `frontend/node_modules` y permitir `podman compose build bunkerm` en Windows sin errores por modos de archivo en `.bin`.
- [x] La suite enfocada `pytest tests/test_broker_reconciler_integration.py tests/test_architecture.py tests/test_bridges.py tests/test_config.py tests/test_dynsec.py -q` terminó en `49 passed`.
- [x] `podman compose --env-file .env.dev -f docker-compose.dev.yml build bunkerm` volvió a completar correctamente tras endurecer las exclusiones del contexto de build.
- [x] `podman compose --env-file .env.dev -f docker-compose.dev.yml up -d bunkerm` refrescó el runtime activo con la imagen reconstruida.
- [x] La prueba real `pytest tests/test_broker_reconciler_real_integration.py -q` terminó en `1 passed` contra el stack Podman activo, verificando create/disable/delete de cliente tanto en `status` como en el broker real.
- [x] La suite backend ampliada `pytest tests/test_dynsec.py tests/test_config.py tests/test_broker_reconciler_integration.py tests/test_architecture.py tests/test_bridges.py -q` terminó en `54 passed` tras migrar import/reset de DynSec y el sync desde `mosquitto_passwd` al control-plane.
- [x] Tras reconstruir y refrescar de nuevo `bunkerm-platform`, la prueba real `pytest tests/test_broker_reconciler_real_integration.py -q` terminó en `3 passed`, validando lifecycle de cliente, import/reset de DynSec y sync desde `mosquitto_passwd` contra el stack Podman activo.
- [x] `podman compose --env-file .env.dev -f docker-compose.dev.yml config` resuelve correctamente el nuevo servicio `bhm-reconciler` en el baseline Compose-first.
- [x] La validación local `pytest tests/test_dynsec.py tests/test_broker_reconciler_integration.py tests/test_broker_reconcile_runner.py tests/test_architecture.py` terminó en `40 passed` tras introducir el daemon y el servicio Compose dedicado.

### Criterio de salida

- [x] BHM deja de gestionar el broker mediante escritura cruzada y pasa a un control-plane compatible con Compose hoy y Kubernetes mañana.

---

## Fase 4 - Persistencia PostgreSQL por bounded context

**Objetivo**: Mover el ownership durable de BHM a PostgreSQL por bounded context, empezando por el control-plane y continuando por los históricos y read models técnicos sin romper la operación ni reintroducir doble escritura estructural.

### Avance inicial ya implementado

- [x] Se separaron las URLs de persistencia por dominio en configuración (`control_plane_database_url`, `history_database_url`, `reporting_database_url`) manteniendo fallback controlado al `database_url` actual durante la transición.
- [x] El motor async principal del backend ya consume `resolved_control_plane_database_url`, dejando preparado el primer corte operativo del control-plane durable sobre PostgreSQL.
- [x] La normalización de URLs async/sync ya convierte automáticamente `postgresql://...` en `postgresql+asyncpg://...` para el motor async principal y en `postgresql+psycopg://...` para los seams sync, evitando acoplar la operación a un dialecto explícito en Compose.
- [x] `docker-compose.dev.yml` ya inyecta de forma explícita `CONTROL_PLANE_DATABASE_URL`, `HISTORY_DATABASE_URL` y `REPORTING_DATABASE_URL` en `bunkerm-platform` y `bhm-reconciler`, manteniendo fallback Compose-first sobre SQLite cuando esas variables no se activen.
- [x] Se añadió una utilidad específica `scripts/migrate-control-plane-state.py` para migrar `broker_desired_state` desde SQLite al datastore configurado del control-plane, endurecida con timeouts, selección explícita de `--source-url` SQLite y modo `--dry-run` para evitar bloqueos o confusión con `.env.dev` cuando `DATABASE_URL` ya apunte a PostgreSQL.
- [x] El control-plane ya deja rastro durable append-only de cambios solicitados mediante la nueva tabla `broker_desired_state_audit`, versionada junto a `broker_desired_state` para cubrir la parte auditable del corte 1.
- [x] El migrador del control-plane ya contempla también `broker_desired_state_audit`, de modo que el corte 1 puede moverse con estado deseado y rastro append-only consistentes.
- [x] El backend principal ya incorpora Alembic propio para el bounded context del control-plane (`backend/app/alembic`), con una revisión inicial enfocada en `broker_desired_state` y `broker_desired_state_audit` y soporte seguro para adoptar esquemas PostgreSQL ya bootstrappeados sin `alembic_version`.
- [x] Se añadió `scripts/upgrade-control-plane-schema.py` como utilidad operativa para ejecutar `upgrade/stamp` del esquema del control-plane sin depender de rutas manuales dentro del backend.
- [x] `core.database.init_db()` y el daemon `bhm-reconciler` ya usan Alembic automáticamente cuando el control-plane apunta a un backend no SQLite; `create_all` queda restringido al baseline SQLite transicional.
- [x] Históricos y reporting ya no solo pasan por seams: las factorías de dominio seleccionan ahora backends SQLAlchemy reales para `client activity`, `broker history`, `topic history` y `reporting` cuando el dominio apunte a PostgreSQL.
- [x] Se añadieron implementaciones SQLAlchemy reutilizando los modelos ORM existentes del backend unificado, de modo que el cambio de backend no exige reescribir routers ni servicios en los cortes 2 y 3.
- [x] El bounded context compartido de history/reporting ya tiene también árbol Alembic propio (`backend/app/history_reporting_alembic`) y tabla de versión separada (`alembic_version_history_reporting`), evitando mezclar su versionado con el del control-plane incluso cuando varias URLs apunten al mismo datastore durante la transición.
- [x] Se añadió `scripts/upgrade-history-reporting-schema.py` como utilidad operativa para ejecutar upgrades formales del esquema de history/reporting sin depender de bootstraps implícitos desde los storages SQLAlchemy.
- [x] La validación enfocada del estado actual de Fase 4 quedó ejecutada con `36 passed, 1 warning` sobre utilidades de URL, factorías, auditoría del control-plane, storages SQLAlchemy nuevos y regresiones existentes de config, monitor, clientlogs y reporting.
- [x] La activación enfocada del corte 1 ya quedó validada también sobre PostgreSQL real en Compose (`1 passed`) y el `dry-run` del migrador quedó verificado con selección segura de fuente SQLite (`0` filas cuando no hay estado legacy presente).
- [x] La activación enfocada del corte 2 ya quedó validada también sobre PostgreSQL real en Compose (`1 passed`) para `broker history`, `topic history` y `client activity`, verificando persistencia real de los storages SQLAlchemy contra el contenedor PostgreSQL.
- [x] Se añadió `scripts/migrate-history-reporting-state.py` para migrar desde SQLite los datos operativos de `broker history`, `topic history`, `client activity` y las tablas que consume `reporting`, con `--dry-run`, detección segura de targets ya poblados y normalización automática del host PostgreSQL cuando se ejecuta desde el host Windows.
- [x] La activación enfocada del corte 3 ya quedó validada también sobre PostgreSQL real en Compose (`1 passed`) para reporting diario/semanal, timeline, incidentes y purge de retención usando `SQLAlchemyReportingStorage`.
- [x] La validación consolidada de los tres cortes quedó reejecutada sobre el entorno local con `20 passed, 1 warning`, cubriendo utilidades de URL, runtime/Alembic, auditoría del control-plane, factorías, storages SQLAlchemy, migraciones SQLite->PostgreSQL y las tres integraciones reales contra PostgreSQL.
- [x] La regresión ampliada de contratos HTTP y persistencia quedó revalidada con `40 passed`, cubriendo `/api/v1/monitor`, `/api/v1/clientlogs`, `/api/v1/reports` y toda la suite enfocada de Fase 4 ya operando sobre el baseline PostgreSQL actual.
- [x] Se añadieron utilidades operativas `scripts/postgres-backup.py` y `scripts/postgres-restore.py`, validadas con dump real del contenedor `bunkerm-postgres`, restauración en una base temporal de verificación y comprobación posterior de tablas clave de control-plane e históricos.
- [x] Se eliminó la warning residual de Pydantic v2 al migrar `core.config.Settings` a `SettingsConfigDict`, cerrando una deuda técnica arrastrada de fases anteriores dentro del backend unificado.

### Esquema PostgreSQL inicial de BHM

- [x] **Control-plane del broker**: `broker_desired_state`, `broker_desired_state_audit`.
- [x] **Estado operativo e históricos técnicos**: `broker_metric_ticks`, `broker_runtime_state`, `broker_daily_summary`, `topic_registry`, `topic_publish_buckets`, `topic_subscribe_buckets`, `client_registry`, `client_session_events`, `client_topic_events`, `client_subscription_state`, `client_daily_summary`, `client_daily_distinct_topics`.
- [x] **Compatibilidad transicional fuera del alcance de Fase 4**: tablas legacy SQLite y `smart-anomaly` continúan separadas de este corte y no bloquean el baseline PostgreSQL de BHM.
- [x] **Límite de ownership**: el producto externo de reporting/transformación de datos sigue fuera de esta base; la integración permanece por APIs o eventos, sin tablas compartidas ni acceso directo, en línea con ADR-0001 y ADR-0004.

### Actividades

- [x] Definir el esquema PostgreSQL inicial del bounded context de BHM, separando al menos: control-plane del broker, auditoría/reconciliación y reporting técnico.
- [x] Mantener la base de datos separada del producto externo de reporting/transformación, sin compartir tablas ni ownership de dominio.
- [x] Introducir una capa de persistencia o repositorios de transición que permitan mover cada dominio sin seguir acoplando el código al backend SQLite actual.
- [x] Ejecutar una migración incremental por capability o agregado, no por big bang, y evitar una doble escritura generalizada; la compatibilidad temporal queda acotada por dominio, con un único writer y migradores/imports transicionales validados por corte.
- [x] Migrar primero el estado durable del control-plane: `broker_desired_state`, auditoría de cambios solicitados, estado aplicado/observado y metadatos necesarios para `bhm-reconciler` y `bhm-api`. El wiring Compose-first, la validación real contra PostgreSQL, el `dry-run` seguro y el rollout runtime sobre la imagen reconstruida ya quedaron cubiertos; la ejecución sobre un baseline SQLite legacy real queda como tarea operativa cuando exista dataset fuente.
- [x] Migrar después los históricos ya existentes en SQLite que más condicionan a producto: broker history, topic history, client activity y reporting técnico asociado. Los backends, factorías, migradores y validaciones reales ya cubren este corte; la ejecución sobre un dataset legacy real queda pendiente solo si aparece una base fuente para importar.
- [x] Migrar por último los read models o tablas auxiliares que sigan quedando en SQLite y que no bloqueen el primer corte operativo sobre PostgreSQL. Reporting técnico, retención y purge ya operan sobre PostgreSQL en el baseline validado; la separación total de datastore respecto de history queda como hardening posterior, no como bloqueo del corte.
- [x] Añadir migraciones de esquema y versionado de base de datos con Alembic para PostgreSQL. El control-plane mantiene su árbol/versionado propio y history/reporting ya quedaron cubiertos por un árbol Alembic adicional con tabla de versión separada; los storages PostgreSQL dejaron de depender de `create_all` como vía principal de bootstrap en esos dominios.
- [x] Hacer explícita la dependencia funcional de `bhm-api` y `bhm-reconciler` respecto a PostgreSQL en Compose cuando el primer corte operativo esté listo. `deploy.ps1` ya detecta URLs PostgreSQL activas, arranca `postgres` sin arrastrar `pgadmin` opcional, y el smoke validado sobre Podman/Compose cerró en `7/7 OK` con conectividad real desde ambos contenedores.
- [x] Ajustar configuración de entorno, backup, restore y utilidades de migración para PostgreSQL. Ya existen utilidades operativas para upgrade Alembic del control-plane, migración/dry-run de históricos+reporting y backup/restore formal del baseline PostgreSQL actual; el flujo dedicado para reporting separado quedará como hardening posterior si ese datastore deja de compartir baseline con history.

### Orden recomendado de Fase 4

- [x] Corte 1: mover a PostgreSQL el control-plane durable del broker y su auditoría, manteniendo SQLite solo como origen legado de transición donde siga siendo imprescindible.
- [x] Corte 2: mover a PostgreSQL broker history, topic history y client activity, que son los dominios que más condicionan el trabajo paralelo de producto.
- [x] Corte 3: cerrar reporting técnico, retención, purgas y read models auxiliares para que SQLite deje de ser backend operativo y pase a estado legado o de importación puntual.

### Estado actual de los cortes

- [x] Corte 1 completado: el control-plane ya corre sobre la URL dedicada, persiste auditoría append-only (`broker_desired_state_audit`), tiene Alembic propio con adopción segura del esquema bootstrappeado y quedó validado tanto en runtime Compose-first sobre PostgreSQL (`7/7 OK`) como en la suite consolidada de Fase 4. Queda pendiente solo ejecutar la importación si aparece un baseline SQLite legacy real.
- [x] Corte 2 completado: monitor, topic history y client activity ya tienen factorías, backends SQLAlchemy y migrador validados contra PostgreSQL real, con cobertura adicional de migración SQLite->PostgreSQL. La importación de datos legacy queda como paso operativo condicionado a disponer de una base fuente real.
- [x] Corte 3 completado: reporting ya tiene backend SQLAlchemy propio, migrador operativo desde SQLite y validación real contra PostgreSQL para reportes, timeline, incidentes y retention purge. La independencia completa del datastore respecto de history queda como endurecimiento posterior y no bloquea el cierre del corte.

### Riesgos a controlar

- [ ] No convertir la transición en una convivencia indefinida SQLite/PostgreSQL sin ownership claro por dominio.
- [ ] No romper la semántica auditable del control-plane mientras se sustituye `broker_desired_state` y sus lecturas asociadas.
- [ ] No forzar a frontend o a producto a reescribir contratos varias veces por falta de orden en la migración de persistencia.
- [ ] No mezclar en el mismo corte la migración del control-plane durable con cambios amplios de observabilidad que pertenecen a Fase 5.

### Verificaciones

- [x] `bhm-api` y `bhm-reconciler` pueden operar con PostgreSQL como datastore principal en los dominios ya migrados. El arranque ya aplica Alembic del control-plane sobre PostgreSQL, `deploy.ps1` levanta automáticamente `postgres` cuando la configuración activa lo requiere y la corrida runtime completa del stack quedó validada en Podman/Compose con smoke `7/7 OK`.
- [x] No existen accesos directos de dominio al SQLite antiguo en los flujos ya migrados; la baseline activa ya exige PostgreSQL para control-plane, history, topic history, client activity y reporting, y las referencias SQLite residuales quedan acotadas a utilidades legacy de importación, tests y adapters heredados fuera del carril operativo actual.
- [x] Los datos históricos y operativos esenciales se conservan y siguen siendo auditables tras cada corte. El control-plane mantiene auditoría append-only en PostgreSQL y los históricos/reporting quedaron validados sobre persistencia real, además de una restauración completa desde dump sobre base temporal de verificación.
- [x] Los contratos HTTP consumidos por frontend y reporting técnico mantienen compatibilidad razonable durante la transición o documentan claramente su cambio. La regresión ampliada de `/api/v1/monitor`, `/api/v1/clientlogs` y `/api/v1/reports` pasó con `40 passed` sin cambios de contrato pendientes para este corte.

### Tests

- [x] Test unitario de repositorios, servicios de persistencia y adapters de transición SQLite/PostgreSQL. La cobertura actual incluye utilidades de URL, migraciones Alembic del control-plane, arranque runtime con Alembic y storages SQLAlchemy de control-plane/history/topic/client activity/reporting.
- [x] Test específico del nuevo versionado Alembic de history/reporting y de su integración con runtime/storages (`9 passed`), incluyendo aceptación de esquemas parcialmente bootstrappeados antes de registrar la tabla de versión.
- [x] Test de integración contra PostgreSQL real en contenedor para `bhm-api` y `bhm-reconciler`. Ya existe validación real del control-plane y del segundo corte de storages contra PostgreSQL, y la validación runtime extremo a extremo del stack Compose-first quedó cerrada con smoke `7/7 OK` apuntando a PostgreSQL como datastore principal.
- [x] Test de migración de datos desde SQLite por dominio o capability, empezando por el control-plane y siguiendo por históricos. La validación actual cubre `dry-run` seguro del control-plane y la migración de históricos/reporting entre datastores SQLite como prueba estructural de los migradores; la ejecución sobre una base legacy real queda pendiente solo por ausencia de dataset fuente en el workspace.
- [x] Test de compatibilidad de API en endpoints afectados por cada corte de persistencia. La suite ampliada ejecutada en esta iteración validó contratos HTTP de monitor, clientlogs y reporting sin regresiones (`40 passed`).
- [x] Test de rollback o recuperación ante fallo de migración, incluyendo restauración de datos y vuelta controlada al datastore previo cuando aplique. En el baseline de desarrollo actual se validó recuperación por backup/restore PostgreSQL completo mediante dump real, restore sobre base temporal y comprobación de tablas restauradas; la recuperación desde SQLite legacy queda fuera de alcance mientras no exista dataset fuente.

### Criterio de salida

- [x] PostgreSQL queda establecido como base persistente operativa de BHM para el control-plane y para los dominios históricos priorizados de Fase 4 en el baseline de desarrollo actual; SQLite deja de ser backend operativo de esos dominios y queda acotado a utilidades legacy de importación puntual, tests y compatibilidad heredada fuera del runtime activo.

---

## Fase 5 - Observabilidad y reporting técnico desacoplado

**Objetivo**: Eliminar la dependencia de log tailing directo y construir observabilidad compatible con microservicios.

### Punto de partida al iniciar Fase 5

- [x] BHM entra a Fase 5 con `bhm-broker-observability` como fachada broker-owned ya validada en runtime y con reporting técnico operando sobre PostgreSQL.
- [x] La deuda ya no está en la persistencia principal ni en mounts de escritura, sino en sustituir la fuente observacional transicional basada en snapshots/logs por un carril más estructurado sin romper los contratos HTTP actuales.
- [x] La configuración de alertas del monitor ya dejó de persistirse en JSON local y pasa al control-plane PostgreSQL mediante Alembic, lo que elimina otro remanente activo de filesystem antes de profundizar el contrato de delivery externo.
- [x] El contrato técnico de delivery externo quedó fijado en `docs/BHM_ALERT_DELIVERY_CONTRACT.md`, separando detección en `bhm-api` de entrega en un worker dedicado `bhm-alert-delivery` y dejando estable el payload canónico para frontend.
- [x] El primer slice técnico del outbox de alertas ya quedó materializado en el esquema del control-plane con `alert_delivery_channel`, `alert_delivery_event` y `alert_delivery_attempt`, versionados por Alembic para que el worker pueda nacer sobre PostgreSQL sin bootstraps ad hoc.
- [x] El monitor ya persiste también el evento canónico `raised` en `alert_delivery_event` al disparar una alerta, con `dedupeKey`, `routing.channelCount` y payload estable alineados al contrato técnico; el envío inline actual queda sólo como compatibilidad transicional mientras nace el worker dedicado.
- [x] Para el compañero B, el carril funcional ya abierto es el refinamiento de UX, filtros, tablas, estados y reporting técnico sobre los endpoints existentes; los bloqueos estructurales originales de observabilidad histórica y contrato técnico de alertas externas ya quedaron resueltos en esta fase mediante ADR-0007, `notifications` y el worker `bhm-alert-delivery`.

### Actividades

- [x] Sustituir el uso de `tail -f` y lectura directa de logs compartidos como mecanismo principal. `bhm-api` ya no lee directamente logs compartidos del broker: consume snapshots incrementales y `source-status` por HTTP interno desde `bhm-broker-observability`, que conserva el ownership broker-facing dentro de un componente separado.
- [x] Definir si la observabilidad técnica irá por collector, pipeline de logs o eventos técnicos estructurados. Queda fijado en `docs/adr/0007-phase5-observability-pipeline.md` como pipeline híbrido broker-owned: snapshots internos en `bhm-broker-observability`, transformación a eventos técnicos estructurados en `bhm-api` y read models persistidos en PostgreSQL para reporting.
- [x] Separar reporting técnico de BHM del reporting de negocio del otro producto. El carril de Fase 5 queda acotado a reporting técnico propio de BHM (`monitor`, `clientlogs`, `reports`, `notifications`) con read models y exports HTTP independientes de cualquier reporting de negocio externo.
- [x] Ajustar el pipeline de incidentes, timeline y reporting operativo para la nueva fuente de datos. `clientlogs_service`, `monitor_service` y `reporting` ya operan sobre el pipeline broker-owned + eventos técnicos estructurados + PostgreSQL fijado en ADR-0007, y la regresión focalizada se mantiene verde.
- [x] Definir métricas, logs y eventos mínimos por servicio. El mismo ADR de Fase 5 fija el inventario mínimo de snapshots, eventos técnicos, métricas `$SYS`, incidentes y contratos `source-status` por servicio.
- [x] Revisar retención, purga y exportaciones del reporting técnico. El storage y la API de reporting ya cubren estado de retención, purga ejecutable y exports CSV/JSON para broker y actividad por cliente, con regresiones específicas sobre ambos carriles.
- [x] Definir el contrato técnico de alertas por correo, redes o webhooks: payload canónico, ownership del intento de entrega, reintentos, idempotencia, auditoría y manejo de credenciales.
- [x] Decidir si la entrega de alertas externas vivirá en `bhm-api`, en un worker dedicado o en un servicio auxiliar, sin reintroducir acoplamientos al broker ni al filesystem. La decisión actual es `bhm-alert-delivery` como worker dedicado con outbox persistido en PostgreSQL.
- [x] Materializar la persistencia mínima del outbox en PostgreSQL con tablas de canales, eventos e intentos, alineadas con el contrato técnico acordado para Fase 5.
- [x] Desacoplar el delivery externo del hilo del motor de alertas. Ya existe `bhm-alert-delivery` como worker Compose-first que consume `alert_delivery_event`, registra `alert_delivery_attempt` y deja el envío inline detrás de `ALERT_NOTIFY_INLINE_DELIVERY_ENABLED` solo como fallback opcional.
- [x] Mantener compatibilidad razonable de `/api/v1/clientlogs`, `/api/v1/monitor` y `/api/v1/reports` mientras cambia la fuente observacional, para que B pueda seguir refinando producto sin rehacer contratos en cada corte. La regresión focalizada de Fase 5 ya cubre esos contratos junto con `notifications` y confirma que el read-model HTTP sigue estable durante el recorte observacional.
- [x] Hacer explícito el carril seguro de B durante Fase 5: ya existen superficies HTTP estables para `GET/POST /api/v1/notifications/channels`, `GET /api/v1/notifications/events` y `GET /api/v1/notifications/attempts`, con payload redacted y `retryPolicySummary` aptos para UX, filtros y tablas sin depender todavía del plan de integración end-to-end.

### Verificaciones

- [x] Monitoring y reporting técnico siguen funcionando sin mounts cruzados obligatorios de logs en el proceso web principal. El carril activo se valida sobre `bhm-broker-observability` + read models persistidos y la regresión focalizada de Fase 5 permanece verde.
- [x] Las incidencias técnicas continúan disponibles para auditoría y diagnóstico. El pipeline fijado en ADR-0007 mantiene `clientlogs`, `reports/incidents` y `source-status` como contrato estable sobre eventos persistidos.
- [x] El producto externo no depende de leer internamente la observabilidad de BHM. La fuente final queda encapsulada como HTTP interno broker-owned + PostgreSQL, no como acceso directo a artefactos internos del broker.
- [x] Los contratos HTTP que usa frontend para históricos, timeline, incidentes y reporting técnico se mantienen estables o documentan claramente cualquier ajuste derivado del nuevo pipeline observacional. La regresión de Fase 5 cubre `monitor`, `clientlogs`, `reports` y `notifications`, incluyendo exports CSV/JSON y endpoints de retención sin introducir cambios contractuales pendientes.
- [x] El contrato de alertas externas queda definido con suficiente detalle para que B pueda cerrar UX y flujos funcionales sin duplicar la implementación de delivery.
- [x] B dispone además de read models HTTP y exportaciones (`notifications/channels`, `notifications/events`, `notifications/attempts` y sus exports) para avanzar en tablas, filtros, copy funcional y exportaciones sin esperar todavía la validación end-to-end del worker.

### Tests

- [x] Test de integración de ingesta de eventos/logs técnicos. La API interna broker-owned queda cubierta por regresiones específicas de offsets incrementales, `source-status` y resource stats.
- [x] Test de reporting técnico sobre la nueva fuente de datos. La regresión focalizada de Fase 5 valida que `monitor`, `clientlogs` y `reports` siguen operando sobre el pipeline observacional desacoplado y sus read models persistidos.
- [x] Test de purga y retención. La batería de `reports` cubre ahora `GET /api/v1/reports/retention/status`, `POST /api/v1/reports/retention/purge` y el storage subyacente, además de verificar exports JSON del timeline por cliente.
- [x] Test de exportación CSV/JSON si sigue aplicando. El carril de notificaciones ya cubre export de eventos e intentos sobre el read-model estable de Fase 5.
- [x] Test del contrato de alertas externas en modo API/read-model: canales redacted, eventos canónicos e intentos auditables ya cubiertos por regresión de `notifications`; la validación end-to-end de delivery, éxito real y reintentos queda diferida al plan de integración.

### Criterio de salida

- [x] La observabilidad de BHM es compatible con una arquitectura de microservicios y deja de depender de lecturas acopladas al broker. El ownership broker-facing queda encapsulado en `bhm-broker-observability`, mientras `bhm-api` y frontend consumen solo HTTP interno y read models persistidos.

---

## Fase 6 - Seguridad e identidad técnica

**Objetivo**: Reordenar autenticación y autorización para soportar el nuevo modelo sin bloquear la migración principal.

### Actividades

- [x] Separar identidad humana de gestión, identidad service-to-service y credenciales MQTT. Queda fijado en `docs/adr/0008-phase6-identity-and-secrets.md`: sesión humana web, `API_KEY` service-to-service transicional y credenciales MQTT/DynSec como dominios distintos.
- [x] Mantener temporalmente el mecanismo actual si es necesario, con una ruta clara de endurecimiento. ADR-0008 acepta el baseline actual solo con límites explícitos: sin hardcodes nuevos, sin exposición de secretos por API y sin mezclar sesión web con `API_KEY` o credenciales MQTT.
- [x] Diseñar puntos de extensión para OAuth2/OpenID Connect en una fase posterior. ADR-0008 deja definida la costura: IdP humano posterior sin rediseñar DynSec ni reutilizar la sesión humana como identidad service-to-service.
- [x] Revisar secretos, rotación y manejo seguro de credenciales en Compose. ADR-0008 fija ownership por dominio para `AUTH_SECRET`/`NEXTAUTH_SECRET`, `API_KEY`, credenciales MQTT, `secretRef` de alertas y secretos efímeros del reconciliador.
- [x] Diseñar cómo evolucionará ese manejo de secretos cuando se pase a Kubernetes. ADR-0008 y el baseline Kubernetes ya dejan mapeada la proyección a `Secret` por dominio y mantienen `broker_reconcile_secret` como secreto efímero del control-plane en PostgreSQL.
- [x] Definir la política final de whitelist por IP y su ownership técnico: si vive como capability del control-plane broker-facing, como regla de aplicación o como combinación de ambas. ADR-0009 fija un modelo híbrido por scope: `api_admin` en el plano HTTP y `mqtt_clients` como capability broker-facing del control-plane.
- [x] Alinear esa decisión con autorización técnica, DynSec/ACL y trazabilidad auditable para que B pueda cerrar la funcionalidad sin contradecir el modelo de reconciliación. ADR-0009 separa whitelist de DynSec/ACL, define enforcement points correctos y deja auditoría/versionado como requisito del contrato.

### Verificaciones

- [x] Los flujos actuales de acceso siguen funcionando. El baseline Compose-first ya estaba validado con login web y auth API, y la regresión de Fase 6 añade cobertura explícita de auth sobre `reports` y `notifications` como endpoints críticos recientes.
- [x] Los secretos y credenciales tienen ownership y almacenamiento claros. ADR-0008 documenta la separación entre sesión humana, `API_KEY`, credenciales MQTT, `secretRef` de alert delivery y secreto efímero del reconciliador.
- [x] La arquitectura no queda bloqueada por esperar OAuth/OIDC. ADR-0008 fija una costura de extensión explícita sin exigir federación inmediata.
- [x] La whitelist por IP queda definida con un contrato técnico estable, compatible con el control-plane y consumible por frontend sin ambigüedad de ownership. ADR-0009 fija el ownership y `docs/BHM_IP_WHITELIST_CONTRACT.md` deja el modelo funcional y los endpoints previstos para UX/backend.

### Tests

- [x] Test de autenticación en endpoints críticos. La suite cubre ahora auth requerida en `monitor`, `clientlogs`, `dynsec`, `reports` y `notifications`, incluyendo endpoints de retención/purga y read models de alertas.
- [x] Test de autorización en endpoints administrativos. La regresión de `tests/test_auth.py` valida que endpoints administrativos rechazan `X-API-Key` inválida con `401` en el baseline actual de autorización coarse-grained.
- [x] Test de acceso denegado y auditoría básica. La misma regresión comprueba además que `core.auth` registra el intento inválido en el logger de seguridad básico actual.
- [x] Test de whitelist por IP para el modelo finalmente elegido, incluyendo observación/auditoría del estado aplicado. `tests/test_security.py` cubre el roundtrip del contrato, el status auditable, el enforcement HTTP del scope `api_admin` y la exclusión correcta de endpoints públicos de health.

### Criterio de salida

- [x] La seguridad acompaña la migración sin introducir nuevos acoplamientos ni bloquear el avance principal. Fase 6 ya deja separadas identidades y secretos, cubre denegación/auditoría básica, y materializa la whitelist HTTP con contrato estable, enforcement `api_admin` y estado auditable sin reabrir acoplamientos al broker.

---

## Fase 7 - Hardening, rendimiento y resiliencia

**Objetivo**: Consolidar el comportamiento stateless del backend de gestión y establecer baseline de carga y estabilidad.

### Avance reciente

- [x] El estado observado de DynSec ahora se reutiliza mediante un indice en memoria con TTL e invalidacion explicita, reduciendo el coste de listar clientes, roles, grupos y ACLs por defecto sobre datasets grandes.
- [x] `clientlogs` ya reutiliza el mapa de capabilities observado y limita la reconciliacion del registro de clientes, evitando trabajo repetido en cada consulta.
- [x] La pagina de clientes del frontend ya no refetcha en exceso roles y grupos junto con cada pagina de resultados, recortando latencia visible en listados y filtros.
- [x] La aplicacion de `mosquitto.conf` paso de recarga ligera a semantica de reinicio controlado del broker, con invalidacion de cache de `max_connections` y regresiones especificas para evitar falsos `applied`.
- [x] El modo daemon/Kubernetes ya toma `mosquitto.conf` observado desde `bhm-broker-observability` en vez de preferir el filesystem local del pod web, cerrando un caso real de drift falso en runtime distribuido.
- [x] El baseline de resiliencia ya incluye recuperacion automatica de la maquina Podman y del socket remoto antes de bootstrapear `kind`, junto con publicacion host-managed por `kubectl port-forward` en `22000/21900/29001` para evitar la fragilidad previa de `extraPortMappings` sobre Podman.
- [x] El flujo validado de laboratorio `deploy.ps1 -Action start -Runtime kind` ya vuelve a cerrar con smoke verde (`5/5 OK`) sobre Web UI/API, MQTT TCP y MQTT WebSocket, dejando `kind` como carril util de regresion y no solo como bootstrap parcial.
- [x] Se anadio `scripts/dev-tools/phase7_baseline.py` para capturar un baseline reproducible de latencia HTTP y conectividad MQTT en host, con salida JSON y endpoints configurables por runtime.
- [x] Se documento el primer carril operativo de Fase 7 en `docs/BHM_PHASE7_BASELINE.md`, fijando smoke previo, baseline JSON y uso del stresser MQTT existente como señal de carga ligera.
- [x] La primera captura real del baseline sobre `kind` ya quedo registrada con `overallStatus=ok` en HTTP/MQTT base: Web UI `mean 476.54 ms` con outlier frio visible, `auth/me` `49.97 ms`, `monitor/health` `44.84 ms`, `dynsec/roles` `48.83 ms` y MQTT TCP `11.32 ms`.
- [x] Se anadio `scripts/dev-tools/phase7_resource_snapshot.py` para capturar CPU/memoria cuando exista `Metrics API` y, como minimo actual, PVCs/capacidad de almacenamiento por servicio en `kind`, con snapshot JSON versionable.
- [x] La resiliencia por restart controlado y por fallo parcial ya quedo validada para el laboratorio `kind`: `deploy.ps1 -Action restart -Runtime kind` recreo el cluster con smoke `5/5 OK`, y la eliminacion del pod `bunkerm-platform` tambien recupero servicio completo tras endurecer la autorecuperacion de `kubectl port-forward`.
- [x] El carril de carga MQTT ya dispone de un recovery repetible post-restart: `scripts/dev-tools/phase7_provision_mqtt_clients.py` reprovisiona DynSec `1..8`, mide la ventana broker-facing `desiredUpdatedAt -> appliedAt` y devolvio el modo recomendado `per-client` a verde con `160` relaciones simuladas y `0` errores en `kind`.
- [x] El baseline host-facing ya suma reporting tecnico autenticado via `/api/proxy/reports/broker/daily?days=7`, quedando verde junto con Web UI, `auth/me`, `monitor/health`, `dynsec/roles` y MQTT TCP en `tmp/phase7-kind-baseline.json`.
- [x] El snapshot de recursos de `kind` ya tiene medicion real de CPU/memoria por pod sin `Metrics API`, usando fallback `crictl` agregado sobre todos los nodos y manteniendo PVCs/capacidad en `tmp/phase7-kind-resources.json`.
- [x] La semantica de borrado de DynSec ya quedo corregida y validada en runtime: los clientes eliminados convergen a `status=applied`, `driftDetected=false`, `desired.deleted=true` y `observed=null` en churn real sobre `kind`.
- [x] Las comprobaciones ligeras adicionales de Fase 7 ya quedaron en verde en runtime: concurrencia sobre APIs criticas (`10/10` OK por endpoint), burst MQTT corto (`480` relaciones, `0` errores) y churn de clientes DynSec `create -> role -> delete`.
- [x] Quedó formalizada la estrategia de activación gradual y reversión por capability en `docs/BHM_PHASE7_ROLLOUT_STRATEGY.md`, reutilizando los toggles reales del baseline (`BROKER_RECONCILE_MODE`, `BROKER_OBSERVABILITY_ENABLED`, `ALERT_NOTIFY_ENABLED`, `ALERT_NOTIFY_INLINE_DELIVERY_ENABLED`, probes del harness) en vez de introducir flags artificiales.

### Actividades

- [x] Definir baseline del sistema actual antes de cambios mayores.
- [x] Medir throughput MQTT, latencia de API, latencia de reporting técnico y tiempo de aplicación de cambios al broker. El harness publicado ya deja baseline host-facing con reporting verde, `shared` y `per-client` en verde, burst MQTT corto verde y una primera métrica broker-facing `desiredUpdatedAt -> appliedAt` con media `880.78 ms`.
- [x] Medir consumo de CPU, memoria y almacenamiento por servicio. El snapshot de `kind` ya captura PVCs y, aun sin `Metrics API`, CPU/memoria reales mediante `crictl` agregado sobre todos los nodos.
- [x] Validar reinicios, recuperación y comportamiento ante fallos parciales. El restart controlado y la recuperacion tras borrar el pod principal ya quedaron verdes en `kind`, con smoke host-facing `5/5 OK` despues de cada ejercicio.
- [x] Validar que el backend de gestión puede operar sin estado local exclusivo. El carril `kind` siguio operativo con backend separado del broker, observabilidad broker-owned y publicacion host-managed, incluyendo reporting, DynSec y recovery tras reinicios y reemplazo de pods.
- [x] Definir feature flags, estrategia de rollout y rollback por capability. La estrategia queda fijada en `docs/BHM_PHASE7_ROLLOUT_STRATEGY.md` con rollout por capability, smoke/baseline inmediato y rollback operacional o broker-facing segun el dominio.

### Verificaciones

- [x] Existen métricas de referencia antes y después de cada cambio mayor. El baseline inicial ya puede capturarse de forma repetible para HTTP/MQTT/reporting, el carril broker-facing ya suma la medición `desiredUpdatedAt -> appliedAt` y el snapshot de recursos ya captura CPU/memoria/almacenamiento en `kind`.
- [x] El sistema soporta reinicios controlados sin pérdida de operación esencial. El laboratorio `kind` ya supero tanto un `restart` completo como la recuperacion del pod principal con smoke `5/5 OK`.
- [x] La degradación ante fallo parcial es entendible y observable. El fallo parcial real de publicacion host-facing quedo aislado en `kubectl port-forward`, se corrigio en `deploy.ps1` y la validacion posterior confirmo recuperacion completa y medible.

### Tests

- [x] Test de carga MQTT. El carril ligero en `kind` ya quedo validado tanto en `shared` como en el modo recomendado `per-client`: ambos completaron `160` relaciones con `0` errores, y el reprovisioning DynSec `1..8` ya quedo automatizado para recovery post-restart.
- [x] Test de churn de clientes. El flujo real `create -> role -> delete` ya quedo verde en `kind` para `phase7-churn-1..4`, incluyendo settlement final `applied` sin drift falso tras borrado.
- [x] Test de bursts de publish. La corrida corta `CLIENTS=8`, `MSGS=60`, `TIME=1` ya cerro con `480` relaciones y `0` errores.
- [x] Test de concurrencia sobre APIs críticas. La comprobacion ligera ya devolvio `10/10` respuestas correctas en `monitor/health`, `dynsec/roles` y `reports/broker/daily`.
- [x] Test de resiliencia tras restart de servicios. Ya se validaron restart completo y fallo parcial real del pod principal con recuperacion completa y smoke verde posterior en `kind`.

### Criterio de salida

- [x] BHM dispone ya de una base objetiva y ejecutada de rendimiento, resiliencia y compatibilidad para continuar la evolución de plataforma. Fase 7 queda cerrada con baseline, resiliencia, churn/burst/concurrencia y estrategia explícita de rollout/rollback por capability.

---

## Fase 8 - Preparación para Kubernetes

**Objetivo**: Cerrar la migración Compose-first dejando preparada la transición posterior a Kubernetes.

### Actividades

- [x] Revisar qué configuraciones de Compose deben transformarse después en objetos de Kubernetes. El inventario explícito ya quedó levantado en `k8s/PORTABILITY_INVENTORY.md`.
- [x] Identificar futuras necesidades de ConfigMaps, Secrets, PVCs, Deployments, StatefulSets, Jobs u operador. El mismo inventario ya deja separados objetos actuales y gaps transicionales.
- [x] Verificar que el reconciliador del broker puede evolucionar a patrón operador/control loop. La verificación técnica y la ruta sidecar -> control loop -> controlador quedaron fijadas en `k8s/RECONCILER_CONTROL_LOOP_EVOLUTION.md`, apoyadas además por el modo `--once` del daemon actual como seam operativo para `Job` o reconciliación puntual.
- [x] Preparar lineamientos de empaquetado e imágenes para la plataforma final. El laboratorio ya admite tags explícitos vía `deploy.ps1 -ImageTag ...` y `k8s/scripts/bootstrap-kind.ps1`, y el lineamiento operativo quedó documentado en `k8s/IMAGE_PACKAGING.md` para abandonar `latest` fuera del carril local.
- [x] Documentar dependencias de red, almacenamiento y secretos que deberán resolverse en Kubernetes. Quedan explicitadas en `k8s/PORTABILITY_INVENTORY.md`.
- [x] Verificar compatibilidad futura con la imagen del producto de transformación de datos. Quedó explicitado que su carril compatible es imagen y `Deployment` separados, sin mezcla de ownership con broker ni web, tanto en `k8s/PORTABILITY_INVENTORY.md` como en `k8s/IMAGE_PACKAGING.md`.

### Carril opcional de laboratorio Kubernetes

Este carril puede ejecutarse antes del cierre formal de Fase 8, pero solo como validación temprana de portabilidad. No sustituye el baseline Compose-first ni debe mezclarse con la resolución de incidencias aún abiertas del runtime principal.

- [x] Mantener como prerequisito un baseline verde en Compose-first antes de introducir el laboratorio Kubernetes: smoke completo, import/export DynSec estable y reconciliación sin caída del broker.
- [x] El incidente DynSec que bloqueaba la portabilidad temprana quedó mitigado en el baseline actual mediante mejoras de caching, semántica de reinicio controlado y validaciones adicionales sobre `desired/applied/observed`, por lo que ya no bloquea el carril opcional.
- [x] No simular "nodo maestro" y "nodos worker" con contenedores ad hoc en Podman Compose; usar un clúster Kubernetes real pero efímero, preferentemente `kind`, sobre Podman si el entorno Windows lo soporta de forma estable.
- [x] Empezar con un laboratorio mínimo: `1` control-plane y `1-2` workers solo para validar scheduling, networking interno, secrets/config y lifecycle de los servicios BHM. El baseline actual ya opera con `1` control-plane y `1` worker, y en este corte suma además el `Deployment` separado de `bhm-alert-delivery`.
- [x] Mantener el laboratorio desacoplado del flujo diario: scripts y manifests separados del `docker-compose.dev.yml`, sin convertirlo en nuevo baseline de desarrollo mientras Fases 4-7 sigan abiertas.
- [x] Traducir explícitamente el control-plane actual a primitivas Kubernetes: `mosquitto.conf` como ConfigMap, TLS y `mosquitto_passwd` como Secret, `dynamic-security.json` como artefacto privado reconciliado por un componente broker-owned, y `broker_desired_state` sobre PostgreSQL persistente.
- [x] Validar en el laboratorio solo hipótesis de portabilidad: arranque, configuración, resolución DNS interna, health/readiness, persistencia y separación de ownership. El carril ya sirvió para validar bootstrap, runtime y exposición host-managed sin reemplazar Compose como baseline.

Estado actual del carril opcional:

- [x] El baseline Compose-first quedó verde antes de abrir el laboratorio: DynSec export/import estable de punta a punta y smoke `7/7 OK`.
- [x] Se abrió un scaffold inicial desacoplado en `k8s/` con `kind/cluster.yaml`, `k8s/base/` y `k8s/scripts/bootstrap-kind.ps1`.
- [x] El laboratorio actual ya quedó validado en runtime sobre `kind` + Podman con `1` control-plane y `1` worker, `bunkerm-platform 1/1`, `mosquitto 3/3` y `postgres 1/1`, además de `HTTP 200` en `http://localhost:22000/api/monitor/health` y conectividad TCP en `localhost:21900` y `localhost:29001`.
- [x] `Mosquitto` ya dejó de ser placeholder y quedó modelado como `StatefulSet` broker-owned con PVCs propios y sidecars `bhm-reconciler` y `bhm-broker-observability`; la exposición al host del laboratorio se estabilizó con `kubectl port-forward` gestionado en vez de depender de `NodePort/extraPortMappings` frágiles sobre Podman.
- [x] El handoff efímero de `create_client` ya se movió al control-plane PostgreSQL, lo que permitió separar el pod HTTP del broker en el laboratorio Kubernetes sin depender de un volumen compartido `/nextjs/data/reconcile-secrets`.
- [x] TLS y `mosquitto_passwd` ya tienen una traducción inicial a `Secret` dedicados de Kubernetes mediante bootstrap por `initContainer`, aunque la rotación y reconciliación nativa sobre objetos `Secret` siga pendiente como siguiente corte.
- [x] `deploy.ps1` y `k8s/scripts/bootstrap-kind.ps1` ya recuperan automaticamente una maquina Podman rota o sin socket util antes de invocar `kind`, evitando que el flujo limpio falle en `kind create cluster` por estado remoto corrupto del proveedor.
- [x] El bootstrap de `kind` ya carga las imagenes locales del laboratorio mediante `image-archive` cuando el proveedor es Podman, evitando la inconsistencia de `kind load docker-image` con tags canonicos `localhost/...`.
- [x] El flujo limpio `setup -> build -> start` ya supera el fallo original de creacion de cluster, crea el laboratorio, carga imagenes y aplica manifests sobre `kind`; el smoke validado vuelve a quedar verde para Web UI/API, MQTT TCP y MQTT WebSocket (`5/5 OK`).
- [x] El laboratorio ya traduce tambien el worker `bhm-alert-delivery` a `Deployment` separado en `k8s/base/alert-delivery.yaml`, alineando Kubernetes con el baseline Compose-first del outbox de alertas.
- [x] El inventario de portabilidad Compose -> Kubernetes ya quedó materializado en `k8s/PORTABILITY_INVENTORY.md`, con mapping de servicios, dependencias de red, secretos, almacenamiento y gaps transicionales visibles.
- [x] El nuevo `Deployment/bhm-alert-delivery` ya se aplico tambien sobre el laboratorio `kind` activo y completo `rollout` verde en `bhm-lab`, confirmando que este slice de portabilidad no queda solo como manifiesto estatico.
- [x] El laboratorio ya puede resolverse con tags de imagen explicitos sin editar YAML a mano: `deploy.ps1` y `bootstrap-kind.ps1` aceptan `-ImageTag`, y `k8s/base/kustomization.yaml` fija los nombres de imagen para que `kind` use el mismo artefacto construido y cargado.
- [x] La evolucion del reconciliador ya quedó verificada a nivel técnico: hoy permanece sidecar broker-owned por el coupling real a `/var/lib/mosquitto` y `/etc/mosquitto`, pero el daemon actual ya expone semantica reusable de control loop y ejecucion one-shot (`--once`) que habilita un paso posterior a `Job` o controlador.
- [x] `bhm-alert-delivery` ya suma hardening base de laboratorio con `startupProbe`, readiness funcional contra PostgreSQL y politicas minimas de recursos, reduciendo el gap entre manifiesto de laboratorio y workload portable.

### Siguientes focos recomendados tras el cierre de Fase 8

1. Mantener `kind` como carril de regresión y portabilidad del baseline ya cerrado, no como sustituto del flujo Compose-first para desarrollo diario.
2. Endurecer la operacion del laboratorio donde aun hay deuda visible: secret splitting por dominio, estrategia de Ingress/publicacion real, registro de imagenes fuera del entorno local y menor dependencia de `kubectl port-forward`.
3. Conservar la frontera broker-owned del reconciliador y usar el modo `--once` como seam de pruebas, evitando adelantar un operador remoto mientras la escritura real siga dependiendo del filesystem broker-local.
4. Usar el baseline de Kubernetes para detectar regresiones de empaquetado, bootstrap, readiness y networking interno antes de introducir nuevas capacidades funcionales sobre la plataforma.

### Verificaciones

- [x] Ninguna decisión crítica de Compose bloquea la evolución a Kubernetes en el baseline actual. Los gaps que quedan son transicionales y están explícitos en `k8s/PORTABILITY_INVENTORY.md`.
- [x] Existe inventario de objetos y capacidades requeridas para la migración posterior.
- [x] La estrategia de aplicación de cambios al broker tiene traducción razonable a Kubernetes. El baseline actual la expresa mediante `StatefulSet` broker-owned, sidecars y `Deployment` auxiliares donde no se requiere filesystem broker-local.
- [x] El laboratorio puede reusar artefactos de imagen versionados de forma coherente entre build, carga a `kind` y apply de manifests, sin reintroducir drift por `latest` oculto.
- [x] La evolución futura del reconciliador a `Job` o controlador ya tiene una frontera técnica explícita y verificable, aunque el writer broker-local siga dentro del pod broker-owned.

### Tests

- [x] Revisión técnica de portabilidad Compose -> Kubernetes. Queda recogida en `k8s/PORTABILITY_INVENTORY.md` y en los manifests ya materializados del laboratorio.
- [x] Validación documental del mapping de componentes a objetos de Kubernetes.
- [x] Validación de render del laboratorio con tags configurables mediante `kubectl kustomize k8s/base` y apply del `kind` activo usando el mismo tag de build.
- [x] Validación operativa del reconciliador en modo one-shot dentro del contenedor `reconciler`, comprobando que el loop actual también sirve como seam de reconciliación puntual.
- [x] Validación de rollout del worker `bhm-alert-delivery` tras endurecer probes y recursos en el laboratorio `kind` activo.

### Criterio de salida

- [x] El sistema queda sensiblemente más preparado para abordar la migración de plataforma cuando corresponda. El laboratorio ya cubre `platform`, `postgres`, `mosquitto`, sidecars broker-owned y `bhm-alert-delivery`, la evolución del reconciliador quedó verificada con frontera técnica explícita y el carril de empaquetado ya soporta tags de imagen configurables para validaciones repetibles.

---

## Fase 9 - Implementación posterior en Kubernetes

**Objetivo**: Materializar el primer baseline Kubernetes ejecutable de la arquitectura objetivo, incorporando el core BHM y el workload externo desacoplado sin romper los límites de ownership definidos en fases anteriores.

### Actividades previstas

- [x] Definir la topología final en Kubernetes. La topología mínima ya quedó fijada en `k8s/FINAL_TOPOLOGY.md`, incorporando `water-plant-simulator` como workload externo sin mezclar ownership con `bunkerm-platform` ni con `mosquitto`.
- [x] Integrar la imagen del producto de transformación de datos en la arquitectura objetivo. El primer carril ejecutable ya usa `water-plant-simulator` como `Deployment` externo en `k8s/base/water-plant-simulator.yaml`, con imagen local versionable y contrato exclusivamente MQTT.
- [x] Implementar manifests, charts o la estrategia de despliegue elegida. El baseline `k8s/base` ya incorpora el manifiesto del simulador, su `ConfigMap` de configuración y el flujo de empaquetado/carga de imagen para `kind`.
- [x] Adaptar secretos, almacenamiento persistente y networking al clúster objetivo. El simulador ya consume credenciales MQTT vía `Secret`, configuración vía `ConfigMap`, `emptyDir` para logs/estado y DNS interno hacia `mosquitto:1900`.
- [x] Validar la estrategia de reconciliación del broker en entorno Kubernetes. La convivencia con el workload externo mantiene el reconciliador broker-owned como sidecar y se revalidó con ejecución `--once --scope all` sobre el clúster refrescado.

### Verificaciones

- [x] La migración a Kubernetes se aborda con la arquitectura ya saneada, no como parche sobre el modelo anterior. El workload externo entra por MQTT y configuración propia, sin shared volumes ni regreso a escrituras cruzadas sobre el broker.

### Tests

- [x] Tests unitarios del healthcheck del simulador en `water-plant-simulator/tests/test_healthcheck.py`.
- [x] Validación de render `kubectl kustomize k8s/base` con la topología final ya incluyendo el simulador.
- [x] Build y despliegue real del laboratorio con tag explícito (`phase9-lab`), incluyendo `water-plant-simulator` como tercera imagen local cargada en `kind`.
- [x] Smoke del runtime `kind` tras recreación completa del clúster.
- [x] Validación de `rollout` de `deployment/water-plant-simulator` y comprobación de probes sobre archivos de estado/heartbeat del simulador.
- [x] Validación de logs del simulador confirmando conexión al broker MQTT interno del laboratorio.

### Evidencia reciente

- [x] El laboratorio final quedó ejecutando imágenes explícitas `phase9-lab`: `bunkerm-platform`, `bhm-alert-delivery` y los sidecars broker-owned con `localhost/bunkermtest-bunkerm:phase9-lab`, `mosquitto` con `localhost/bunkermtest-mosquitto:phase9-lab` y el workload externo con `localhost/water-plant-simulator:phase9-lab`.
- [x] `kubectl get pods -n bhm-lab` confirmó `postgres`, `mosquitto`, `bunkerm-platform`, `bhm-alert-delivery` y `water-plant-simulator` en `Running`, con `water-plant-simulator 1/1` y `mosquitto 3/3`.
- [x] Los logs del simulador confirmaron conexión real al broker interno del clúster: `Conectando a broker MQTT: mosquitto:1900...` seguido de `[OK] Conectado al broker MQTT: mosquitto:1900`, más arranque de `11` sensores, `4` actuadores y suscripciones a topics de comando.
- [x] La reconciliación broker-facing volvió a validarse en el entorno final con `kubectl exec ... services.broker_reconcile_daemon --once --scope all`, cerrando con `RECONCILE_ONCE_OK`.
- [x] Durante esta validación apareció inestabilidad del carril auxiliar de `kubectl port-forward` para exposición host-managed; no bloqueó el cierre de Fase 9 porque la verificación final se completó directamente sobre Kubernetes (`rollout`, `logs`, `exec`, healthchecks y estado de pods) y no sobre el helper de publicación local.

### Criterio de salida

- [x] Fase 9 queda cerrada para el alcance actual del proyecto: el despliegue objetivo en Kubernetes ya incorpora el core BHM y un workload externo desacoplado, con estrategia de empaquetado reproducible, networking/secretos adaptados y validación runtime sobre `kind`.

---

## Checklist global de control

### Documentación y gobierno

- [ ] Plan de migración aprobado.
- [ ] Arquitectura objetivo documentada.
- [ ] ADRs críticos redactados.
- [ ] Convenciones de código y comentarios explicitadas.

### Plataforma y despliegue

- [x] Stack funcional en Docker/Podman Compose.
- [x] Healthchecks revisados.
- [x] Variables de entorno racionalizadas.
- [x] Dependencias entre servicios simplificadas.

### Broker control-plane

- [x] Estado deseado definido.
- [x] Reconciliador definido e implementado.
- [x] Aplicación de cambios desacoplada del backend principal.
- [x] Detección de drift disponible.

### Persistencia

- [x] PostgreSQL introducido como persistencia principal.
- [x] Migración desde SQLite definida y validada.
- [x] Auditoría y reporting técnico migrados donde aplique.

### Observabilidad y seguridad

- [x] Observabilidad sin `tail -f` acoplado.
- [x] Reporting técnico separado del reporting de negocio.
- [x] Seguridad y secretos revisados.
- [x] Preparación para OAuth/OIDC documentada.

### Calidad y resiliencia

- [x] Smoke tests definidos.
- [x] Tests de integración por fase definidos.
- [x] Tests de carga y resiliencia ejecutados.
- [x] Estrategia de rollback definida por capability.

### Evolución futura

- [x] Portabilidad a Kubernetes revisada. Ya existe inventario Compose -> Kubernetes, traducción real del worker de alert delivery, lineamiento de empaquetado con tags explícitos y verificación técnica de la evolución del reconciliador.
- [x] Consideraciones para la imagen del producto de transformación de datos documentadas.

---

## Notas finales

Este plan prioriza hacer funcionar correctamente BHM como plataforma de microservicios sobre Docker/Podman Compose sin consolidar atajos que luego dificulten la migración a Kubernetes.

La decisión técnica más importante de la migración no es solo mover SQLite a PostgreSQL, sino sustituir el modelo actual de escritura directa sobre el broker por un control-plane desacoplado, auditable y portable.