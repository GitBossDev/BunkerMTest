# Fase 2: Simulador de Planta de Tratamiento de Agua

## Descripción General

El simulador de planta de tratamiento es un sistema IoT industrial completo que genera datos realistas de sensores y responde a comandos de actuadores a través de MQTT. Diseñado para probar las capacidades de BunkerM en un entorno industrial simulado.

## Estado: COMPLETO [OK]

- [OK] Arquitectura diseñada (8 sensores, 4 actuadores)
- [OK] Implementación completa de dispositivos
- [OK] Modelo físico con dinámica de tanques
- [OK] Controlador automático con reglas
- [OK] Generador de anomalías (freeze, spike, drift, disconnect)
- [OK] Docker Compose configurado
- [OK] Script de gestión (simulator.ps1)
- [OK] Documentación completa

---

## Arquitectura del Simulador

### Componentes Principales

```
water-plant-simulator/
├── src/
│   ├── main.py                     # Orquestador principal
│   ├── mqtt_client.py              # Gestor de conexión MQTT
│   ├── devices/
│   │   ├── base_device.py          # Clase base abstracta
│   │   ├── sensor.py               # Dispositivos sensores
│   │   ├── actuator.py             # Dispositivos actuadores
│   │   └── controller.py           # Controlador automático
│   └── simulation/
│       ├── physics_model.py        # Modelo físico de la planta
│       └── anomaly_generator.py    # Generador de anomalías
├── config/
│   └── plant_config.yaml           # Configuración completa
├── Dockerfile                       # Imagen Docker
└── requirements.txt                # Dependencias Python
```

### Sensores (8 dispositivos)

| Sensor | Topic | Unidad | Rango | Descripción |
|--------|-------|--------|-------|-------------|
| **tank1_level** | `sensors/tank1/level` | % | 0-100 | Nivel del tanque principal |
| **tank1_ph** | `sensors/tank1/ph` | pH | 0-14 | pH del agua |
| **tank1_turbidity** | `sensors/tank1/turbidity` | NTU | 0-100 | Turbidez (partículas suspendidas) |
| **flow_inlet** | `sensors/flow/inlet` | L/min | 0-200 | Flujo de entrada |
| **flow_outlet** | `sensors/flow/outlet` | L/min | 0-200 | Flujo de salida |
| **pump1_pressure** | `sensors/pump1/pressure` | bar | 0-10 | Presión de bomba 1 |
| **pump2_pressure** | `sensors/pump2/pressure` | bar | 0-10 | Presión de bomba 2 |
| **ambient_temperature** | `sensors/ambient/temperature` | °C | -10 a 50 | Temperatura ambiente |

### Actuadores (4 dispositivos)

| Actuador | Status Topic | Command Topic | Descripción |
|----------|-------------|---------------|-------------|
| **pump1** | `actuators/pump1/status` | `actuators/pump1/command` | Bomba de entrada |
| **pump2** | `actuators/pump2/status` | `actuators/pump2/command` | Bomba de salida |
| **valve1** | `actuators/valve1/status` | `actuators/valve1/command` | Válvula de dosificación pH |
| **valve2** | `actuators/valve2/status` | `actuators/valve2/command` | Válvula de drenaje |

---

## Instalación y Configuración

### Prerequisitos

1. **Docker y Docker Compose** instalados
2. **Servicios base de BunkerM** ejecutándose:
   ```powershell
   .\deploy.ps1 status
   ```
   Debe mostrar `mosquitto`, `postgres`, y `nginx` en estado **Up**.

3. **Archivo .env.dev** generado:
   ```powershell
   python .\scripts\generate-secrets.py
   ```

### Construcción de la Imagen

```powershell
# Opción 1: Build manual
.\simulator.ps1 build

# Opción 2: Build automático en primer start
.\simulator.ps1 start
```

### Configuración

Edita el archivo [plant_config.yaml](water-plant-simulator/config/plant_config.yaml) para ajustar:

- **mqtt**: Configuración de conexión (broker, puerto, credenciales)
- **sensors**: Rangos, intervalos de publicación, ruido
- **actuators**: Intervalos de estado
- **controller**: Reglas de control automático
- **physics**: Parámetros físicos (capacidad tanque, caudales)
- **anomalies**: Probabilidad y tipos de anomalías

---

## Uso del Simulador

