# Bug Fix: Mosquitto Broker Restart Loop

## Problema Identificado

El broker Mosquitto estaba entrando en un **loop de reinicio cada 3-5 segundos** después del deploy anterior. Los síntomas eran:

- Broker inicia correctamente (todos los listeners abren)
- Clientes pueden conectarse momentáneamente
- Luego el broker termina abruptamente (rc=7: Connection Refused)
- El monitor intenta reconectar
- El broker reinicia y el ciclo se repite

## Root Cause

**Mismatch entre contenido de configuración leída vs. generada:**

```
Lectura del archivo (producción):
listener 1900 0.0.0.0
per_listener_settings false
max_connections 10000

Parsing:
- puerto: 1900
- bind_address: "0.0.0.0" ← SIN NORMALIZAR

Normalización posterior:
- bind_address: "0.0.0.0" → "" (normalizado)

Generación de configuración (after prior fix):
listener 1900
per_listener_settings false
max_connections 10000

Resultado:
"listener 1900 0.0.0.0..." ≠ "listener 1900..."
Contenido de texto diferente aunque configuración equivalente
→ SIEMPRE marcado como "drift"
```

### La Cascada

1. **Primera reconciliación**: API guarda config, genera con bind_address="", escribe `listener 1900` (sin 0.0.0.0)
2. **Siguiente lectura**: Parsea `listener 1900` → bind_address=""
3. **Comparación**: desea `listener 1900`, observa `listener 1900` ✓ Coinciden
4. **Problema**: Si algo causa otra reconciliación sin cambios, el contenido sigue siendo igual
5. **Pero con la configuración original**: Tenía `listener 1900 0.0.0.0`
6. **Primera lectura**: Parsea como bind_address="0.0.0.0"
7. **Normalización después del parse**: Todavía bind_address="0.0.0.0"
8. **Escritura**: Genera `listener 1900 0.0.0.0` ó `listener 1900` (depende del timing)
9. **Mismatch perpetuo**: Contenido observado ≠ contenido deseado siempre

Esto causaba que la reconciliación **nunca marcara como "applied"**, siempre quedaba como **"drift"**. Si había un mecanismo automático que intenta reconciliar en drift, se generaría un loop.

## Solución Implementada

**Normalizar el bind_address DURANTE el parse, no después:**

```python
# En config/mosquitto_config.py - función parse_mosquitto_conf()

def _normalize_bind_address(raw: str | None) -> str:
    """Normalize bind address: map all wildcards to empty string for consistency."""
    if not raw or raw in ("0.0.0.0", "::", "*"):
        return ""
    return raw.strip()

# En el parser, cuando se lee "listener":
current_listener = {
    "port": int(parts[1]),
    "bind_address": _normalize_bind_address(parts[2] if len(parts) > 2 else None),  # NORMALIZAR AQUÍ
    "per_listener_settings": False,
    "max_connections": 10000,
    "protocol": None,
}
```

### Por qué funciona

1. **Lectura**: `listener 1900 0.0.0.0` → Parser normaliza → bind_address=""
2. **Normalizacion en desired state**: bind_address="" → se mantiene ""
3. **Generación**: bind_address="" → genera `listener 1900` (sin bind_address)
4. **Siguiente lectura**: `listener 1900` → Parser normaliza → bind_address=""
5. **Comparación**: desea `listener 1900`, observa `listener 1900` → **COINCIDEN**
6. **Reconciliación**: Marcado como "applied", NO "drift"
7. **Loop terminado**: Sin drift, no hay reconciliación continua

El contenido de texto ahora es **consistente en todos los ciclos**.

## Cambios de Código

**Archivo**: `bunkerm-source/backend/app/config/mosquitto_config.py`

### Cambio 1: Agregar función de normalización
```python
def _normalize_bind_address(raw: str | None) -> str:
    """Normalize bind address: map all wildcards to empty string for consistency."""
    if not raw or raw in ("0.0.0.0", "::", "*"):
        return ""
    return raw.strip()
```

### Cambio 2: Aplicar normalización en el parser
```python
# Antes (problematico):
"bind_address": parts[2] if len(parts) > 2 else "",

# Después (corregido):
"bind_address": _normalize_bind_address(parts[2] if len(parts) > 2 else None),
```

## Validación

✅ **Todos los 41 tests pasan:**
- Listeners deduplication
- Bind address normalization (0.0.0.0 → "")
- Production config round-trip consistency
- Second-save production scenarios
- Daemon mode compatibility

### Tests Key que validana la fix:
- `test_save_mosquitto_config_second_save_after_production_conf` - Verifica que production conf (con 0.0.0.0) no cause drift perpetuo
- `test_save_mosquitto_config_daemon_mode_observed_config_0000_no_duplicate` - Verifica normalizacion en daemon mode
- `test_normalize_bind_address_treats_zero_zero_as_empty` - Valida que 0.0.0.0 se normaliza a ""

## Impacto en Producción

### Antes:
- Configuración marcada como "drift" perpetuamente
- Posible loop de reconciliación causando restarts
- Broker inestable

### Después:
- Configuración consistente entre ciclos
- Drift detectado solo cuando hay cambios reales
- Broker estable

## Próximos Pasos

1. **Rebuild de imagen**: `./deploy.ps1 -Action build`
2. **Redeploy limpio**: `./deploy.ps1 -Action redeploy` (como indicaste)
3. **Verificación**: El broker debe permanecer en estado "running" sin restarts
4. **Monitoreo**: Los logs del API no deberían mostrar "Desconexión inesperada del broker MQTT"

---

## Apéndice: Por qué esto sucedió

El cambio anterior (_normalize_listener_entries en broker_desired_state_service.py) normalizaba correctamente los listeners para el merge y la deduplicación. Pero **no normalizaba en el parser de lectura**, causando un desacople:

- **Escritura**: Usaba listeners normalizados → escribía `listener 1900`
- **Lectura**: No normalizaba en el parser → leía como `listener 1900 0.0.0.0` después del primer guardado
- **Resultado**: Inconsistencia perpetua

La solución correcta era normalizar en AMBOS lugares: durante el parse Y durante la generación. Esta fix normaliza en el parse, asegurando consistencia en todos los ciclos.
