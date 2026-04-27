# Plan de Acción — Corrección de Funcionalidades BunkerM

**Fecha:** 2026-04-27  
**Ámbito:** Backend (FastAPI), Frontend (Next.js), Kubernetes (k8s manifests)  
**Issues:** 3 bugs confirmados tras análisis de código

---

## Resumen Ejecutivo

| # | Bug | Causa raíz | Archivos afectados |
|---|-----|------------|--------------------|
| 1 | ACL Test → `{"detail":"Not Found"}` | Endpoint `POST /roles/{role}/acls/test` no existe en el backend | `routers/dynsec.py` |
| 2 | Broker Config → `Duplicate listener port 1900` | Listener 1901 definido en seed config y también agregado automáticamente → duplicado en fusión | `config/mosquitto/mosquitto.conf` |
| 3 | Client Log sin actividad (Kubernetes) | Mosquitto escribe logs a `stdout`, el fichero `/var/log/mosquitto/mosquitto.log` queda vacío | `config/mosquitto/mosquitto.conf` |
| 4 | Permisos del rol `user` incorrectos | Middleware bloquea **todas** las mutaciones; el contrato real requiere granularidad | `frontend/middleware.ts` |

---

## Bug 1 — ACL Test devuelve 404 en gestión de roles

### Diagnóstico

El frontend llama a `dynsecApi.testRoleACL(rolename, aclType, topic)` que genera:

```
POST /api/proxy/dynsec/roles/{rolename}/acls/test
Body: { aclType, topic }
```

El proxy redirige a:
```
POST http://bhm-api:9001/api/v1/dynsec/roles/{role_name}/acls/test
```

**Ese endpoint no existe** en `routers/dynsec.py`. FastAPI devuelve `{"detail":"Not Found"}` (HTTP 404).

El frontend maneja el resultado esperando:
```typescript
{ allowed: boolean, reason: "role_acl" | "default_acl", matchedRule: {...} | null }
```

#### Nota sobre `#` y `$SYS/broker/#`

El estándar MQTT (sección 4.7.3) especifica que el wildcard `#` **no coincide** con topics que empiecen por `$`. Por tanto:
- Un rol con ACL `subscribePattern` → `#` **no** tiene acceso a `$SYS/broker/clients/connected`.
- Para `$SYS`, el ACL debe ser explícito: `$SYS/#` o `$SYS/broker/#`.

El test debe implementar esta semántica correctamente.

### Pasos de implementación

#### Paso 1.1 — Añadir función de matching de topics en el router

**Archivo:** `bunkerm-source/backend/app/routers/dynsec.py`

Añadir después de las funciones auxiliares existentes (línea ~105):

```python
def _mqtt_topic_matches(pattern: str, topic: str) -> bool:
    """
    Implementa el algoritmo de matching de topics de Mosquitto DynSec.

    Reglas:
    - '+' coincide exactamente con un nivel de topic.
    - '#' coincide con cero o más niveles finales.
    - '#' NO coincide con topics que empiecen por '$' (estándar MQTT §4.7.3).
    - '$SYS/...' solo puede ser accedido con patrones que comiencen por '$'.
    """
    # Prevenir que '#' o '+/...' coincidan con topics $SYS
    if topic.startswith("$") and not pattern.startswith("$"):
        return False

    pattern_parts = pattern.split("/")
    topic_parts = topic.split("/")

    def _match(pp: list[str], tp: list[str]) -> bool:
        if not pp and not tp:
            return True
        if not pp:
            return False
        if pp[0] == "#":
            return True  # coincide con el resto (incluido vacío)
        if not tp:
            return False
        if pp[0] == "+" or pp[0] == tp[0]:
            return _match(pp[1:], tp[1:])
        return False

    return _match(pattern_parts, topic_parts)
```

#### Paso 1.2 — Añadir modelo de request

**Archivo:** `bunkerm-source/backend/app/routers/dynsec.py`

Añadir junto a los otros modelos Pydantic locales (cerca de línea ~50):

```python
class TestACLRequest(BaseModel):
    aclType: str
    topic: str
```

#### Paso 1.3 — Añadir el endpoint `POST /roles/{role_name}/acls/test`