### Script de Gestión: simulator.ps1

```powershell
# Iniciar simulador
.\simulator.ps1 start

# Ver estado
.\simulator.ps1 status

# Ver logs en tiempo real
.\simulator.ps1 logs -Follow

# Ver últimos logs
.\simulator.ps1 logs

# Reiniciar simulador
.\simulator.ps1 restart

# Detener simulador
.\simulator.ps1 stop

# Gestionar anomalías
.\simulator.ps1 anomalies enable
.\simulator.ps1 anomalies disable

# Reconstruir imagen
.\simulator.ps1 build

# Limpiar recursos
.\simulator.ps1 clean
```

### Comandos Docker Directos

```powershell
# Iniciar con logs en tiempo real
docker-compose -f docker-compose.simulator.yml --env-file .env.dev up

# Iniciar en background
docker-compose -f docker-compose.simulator.yml --env-file .env.dev up -d

# Ver logs
docker logs -f water-plant-simulator

# Detener
docker-compose -f docker-compose.simulator.yml down
```

---

## Modelo Físico

### Dinámica del Tanque

El modelo físico simula un tanque de tratamiento con las siguientes ecuaciones:

```
ΔVolumen = (Flujo_Entrada - Flujo_Salida - Evaporación) × Δt

Nivel(%) = (Volumen / Capacidad) × 100

Flujo_Entrada = (Pump1_Speed / 100) × Caudal_Nominal

Flujo_Salida = (Pump2_Speed / 100) × Caudal_Nominal
```

### Parámetros Físicos

- **Capacidad del tanque**: 10,000 litros
- **Caudal nominal bombas**: 100 L/min al 100%
- **Caudal nominal válvulas**: 50 L/min al 100%
- **Evaporación**: 0.1 L/min
- **Intervalo de actualización**: 1 segundo

### Presiones de Bombas

```
Presión_Pump1 = (Velocidad / 100) × 5.0 bar × (1 + Nivel × 0.3)

Presión_Pump2 = (Velocidad / 100) × 4.5 bar × (0.7 + (1-Nivel) × 0.6)
```

### pH y Turbidez

- **pH**: Deriva natural hacia 7.0, corregido por `valve1`
- **Turbidez**: Aumenta gradualmente, disminuye con flujo de salida

---

## Control Automático

### Reglas de Control

El controlador automático implementa las siguientes reglas:

#### 1. Control de Nivel (tank1_level)

```yaml
Rango objetivo: 20-90%

Si nivel < 20%:
  - Activar pump1 al 80%
  
Si nivel > 90%:
  - Desactivar pump1
```

#### 2. Control de pH (tank1_ph)

```yaml
Rango objetivo: 6.5-8.0

Si pH < 6.5 o pH > 8.0:
  - Abrir valve1 proporcional a desviación
  - Apertura = |pH - 7.0| × 20%
  
Si pH en rango:
  - Cerrar valve1 (0%)
```

#### 3. Control de Turbidez (tank1_turbidity)

```yaml
Umbral: 5 NTU

Si turbidez > 5 NTU:
  - Activar pump2 al 60%
  
Si turbidez ≤ 5 NTU:
  - Desactivar pump2
```

#### 4. Protecciones de Seguridad

```yaml
Pump1:
  Si presión > 8.0 bar:
    - Detener pump1
    - Estado = error
    
Pump2:
  Si presión > 7.0 bar:
    - Detener pump2
    - Estado = error
```

### Modos de Operación

Los actuadores soportan dos modos:

- **manual**: Control directo por comandos MQTT (controlador deshabilitado)
- **auto**: Control automático habilitado (respeta reglas del controlador)

---

## Generación de Anomalías

### Tipos de Anomalías

#### 1. Freeze (Congelación)

El sensor se queda en un valor fijo durante 30-180 segundos.

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "device_id": "sensor_tank1_level",
  "value": 45.2,
  "unit": "%",
  "quality": "frozen"
}
```

#### 2. Spike (Pico Anormal)

El sensor muestra un valor anormalmente alto/bajo instantáneamente.

```json
{
  "value": 145.8  // Normal: 45.2, Spike: ×3
}
```

#### 3. Drift (Deriva)

El sensor deriva gradualmente fuera del rango durante 60-300 segundos.

```json
{
  "value": 45.2  // t=0
  "value": 52.7  // t=60s  (deriva: +0.125/s)
  "value": 60.2  // t=120s
}
```

#### 4. Disconnect (Desconexión)

El sensor deja de publicar durante 20-120 segundos.

### Configuración de Anomalías

Editar [plant_config.yaml](water-plant-simulator/config/plant_config.yaml):

```yaml
anomalies:
  enabled: true               # Habilitar/deshabilitar
  check_interval: 60          # Verificar cada 60s
  probability: 0.1            # 10% probabilidad por intervalo
