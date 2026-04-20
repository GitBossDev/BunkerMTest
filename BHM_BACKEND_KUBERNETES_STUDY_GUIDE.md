# BHM - Guia de Estudio del Backend y la Logica de Microservicios en Kubernetes

> Documento de estudio
> Alcance: entender el backend actual, el control-plane, la topologia Kubernetes y los canales de comunicacion entre servicios
> Ultima actualizacion: 2026-04-20

---

## 1. Idea principal en una frase

BHM ya no se comporta como una aplicacion web que toca directamente los archivos internos del broker, sino como un control-plane que guarda estado deseado en PostgreSQL, lo reconcilia hacia Mosquitto mediante un componente broker-owned y observa el runtime por canales internos desacoplados.

---

## 2. Que problema resolvio esta migracion

Antes, una parte importante del backend hacia mutaciones directas sobre artefactos del broker como `mosquitto.conf`, `dynamic-security.json`, `mosquitto_passwd` o marcadores de reload. Ese modelo tenia varios problemas:

- el proceso web tenia demasiado poder sobre el broker
- habia acoplamiento fuerte al filesystem del contenedor
- era dificil auditar que se queria aplicar, que se aplico y que quedo realmente observado
- la traduccion a Kubernetes era mala porque el backend dependia de mounts y writers cruzados
- resultaba facil romper el broker desde una ruta HTTP si algo salia mal

La migracion cambia ese modelo por otro mas claro:

1. la API registra intencion de cambio
2. PostgreSQL guarda esa intencion como estado deseado auditable
3. un reconciliador broker-owned decide como aplicar el cambio real
4. el sistema compara lo deseado con lo aplicado y lo observado
5. la observabilidad del broker ya no depende del proceso web leyendo archivos locales

---

## 3. Mental model correcto

La mejor forma de pensar BHM hoy es separar el sistema en cuatro planos:

### Plano 1: producto y UX

- pantallas
- formularios
- tablas
- filtros
- estados de error/loading
- experiencia de usuario

Este plano entra principalmente por `bunkerm-platform`.

### Plano 2: control-plane

- recibe acciones HTTP
- valida payloads
- registra desired state
- expone estado `desired/applied/observed`
- consulta reporting, historicos y observabilidad ya desacoplada

Este plano vive en el backend de `bunkerm-platform` y usa PostgreSQL como datastore durable.

### Plano 3: broker-facing runtime

- aplica cambios reales al broker
- toca archivos o runtime local del broker solo desde componentes broker-owned
- hace rollback o deja error auditable cuando algo falla

Este plano vive dentro del pod de `mosquitto`, no en el pod web.

### Plano 4: workloads externos

- consumidores o productores de datos que no deben mezclarse con el ownership de BHM
- ejemplo actual: `greenhouse-simulator` como herramienta externa de carga MQTT

Estos workloads se integran por MQTT, HTTP o datos persistidos, pero no por volumen compartido con el broker.

---

## 4. Workloads actuales en Kubernetes

El baseline actual en `kind` despliega estos workloads:

| Workload | Tipo | Rol principal |
| --- | --- | --- |
| `bunkerm-platform` | `Deployment` | Punto de entrada HTTP del producto, UI y API |
| `postgres` | `StatefulSet` | Persistencia durable del control-plane, historicos, reporting y outbox |
| `mosquitto` | `StatefulSet` | Broker MQTT y ownership broker-local |
| `reconciler` | sidecar en `mosquitto` | Aplicacion broker-facing de desired state |
| `observability` | sidecar en `mosquitto` | Lectura broker-owned de logs, config y artefactos observados |
| `bhm-alert-delivery` | `Deployment` | Worker que consume outbox y hace delivery externo |
| `greenhouse-simulator` | herramienta externa | Carga MQTT externa usada fuera del baseline persistente |

---

## 5. Como pensar cada workload

### `bunkerm-platform`

No es solo una pagina web. Es el punto donde viven:

- frontend del producto
- backend HTTP
- validaciones de entrada
- consultas de historicos y reporting
- escritura de desired state al control-plane

Lo importante es lo que ya no hace:

- no escribe directamente archivos del broker
- no es owner del filesystem de Mosquitto
- no aplica DynSec o config broker-facing por su cuenta

### `postgres`

Es la memoria durable del sistema. Aqui viven, segun el dominio:

- control-plane del broker
- auditoria
- historicos tecnicos
- reporting
- outbox de alertas

Si quieres entender por que el sistema es mas portable hoy, la respuesta mas corta es: el estado importante ya no depende de SQLite local ni del filesystem implicito del contenedor web.

### `mosquitto`

Sigue siendo stateful por naturaleza. No se intento volverlo un componente falso-stateless. El cambio fue otro: delimitar mejor quien puede modificarlo.

### Sidecar `reconciler`

Su trabajo es leer el desired state pendiente o con drift y convertirlo en cambios reales sobre el broker.

Esta dentro del pod broker-owned porque aun necesita acceso broker-local a:

- `/var/lib/mosquitto`
- `/etc/mosquitto`

Por eso hoy no conviene moverlo a un `Deployment` remoto ni fingir un operador completo si todavia pisaria el filesystem del broker desde fuera.

### Sidecar `observability`

Este sidecar existe para que el web backend no lea directamente:

- logs del broker
- `mosquitto.conf`
- `dynamic-security.json`
- `mosquitto_passwd`
- otros artefactos observados broker-facing

En vez de eso, el sidecar expone una API HTTP interna y el backend consume esa lectura desacoplada.

### `bhm-alert-delivery`

Separa deteccion de alerta y envio externo. La idea es simple:

- `bhm-api` detecta la alerta
- persiste evento canonicamente en PostgreSQL
- `bhm-alert-delivery` consume el outbox
- el worker resuelve canal, reintentos e idempotencia

Eso evita hacer delivery en el hilo sincrono del request original.

### `greenhouse-simulator`

Es el ejemplo concreto del workload externo desacoplado. Sirve para validar que la arquitectura ya admite otro producto o consumidor sin mezclar ownership.

Sus reglas son importantes:

- no comparte volumen con BHM
- no entra en el pod broker-owned
- no usa acceso directo a PostgreSQL de BHM para control-plane
- se conecta al broker por MQTT

---

## 6. Diagrama mental rapido

```text
Usuario/Navegador
        |
        | HTTP
        v
  bunkerm-platform
    |        |
    |        +------------------------------+
    |                                       |
    | SQL                                   | HTTP interno
    v                                       v
 postgres                           observability sidecar
    ^                                       ^
    |                                       |
    | SQL / desired state                   | lectura read-only
    |                                       |
 reconciler sidecar --------------------> mosquitto
    |                cambios broker-facing      ^
    |                                           |
    +---------------- MQTT / runtime -----------+

greenhouse-simulator ---------------------> mosquitto

bhm-alert-delivery <---------------------- postgres
        |
        +---- SMTP / webhook / delivery externo
```

---

## 7. Canales de comunicacion reales

Esta es la parte mas importante para estudiar la arquitectura actual sin confundirse.

### Canal 1: HTTP usuario -> plataforma

El usuario entra por `bunkerm-platform`.

- puerto del servicio: `2000`
- en laboratorio existe `NodePort 32000`
- tambien se uso `kubectl port-forward` como ayuda de acceso host-managed

Todo lo que B toca desde frontend vive sobre este canal.

### Canal 2: plataforma -> PostgreSQL

`bunkerm-platform` habla con `postgres` por SQL.

Aqui caen:

- desired state
- auditoria
- historicos
- reporting
- outbox de alertas

Este canal es el corazon del nuevo backend porque separa intencion durable de aplicacion runtime.

### Canal 3: reconciler -> PostgreSQL

El reconciliador consulta que trabajo pendiente existe, que version debe aplicar y que drift hay.

No depende del router HTTP para decidir que hacer. Esa es una mejora arquitectonica clave.

### Canal 4: reconciler -> broker local

Este es el canal broker-facing real.

Aqui se aplican cambios sobre:

- DynSec
- `mosquitto.conf`
- `mosquitto_passwd`
- certificados TLS
- señales de reload

Este canal sigue siendo broker-local, por eso el reconciliador sigue como sidecar y no como controlador remoto puro.