**Archivo:** `bunkerm-source/backend/app/routers/dynsec.py`

Añadir **después** del endpoint `DELETE /roles/{role_name}/acls` (línea ~762, antes de la sección de Grupos):

```python
@router.post("/roles/{role_name}/acls/test")
async def test_role_acl(
    role_name: str,
    payload: TestACLRequest,
    api_key: str = Security(get_api_key),
):
    """
    Evalúa si el rol tiene acceso a un topic para un tipo de ACL dado.

    Implementa el algoritmo de matching de Mosquitto:
    - Primero evalúa las ACLs del rol (prioridad descendente).
    - Si ninguna regla del rol coincide, consulta el ACL por defecto.
    - Retorna la primera regla que coincide o la decisión por defecto.

    Nota: '#' no coincide con topics que empiecen por '$' (MQTT §4.7.3).
    """
    acl_type = payload.aclType
    topic = payload.topic.strip()

    if not topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El campo 'topic' no puede estar vacío.",
        )

    # Obtener las ACLs del rol desde el estado observado
    role_data = desired_state_svc.get_observed_role(role_name)
    if role_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rol '{role_name}' no encontrado.",
        )

    acls: list[dict] = role_data.get("acls", [])

    # Filtrar por tipo de ACL y ordenar por prioridad (mayor primero)
    matching_type = [
        entry for entry in acls
        if entry.get("acltype", "").lower() == acl_type.lower()
    ]
    matching_type.sort(key=lambda e: e.get("priority", 0), reverse=True)

    # Evaluar cada regla del rol
    for entry in matching_type:
        pattern = entry.get("topic", "")
        if _mqtt_topic_matches(pattern, topic):
            allowed = bool(entry.get("allow", False))
            return {
                "allowed": allowed,
                "reason": "role_acl",
                "matchedRule": {
                    "topic": pattern,
                    "aclType": entry.get("acltype", acl_type),
                    "allow": allowed,
                    "priority": entry.get("priority", 0),
                },
            }

    # Sin coincidencia en el rol → consultar ACL por defecto
    default_acl = desired_state_svc.get_observed_default_acl()
    default_key_map = {
        "publishClientSend":    "publishClientSend",
        "publishclientsend":    "publishClientSend",
        "publishClientReceive": "publishClientReceive",
        "publishclientreceive": "publishClientReceive",
        "subscribe":            "subscribe",
        "subscribeliteral":     "subscribe",
        "subscribepattern":     "subscribe",
        "unsubscribe":          "unsubscribe",
        "unsubscriteliteral":   "unsubscribe",
        "unsubscribepattern":   "unsubscribe",
    }
    default_key = default_key_map.get(acl_type.lower())
    default_allowed = False
    if default_acl and default_key:
        default_allowed = bool(default_acl.get(default_key, False))

    return {
        "allowed": default_allowed,
        "reason": "default_acl",
        "matchedRule": None,
        "defaultKey": default_key,
    }
```

#### Paso 1.4 — Verificar en `desired_state_svc` que `get_observed_role` existe

**Archivo:** `bunkerm-source/backend/app/services/broker_desired_state_service.py`

Confirmar que existe la función `get_observed_role(role_name: str)`. Si no existe, añadir:

```python
def get_observed_role(role_name: str) -> dict | None:
    """Devuelve el estado observado de un rol o None si no existe."""
    index = get_cached_observed_dynsec_index()
    return index.get("role_lookup", {}).get(role_name)
```

#### Paso 1.5 — Test manual de validación

```bash
# Desde dentro del clúster (kubectl exec en bhm-api) o via port-forward:
curl -s -X POST \
  http://localhost:9001/api/v1/dynsec/roles/test-role/acls/test \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"aclType":"subscribePattern","topic":"#"}'

# Esperado: { "allowed": true|false, "reason": "role_acl"|"default_acl", ... }

# Test con $SYS (debe dar denied si el rol solo tiene '#')
curl -s -X POST \
  http://localhost:9001/api/v1/dynsec/roles/test-role/acls/test \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"aclType":"subscribePattern","topic":"$SYS/broker/clients/connected"}'

# Esperado: { "allowed": false, "reason": "role_acl"|"default_acl", "matchedRule": null }
```