```

### Generación Manual de Anomalías

Para generar una anomalía específica, usa la API del simulador (futuro) o edita temporalmente el código en [anomaly_generator.py](water-plant-simulator/src/simulation/anomaly_generator.py).

---

## Formato de Mensajes MQTT

### Sensores (Publicación)

```json
{
  "timestamp": "2024-01-15T10:30:45.123456Z",
  "device_id": "sensor_tank1_level",
  "value": 45.2,
  "unit": "%",
  "quality": "good"
}
```

**Campos**:
- `timestamp`: ISO 8601 UTC
- `device_id`: Identificador único
- `value`: Valor medido (float)
- `unit`: Unidad de medida
- `quality`: `"good"`, `"frozen"`, `"drift"`, etc.

### Actuadores - Status (Publicación)

```json
{
  "timestamp": "2024-01-15T10:30:45.123456Z",
  "device_id": "actuator_pump1",
  "state": "on",
  "mode": "auto",
  "value": 80.0,
  "health": "ok"
}
```

**Campos**:
- `state`: `"on"`, `"off"`, `"error"`
- `mode`: `"manual"`, `"auto"`
- `value`: Velocidad/apertura 0-100%
- `health`: `"ok"`, `"error: mensaje"`

### Actuadores - Command (Suscripción)

```json
{
  "command": "on",
  "value": 80,
  "mode": "manual"
}
```

**Comandos disponibles**:
- `"on"`: Encender con valor especificado
- `"off"`: Apagar (value=0)
- `"set_value"`: Cambiar velocidad/apertura
- `"set_mode"`: Cambiar a manual/auto

---

## Integración con BunkerM

### 1. Verificar Mosquitto

```powershell
# Ver estado del broker
.\deploy.ps1 status

# Ver logs de Mosquitto
docker logs -f mosquitto
```

### 2. Iniciar Simulador

```powershell
.\simulator.ps1 start
```

### 3. Suscribirse a Topics (Testing)

```powershell
# Instalar cliente MQTT
pip install paho-mqtt

# Suscribirse a todos los sensores
mosquitto_sub -h localhost -p 1900 -t "sensors/#" -v

# Suscribirse a un sensor específico
mosquitto_sub -h localhost -p 1900 -t "sensors/tank1/level" -v

# Suscribirse a todos los actuadores
mosquitto_sub -h localhost -p 1900 -t "actuators/#" -v
```

### 4. Enviar Comandos (Testing)

```powershell
# Encender pump1 al 70%
mosquitto_pub -h localhost -p 1900 -t "actuators/pump1/command" -m '{"command":"on","value":70,"mode":"manual"}'

# Apagar pump1
mosquitto_pub -h localhost -p 1900 -t "actuators/pump1/command" -m '{"command":"off"}'

# Abrir valve1 al 50%
mosquitto_pub -h localhost -p 1900 -t "actuators/valve1/command" -m '{"command":"set_value","value":50}'

# Cambiar a modo automático
mosquitto_pub -h localhost -p 1900 -t "actuators/pump1/command" -m '{"command":"set_mode","mode":"auto"}'
```

### 5. Monitoreo en BunkerM (Futuro)

Una vez que BunkerM esté integrado:

1. Acceder a la interfaz web: http://localhost:2000
2. Configurar dispositivos IoT desde la planta del simulador
3. Crear dashboards con los 8 sensores
4. Configurar alertas para anomalías
5. Probar control de actuadores desde la UI

---

## Configuración de ACLs en Mosquitto

Para producción, configura ACLs para restringir acceso:

### Archivo: mosquitto/config/acl.conf

```conf
# Usuario del simulador
user simulator
topic write sensors/#
topic read actuators/+/command
topic write actuators/+/status