### Canal 5: observability sidecar -> plataforma

El sidecar de observabilidad expone HTTP interno en el pod broker-owned. En el manifiesto actual, el servicio interno del broker publica tambien el puerto `9102` para esta lectura.

La plataforma consume ese canal para leer informacion observada sin tocar los archivos del broker directamente.

### Canal 6: plataforma -> mosquitto

La plataforma sigue pudiendo hablar con el broker por los contratos de producto que correspondan, pero ya no como writer principal del filesystem del broker.

### Canal 7: simulator -> mosquitto

`greenhouse-simulator` se conecta al broker por `localhost:21900` desde Windows o por `bhm-lab-control-plane:31900` cuando corre en contenedor unido a la red `kind`:

- host: `mosquitto`
- puerto: `1900`

Ese workload publica y consume MQTT como un actor externo realista.

### Canal 8: alert-delivery -> mundo externo

El worker de delivery sale a canales externos como:

- SMTP
- webhook

El punto clave es que el frontend administra canales y visualiza intentos, pero el envio real vive en el worker dedicado.

---

## 8. La logica de control-plane paso a paso

La pieza conceptual mas importante del sistema es esta.

### Paso 1: llega una intencion de cambio

Ejemplo:

- crear cliente DynSec
- cambiar ACL por defecto
- subir certificado TLS
- cambiar politica de whitelist

### Paso 2: el backend valida y persiste desired state

El backend no deberia pensar "voy a escribir ahora mismo el archivo del broker".

Deberia pensar:

"voy a registrar cual es el estado que el sistema quiere alcanzar".

### Paso 3: el reconciliador intenta converger el broker al estado deseado

Si puede aplicar el cambio, actualiza estado aplicado.

Si falla:

- deja error auditable
- puede hacer rollback segun la capability
- no obliga a que el router HTTP sea el punto de aplicacion directa

### Paso 4: el sistema expone estado observado

No alcanza con saber que alguien pidio un cambio. Hay que saber que quedo realmente en runtime.

Por eso aparecen conceptos como:

- `desired`
- `applied`
- `observed`
- `drift`

### Paso 5: la UI o los operadores consultan status

Esto permite pantallas tecnicas y debugging sin tener que entrar manualmente al contenedor a inspeccionar archivos.

---

## 9. Diferencia entre desired, applied y observed

Este glosario vale oro para entender el backend.

### Desired state

Es lo que BHM quiere que exista.

Ejemplo: "el cliente `sensor-01` debe estar habilitado y tener cierto rol".

### Applied state

Es lo ultimo que el reconciliador cree haber aplicado con exito.

No siempre garantiza que el runtime siga igual, pero registra la ultima convergencia conocida.

### Observed state

Es lo que el sistema logro leer del runtime real.

Ejemplo: el contenido actual del documento DynSec o el estado real de una policy.

### Drift

Es la diferencia entre lo deseado y lo observado.

Cuando hay drift, el reconciliador tiene trabajo pendiente aunque nadie haya hecho un request nuevo.

---

## 10. Donde entra whitelist por IP

Whitelist es util para estudiar porque muestra bien la separacion entre UX, contrato y enforcement real.

Hoy ya existe contrato HTTP estable para:

- `GET /api/v1/security/ip-whitelist`
- `PUT /api/v1/security/ip-whitelist`
- `GET /api/v1/security/ip-whitelist/status`

Eso permite a frontend trabajar sobre:

- edicion del documento
- modos `disabled`, `audit`, `enforce`
- entries por scope
- estado visible del enforcement

Pero eso no significa que frontend o backend web deban aplicar por si mismos el enforcement broker-facing para `mqtt_clients`.

Esa frontera sigue perteneciendo al control-plane y al carril broker-owned.

---

## 11. Donde entra alert delivery

Las alertas muestran otra separacion importante: detectar no es lo mismo que entregar.

### Deteccion

La API y el monitor detectan estados como alertas del broker.

### Persistencia

Se guarda un evento canonico y auditable en PostgreSQL.

### Entrega

`bhm-alert-delivery` consume el outbox y registra intentos por canal.