---

## Bug 2 — Broker Config devuelve "Duplicate listener port 1900" al guardar cambios

### Diagnóstico

Cuando el usuario intenta guardar cambios en la configuración del broker (sección **Broker Config → Edit**), recibe el error:

```
{"success": false, "message": "Duplicate listener port 1900 found in configuration"}
```

#### Causa raíz confirmada

El archivo seed `/config/mosquitto/mosquitto.conf` contiene explícitamente el listener interno 1901:

```conf
listener 1901 0.0.0.0
protocol mqtt
max_connections 16
```

Simultáneamente, el código de **desired state** (`broker_desired_state_service.py`) intenta **agregar automáticamente** el mismo listener 1901 como `_MANAGED_MOSQUITTO_INTERNAL_LISTENER`:

```python
_MANAGED_MOSQUITTO_INTERNAL_LISTENER: Dict[str, Any] = {
    "port": 1901,
    "bind_address": "",
    "per_listener_settings": False,
    "max_connections": 16,
    "protocol": None,
}
```

En la función `_merge_listener_payload`, se fusionan los listeners:
1. Se cargan los listeners actuales desde el archivo (incluye 1901)
2. Se cargan los listeners solicitados desde el frontend (puede no incluir 1901)
3. **Se agrega siempre** el listener 1901 "managed"
4. El diccionario de merge usa `_listener_identity()` como clave

Aunque la función intenta deduplicar mediante la clave de identidad, hay un fallo: si el frontend no envía el listener 1901 en la lista (porque asume que el servidor ya lo maneja), al guardar cambios se termina con [1900, 9001, 1901] de la current + [1901] del managed, creando un duplicado en la lista final después de la validación.

**El verdadero problema:** El listener 1901 **no debería estar en el seed de configuración** — debe ser gestionado exclusivamente por el código como un listener especial del sistema.

### Pasos de implementación

#### Paso 2.1 — Remover el listener 1901 del seed de configuración

**Archivo:** `config/mosquitto/mosquitto.conf`

Eliminar las líneas del listener interno 1901 (déjalo que el código lo maneje automáticamente):

```diff
 # ------------------------------------------
-# Internal System Listener (BHM monitor/control plane)
-# ------------------------------------------
-listener 1901 0.0.0.0
-protocol mqtt
-max_connections 16

 # ------------------------------------------
 # WebSocket Listener
 # ------------------------------------------
```

Resultado: el seed solo debe tener los listeners de usuario [1900, 9001]. El listener 1901 será agregado automáticamente por el código en `_merge_listener_payload`.

#### Paso 2.2 — Actualizar el PVC existente (deployments ya corriendo)

Para clústeres que ya tienen el PVC con el archivo antiguo:

```bash
# Editar el archivo mosquitto.conf en el PVC
MOSQUITTO_POD=$(kubectl -n bhm get pod -l app.kubernetes.io/name=mosquitto -o name | head -1)

kubectl -n bhm exec -it $MOSQUITTO_POD -c broker -- sh -c \
  "sed -i '/^# Internal System Listener/,/^max_connections 16$/d' \
   /etc/mosquitto/mosquitto.conf"

# Verificar que se eliminó
kubectl -n bhm exec $MOSQUITTO_POD -c broker -- grep -n 'listener' /etc/mosquitto/mosquitto.conf

# Reiniciar para que mosquitto relea la config
kubectl -n bhm rollout restart statefulset mosquitto
```

#### Paso 2.3 — Test de validación

Tras eliminar el listener 1901 del seed y actualizar el PVC:

```bash
# 1. Confirmar que la config actual (observada) no tiene duplicados
BHM_API_POD=$(kubectl -n bhm get pod -l app.kubernetes.io/name=bhm-api -o name | head -1)
kubectl -n bhm exec $BHM_API_POD -c api -- \
  curl -s -H "X-API-Key: $API_KEY" \
  http://localhost:9001/api/v1/config/mosquitto-config | python3 -m json.tool | grep -A 20 '"listeners"'

# Esperado: 3 listeners [1900, 1901, 9001]

# 2. Simular un cambio de parámetro (ej: max_inflight_messages) 
curl -s -X POST \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "config": {"max_inflight_messages": "25"},
    "listeners": [
      {"port": 1900, "bind_address": "0.0.0.0", "protocol": "mqtt", "max_connections": 10000},
      {"port": 9001, "bind_address": "0.0.0.0", "protocol": "websockets", "max_connections": 10000}
    ]
  }' \
  http://localhost:9001/api/v1/config/mosquitto-config

# Esperado: {"success": true, "message": "Mosquitto configuration saved successfully"}
# NO debe dar error de puerto duplicado
```

---

## Bug 3 — Client Log no muestra actividad en Kubernetes

### Diagnóstico

#### Flujo de datos en Kubernetes

```
mosquitto (pod: mosquitto-0)
  └── broker container  →  escribe logs en /var/log/mosquitto/mosquitto.log
                             (solo si log_dest = file ...)
  └── observability sidecar (puerto 9102)
        └── lee /var/log/mosquitto/mosquitto.log
        └── expone GET /internal/broker/logs

bhm-api (pod: bhm-api-xxx)
  └── monitor_mosquitto_logs() thread
        └── llama http://bhm-broker-observability:9102/internal/broker/logs cada 2 s
        └── procesa líneas y alimenta mqtt_monitor
```

#### Causa raíz confirmada

El seed de configuración `config/mosquitto/mosquitto.conf` (copiado al PVC `mosquitto-conf` en primer arranque) contiene:

```conf
log_dest stdout      # ← logs van a stdout del contenedor, NO a fichero
```

Sin embargo, el servicio de observabilidad espera el fichero:
```
/var/log/mosquitto/mosquitto.log  # ← siempre vacío en k8s
```

El error que aparece en los logs del servicio de observabilidad:
```
Log file not found: /var/log/mosquitto/mosquitto.log
```

Y la respuesta del endpoint `/internal/broker/logs`:
```json
{ "logs": [], "error": "Log file not found", "source": {"available": false} }
```

Consecuencia: el `mqtt_monitor` nunca recibe líneas → la UI muestra 0 eventos.

#### Por qué funciona en Docker Compose pero no en k8s

En Docker Compose la imagen `bunkerm-source/backend/mosquitto/config/mosquitto.conf` tiene:
```conf
log_dest file /var/log/mosquitto/mosquitto.log
log_type all
```

En k8s se usa el seed de `config/mosquitto/mosquitto.conf` (el del repositorio raíz), que tiene `log_dest stdout`.

### Pasos de implementación

#### Paso 3.1 — Corregir el seed de configuración para Kubernetes

**Archivo:** `config/mosquitto/mosquitto.conf`

Cambiar la sección de Logging:

```diff
-log_dest stdout
+log_dest file /var/log/mosquitto/mosquitto.log
+log_dest stdout
 log_type error
 log_type warning
 log_type notice
 log_type information
 log_type subscribe
+log_type connect
 log_timestamp true
 log_timestamp_format %Y-%m-%dT%H:%M:%S
 connection_messages true
```

> **Nota sobre `log_type connect`:** En Mosquitto ≥ 2.x, los eventos de conexión/desconexión se emiten con `log_type notice` si `connection_messages true` está activo. Añadir `log_type connect` garantiza compatibilidad también si se cambia la versión del broker.

#### Paso 3.2 — Actualizar el PVC existente (deployments ya corriendo)

El seed solo se aplica cuando el PVC está vacío (primer arranque). En clústeres con PVCs ya existentes es necesario actualizar la config manualmente:

```bash
# Obtener el nombre del pod mosquitto
MOSQUITTO_POD=$(kubectl -n bhm get pod -l app.kubernetes.io/name=mosquitto -o name | head -1)

# Ver la configuración actual
kubectl -n bhm exec $MOSQUITTO_POD -c broker -- cat /etc/mosquitto/mosquitto.conf

# Editar en el PVC (requiere un editor disponible en la imagen)
kubectl -n bhm exec -it $MOSQUITTO_POD -c broker -- sh -c \
  "sed -i 's/^log_dest stdout/log_dest file \/var\/log\/mosquitto\/mosquitto.log\nlog_dest stdout/' \
   /etc/mosquitto/mosquitto.conf"

# Verificar el cambio
kubectl -n bhm exec $MOSQUITTO_POD -c broker -- grep 'log_dest' /etc/mosquitto/mosquitto.conf

# Reiniciar el pod para que mosquitto relea la config
kubectl -n bhm rollout restart statefulset mosquitto
```

