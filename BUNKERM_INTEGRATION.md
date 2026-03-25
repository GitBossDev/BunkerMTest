# BunkerM - Integración Completa

## ✅ Estado Actual: OPERACIONAL

BunkerM ha sido desplegado exitosamente y está corriendo en modo productivo.

## 🌐 URLs de Acceso

### Interfaz Web
- **UI Principal**: [http://localhost:3000](http://localhost:3000)
- **Login**: admin@bunker.local
- **Password**: (Ver archivo `.env.dev` para credenciales)

### Broker MQTT
- **Host**: localhost
- **Puerto**: 1901
- **Puerto WebSocket**: 9001
- **Username**: bunker
- **Password**: bunker

### APIs Backend
- **Dynsec API** (Seguridad MQTT): [http://localhost:1000](http://localhost:1000)
- **Monitor API** (Datos históricos): [http://localhost:1001](http://localhost:1001)
- **AWS Bridge API**: [http://localhost:1003](http://localhost:1003)
- **Azure Bridge API**: [http://localhost:1004](http://localhost:1004)
- **Config API**: [http://localhost:1005](http://localhost:1005)
- **Smart Anomaly API**: [http://localhost:8100](http://localhost:8100)

---

## 🚀 Comandos de Gestión

### Iniciar BunkerM
```powershell
.\deploy.ps1 -Action start-bunkerm
```

### Detener BunkerM
```powershell
.\deploy.ps1 -Action stop-bunkerm
```

### Ver Logs
```powershell
docker logs bunkerm-platform -f
```

### Reiniciar BunkerM
```powershell
docker restart bunkerm-platform
```

### Estado de Servicios
```powershell
docker exec bunkerm-platform supervisorctl status
```

---

## 🛠️ Arquitectura

### Contenedor BunkerM
El contenedor `bunkerm-platform` incluye múltiples servicios gestionados por Supervisord:

1. **Mosquitto MQTT Broker** (puerto interno 1900)
   - Dynamic Security habilitado
   - Gestión de usuarios y ACLs
   - Persistencia de datos

2. **Nginx** (proxy reverso interno)
   - Sirve frontend Next.js
   - Proxy para APIs backend

3. **Next.js Frontend**
   - SSR (Server-Side Rendering)
   - Standalone build optimizado

4. **APIs Backend FastAPI**:
   - **Dynsec**: Gestión de seguridad dinámica MQTT
   - **Monitor**: Almacenamiento y consulta de datos
   - **Config**: Configuración de Mosquitto
   - **AWS/Azure Bridge**: Integración con clouds
   - **Smart Anomaly**: Detección de anomalías

### Infraestructura Externa
- **PostgreSQL**: Base de datos compartida (bunkerm-postgres:5432)
- **Red Docker**: bunkerm-network

### Puertos Expuestos
```yaml
3000:2000   # Web UI (puerto externo → interno)
1901:1900   # MQTT Broker
1000:1000   # Dynsec API
1001:1001   # Monitor API
1003:1003   # AWS Bridge API
1004:1004   # Azure Bridge API
1005:1005   # Config API
8100:8100   # Smart Anomaly API
```

---

## 🔧 Integración con Simulador

### Configuración Actual
El simulador de planta de agua está configurado para publicar datos al Mosquitto de BunkerM:

**docker-compose.simulator.yml**:
```yaml
environment:
  - MQTT_BROKER=bunkerm-platform
  - MQTT_PORT=1900
  - MQTT_USERNAME=bunker
  - MQTT_PASSWORD=bunker
```

### Iniciar Simulador
```powershell
.\simulator.ps1 start
```

### Topics Publicados por el Simulador
```
sensors/water_plant/tank1_level
sensors/water_plant/tank1_ph
sensors/water_plant/tank1_turbidity
sensors/water_plant/flow_inlet
sensors/water_plant/flow_outlet
sensors/water_plant/pump1_pressure
sensors/water_plant/pump2_pressure
sensors/water_plant/ambient_temperature
```

### Topics de Actuadores (Comandos)
```
actuators/water_plant/pump1
actuators/water_plant/pump2
actuators/water_plant/valve1
actuators/water_plant/valve2
```

**Formato de comandos**:
```json
{
  "command": "on|off|set",
  "value": 0-100,
  "timestamp": "2026-03-25T23:45:00Z"
}
```

---

## 📊 Visualización de Datos

### Acceso a Dashboard
1. Abrir [http://localhost:3000](http://localhost:3000)
2. Login con credenciales (email: `admin@bunker.local`)
3. Navegar a **Devices** para ver dispositivos MQTT

### Dispositivos Esperados
Una vez que el simulador esté publicando datos, deberían aparecer:
- **8 Sensores**: tank1_level, tank1_ph, tank1_turbidity, flow_inlet, flow_outlet, pump1_pressure, pump2_pressure, ambient_temperature
- **4 Actuadores**: pump1, pump2, valve1, valve2

---

## 🧪 Pruebas y Verificación

### 1. Verificar Servicios BunkerM
```powershell
docker exec bunkerm-platform supervisorctl status
```

**Salida esperada**:
```
aws-bridge-api           RUNNING
azure-bridge-api         RUNNING
clientlogs               RUNNING
config-api               RUNNING
dynsec-api               RUNNING
monitor-api              RUNNING
mosquitto                RUNNING
nginx                    RUNNING
nextjs-frontend          RUNNING
smart-anomaly            RUNNING (o EXITED - no crítico)
```

### 2. Probar MQTT desde Terminal
```powershell
# Subscribirse a todos los topics del simulador
docker exec bunkerm-platform mosquitto_sub -h localhost -p 1900 -u bunker -P bunker -t "sensors/#" -v

# Publicar comando a actuador
docker exec bunkerm-platform mosquitto_pub -h localhost -p 1900 -u bunker -P bunker -t "actuators/water_plant/pump1" -m '{"command":"on","value":75,"timestamp":"2026-03-25T23:45:00Z"}'
```

### 3. Verificar API Monitor
```powershell
curl http://localhost:1001/health
```

### 4. Verificar UI Responde
```powershell
curl http://localhost:3000 -UseBasicParsing | Select-Object StatusCode
# Debe devolver: 200
```

---

## 🐛 Troubleshooting

### Problema: BunkerM no inicia
```powershell
# Ver logs detallados
docker logs bunkerm-platform

# Verificar que postgres esté funcionando
docker ps --filter "name=bunkerm-postgres"

# Reiniciar servicios
docker restart bunkerm-platform
```

### Problema: No aparecen dispositivos en UI
1. Verificar que el simulador esté corriendo:
   ```powershell
   docker ps --filter "name=water-plant-simulator"
   ```

2. Ver logs del simulador:
   ```powershell
   docker logs water-plant-simulator -f
   ```

3. Verificar connectivity MQTT:
   ```powershell
   docker exec bunkerm-platform mosquitto_sub -h localhost -t "#" -v -C 10
   ```

### Problema: Smart Anomaly falla (.EXITED)
- **Esto es normal y no afecta funcionalidad básica**
- El servicio smart-anomaly requiere configuración adicional de licencia
- Los servicios principales (MQTT, Monitor, Dynsec, UI) funcionan independientemente

---

## 📂 Estructura de Datos Persistentes

```
data/bunkerm/
├── nextjs/          # Datos de Next.js (API keys, sessiones)
├── mosquitto/       # Datos MQTT (dynamic-security.json, usuarios)
└── logs/
    ├── api/         # Logs de APIs backend
    ├── mosquitto/   # Logs de Mosquitto broker
    └── nginx/       # Logs de Nginx
```

---

## 🔐 Seguridad

### Credenciales Principales
Consultar `.env.dev` para:
- `JWT_SECRET`: Autenticación JWT
- `API_KEY`: Clave de APIs
- `AUTH_SECRET`: Autenticación Next.js
- `MQTT_PASSWORD`: Password MQTT

### Cambiar Credenciales MQTT
```powershell
# Acceder al contenedor
docker exec -it bunkerm-platform sh

# Crear nuevo usuario
mosquitto_passwd -b /etc/mosquitto/mosquitto_passwd nuevo_usuario nueva_password

# Reiniciar mosquitto
supervisorctl restart mosquitto
```

---

## 📝 Notas Importantes

### Diferencias con Infraestructura Original
- **Puerto Web UI**: 3000 (en lugar de 2000, evita conflicto con nginx original)
- **Puerto MQTT**: 1901→1900 interno (en lugar de 1900 directo)
- **Simulador**: Apunta a `bunkerm-platform:1900` en lugar de `mosquitto:1883`

### Servicios No Utilizados
La infraestructura original (mosquitto en puerto 1900, nginx en puerto 2000) permanece detenida para evitar conflictos. BunkerM incluye su propio Mosquitto con Dynamic Security completo.

### Compatibilidad
- Compatible con arquitecturas x86_64, ARM64, ARMv7
- Requiere Docker 20.10+ y Docker Compose v2.0+

---

## 🚦 Estado de Implementación

| Componente | Estado | Puerto | Notas |
|------------|--------|--------|-------|
| PostgreSQL | ✅ Operacional | 5432 | Compartido |
| BunkerM Mosquitto | ✅ Operacional | 1901 | Con Dynamic Security |
| BunkerM Web UI | ✅ Operacional | 3000 | Next.js SSR |
| APIs Backend | ✅ Operacional | 1000-1005 | FastAPI |
| Smart Anomaly | ⚠️ Warning | 8100 | No crítico |
| Simulador | 🔄 Pendiente | - | Listo para conectar |

---

## 🎯 Próximos Pasos

1. **Iniciar Simulador**:
   ```powershell
   .\simulator.ps1 start
   ```

2. **Acceder a UI**: [http://localhost:3000](http://localhost:3000)

3. **Verificar Dispositivos**: Navegar a sección "Devices" en dashboard

4. **Configurar Alertas**: Usar Config API para configurar reglas personalizadas

5. **Explorar Smart Anomaly**: Analizar detecciones automáticas de anomalías

---

## 📚 Documentación Adicional

- **PHASE2_SIMULATOR.md**: Documentación completa del simulador
- **ROADMAP.md**: Plan de desarrollo y fases
- **bunkerm-source/README.md**: Documentación oficial de BunkerM

---

**Fecha de Implementación**: 2026-03-25
**Versión de BunkerM**: 2.0.0 (Next.js)
**Estado**: PRODUCCIÓN