### Consumo desde UX

Frontend trabaja sobre:

- canales
- eventos
- intentos
- exportaciones
- estados funcionales

No necesita conocer detalles internos del retry loop para construir una buena experiencia de usuario.

---

## 12. Donde entran historicos y reporting tecnico

Estos dominios ya no deberian pensarse como "leer SQLite del monolito".

Ahora deben pensarse como:

- lectura desde PostgreSQL
- servicios y routers dedicados
- observabilidad desacoplada del broker
- contratos HTTP mas estables para frontend

Por eso B puede trabajar sobre filtros, tablas y exportaciones sin tocar la capa de persistencia.

---

## 13. Que significa que el reconciliador siga como sidecar

No significa que la arquitectura este incompleta. Significa que se respeto una frontera tecnica real.

Mientras la aplicacion efectiva del broker dependa de archivos broker-locales, mover el writer fuera del pod seria crear un acoplamiento falso o peligroso.

Entonces el modelo correcto es:

- decision y desired state: desacoplados del router HTTP
- writer real: broker-owned
- evolucion futura: posible hacia `Job` o controlador cuando el writer broker-local quede mas encapsulado

---

## 14. Compose-first vs Kubernetes

La idea no fue tirar Compose y reescribir todo para Kubernetes. La idea fue usar Compose-first para sanear la arquitectura y luego traducirla mejor.

Ejemplos de traduccion:

- `bhm-alert-delivery` paso de proceso auxiliar a `Deployment`
- `postgres` paso naturalmente a `StatefulSet`
- `mosquitto` paso a `StatefulSet` con sidecars broker-owned
- el empaquetado usa tags explicitos para evitar drift entre build y cluster

La leccion importante es esta: Kubernetes vino despues de corregir ownership y contratos, no antes.

---

## 15. Que sigue siendo transicional

Aunque el baseline actual ya es fuerte, todavia hay deuda visible:

- la publicacion host-managed con `kubectl port-forward` sigue siendo inestable en el laboratorio Windows + Podman
- la separacion final de secretos por dominio todavia puede endurecerse
- la estrategia final de Ingress/publicacion aun no es el contrato definitivo
- el reconciliador todavia depende de filesystem broker-local para la mutacion real
- las imagenes siguen pensadas para laboratorio local; falta carril de registry real como siguiente paso natural

Esto no invalida la arquitectura. Solo marca donde esta el siguiente trabajo serio de plataforma.

---

## 16. Glosario rapido

### BHM

Broker Health Manager. Producto de gestion tecnica del broker.

### Control-plane

Capa que decide y registra que deberia existir, sin ser necesariamente la que aplica el cambio final de runtime.

### Broker-owned

Componente que vive del lado del broker y conserva ownership sobre artefactos locales del broker.

### Desired state

Estado que el sistema quiere alcanzar.

### Applied state

Ultimo estado que el reconciliador cree haber aplicado con exito.

### Observed state

Estado real que el sistema logra leer del runtime.

### Drift

Diferencia entre desired y observed.

### Outbox

Tabla o flujo durable de eventos pendientes de entrega asincrona.

### Sidecar

Contenedor que vive en el mismo pod que otro componente principal para compartir lifecycle y cercania operativa.

### StatefulSet

Objeto de Kubernetes pensado para workloads stateful con identidad y almacenamiento persistente mas estable.

### Deployment

Objeto de Kubernetes pensado para workloads mas facilmente reemplazables y normalmente stateless o casi stateless.

---

## 17. Resumen final para estudiar

Si tuvieras que memorizar solo cinco ideas, que sean estas:

1. BHM ya no gobierna al broker escribiendo archivos directamente desde la web.
2. PostgreSQL es la base durable del control-plane, auditoria, historicos, reporting y outbox.
3. El reconciliador aplica cambios reales al broker desde un contexto broker-owned.
4. La observabilidad del broker ya no depende de que el backend web comparta el filesystem del broker.
5. Kubernetes ya tiene un baseline real en el repo y valida que esta separacion funciona tambien fuera de Compose.

Si entiendes esas cinco ideas, ya entiendes el mapa mental principal del cambio arquitectonico.