#### Paso 3.3 — Verificar el estado del pipeline de logs

Tras el reinicio, verificar cada eslabón de la cadena:

```bash
# 1. Confirmar que mosquitto escribe al fichero
kubectl -n bhm exec $MOSQUITTO_POD -c broker -- \
  tail -20 /var/log/mosquitto/mosquitto.log

# 2. Confirmar que el sidecar de observabilidad puede leer el log
kubectl -n bhm exec $MOSQUITTO_POD -c observability -- \
  curl -s http://localhost:9102/internal/broker/logs?limit=5 | python3 -m json.tool

# 3. Desde bhm-api, confirmar conectividad al servicio de observabilidad
BHM_API_POD=$(kubectl -n bhm get pod -l app.kubernetes.io/name=bhm-api -o name | head -1)
kubectl -n bhm exec $BHM_API_POD -c api -- \
  curl -s http://bhm-broker-observability:9102/internal/broker/logs?limit=5 | python3 -m json.tool

# 4. Ver el estado del source en la API de clientlogs
kubectl -n bhm exec $BHM_API_POD -c api -- \
  curl -s -H "X-API-Key: $API_KEY" \
  http://localhost:9001/api/v1/clientlogs/source-status | python3 -m json.tool
```

**Resultado esperado en `source-status`:**
```json
{
  "logTail": {
    "available": true,
    "running": true,
    "replayCompleted": true,
    "lastError": null
  }
}
```

#### Paso 3.4 — Verificar tipos de log activos

Para que aparezcan todos los eventos en Client Log, mosquitto debe emitir los siguientes tipos:

| Evento en UI | `log_type` necesario | Depende de |
|---|---|---|
| Client Connection | `notice` + `connection_messages true` | Ambos requeridos |
| Client Disconnection | `notice` + `connection_messages true` | Ambos requeridos |
| Auth Failure | `notice` o `warning` | Uno de los dos |
| Subscribe | `subscribe` | Requerido |
| Publish | suscripción MQTT del monitor | `bunkerm-mqtt-monitor` conectado |

> **Sobre Publish events:** Los eventos de Publish **no se detectan por log** sino por suscripción directa MQTT. El hilo `monitor_mqtt_publishes` en la versión actual está desactivado con estado `"integrated_into_primary_mqtt_monitor"`. Si los publishes tampoco aparecen, verificar que el cliente MQTT del monitor (`bunkerm-mqtt-monitor`) está conectado al broker. Ver `GET /api/v1/clientlogs/source-status` para el campo `mqttSubscribe`.

---

## Bug 4 — Permisos del rol `user` incorrectos

### Diagnóstico

El contrato de permisos requerido:

| Sección | Rol `admin` | Rol `user` |
|---------|-------------|------------|
| ACL: Clientes | CRUD completo | Crear, ver, editar — **SIN eliminar** |
| ACL: Roles | CRUD completo | Crear, ver, editar, gestionar ACLs — **SIN eliminar rol** |
| ACL: Grupos | CRUD completo | Crear, ver, editar — **SIN eliminar** |
| ACL: reglas dentro de un rol | CRUD completo | CRUD completo (añadir/quitar ACLs del rol) |
| ACL: Test de acceso | Permitido | **Permitido** |
| Broker Config | CRUD completo | **Solo lectura** |
| Security / DynSec Config | CRUD + import | **Solo exportar** (GET) |
| Import Password | Permitido | **Bloqueado** |
| Alarmas (config) | CRUD completo | **Solo lectura** |
| Reportes, Monitor | Lectura + acciones | Igual que admin |

**Estado actual en `middleware.ts`:**
```typescript
if (
  role === 'user' &&
  pathname.startsWith('/api/proxy') &&
  MUTATING_METHODS.includes(request.method)    // POST, PUT, DELETE, PATCH
) → 403
```

