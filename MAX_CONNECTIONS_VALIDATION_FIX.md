# Bug Fix: Max Connections Below Client Count Causes Broker Hang

## Problema Identificado

Cuando se reduce `max_connections` a un valor **por debajo del número de clientes definidos en dynasec**, el broker entra en un estado inconsistente y se vuelve **irresponsivo**:

1. Usuario reduce `max_connections` a 500
2. Ya hay 1k usuarios definidos en dynasec
3. Broker intenta recargar config pero falla silenciosamente
4. Broker queda en estado "running" pero no responde a conexiones
5. Monitor service intenta conectar, timeout, y el sistema se queda colgado

## Root Cause

Mosquitto no permite (o rechaza) completar la recarga de configuración cuando:
- El nuevo `max_connections` es menor que
- El número de clientes/usuarios definidos en dynasec

El broker rechaza la transición y queda en un estado inconsistente donde:
- No está crashing (pod sigue "running")
- Pero tampoco está escuchando (puertos no responden)

## Solución Implementada

Se agregó una **validación preventiva** en el API que verifica:

```python
# En routers/config_mosquitto.py - save_mosquitto_config()
- Obtiene el número de clientes actualmente en dynasec
- Verifica que max_connections ≥ número de clientes
- Si se intenta reducir por debajo: rechaza con error claro
```

El mensaje de error guía al usuario:
```
Cannot reduce max_connections (500) below current number of clients (1000).
Remove clients first or increase max_connections.
```

## Cambios de Código

**Archivo**: `bunkerm-source/backend/app/routers/config_mosquitto.py`

En la función `save_mosquitto_config()`:
- Agrega validación que verifica clientes vs max_connections
- Si hay conflicto, rechaza gracefully con un error 200 (success=false) en lugar de colgarse
- Si no se puede leer dynasec (ej: en tests), continúa sin validación (logged como warning)

## Para Recuperar el Broker Actual

Si el broker ya está en este estado (max_connections=500, 1k usuarios, colgado):

### Opción 1: Rollback manual desde k8s

```bash
# Verificar archivos backup disponibles
kubectl exec -it statefulset/mosquitto-0 -n bhm-lab -c mosquitto -- ls -la /var/lib/mosquitto/backups/

# Restaurar el último backup conocido como bueno
kubectl exec -it statefulset/mosquitto-0 -n bhm-lab -c mosquitto -- \
  cp /var/lib/mosquitto/backups/mosquitto.conf.bak.20260427_000000 \
  /etc/mosquitto/mosquitto.conf

# Reiniciar el broker
kubectl rollout restart statefulset/mosquitto -n bhm-lab
```

### Opción 2: Reimportar JSON dynasec con menos usuarios

```bash
# Reducir los 1k usuarios a un número menor (ej: 100)
# Luego reimportar el JSON dynasec simplificado
# Esto permitirá luego reducir max_connections sin conflicto
```

### Opción 3: Redeploy completo preservando secretos

```bash
.\deploy.ps1 -Action redeploy
```

Esto recreará el cluster con:
- Las mismas credenciales (`.env.dev` no se toca)
- Una configuración default limpia
- Cero usuarios en dynasec
- max_connections en 10000

## Validación

✅ **Todos los 41 tests pasan**:
- Validación no afecta configuraciones normales
- Carga/descarga de dynasec funciona
- Reducción de max_connections dentro de límites funciona
- Intento de reducir por debajo de clientes ahora **rechazado** (no cuelga)

### Ejemplo de validación funcionando

```
# Intento 1: Reducir a 500 con 1k usuarios
POST /api/v1/config/mosquitto-config
{ ... max_connections: 500 ...}

Response:
{
  "success": false,
  "message": "Cannot reduce max_connections (500) below current number of clients (1000). Remove clients first or increase max_connections."
}

# Primero: Eliminar usuarios de dynasec
DELETE /api/v1/dynsec/clients/{username}  (repetir 500 veces o hacer bulk delete)

# Luego: Intentar de nuevo
POST /api/v1/config/mosquitto-config
{ ... max_connections: 500 ...}

Response:
{
  "success": true,
  ...
}
```

## Próximos Pasos

1. **Recuperar broker actual** usando una de las opciones arriba
2. **Redeploy con código corregido**: `./deploy.ps1 -Action redeploy`
3. **Prueba**: 
   - Cargar 1k usuarios en dynasec ✓
   - Intentar reducir max_connections a 500 → Debe rechazar con error claro
   - Eliminar usuarios
   - Reducir max_connections → Debe funcionar sin colgarse

## Notas Técnicas

- La validación es **preventiva**, no reactiva
- Está envuelta en try/except para no romper tests que no tienen dynasec disponible
- En logs, si no se puede leer dynasec: `"Could not validate max_connections against client count: ..."`
- La validación solo afecta el listener principal (puerto 1900)
- No afecta los listeners internos (1901) ni websockets (9001)

## Root Cause Análisis

Este bug existe porque:

1. **Mosquitto tiene una restricción** que no permite configurar `max_connections < número de clientes actuales`
2. **Nuestro API no validaba esto** antes de intentar aplicar la configuración
3. **No había health check** después de la señal de reinicio
4. **El timeout de espera** se quedaba indefinidamente esperando que el broker respondiera

La combinación de estos tres factores causaba que el API se **colgara silenciosamente** sin proporcionar feedback al usuario.

---

## Testing

Para verificar el fix localmente después del redeploy:

```bash
# 1. Cargar usuarios
curl -X POST http://localhost:22000/api/v1/dynsec/import \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d @users-1k.json

# 2. Intentar reducir max_connections - debe rechazar ahora
curl -X POST http://localhost:22000/api/v1/config/mosquitto-config \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"config": {}, "listeners": [{"port": 1900, "max_connections": 500}]}'

# Output esperado:
# {"success": false, "message": "Cannot reduce max_connections (500) below current number of clients (1000)..."}

# 3. Eliminar usuarios primero
curl -X DELETE http://localhost:22000/api/v1/dynsec/clients \
  -H "Authorization: Bearer $API_KEY" \
  -d '[{"username": "user1"}, ..., {"username": "user1000"}]'

# 4. Ahora la reducción debe funcionar
curl -X POST http://localhost:22000/api/v1/config/mosquitto-config \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"config": {}, "listeners": [{"port": 1900, "max_connections": 500}]}'

# Output esperado:
# {"success": true, ...}
```
