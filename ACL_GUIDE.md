# Guía de ACL — BunkerM

## Índice

1. [Conceptos clave](#1-conceptos-clave)
2. [Tipos de ACL disponibles](#2-tipos-de-acl-disponibles)
3. [Default ACL Access](#3-default-acl-access)
4. [Cómo funciona la evaluación de permisos](#4-cómo-funciona-la-evaluación-de-permisos)
5. [Casos de uso prácticos](#5-casos-de-uso-prácticos)
6. [Configuración actual del proyecto](#6-configuración-actual-del-proyecto)

---

## 1. Conceptos clave

BunkerM usa el módulo **Dynamic Security** de Mosquitto para controlar qué clientes MQTT pueden publicar o suscribirse a qué topics. El sistema tiene tres capas:

```
Cliente MQTT
    └─► pertenece a un Grupo (opcional)
             └─► tiene un Rol asignado
                      └─► el Rol lleva reglas ACL (allow/deny por topic)
                               └─► si ninguna regla aplica → se usa el Default ACL Access
```

**Rol**: conjunto de reglas ACL. Un cliente puede tener varios roles; se evalúan en orden de prioridad.

**Regla ACL**: combinación de `[tipo] [topic] [allow|deny]`. Cuando un cliente intenta publicar o suscribirse, Mosquitto recorre las reglas del rol en orden hasta encontrar una que aplique.

**Default ACL Access**: permiso de último recurso cuando ninguna regla de ningún rol cubre la operación. Es global para todos los clientes.

---

## 2. Tipos de ACL disponibles

Hay 6 tipos de ACL, divididos en 3 categorías:

### Publicación

| Tipo | Qué controla |
|------|-------------|
| `publishClientSend` | Si el cliente puede **enviar** un mensaje al broker (publicar) |
| `publishClientReceive` | Si el broker puede **entregar** ese mensaje a este cliente como receptor |

> **Diferencia práctica**: `Send` se aplica al publicador; `Receive` se aplica al suscriptor cuando recibe un mensaje publicado por otro cliente. En la mayoría de casos solo necesitas `Send`.

### Suscripción

| Tipo | Qué controla |
|------|-------------|
| `subscribeLiteral` | Suscripción a un topic **exacto** (sin wildcards). Ejemplo: `plant/water-plant-1/temperature` |
| `subscribePattern` | Suscripción a un topic con **wildcards** (`+` y `#`). Ejemplo: `plant/water-plant-1/#` |

> **Diferencia clave**:
> - `subscribeLiteral` → la cadena del topic debe coincidir exactamente carácter a carácter.
> - `subscribePattern` → se evalúa como patrón MQTT, donde `+` es un nivel y `#` es "el resto".
>
> Si un cliente se suscribe a `plant/#`, usa `subscribePattern`. Si se suscribe a `plant/sensor1`, puede usar `subscribeLiteral`.

### Desuscripción

| Tipo | Qué controla |
|------|-------------|
| `unsubscribeLiteral` | Permitir/denegar que el cliente se desuscriba de un topic exacto |
| `unsubscribePattern` | Permitir/denegar que el cliente se desuscriba de un patrón con wildcards |

> Las reglas de unsubscribe raramente se usan. Solo son necesarias si quieres impedir que ciertos clientes se desuscriban de topics críticos (p. ej. clientes de auditoría obligatoria).

---

## 3. Default ACL Access

Accesible en **Settings → Default ACL Access** o en **DynSec Config**.

Controla el permiso de **fallback** para las 4 operaciones fundamentales:

| Parámetro | Descripción | Valor recomendado para producción |
|-----------|-------------|----------------------------------|
| **Publish (Client Send)** | Permiso por defecto para publicar | `Allow` (los dispositivos IoT necesitan publicar) |
| **Publish (Client Receive)** | Permiso por defecto para recibir mensajes | `Allow` |
| **Subscribe** | Permiso por defecto para suscribirse | ⚠️ **`Deny`** — crítico para la seguridad |
| **Unsubscribe** | Permiso por defecto para desuscribirse | `Allow` |

### Por qué el `Subscribe` debe ser `Deny`

Con `Subscribe = Allow` (valor de instalación por defecto de Mosquitto):

```
Cliente "legacy" tiene rol con: subscribeLiteral plant/water-plant-1/legacy/# Allow
                                 subscribeLiteral #                          Deny

Resultado real: puede suscribirse a plant/water-plant-1/legacy/# ✓
                pero también puede suscribirse a cualquier otro topic ✗
                porque si no hay regla que deniegue exacta, el fallback es Allow
```

Con `Subscribe = Deny`:

```
Cliente "legacy" tiene rol con: subscribePattern plant/water-plant-1/legacy/# Allow

Resultado: SOLO puede suscribirse a plant/water-plant-1/legacy/# ✓
           Todo lo demás está denegado por defecto ✓
```

---

## 4. Cómo funciona la evaluación de permisos

Cuando un cliente intenta una operación MQTT, Mosquitto evalúa en este orden:

```
1. ¿El cliente tiene roles asignados?
      Sí → Evalúa reglas del rol de mayor prioridad a menor
              ¿Alguna regla coincide con el topic y tipo de operación?
                  Sí → Aplica allow/deny de esa regla → FIN
                  No → Continúa con el siguiente rol
      No (o ningún rol tiene regla aplicable) → va al paso 2

2. ¿Hay un Default ACL Access configurado para este tipo de operación?
      Sí → Aplica ese valor (allow/deny) → FIN
```

### Prioridad de ACLs dentro de un rol

Si un rol tiene múltiples reglas, se evalúan en orden de **prioridad numérica** (mayor número = mayor prioridad). Si dos reglas tienen la misma prioridad, gana la primera definida.

---

## 5. Casos de uso prácticos

### Caso A — Dispositivo IoT (solo publica)

**Escenario**: sensor de temperatura que solo debe publicar en su topic, nunca suscribirse.

**Configuración**:
- Default ACL: Subscribe = **Deny**
- Rol `sensor-only`:
  - `publishClientSend` → `plant/water-plant-1/sensors/temperature` → `Allow`

```
Cliente: sensor-temp-01
Rol: sensor-only
```

El sensor puede publicar su temperatura; no puede suscribirse a nada.

---

### Caso B — Cliente de solo lectura (dashboard)

**Escenario**: aplicación que visualiza datos, nunca publica.

**Configuración**:
- Rol `read-only`:
  - `subscribePattern` → `plant/water-plant-1/#` → `Allow`
  - `publishClientSend` → `#` → `Deny` *(opcional si Default publish = Allow)*

```
Cliente: dashboard-01
Rol: read-only
```

---

### Caso C — Cliente legacy con acceso restringido

**Escenario**: sistema heredado que solo puede ver sus topics específicos en formato antiguo (CSV/plain).

**Configuración**:
- Default ACL: Subscribe = **Deny** ← imprescindible
- Rol `legacy`:
  - `subscribePattern` → `plant/water-plant-1/legacy/#` → `Allow`

```
Cliente: testlegacy
Rol: legacy
```

El cliente legacy ve únicamente los topics bajo `plant/water-plant-1/legacy/`. El resto le está denegado por el Default ACL.

> ⚠️ Si usas `subscribeLiteral` en vez de `subscribePattern`, el topic `plant/water-plant-1/legacy/#` se trata como una cadena literal, NO como un wildcard. El cliente solo podría suscribirse exactamente al topic llamado `plant/water-plant-1/legacy/#`, no a los subtopics que cuelgan de él.

---

### Caso D — Administrador con acceso total

**Configuración**:
- Rol `admin`:
  - `publishClientSend` → `#` → `Allow`
  - `subscribePattern` → `#` → `Allow`

```
Cliente: admin-tool
Rol: admin
```

---

### Caso E — Separación por departamentos (multi-tenant)

**Escenario**: varios equipos comparten el mismo broker. Cada equipo accede solo a su namespace.

```
Rol: equipo-planta-1
  subscribePattern  plant/planta-1/#   Allow
  publishClientSend plant/planta-1/#   Allow

Rol: equipo-planta-2
  subscribePattern  plant/planta-2/#   Allow
  publishClientSend plant/planta-2/#   Allow
```

Con Default Subscribe = Deny, cada equipo queda automáticamente aislado sin necesidad de añadir reglas de denegación explícitas para el namespace del otro equipo.

---

### Caso F — Auditoría (suscripción obligatoria)

**Escenario**: cliente de auditoría que debe estar suscrito a todo y no puede desuscribirse.

```
Rol: auditoria
  subscribePattern       #       Allow
  unsubscribePattern     #       Deny
  unsubscribeLiteral     #       Deny
```

---

## 6. Configuración actual del proyecto

### Default ACL Access (estado actual)

| Parámetro | Valor |
|-----------|-------|
| Publish (Client Send) | ✅ Allow |
| Publish (Client Receive) | ✅ Allow |
| Subscribe | 🔒 **Deny** |
| Unsubscribe | ✅ Allow |

### Roles definidos

#### Rol: `legacy`
| Tipo | Topic | Permiso |
|------|-------|---------|
| `subscribePattern` | `plant/water-plant-1/legacy/#` | Allow |

Con Subscribe por defecto en Deny, este rol limita al cliente `testlegacy` exclusivamente a los topics bajo `plant/water-plant-1/legacy/#`.

### Topics del simulador

El simulador `water-plant-simulator` publica en la siguiente jerarquía:

```
plant/water-plant-1/
├── sensors/
│   ├── tank1/level          (float, JSON)
│   ├── tank2/level          (float, JSON)
│   ├── pump1/flow_rate      (float, JSON)
│   ├── pump2/flow_rate      (float, JSON)
│   ├── inlet/pressure       (float, JSON)
│   └── outlet/pressure      (float, JSON)
├── actuators/
│   ├── pump1/state          (bool, JSON)
│   ├── pump2/state          (bool, JSON)
│   └── valve/position       (float, JSON)
└── legacy/
    ├── sensors/tank1/level  (plain text: "45.23")
    ├── sensors/pump1/flow   (CSV: "timestamp,value,unit")
    └── sensors/inlet/pres   (CSV: "timestamp,value,unit")
```

Los topics bajo `legacy/` son los que consume el cliente `testlegacy` con el rol `legacy`.

---

## Referencia rápida: ¿qué tipo usar?

| Situación | Tipo recomendado |
|-----------|-----------------|
| El cliente se suscribe usando `#` o `+` | `subscribePattern` |
| El cliente se suscribe a un topic exacto sin wildcards | `subscribeLiteral` |
| El cliente publica mensajes | `publishClientSend` |
| Quieres controlar quién puede recibir mensajes de otro | `publishClientReceive` |
| Quieres impedir desuscripciones | `unsubscribeLiteral` / `unsubscribePattern` |
| Quieres bloquear todo lo no permitido explícitamente | Default ACL Subscribe → **Deny** |