Esto bloquea **todo** para `user`, incluyendo acciones que sí debería poder hacer (crear clientes, añadir ACLs, etc.).

### Pasos de implementación

#### Paso 4.1 — Reescribir la lógica de autorización del middleware

**Archivo:** `bunkerm-source/frontend/middleware.ts`

Reemplazar el bloque de autorización del rol `user` con una lógica granular:

```typescript
// ─── Constantes de control de acceso por rol ─────────────────────────────────

// Páginas solo accesibles por admin
const ADMIN_ONLY_PATHS = ['/settings/users']

// Prefijos de proxy donde el rol 'user' NO puede hacer NINGUNA mutación
const USER_READONLY_PREFIXES = [
  '/api/proxy/config/',           // Configuración del broker (mosquitto.conf)
  '/api/proxy/security/',         // Ajustes de seguridad
]

// Endpoints de proxy bloqueados para 'user' por método específico
const USER_BLOCKED_ENDPOINTS: Array<{ prefix: string; methods: string[] }> = [
  // No puede importar ficheros de contraseñas
  { prefix: '/api/proxy/dynsec/import-password-file', methods: ['POST', 'PUT', 'PATCH'] },
  // No puede modificar umbrales de alertas
  { prefix: '/api/proxy/monitor/alerts/config',        methods: ['POST', 'PUT', 'PATCH', 'DELETE'] },
]
```

Y la función de comprobación:

```typescript
function isBlockedForUser(pathname: string, method: string): boolean {
  // 1. Prefijos completamente de solo lectura
  if (
    MUTATING_METHODS.includes(method) &&
    USER_READONLY_PREFIXES.some((p) => pathname.startsWith(p))
  ) {
    return true
  }

  // 2. Endpoints específicos bloqueados por método
  for (const rule of USER_BLOCKED_ENDPOINTS) {
    if (rule.methods.includes(method) && pathname.startsWith(rule.prefix)) {
      return true
    }
  }

  // 3. DELETE de entidades raíz DynSec (cliente/rol/grupo)
  //    Patrón: /api/proxy/dynsec/{clients|roles|groups}/{name}  (exactamente 2 segmentos tras 'dynsec')
  //    Permitido: /api/proxy/dynsec/roles/{name}/acls  (sub-recurso, 3+ segmentos)
  if (method === 'DELETE' && pathname.startsWith('/api/proxy/dynsec/')) {
    const dynsecPath = pathname.slice('/api/proxy/dynsec/'.length)
    const segments = dynsecPath.split('/').filter(Boolean)
    const ROOT_COLLECTIONS = ['clients', 'roles', 'groups']
    if (segments.length === 2 && ROOT_COLLECTIONS.includes(segments[0])) {
      return true  // DELETE /clients/{name} | /roles/{name} | /groups/{name}
    }
  }

  return false
}
```

Y sustituir el bloque actual:

```typescript
// Antes:
if (
  role === 'user' &&
  pathname.startsWith('/api/proxy') &&
  MUTATING_METHODS.includes(request.method)
) {
  return NextResponse.json(
    { error: 'Insufficient permissions — this account is read-only' },
    { status: 403 }
  )
}

// Después:
if (role === 'user' && isBlockedForUser(pathname, request.method)) {
  return NextResponse.json(
    { error: 'Insufficient permissions for this operation' },
    { status: 403 }
  )
}
```

#### Paso 4.2 — Adaptar la UI del frontend para ocultar botones según el rol

Aunque el middleware protege el backend, la experiencia de usuario mejora ocultando los controles bloqueados. En los componentes relevantes verificar el rol del usuario y condicionar la visibilidad de botones destructivos.

**Archivos a revisar (UI):**
- `frontend/components/mqtt/clients/` — ocultar botón Delete para rol `user`
- `frontend/components/mqtt/roles/RolesTable.tsx` — ocultar botón Delete
- `frontend/components/mqtt/groups/` — ocultar botón Delete
- Páginas de broker config, DynSec config, import password — deshabilitar controles de escritura
- Página de alertas — deshabilitar formulario de configuración de umbrales

**Patrón recomendado:**

