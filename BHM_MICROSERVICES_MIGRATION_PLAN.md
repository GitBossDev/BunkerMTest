# BHM - Plan de Migración a Microservicios

> **Proyecto**: BHM (Broker Health Manager)
> **Objetivo**: Migrar la solución actual a una arquitectura de microservicios, operativa primero sobre Docker/Podman Compose y preparada para una evolución posterior a Kubernetes.
> **Última actualización**: 2026-04-14

---

## Propósito

Este documento define las fases de trabajo, el orden recomendado de ejecución y el checklist operativo para migrar BHM hacia una arquitectura más desacoplada, portable y mantenible.

El objetivo inmediato es que los contenedores funcionen correctamente en Docker/Podman con límites claros entre servicios. La migración futura a Kubernetes se considera una etapa posterior, por lo que cada decisión de esta hoja de ruta debe evitar acoplamientos que dificulten esa evolución.

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
| 9 | Implementación posterior en Kubernetes | Ejecutar la migración de plataforma con la imagen del producto de transformación de datos | Fuera del alcance inmediato |

---

## Fase 0 - Preparación y gobierno técnico

**Objetivo**: Alinear el trabajo, el lenguaje común y las reglas de ejecución antes de tocar la arquitectura.

### Actividades

- [x] Confirmar que el nombre oficial del producto es BHM (Broker Health Manager) en la documentación nueva.
- [x] Identificar documentación vigente que siga describiendo el sistema como BunkerM y marcarla para actualización progresiva.
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
- [x] `water-plant-simulator/README.md` - referencia histórica pendiente de alineación futura.
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
- [ ] Eliminar dependencias no necesarias entre contenedores.
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
- [ ] El backend de gestión no depende de escribir directamente en archivos del broker para arrancar.

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
- [x] `deploy.ps1 -Action smoke` terminó en `5/5 OK` después de endurecer el check autenticado de DynSec frente a timing de arranque.
- [x] `GET /login` respondió `200 OK` y devolvió la pantalla de autenticación de Next.js.
- [x] `POST /api/auth/login` con las credenciales iniciales dejó una cookie de sesión reutilizable en `http://localhost:2000` tras ajustar la política `Secure` al esquema real de `FRONTEND_URL`.
- [x] `GET /api/auth/me` respondió `200 OK` con sesión autenticada y `GET /dashboard` devolvió contenido autenticado del dashboard.
- [x] El runtime activo expone `2000/tcp` para la plataforma y `1900/tcp`, `9001/tcp` para el broker.
- [x] Dos reinicios controlados mantuvieron estable el hash de `dynamic-security.json`, confirmando que el entrypoint del broker dejó de reescribir el archivo cuando no hay cambios efectivos de credenciales.
- [x] El broker registró `Credentials already synchronized for admin`, confirmando sincronización idempotente en arranque.

### Hallazgos abiertos

- [ ] El backend actual sigue acoplado a `dynamic-security.json`, `mosquitto.conf` y logs compartidos; la verificación de arranque sin escritura/lectura directa del filesystem del broker sigue pendiente y se resolverá en Fase 3.
- [x] El smoke test de `deploy.ps1` fue endurecido con reintentos en la llamada autenticada a DynSec porque el hot-patch posterior al arranque puede introducir una ventana corta de falso negativo.
- [x] La cookie de autenticación del frontend ya no fuerza `Secure` en el baseline HTTP local; se usa cookie segura automáticamente cuando `FRONTEND_URL` es `https`.

### Criterio de salida

- [ ] BHM funciona correctamente como stack Compose-first y deja de depender de supuestos de despliegue monolítico.

---

## Fase 3 - Broker control-plane y aplicación de cambios

**Objetivo**: Sustituir la escritura directa sobre `mosquitto.conf`, `dynamic-security.json` y otros artefactos del broker por un flujo basado en estado deseado y reconciliación.

### Actividades

- [ ] Diseñar el modelo de estado deseado para configuración del broker.
- [ ] Diseñar el modelo de estado deseado para clientes, roles, grupos y ACLs.
- [ ] Definir el servicio o worker reconciliador responsable de aplicar cambios al broker.
- [ ] Separar configuración deseada, configuración generada, estado aplicado y estado observado.
- [ ] Diseñar detección de drift entre el estado deseado y el estado real del broker.
- [ ] Rediseñar los endpoints de gestión para que soliciten cambios en lugar de escribir archivos directamente.
- [ ] Definir estrategia de aplicación de cambios en Docker/Podman Compose.
- [ ] Definir equivalencia conceptual para Kubernetes, aunque la implementación llegue más adelante.
- [x] Evaluar si un laboratorio local de Kubernetes agrega valor en Fase 3 o si debe mantenerse fuera del camino crítico.
- [ ] Replantear la gestión de bridges y certificados dentro del mismo modelo de reconciliación.
- [ ] Definir rollback para cambios fallidos al broker.

