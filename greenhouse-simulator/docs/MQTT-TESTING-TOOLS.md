# Guía de Pruebas MQTT - Fase 1

## Herramientas para Probar MQTT

Esta guía te muestra cómo probar la comunicación MQTT usando diferentes herramientas externas.

---

## 1. MQTT Explorer (Recomendado para principiantes)

MQTT Explorer es una herramienta gráfica gratuita y fácil de usar para interactuar con brokers MQTT.

### Instalación

**Windows:**
1. Descargar desde: https://mqtt-explorer.com/
2. Instalar el .exe descargado
3. Abrir MQTT Explorer

### Configuración de Conexión

1. Abrir MQTT Explorer
2. Hacer clic en el botón "+" para nueva conexión
3. Configurar:
   ```
   Name: Greenhouse Local
   Protocol: mqtt://
   Host: localhost
   Port: 1883
   Username: (dejar vacío)
   Password: (dejar vacío)
   ```
4. Hacer clic en "CONNECT"

### Funcionalidades Principales

**Ver Topics:**
- Al conectarse, verás automáticamente todos los topics activos
- La estructura jerárquica se muestra como un árbol expandible
- Ejemplos:
  ```
  greenhouse/
    └── test/
        ├── qos0
        ├── qos1
        ├── qos2
        ├── status
        └── heartbeat
  ```

**Publicar Mensajes:**
1. En la parte inferior derecha, pestaña "Publish"
2. Configurar:
   - **Topic**: `greenhouse/test/manual`
   - **Payload**: `Mensaje de prueba desde MQTT Explorer`
   - **QoS**: 0, 1, o 2
   - **Retain**: marcar si quieres que se retenga
3. Clic en "PUBLISH"

**Ver Mensajes Recibidos:**
- Clic en cualquier topic del árbol
- En el panel derecho verás:
  - Timestamp de recepción
  - Payload (contenido del mensaje)
  - QoS utilizado
  - Si tiene flag de retain

**Estadísticas:**
- Número de mensajes por topic
- Frecuencia de actualización
- Tamaño de payloads

---

## 2. Mosquitto CLI (Línea de Comandos)

Las herramientas de línea de comandos de Mosquitto vienen con la instalación de Docker.

### mosquitto_pub - Publicar mensajes

**Sintaxis básica:**
```bash
docker exec -it greenhouse-mosquitto mosquitto_pub -h localhost -t "TOPIC" -m "MENSAJE"
```

**Ejemplos prácticos:**

```bash
# Publicar mensaje simple (QoS 0)
docker exec -it greenhouse-mosquitto mosquitto_pub -h localhost -t "greenhouse/test/cli" -m "Hola desde CLI"

# Publicar con QoS 1
docker exec -it greenhouse-mosquitto mosquitto_pub -h localhost -t "greenhouse/test/qos1" -m "Mensaje QoS 1" -q 1

# Publicar con QoS 2
docker exec -it greenhouse-mosquitto mosquitto_pub -h localhost -t "greenhouse/test/qos2" -m "Mensaje QoS 2" -q 2

# Publicar mensaje retenido
docker exec -it greenhouse-mosquitto mosquitto_pub -h localhost -t "greenhouse/status" -m "Sistema activo" -r

# Publicar múltiples mensajes en secuencia
for i in {1..5}; do
    docker exec -it greenhouse-mosquitto mosquitto_pub -h localhost -t "greenhouse/test/loop" -m "Mensaje $i"
    sleep 1
done
```

**Parámetros importantes:**
- `-h`: Host del broker (localhost, IP, dominio)
- `-p`: Puerto (por defecto 1883)
- `-t`: Topic donde publicar
- `-m`: Mensaje (payload) a enviar
- `-q`: QoS level (0, 1, o 2)
- `-r`: Retain flag (mensaje retenido)
- `-u`: Usuario (para autenticación)
- `-P`: Contraseña (para autenticación)

### mosquitto_sub - Suscribirse a topics

**Sintaxis básica:**
```bash
docker exec -it greenhouse-mosquitto mosquitto_sub -h localhost -t "TOPIC"
```

**Ejemplos prácticos:**