```tsx
import { useSession } from 'next-auth/react'

// En el componente:
const { data: session } = useSession()
const isAdmin = (session?.user as { role?: string })?.role === 'admin'

// En el JSX:
{isAdmin && (
  <Button variant="destructive" onClick={() => handleDelete(item)}>
    Delete
  </Button>
)}
```

#### Paso 4.3 — Verificar que el ACL Test no queda bloqueado para `user`

El endpoint `POST /api/proxy/dynsec/roles/{role}/acls/test` no está en ningún prefijo bloqueado ni en ninguna regla de `USER_BLOCKED_ENDPOINTS`. La regla 3 del DELETE no aplica (es POST). Por tanto, el test de ACL funciona para ambos roles ✓.

#### Paso 4.4 — Test de validación de permisos

```bash
# Obtener un token de usuario con rol 'user'
USER_TOKEN=$(curl -s -X POST http://localhost:2000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@bhm.local","password":"..."}' | jq -r '.token')

# DEBE dar 403 — eliminar un cliente
curl -s -X DELETE \
  -H "Cookie: bunkerm_token=$USER_TOKEN" \
  http://localhost:2000/api/proxy/dynsec/clients/test-client
# Esperado: {"error":"Insufficient permissions for this operation"}

# DEBE dar 200 — crear un cliente
curl -s -X POST \
  -H "Cookie: bunkerm_token=$USER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"username":"nuevo","password":"Test@1234"}' \
  http://localhost:2000/api/proxy/dynsec/clients
# Esperado: 201 Created

# DEBE dar 403 — modificar config del broker
curl -s -X PUT \
  -H "Cookie: bunkerm_token=$USER_TOKEN" \
  -H 'Content-Type: application/json' \
  http://localhost:2000/api/proxy/config/mosquitto
# Esperado: {"error":"Insufficient permissions for this operation"}

# DEBE dar 200 — leer config del broker
curl -s \
  -H "Cookie: bunkerm_token=$USER_TOKEN" \
  http://localhost:2000/api/proxy/config/mosquitto
# Esperado: 200 con los valores actuales

# DEBE dar 403 — importar contraseñas
curl -s -X POST \
  -H "Cookie: bunkerm_token=$USER_TOKEN" \
  http://localhost:2000/api/proxy/dynsec/import-password-file
# Esperado: {"error":"Insufficient permissions for this operation"}

# DEBE dar 200 — test de ACL (nuevo endpoint)
curl -s -X POST \
  -H "Cookie: bunkerm_token=$USER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"aclType":"subscribePattern","topic":"sensor/#"}' \
  http://localhost:2000/api/proxy/dynsec/roles/readonly-role/acls/test
# Esperado: { "allowed": true|false, ... }
```

---

## Orden de implementación recomendado (optimizado para evitar duplicar trabajo)

### Fase 1: Backend (sin dependencias externas)
**Bugs a resolver:** Bug 1
- **Paso 1.1-1.5:** Implementar endpoint `POST /roles/{role}/acls/test`
- **Tiempo estimado:** 30 min
- **Validación:** Test manual con curl

### Fase 2: Configuración (una sola edición a `config/mosquitto/mosquitto.conf`)
**Bugs a resolver:** Bug 2 + Bug 3 (comparten archivo seed)
- **Paso 2.1 + 3.1 combinados:** Editar `config/mosquitto/mosquitto.conf` UNA SOLA VEZ:
  - ✓ Remover listener 1901 (Bug 2)
  - ✓ Cambiar `log_dest stdout` a `log_dest file /var/log/mosquitto/mosquitto.log` (Bug 3)
  - ✓ Añadir `log_type connect` (Bug 3)
- **Paso 2.2 + 3.2 combinados:** Un solo comando kubectl para actualizar el PVC
- **Tiempo estimado:** 20 min (edición) + 5 min kubectl
- **Validación:** Doble check en la siguiente fase

### Fase 3: Kubernetes (post-actualización de config)
**Verificación de:** Bug 2 + Bug 3
- **Paso 2.3:** Test de guardado de broker config (sin error de puerto duplicado)
- **Paso 3.3:** Verificar listeners activos y pipeline de logs
- **Paso 3.4:** Confirmar tipos de log emitidos
- **Tiempo estimado:** 10 min
- **Validación:** Cambiar parámetro en broker config + verificar logs en Client Log