### Primer corte implementado

- [x] Se introdujo la tabla transicional `broker_desired_state` para persistir estado deseado/aplicado/observado del control-plane antes de la migración a PostgreSQL.
- [x] `PUT /api/v1/dynsec/default-acl` dejó de dual-escribir desde el router y ahora registra estado deseado antes de reconciliar.
- [x] Se implementó un primer reconciliador de aplicación para `defaultACLAccess`, encapsulado en servicio y con detección básica de drift.
- [x] Se añadió `GET /api/v1/dynsec/default-acl/status` para auditar `desired`, `applied`, `observed`, `status`, `version` y `lastError`.
- [x] El primer corte usa SQLite transicional como soporte de estado deseado; PostgreSQL sigue siendo el destino definitivo de Fase 4.

### Consideraciones Docker/Podman ahora

- [x] El primer reconciliador de `defaultACLAccess` es compatible con el runtime Compose-first actual.
- [ ] La solución no debe depender de que el backend principal comparta ownership del filesystem del broker.
- [ ] Si existe un volumen persistente del broker, su manipulación efectiva debe quedar encapsulada en el componente que aplica cambios.

### Consideraciones Kubernetes después

- [ ] El modelo de estado deseado debe poder mapearse a ConfigMaps, Secrets, CRDs o un operador más adelante.
- [ ] La semántica de reconciliación no debe depender de comandos ad hoc imposibles de portar a Kubernetes.
- [ ] La aplicación de certificados y bridges debe poder evolucionar a secretos gestionados por la plataforma.
- [x] Se documentó que un clúster local de Kubernetes puede usarse más adelante como carril opcional de validación, pero no como baseline obligatorio de Fase 3.

### Decisión aplicada en esta fase

- [x] Se evaluó el uso de un clúster local de Kubernetes sobre Docker/Podman.
- [x] Se decidió no incorporarlo ahora como entorno principal porque no resuelve la deuda del control-plane y añade complejidad operativa en Windows + Podman remoto.
- [x] Si se habilita una validación temprana de Kubernetes antes de Fase 8, la opción preferida será `kind` como laboratorio efímero y no `minikube` con driver Podman.

### Verificaciones

- [x] Un cambio de configuración puede solicitarse desde la API sin escritura directa del backend sobre rutas internas del broker para el caso de `defaultACLAccess`.
- [x] El estado aplicado y el estado observado pueden auditarse para `defaultACLAccess` mediante `GET /api/v1/dynsec/default-acl/status`.
- [ ] Existe trazabilidad de cambios y rollback básico.

### Tests

- [x] Test unitario del modelo de estado deseado para `defaultACLAccess`.
- [x] Test unitario del reconciliador de `defaultACLAccess`.
- [ ] Test de integración de aplicación de cambios al broker.
- [ ] Test de rollback cuando la reconciliación falla.
- [x] Test de drift detection para `defaultACLAccess`.

### Evidencia reciente

- [x] Se añadió `services/broker_desired_state_service.py` como primer servicio transicional de control-plane.
- [x] Se añadió el modelo ORM `BrokerDesiredState` en el backend unificado.
- [x] La suite enfocada `pytest tests/test_dynsec.py -q` terminó en `18 passed`.

### Criterio de salida

- [ ] BHM deja de gestionar el broker mediante escritura cruzada y pasa a un control-plane compatible con Compose hoy y Kubernetes mañana.

---

## Fase 4 - Persistencia PostgreSQL por bounded context

**Objetivo**: Migrar el estado operativo y la configuración persistente de BHM desde SQLite a PostgreSQL sin romper la operación.

### Actividades

- [ ] Definir el esquema PostgreSQL para el bounded context de BHM.
- [ ] Mantener la base de datos separada del producto externo de reporting/transformación.
- [ ] Crear estrategia de migración incremental desde SQLite.
- [ ] Decidir si la migración será por tablas, por capacidades o con doble escritura temporal.
- [ ] Introducir una capa de persistencia que abstraiga SQLite/PostgreSQL durante la transición.
- [ ] Migrar broker history, topic history, client activity y reporting técnico.
- [ ] Migrar también la configuración deseada del broker, cambios solicitados y auditoría.
- [ ] Añadir migraciones de esquema y versionado de base de datos.
- [ ] Ajustar configuración de entorno, backup y restore para PostgreSQL.