```bash
# Suscribirse a un topic específico
docker exec -it greenhouse-mosquitto mosquitto_sub -h localhost -t "greenhouse/test/heartbeat"

# Suscribirse con wildcard # (todos los subniveles)
docker exec -it greenhouse-mosquitto mosquitto_sub -h localhost -t "greenhouse/#"

# Suscribirse con wildcard + (un nivel)
docker exec -it greenhouse-mosquitto mosquitto_sub -h localhost -t "greenhouse/test/+"

# Mostrar información adicional (topic, QoS, retain)
docker exec -it greenhouse-mosquitto mosquitto_sub -h localhost -t "greenhouse/#" -v

# Suscribirse con QoS específico
docker exec -it greenhouse-mosquitto mosquitto_sub -h localhost -t "greenhouse/test/qos2" -q 2
```

**Parámetros importantes:**
- `-h`: Host del broker
- `-p`: Puerto
- `-t`: Topic al cual suscribirse
- `-v`: Verbose (muestra topic además del payload)
- `-q`: QoS level deseado
- `-u`: Usuario
- `-P`: Contraseña

**Wildcards:**
- `+`: Un nivel de jerarquía
  - `sensor/+/temp` coincide con `sensor/1/temp`, `sensor/2/temp`
  - NO coincide con `sensor/1/temp/max`
- `#`: Múltiples niveles (debe ser el último carácter)
  - `sensor/#` coincide con TODO bajo `sensor/`
  - `sensor/1/#` coincide con todo bajo `sensor/1/`

---

## 3. Postman (Versión 10+)

Postman ahora soporta MQTT de forma nativa desde la versión 10.

### Configuración

1. Abrir Postman
2. Ir a **File > New > MQTT Request**
3. Configurar conexión:
   ```
   Server URL: mqtt://localhost:1883
   Client ID: postman-client-01
   ```

### Publicar Mensaje

1. Seleccionar pestaña "Message"
2. Configurar:
   - **Topic**: `greenhouse/test/postman`
   - **Message**: `{"source": "postman", "timestamp": "2026-03-19T10:30:00Z"}`
   - **QoS**: 0, 1, o 2
   - **Retain**: Marcar si es necesario
3. Clic en "Send"

### Suscribirse

1. Seleccionar pestaña "Subscribe"
2. Topic: `greenhouse/test/#`
3. QoS: 1
4. Clic en "Subscribe"
5. Los mensajes aparecerán en el panel inferior

**Limitaciones:**
- No todas las versiones de Postman tienen MQTT
- Verifica que tengas Postman v10 o superior
- Solo soporta conexiones MQTT básicas (sin SSL por el momento)

---

## 4. Broker Web UI - HiveMQ WebSockets Client

Alternativa completamente online, sin instalación.

### Acceso
1. Ir a: http://www.hivemq.com/demos/websocket-client/
2. Conectar a tu broker local:
   ```
   Host: localhost
   Port: 9001
   Path: /mqtt
   Client ID: hivemq-webclient
   ```

**Nota:** Esto puede NO funcionar si tu browser no permite conexiones a localhost desde un sitio externo. En ese caso, usa MQTT Explorer.

---

## 5. Escenarios de Prueba Recomendados

### Escenario 1: Verificar Conexión del Broker

```bash
# Terminal 1: Suscribirse para escuchar
docker exec -it greenhouse-mosquitto mosquitto_sub -h localhost -t "test/ping" -v

# Terminal 2: Publicar mensaje
docker exec -it greenhouse-mosquitto mosquitto_pub -h localhost -t "test/ping" -m "pong"
```

**Resultado esperado:** Deberías ver "pong" en la Terminal 1

### Escenario 2: Probar QoS Levels

```bash
# Terminal 1: Subscriber con QoS 0
docker exec -it greenhouse-mosquitto mosquitto_sub -h localhost -t "test/qos/#" -v

# Terminal 2: Publicar con diferentes QoS
docker exec -it greenhouse-mosquitto mosquitto_pub -h localhost -t "test/qos/0" -m "QoS 0" -q 0
docker exec -it greenhouse-mosquitto mosquitto_pub -h localhost -t "test/qos/1" -m "QoS 1" -q 1
docker exec -it greenhouse-mosquitto mosquitto_pub -h localhost -t "test/qos/2" -m "QoS 2" -q 2
```

### Escenario 3: Retained Messages