# Usuario de BunkerM backend
user bunkerm
topic read sensors/#
topic write actuators/+/command
topic read actuators/+/status
```

### Actualizar mosquitto.conf

```conf
# ACL configuration
acl_file /mosquitto/config/acl.conf

# Require authentication
allow_anonymous false
password_file /mosquitto/config/passwd
```

### Crear usuarios

```powershell
# Entrar al contenedor de Mosquitto
docker exec -it mosquitto sh

# Crear usuario simulator
mosquitto_passwd -c /mosquitto/config/passwd simulator

# Crear usuario bunkerm
mosquitto_passwd /mosquitto/config/passwd bunkerm

# Reiniciar Mosquitto
docker restart mosquitto
```

---

## Troubleshooting

### Problema: Simulador no se conecta a Mosquitto

**Verificación**:
```powershell
# Ver estado de Mosquitto
docker ps --filter "name=mosquitto"

# Ver logs de Mosquitto
docker logs mosquitto

# Verificar red Docker
docker network inspect bunkerm-network
```

**Solución**:
1. Asegurarse de que Mosquitto está corriendo: `.\deploy.ps1 start`
2. Verificar puerto 1883 disponible
3. Revisar credenciales en `.env.dev`

### Problema: Sensores no publican datos

**Verificación**:
```powershell
# Ver logs del simulador
.\simulator.ps1 logs

# Ejecutar en modo interactivo
docker-compose -f docker-compose.simulator.yml --env-file .env.dev up
```

**Solución**:
1. Verificar configuración en `plant_config.yaml`
2. Asegurar que `publish_interval` > 0
3. Revisar nivel de log (DEBUG para más detalle)

### Problema: Actuadores no responden a comandos

**Verificación**:
```powershell
# Ver suscripciones del simulador
.\simulator.ps1 logs | Select-String "Suscrito a topic"

# Test manual con mosquitto_pub
mosquitto_pub -h localhost -p 1900 -t "actuators/pump1/command" -m '{"command":"on","value":50}'
```

**Solución**:
1. Verificar formato JSON del comando
2. Asegurar que el topic es correcto
3. Revisar modo del actuador (manual vs auto)

### Problema: Modelo físico no actualiza valores

**Verificación**:
```powershell
# Ver logs del modelo físico
.\simulator.ps1 logs | Select-String "Modelo físico\|Tanque1"
```

**Solución**:
1. Verificar `update_dt` en configuración
2. Asegurar que actuadores están en estado conocido
3. Reiniciar simulador: `.\simulator.ps1 restart`

---

## Desarrollo Futuro

### Mejoras Planificadas

#### API REST para Control
```python
# GET /api/status
# GET /api/devices
# POST /api/anomaly/trigger
# PUT /api/controller/enable
# PUT /api/controller/disable
```

#### Interfaz Web Local
- Dashboard con gráficos en tiempo real
- Control manual de actuadores
- Generación de anomalías con botones
- Visualización del modelo físico

#### Persistencia de Datos
- Guardar histórico de mediciones en PostgreSQL
- Exportar datos a CSV/JSON
- Replay de escenarios grabados

#### Escenarios Predefinidos
- Escenario "Día Normal"
- Escenario "Fallo de Bomba"
- Escenario "Contaminación Alta"
- Escenario "Sobrecarga del Sistema"

---

## Referencias

### Archivos Principales

- [README.md](water-plant-simulator/README.md) - Documentación técnica
- [plant_config.yaml](water-plant-simulator/config/plant_config.yaml) - Configuración
- [main.py](water-plant-simulator/src/main.py) - Orquestador principal
- [Dockerfile](water-plant-simulator/Dockerfile) - Imagen Docker
- [simulator.ps1](simulator.ps1) - Script de gestión

### Estándares y Protocolos

- **MQTT 3.1.1**: http://docs.oasis-open.org/mqtt/mqtt/v3.1.1/mqtt-v3.1.1.html
- **ISO 8601**: Formato de timestamps
- **IEC 61131-3**: Estándares de control industrial
- **OPC UA**: Futuro protocolo alternativo

---

## Autor y Licencia

**Proyecto**: BunkerM Test - Water Plant Simulator  
**Autor**: BunkerM Development Team  
**Versión**: 1.0.0  
**Fecha**: Enero 2025  

Este simulador es parte del proyecto BunkerM y está diseñado exclusivamente para testing y desarrollo.