### Verificaciones

- [ ] BHM puede operar con PostgreSQL como datastore principal.
- [ ] No existen accesos directos de dominio al SQLite antiguo en flujos ya migrados.
- [ ] Los datos históricos y operativos esenciales se conservan.

### Tests

- [ ] Test unitario de repositorios y servicios de persistencia.
- [ ] Test de integración contra PostgreSQL real en contenedor.
- [ ] Test de migración de datos desde SQLite.
- [ ] Test de compatibilidad de API en endpoints afectados.
- [ ] Test de rollback o recuperación ante fallo de migración.

### Criterio de salida

- [ ] PostgreSQL queda establecido como base persistente principal de BHM en los dominios migrados.

---

## Fase 5 - Observabilidad y reporting técnico desacoplado

**Objetivo**: Eliminar la dependencia de log tailing directo y construir observabilidad compatible con microservicios.

### Actividades

- [ ] Sustituir el uso de `tail -f` y lectura directa de logs compartidos como mecanismo principal.
- [ ] Definir si la observabilidad técnica irá por collector, pipeline de logs o eventos técnicos estructurados.
- [ ] Separar reporting técnico de BHM del reporting de negocio del otro producto.
- [ ] Ajustar el pipeline de incidentes, timeline y reporting operativo para la nueva fuente de datos.
- [ ] Definir métricas, logs y eventos mínimos por servicio.
- [ ] Revisar retención, purga y exportaciones del reporting técnico.

### Verificaciones

- [ ] Monitoring y reporting técnico siguen funcionando sin mounts cruzados obligatorios de logs.
- [ ] Las incidencias técnicas continúan disponibles para auditoría y diagnóstico.
- [ ] El producto externo no depende de leer internamente la observabilidad de BHM.

### Tests

- [ ] Test de integración de ingesta de eventos/logs técnicos.
- [ ] Test de reporting técnico sobre la nueva fuente de datos.
- [ ] Test de purga y retención.
- [ ] Test de exportación CSV/JSON si sigue aplicando.

### Criterio de salida

- [ ] La observabilidad de BHM es compatible con una arquitectura de microservicios y deja de depender de lecturas acopladas al broker.

---

## Fase 6 - Seguridad e identidad técnica

**Objetivo**: Reordenar autenticación y autorización para soportar el nuevo modelo sin bloquear la migración principal.

### Actividades

- [ ] Separar identidad humana de gestión, identidad service-to-service y credenciales MQTT.
- [ ] Mantener temporalmente el mecanismo actual si es necesario, con una ruta clara de endurecimiento.
- [ ] Diseñar puntos de extensión para OAuth2/OpenID Connect en una fase posterior.
- [ ] Revisar secretos, rotación y manejo seguro de credenciales en Compose.
- [ ] Diseñar cómo evolucionará ese manejo de secretos cuando se pase a Kubernetes.

### Verificaciones

- [ ] Los flujos actuales de acceso siguen funcionando.
- [ ] Los secretos y credenciales tienen ownership y almacenamiento claros.
- [ ] La arquitectura no queda bloqueada por esperar OAuth/OIDC.

### Tests

- [ ] Test de autenticación en endpoints críticos.
- [ ] Test de autorización en endpoints administrativos.
- [ ] Test de acceso denegado y auditoría básica.

### Criterio de salida

- [ ] La seguridad acompaña la migración sin introducir nuevos acoplamientos ni bloquear el avance principal.

---

## Fase 7 - Hardening, rendimiento y resiliencia

**Objetivo**: Consolidar el comportamiento stateless del backend de gestión y establecer baseline de carga y estabilidad.

### Actividades

- [ ] Definir baseline del sistema actual antes de cambios mayores.
- [ ] Medir throughput MQTT, latencia de API, latencia de reporting técnico y tiempo de aplicación de cambios al broker.
- [ ] Medir consumo de CPU, memoria y almacenamiento por servicio.
- [ ] Validar reinicios, recuperación y comportamiento ante fallos parciales.
- [ ] Validar que el backend de gestión puede operar sin estado local exclusivo.
- [ ] Definir feature flags, estrategia de rollout y rollback por capability.

### Verificaciones

- [ ] Existen métricas de referencia antes y después de cada cambio mayor.
- [ ] El sistema soporta reinicios controlados sin pérdida de operación esencial.
- [ ] La degradación ante fallo parcial es entendible y observable.

### Tests