```bash
# Publicar mensaje retenido
docker exec -it greenhouse-mosquitto mosquitto_pub -h localhost -t "status/system" -m "Online" -r

# Desconectar y  reconectar un nuevo subscriber
# El nuevo subscriber recibirá inmediatamente el mensaje "Online"
docker exec -it greenhouse-mosquitto mosquitto_sub -h localhost -t "status/system"
```

### Escenario 4: Publisher y Subscriber Personalizados

```bash
# Terminal 1: Ejecutar nuestro Subscriber (Controller)
dotnet run --project src/Greenhouse.Controller

# Terminal 2: Ejecutar nuestro Publisher (Sensors)
dotnet run --project src/Greenhouse.Sensors

# Terminal 3: MQTT Explorer para ver el tráfico visualmente
```

### Escenario 5: Simular Múltiples Sensores

```bash
# Simular 3 sensores de temperatura publicando datos
for i in {1..3}; do
    docker exec -it greenhouse-mosquitto mosquitto_pub \
        -h localhost \
        -t "greenhouse/sensors/temperature/sensor-$i" \
        -m "{\"value\": $((20 + i)), \"unit\": \"celsius\"}" &
done
```

---

## 6. Verificar Logs del Broker Mosquitto

Ver qué está sucediendo en el broker:

```bash
# Ver logs en tiempo real
docker logs -f greenhouse-mosquitto

# Ver últimas 50 líneas
docker logs --tail 50 greenhouse-mosquitto

# Buscar errores específicos
docker logs greenhouse-mosquitto | grep -i error
```

---

## 7. Troubleshooting Común

### Problema: No puedo conectarme al broker

**Verificar que Docker esté corriendo:**
```bash
docker ps
```

Deberías ver `greenhouse-mosquitto` en la lista.

**Verificar que el puerto esté expuesto:**
```bash
docker port greenhouse-mosquitto
```

Deberías ver:
```
1883/tcp -> 0.0.0.0:1883
9001/tcp -> 0.0.0.0:9001
```

**Reiniciar el contenedor:**
```bash
docker-compose restart mosquitto
```

### Problema: Los mensajes no llegan

**Verificar topics:**
- Los topics son case-sensitive: `Test` != `test`
- No usar espacios en topics
- Usar `/` como separador

**Verificar QoS:**
- Si el subscriber tiene QoS 0 y el publisher QoS 2, el broker ajusta al menor (0)
- Usa QoS 1 o 2 para garantizar entrega

### Problema: Mensajes duplicados

- Es normal con QoS 1 bajo condiciones de red inestables
- Si necesitas evitar duplicados, usa QoS 2 (más lento pero garantizado)

---

## 8. Resumen de Topics de Prueba

| Topic | Descripción | Uso |
|-------|-------------|-----|
| `greenhouse/test/qos0` | Pruebas de QoS 0 | Publisher y Subscriber automáticos |
| `greenhouse/test/qos1` | Pruebas de QoS 1 | Publisher y Subscriber automáticos |
| `greenhouse/test/qos2` | Pruebas de QoS 2 | Publisher y Subscriber automáticos |
| `greenhouse/test/status` | Mensaje retenido | Publisher automático |
| `greenhouse/test/heartbeat` | Mensajes continuos | Publisher automático cada 3s |
| `greenhouse/test/manual` | Pruebas manuales | Usar con MQTT Explorer o CLI |
| `greenhouse/test/#` | Todos los test topics | Wildcard para monitoreo |

---

## 9. Comandos Rápidos de Referencia

```bash
# Levantar broker
docker-compose up -d

# Ver logs
docker logs -f greenhouse-mosquitto

# Publicar mensaje rápido
docker exec -it greenhouse-mosquitto mosquitto_pub -h localhost -t "test" -m "hello"

# Escuchar todos los topics
docker exec -it greenhouse-mosquitto mosquitto_sub -h localhost -t "#" -v

# Detener broker
docker-compose down

# Ver estado del broker
docker ps | grep mosquitto
```

---

## Siguiente Paso

Una vez que hayas probado la comunicación MQTT básica con estas herramientas, estarás listo para la **FASE 2: Simulador de Sensores**, donde crearemos sensores realistas que publiquen datos de temperatura, humedad, CO2 y luz.