### Fase 4: Frontend
**Bugs a resolver:** Bug 4
- **Paso 4.1-4.4:** Actualizar middleware + UI + tests
- **Tiempo estimado:** 45 min
- **Validación:** Test con rol `user` y `admin`

---

## Resumen de cambios a archivos (1 archivo principal, 2 routers):

| Archivo | Bug(s) | Cambio | Criticidad |
|---------|--------|--------|------------|
| `config/mosquitto/mosquitto.conf` | 2, 3 | Remover listener 1901 + cambiar log_dest | **Alta** (blocking) |
| `bunkerm-source/backend/app/routers/dynsec.py` | 1 | Añadir endpoint `/acls/test` + función matching | Media |
| `bunkerm-source/frontend/middleware.ts` | 4 | Reescribir autorización granular | Media |
| `bunkerm-source/frontend/components/mqtt/**` | 4 | Ocultar botones destructivos para `user` | Baja (UX) |

---

## Checklist de validación final

- [ ] `POST /roles/{role}/acls/test` con topic `#` devuelve resultado correcto
- [ ] `POST /roles/{role}/acls/test` con topic `$SYS/broker/#` devuelve `allowed: false` si el rol solo tiene ACL `#`
- [ ] Guardar cambios en Broker Config **SIN error** "Duplicate listener port 1900"
- [ ] Config del broker muestra solo 3 listeners: [1900, 1901, 9001] (1901 agregado automáticamente)
- [ ] `GET /api/v1/config/mosquitto-config/status` → sin errores de validación
- [ ] `GET /api/v1/clientlogs/source-status` → `logTail.available: true` en k8s
- [ ] Client Log muestra eventos de Connection, Disconnection, Auth Failure, Subscribe
- [ ] Rol `user` puede crear un cliente MQTT desde la UI → HTTP 201
- [ ] Rol `user` NO puede eliminar un cliente MQTT → HTTP 403
- [ ] Rol `user` NO puede modificar broker config → HTTP 403
- [ ] Rol `user` NO puede importar contraseñas → HTTP 403
- [ ] Botones Delete no visibles en la UI cuando el usuario tiene rol `user`
- [ ] Config de alertas no editable en la UI cuando el usuario tiene rol `user`

---

## Notas Importantes

### Por qué reordenar los bugs:
1. **Bug 2 (Listener 1901 duplicado)** y **Bug 3 (log_dest)** comparten el archivo `config/mosquitto/mosquitto.conf`
   - Cambiar este archivo de forma centralizada evita múltiples validaciones y reinicios
   - Ambos requieren actualizar el PVC en kubernetes, que puede hacerse en un solo comando

2. **Bug 2 debe resolverse ANTES que Bug 3** porque:
   - El listener 1901 en el seed genera error al guardar cambios de configuración
   - Una vez que se permite guardar cambios, se puede verificar que los logs se escriben correctamente
   - Ambas son críticas para la migración a k8s, pero el orden elimina bloqueos mutuos

3. **Bug 1 (ACL Test)** es completamente independiente:
   - Se implementa en paralelo, sin dependencias en los otros bugs
   - El endpoint estará disponible con o sin los otros fixes

4. **Bug 4 (Permisos)** debe ser el ÚLTIMO:
   - Depende de que Bug 1 esté funcionando (para testear el acceso de ACLs con rol `user`)
   - No afecta los otros bugs y es principalmente un cambio de política de autorización

### Arquitectura de la migración a Kubernetes:
- El seed `config/mosquitto/mosquitto.conf` es una **plantilla** que se copia al PVC en primer arranque
- Los listeners 1900 y 9001 son **escucha de clientes**, deben estar en el seed
- El listener 1901 es **solo para administración interna**, el código lo gestiona automáticamente
- Los logs deben escribirse a **fichero** (no stdout) para que el servicio de observabilidad pueda leerlos
- El pipeline es: `mosquitto.log` → broker observability sidecar → bhm-api → mqtt_monitor → UI Client Log