- [ ] Test de carga MQTT.
- [ ] Test de churn de clientes.
- [ ] Test de bursts de publish.
- [ ] Test de concurrencia sobre APIs críticas.
- [ ] Test de resiliencia tras restart de servicios.

### Criterio de salida

- [ ] BHM dispone de una base objetiva de rendimiento y resiliencia para continuar la evolución de plataforma.

---

## Fase 8 - Preparación para Kubernetes

**Objetivo**: Cerrar la migración Compose-first dejando preparada la transición posterior a Kubernetes.

### Actividades

- [ ] Revisar qué configuraciones de Compose deben transformarse después en objetos de Kubernetes.
- [ ] Identificar futuras necesidades de ConfigMaps, Secrets, PVCs, Deployments, StatefulSets, Jobs u operador.
- [ ] Verificar que el reconciliador del broker puede evolucionar a patrón operador/control loop.
- [ ] Preparar lineamientos de empaquetado e imágenes para la plataforma final.
- [ ] Documentar dependencias de red, almacenamiento y secretos que deberán resolverse en Kubernetes.
- [ ] Verificar compatibilidad futura con la imagen del producto de transformación de datos.

### Verificaciones

- [ ] Ninguna decisión crítica de Compose bloquea la evolución a Kubernetes.
- [ ] Existe inventario de objetos y capacidades requeridas para la migración posterior.
- [ ] La estrategia de aplicación de cambios al broker tiene traducción razonable a Kubernetes.

### Tests

- [ ] Revisión técnica de portabilidad Compose -> Kubernetes.
- [ ] Validación documental del mapping de componentes a objetos de Kubernetes.

### Criterio de salida

- [ ] El sistema queda listo para abordar la migración de plataforma cuando corresponda.

---

## Fase 9 - Implementación posterior en Kubernetes

**Objetivo**: Ejecutar más adelante la migración de despliegue a Kubernetes junto con la imagen del producto de transformación de datos.

### Actividades previstas

- [ ] Definir la topología final en Kubernetes.
- [ ] Integrar la imagen del producto de transformación de datos en la arquitectura objetivo.
- [ ] Implementar manifests, charts o la estrategia de despliegue elegida.
- [ ] Adaptar secretos, almacenamiento persistente y networking al clúster objetivo.
- [ ] Validar la estrategia de reconciliación del broker en entorno Kubernetes.

### Verificaciones

- [ ] La migración a Kubernetes se aborda con la arquitectura ya saneada, no como parche sobre el modelo anterior.

### Tests

- [ ] Quedan fuera del alcance inmediato de este plan y se detallarán en una hoja específica cuando empiece esa etapa.

### Criterio de salida

- [ ] Fase diferida. No bloquea la ejecución del plan actual.

---

## Checklist global de control

### Documentación y gobierno

- [ ] Plan de migración aprobado.
- [ ] Arquitectura objetivo documentada.
- [ ] ADRs críticos redactados.
- [ ] Convenciones de código y comentarios explicitadas.

### Plataforma y despliegue

- [ ] Stack funcional en Docker/Podman Compose.
- [ ] Healthchecks revisados.
- [ ] Variables de entorno racionalizadas.
- [ ] Dependencias entre servicios simplificadas.

### Broker control-plane

- [ ] Estado deseado definido.
- [ ] Reconciliador definido e implementado.
- [ ] Aplicación de cambios desacoplada del backend principal.
- [ ] Detección de drift disponible.

### Persistencia

- [ ] PostgreSQL introducido como persistencia principal.
- [ ] Migración desde SQLite definida y validada.
- [ ] Auditoría y reporting técnico migrados donde aplique.

### Observabilidad y seguridad

- [ ] Observabilidad sin `tail -f` acoplado.
- [ ] Reporting técnico separado del reporting de negocio.
- [ ] Seguridad y secretos revisados.
- [ ] Preparación para OAuth/OIDC documentada.

### Calidad y resiliencia

- [ ] Smoke tests definidos.
- [ ] Tests de integración por fase definidos.
- [ ] Tests de carga y resiliencia ejecutados.
- [ ] Estrategia de rollback definida por capability.

### Evolución futura

- [ ] Portabilidad a Kubernetes revisada.
- [ ] Consideraciones para la imagen del producto de transformación de datos documentadas.

---

## Notas finales

Este plan prioriza hacer funcionar correctamente BHM como plataforma de microservicios sobre Docker/Podman Compose sin consolidar atajos que luego dificulten la migración a Kubernetes.

La decisión técnica más importante de la migración no es solo mover SQLite a PostgreSQL, sino sustituir el modelo actual de escritura directa sobre el broker por un control-plane desacoplado, auditable y portable.