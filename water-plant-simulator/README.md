# Water Plant Simulator - Planta de Tratamiento de Aguas

Simulador IoT completo de una planta de tratamiento de aguas con sensores, actuadores y lógica de control automático.

## Arquitectura de la Planta

```
┌─────────────────────────────────────────────────────────┐
│                  Planta de Tratamiento                   │
│                                                           │
│  ┌────────┐      ┌─────────┐      ┌────────┐           │
│  │ Tanque │──────│ Bomba 1 │──────│ Tanque │           │
│  │   1    │      │         │      │   2    │           │
│  │        │      └─────────┘      │        │           │
│  └────────┘                       └────────┘           │
│      │                                 │                │
│      │                                 │                │
│  ┌───▼───┐                        ┌───▼───┐           │
│  │Válvula│                        │Válvula│           │
│  │   1   │                        │   2   │           │
│  └───────┘                        └───────┘           │
│                                                         │
│  Sensores: Nivel, pH, Turbidez, Caudal, Presión, Temp │
└─────────────────────────────────────────────────────────┘
```

## Dispositivos Simulados

### Sensores (8)
- **tank1_level**: Nivel del tanque 1 (0-100%)
- **tank1_ph**: pH del agua (6.0-8.5)
- **tank1_turbidity**: Turbidez del agua (0-10 NTU)
- **flow_inlet**: Caudal de entrada (0-500 L/min)
- **flow_outlet**: Caudal de salida (0-500 L/min)
- **pump1_pressure**: Presión bomba 1 (0-5 bar)
- **pump2_pressure**: Presión bomba 2 (0-5 bar)
- **ambient_temperature**: Temperatura ambiente (15-35°C)

### Actuadores (4)
- **pump1**: Bomba 1 con control de velocidad (0-100%)
- **pump2**: Bomba 2 con control de velocidad (0-100%)
- **valve1**: Válvula 1 con control de posición (0-100%)
- **valve2**: Válvula 2 con control de posición (0-100%)

## Topics MQTT

### Sensores (Publishers)
```
sensors/tank1/level
sensors/tank1/ph
sensors/tank1/turbidity
sensors/flow/inlet
sensors/flow/outlet
sensors/pump1/pressure
sensors/pump2/pressure
sensors/ambient/temperature
```

### Actuadores (Command/Status)
```
actuators/pump1/command
actuators/pump1/status
actuators/pump2/command
actuators/pump2/status
actuators/valve1/command
actuators/valve1/status
actuators/valve2/command
actuators/valve2/status
```

### Control
```
control/plant/status
control/alerts
control/commands
```

## Formato de Mensajes

### Sensor Message
```json
{
  "timestamp": "2026-03-25T10:30:45Z",
  "device_id": "sensor_tank1_level",
  "value": 75.3,
  "unit": "%",
  "quality": "good"
}
```

### Actuator Command
```json
{
  "action": "start",
  "speed": 70,
  "timestamp": "2026-03-25T10:30:45Z"
}
```

### Actuator Status
```json
{
  "timestamp": "2026-03-25T10:30:45Z",
  "device_id": "pump1",
  "status": "running",
  "speed": 70,
  "power_consumption": 2.3,
  "hours_operation": 1234.5
}
```

## Lógica de Control Automático

El controlador implementa las siguientes reglas:

1. **Control de Nivel**:
   - Si nivel tanque1 < 20% → encender pump1
   - Si nivel tanque1 > 90% → apagar pump1

2. **Control de pH**:
   - Si pH < 6.5 o pH > 8.0 → generar alerta
   - Ajustar dosificación química

3. **Control de Turbidez**:
   - Si turbidez > 5 NTU → generar alerta
   - Aumentar filtración

4. **Seguridad**:
   - Monitorear presión de bombas
   - Detectar anomalías en sensores

## Generador de Anomalías

Tipos de anomalías simuladas:

- **Freeze**: Sensor congela valor durante 5+ minutos
- **Spike**: Valor aumenta >3× repentinamente
- **Drift**: Incremento gradual sostenido
- **Disconnect**: Cliente MQTT se desconecta temporalmente
- **Out of Range**: Valores fuera de rangos físicos posibles

## Comandos

Ver `simulator.ps1` para gestión completa:

```powershell
# Iniciar simulador
.\simulator.ps1 -Action start

# Detener simulador
.\simulator.ps1 -Action stop

# Ver estado
.\simulator.ps1 -Action status

# Activar anomalías
.\simulator.ps1 -Action anomalies -Enable
```

## Configuración

Editar `config/plant_config.yaml` para ajustar:
- Frecuencia de publicación de sensores
- Rangos de valores
- Configuración de ACL
- Reglas de control automático

## Requisitos

- Python 3.10+
- paho-mqtt
- PyYAML
- Docker (opcional)

## Instalación

```bash
cd water-plant-simulator
pip install -r requirements.txt
```

## Uso

### Modo Local (sin Docker)
```bash
python src/main.py
```

### Modo Docker
```bash
docker-compose -f ../docker-compose.simulator.yml up -d
```

---

**Parte del proyecto Broker Health Manager**  
Ver [../ROADMAP.md](../ROADMAP.md) para más información.
