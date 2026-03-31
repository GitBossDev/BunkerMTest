# Conceptos MQTT - Fase 1

## Resumen de Conceptos Aprendidos

Esta guía documenta los conceptos fundamentales de MQTT que hemos cubierto en la Fase 1.

---

## 1. Arquitectura Pub/Sub

MQTT utiliza el patrón **Publish/Subscribe** (Publicar/Suscribirse), que es fundamentalmente diferente al patrón Request/Response tradicional.

### Request/Response (HTTP tradicional)
```
Cliente → Solicita datos específicos → Servidor
Cliente ← Respuesta con datos    ← Servidor
```
- Comunicación directa uno-a-uno
- El cliente debe saber la dirección del servidor
- Conexión por solicitud (no persistente)

### Publish/Subscribe (MQTT)
```
Publisher → Publica en topic → Broker → Entrega a → Subscribers
```
- Comunicación desacoplada
- Publishers y Subscribers no se conocen entre sí
- Broker actúa como intermediario central
- Conexión persistente (mantiene el estado)

**Ventajas del Pub/Sub:**
- Desacoplamiento: Publishers y Subscribers son independientes
- Escalabilidad: Un mensaje puede llegar a múltiples subscribers
- Flexibilidad: Nuevos subscribers pueden unirse sin modificar publishers
- Mejor para IoT: Eficiente para dispositivos con conectividad limitada

---

## 2. Componentes Principales

### Broker (Corredor/Intermediario)
- **Mosquitto** en nuestro caso
- Servidor central que gestiona todas las comunicaciones
- Recibe mensajes de publishers
- Distribuye mensajes a subscribers
- Mantiene sesiones de clientes
- Gestiona subscripciones

**Analogía:** El broker es como un cartero que recibe cartas (mensajes) y las distribuye a los buzones (topics) correctos.

### Publisher (Publicador)
- Cliente que ENVÍA mensajes al broker
- Especifica el topic donde publicar
- No sabe quién (si alguien) recibirá el mensaje
- Puede publicar y desconectarse inmediatamente

**Nuestro Publisher:** `Greenhouse.Sensors`

### Subscriber (Suscriptor)
- Cliente que RECIBE mensajes del broker
- Se suscribe a uno o más topics
- Recibe mensajes cuando se publican en esos topics
- Mantiene conexión activa para recibir mensajes

**Nuestro Subscriber:** `Greenhouse.Controller`

### Client (Cliente)
- Puede ser Publisher, Subscriber, o ambos
- Cada cliente necesita un **ClientId único**
- Si dos clientes usan el mismo ID, el broker desconecta al primero

---

## 3. Topics (Temas/Canales)

Los topics son "direcciones" o "canales" donde se publican los mensajes.

### Estructura Jerárquica

Topics usan `/` como separador jerárquico:

```
greenhouse/
├── sensors/
│   ├── temperature/
│   │   ├── sensor-01
│   │   └── sensor-02
│   ├── humidity/
│   │   └── sensor-01
│   └── co2/
│       └── sensor-01
└── actuators/
    ├── ventilation/
    │   └── command
    └── irrigation/
        └── command
```

### Reglas para Topics

**Permitido:**
- Letras, números, guiones, guiones bajos
- Separador `/` para jerarquía
- Ejemplo: `greenhouse/sensors/temp/01`

**NO permitido:**
- Espacios
- Caracteres especiales: `#`, `+` (reservados para wildcards)
- No comenzar con `/` (pero se permite internamente)

**Buenas prácticas:**
- Usar minúsculas consistentemente
- Ser descriptivo pero conc iso
- Máximo 3-5 niveles de profundidad
- Ejemplos:
  - `company/location/device/sensor/reading`
  - `greenhouse/zone1/temp/current`

---

## 4. QoS (Quality of Service)

QoS define la garantía de entrega de mensajes entre cliente y broker.

### QoS 0: At Most Once (Máximo una vez)
```
Publisher → Mensaje → Broker → Mensaje → Subscriber
         (sin confirmación)      (sin confirmación)
```

**Características:**
- "Fire and forget" (disparar y olvidar)
- Sin confirmación, sin reintentos
- Más rápido, menos overhead
- El mensaje puede perderse
- Sin duplicados

**Uso recomendado:**
- Datos que se actualizan frecuentemente (temperatura cada segundo)
- Datos no críticos
- Cuando la velocidad es más importante que la confiabilidad
- Telemetría de alta frecuencia

**Ejemplo:** Sensor que envía temperatura cada 1 segundo. Si se pierde un mensaje, el siguiente llegará pronto.

### QoS 1: At Least Once (Al menos una vez)
```
Publisher → Mensaje → Broker → Mensaje → Subscriber
         ← PUBACK ←          ← PUBACK ←
```

**Características:**
- El broker confirma recepción (PUBACK)
- Si no hay confirmación, se reintenta
- Garantiza que el mensaje llegue
- Pueden haber duplicados si la confirmación se pierde
- Overhead moderado

**Uso recomendado:**
- Datos importantes que no deben perderse
- Cuando duplicados son aceptables
- Lecturas de sensores críticos
- Estados de dispositivos

**Ejemplo:** Lectura de nivel de tanque de agua. Es importante que llegue, pero si se duplica, no es problema.

### QoS 2: Exactly Once (Exactamente una vez)
```
Publisher → Mensaje → Broker → Mensaje → Subscriber
         ← PUBREC ←          ← PUBREC ←
         → PUBREL →          → PUBREL →
         ← PUBCOMP ←         ← PUBCOMP ←
```

**Características:**
- Handshake de 4 pasos (más complejo)
- Garantiza entrega única (sin duplicados)
- Más lento, mayor overhead
- Uso intensivo de recursos

**Uso recomendado:**
- Comandos críticos que no deben ejecutarse dos veces
- Transacciones financieras
- Activación/desactivación de sistemas críticos
- Configuraciones que no deben duplicarse

**Ejemplo:** Comando para abrir una válvula de gas. No queremos que se ejecute dos veces.

### Comparación Visual

| QoS | Velocidad | Confiabilidad | Duplicados | Uso de Red | Casos de Uso |
|-----|-----------|---------------|------------|------------|--------------|
| 0   | Rápido    | Baja         | No         | Bajo       | Telemetría frecuente |
| 1   | Medio     | Alta         | Posibles   | Medio      | Datos importantes |
| 2   | Lento     | Muy Alta     | No         | Alto       | Comandos críticos |

### QoS Efectivo

El QoS efectivo es el MENOR entre publisher y subscriber:
- Publisher: QoS 2, Subscriber: QoS 0 → Resultado: QoS 0
- Publisher: QoS 1, Subscriber: QoS 2 → Resultado: QoS 1
- Publisher: QoS 2, Subscriber: QoS 2 → Resultado: QoS 2

---

## 5. Retained Messages (Mensajes Retenidos)

Un mensaje con flag `retain = true` se GUARDA en el broker.

### Comportamiento

```
1. Publisher publica mensaje con retain=true
   Topic: "status/system"
   Payload: "Online"
   
2. Broker GUARDA el mensaje

3. Nuevo subscriber se conecta y se suscribe a "status/system"
   → Recibe INMEDIATAMENTE el mensaje "Online"
```

### Características

- El broker guarda SOLO el último mensaje por topic
- Nuevos subscribers reciben el mensaje inmediatamente al suscribirse
- Útil para "estado actual" de dispositivos
- Solo un mensaje retenido por topic

### Casos de Uso

**Estados de dispositivos:**
```
Topic: "greenhouse/actuator/ventilation/state"
Payload: "ON" o "OFF"
Retain: true
```
Cualquier cliente que se conecte sabrá inmediatamente el estado actual.

**Configuraciones:**
```
Topic: "greenhouse/config/temperature/threshold"
Payload: "25.5"
Retain: true
```

**Último valor conocido:**
```
Topic: "sensor/temperature/last"
Payload: "22.3"
Retain: true
```

### Eliminar Mensaje Retenido

Publicar payload vacío con retain=true:
```csharp
await mqttHelper.PublishAsync("status/system", "", MqttQualityOfServiceLevel.AtLeastOnce, retain: true);
```

---

## 6. Wildcards (Comodines)

Los wildcards permiten suscribirse a múltiples topics a la vez.

### Single Level Wildcard: `+`

Reemplaza EXACTAMENTE UN nivel de jerarquía.

**Ejemplos:**
```
sensor/+/temperature
  ✓ sensor/1/temperature
  ✓ sensor/2/temperature
  ✗ sensor/1/temp/max          (dos niveles después de sensor)
  ✗ temperature                 (falta nivel)

greenhouse/+/+/reading
  ✓ greenhouse/zone1/temp/reading
  ✓ greenhouse/zone2/humidity/reading
  ✗ greenhouse/zone1/reading    (falta un nivel)
```

### Multi Level Wildcard: `#`

Reemplaza TODOS los niveles restantes. **Debe ser el último carácter.**

**Ejemplos:**
```
sensor/#
  ✓ sensor/1
  ✓ sensor/1/temperature
  ✓ sensor/1/temperature/max
  ✓ sensor/1/temperature/max/daily
  ✓ Cualquier cosa bajo sensor/

greenhouse/zone1/#
  ✓ greenhouse/zone1/temp
  ✓ greenhouse/zone1/temp/sensor-01
  ✓ greenhouse/zone1/humidity/sensor-01/reading

#
  ✓ Todos los topics del broker (úsalo con cuidado)
```

### Reglas Importantes

**Válido:**
- `sensor/+/temp`
- `sensor/#`
- `greenhouse/+/+/reading`
- `greenhouse/zone1/#`

**NO válido:**
- `sensor#` (falta `/` antes de `#`)
- `sensor/#/temp` (`#` debe ser el último)
- `sensor/+` (válido técnicamente, pero poco útil)

### Uso en Suscripciones

```csharp
// Suscribirse a todos los sensores de temperatura
await mqttHelper.SubscribeAsync("greenhouse/sensors/temperature/#");

// Suscribirse a todos los tipos de sensores del zone1
await mqttHelper.SubscribeAsync("greenhouse/zone1/+/#");

// Monitorear TODO el sistema (cuidado con el volumen de datos)
await mqttHelper.SubscribeAsync("greenhouse/#");
```

**Importante:** NO puedes publicar en topics con wildcards, solo suscribirte.

---

## 7. Keep Alive y Heartbeat

### Keep Alive

Mecanismo para mantener conexión activa entre cliente y broker.

**Funcionamiento:**
1. Cliente especifica intervalo de Keep Alive (ej: 60 segundos)
2. Si el cliente no envía ningún mensaje en ese tiempo, envía un PING
3. El broker responde con PONG
4. Si el broker no recibe nada durante KeepAlive * 1.5, cierra la conexión

**Configuración en nuestro código:**
```csharp
var settings = new MqttSettings
{
    KeepAliveSeconds = 60  // Ping cada 60 segundos si no hay actividad
};
```

**Propósito:**
- Detectar conexiones muertas (cable desconectado, WiFi perdido)
- Mantener firewalls/NAT abiertos
- Optimizar uso de red en dispositivos con batería

### Heartbeat

Mensajes periódicos para indicar que el cliente está vivo.

**Diferencia con Keep Alive:**
- Keep Alive es del protocolo MQTT (nivel de conexión)
- Heartbeat es lógica de aplicación (nivel de negocio)

**Ejemplo:**
```csharp
// Publicar heartbeat cada 30 segundos
while (true)
{
    await mqttHelper.PublishAsync(
        "greenhouse/device/heartbeat",
        $"Alive at {DateTime.Now}",
        MqttQualityOfServiceLevel.AtLeastOnce
    );
    await Task.Delay(30000);
}
```

---

## 8. Clean Session vs Persistent Session

Define qué sucede con subscripciones y mensajes cuando el cliente se desconecta.

### Clean Session = true (Por defecto en nuestro código)

**Al conectar:**
- Se elimina cualquier sesión anterior
- Se borran subscripciones previas
- Se descartan mensajes pendientes

**Al desconectar:**
- El broker elimina toda información del cliente
- Mensajes QoS 1-2 publicados mientras estaba offline se pierden

**Uso:** Dispositivos que siempre están online o no necesitan mensajes perdidos.

### Clean Session = false (Persistent Session)

**Al conectar:**
- Se restauran subscripciones previas
- Se entregan mensajes QoS 1-2 que llegaron mientras estaba offline

**Al desconectar:**
- El broker guarda subscripciones
- El broker almacena mensajes QoS 1-2 para entregar al reconectar

**Uso:** Dispositivos con conectividad intermitente que no deben perder mensajes.

**Ejemplo:**
```csharp
var options = new MqttClientOptionsBuilder()
    .WithCleanSession(false)  // Sesión persistente
    .Build();
```

---

## 9. Last Will and Testament (LWT)

Mensaje automático que el broker envía si el cliente se desconecta inesperadamente.

### Funcionamiento

1. Al conectar, el cliente configura su LWT:
```csharp
var options = new MqttClientOptionsBuilder()
    .WithWillTopic("greenhouse/sensors/temp-01/status")
    .WithWillPayload("offline")
    .WithWillQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce)
    .WithWillRetain(true)
    .Build();
```

2. Si el cliente se desconecta NORMALMENTE, el LWT NO se envía

3. Si el cliente se desconecta INESPERADAMENTE (crash, red caída), el broker envía el LWT

### Casos de Uso

**Detectar sensores offline:**
```
LWT Topic: "sensor/temp-01/status"
LWT Payload: "offline"
Retain: true
```

**Sistema de alarmas:**
```
LWT Topic: "alarm/system/status"
LWT Payload: "connection_lost"
```

**Monitoreo de dispositivos críticos:**
Los operadores pueden ser notificados automáticamente cuando un dispositivo falla.

---

## 10. Resumen de Comandos Clave

### Conceptos en Código

**Publisher:**
```csharp
await mqttHelper.PublishAsync(
    topic: "greenhouse/sensor/temp",
    payload: "22.5",
    qos: MqttQualityOfServiceLevel.AtLeastOnce,
    retain: false
);
```

**Subscriber:**
```csharp
// Suscribirse
await mqttHelper.SubscribeAsync(
    topic: "greenhouse/sensor/#",
    qos: MqttQualityOfServiceLevel.AtLeastOnce
);

// Manejar mensajes recibidos
mqttHelper.SetMessageHandler(async e =>
{
    var topic = e.ApplicationMessage.Topic;
    var payload = Encoding.UTF8.GetString(e.ApplicationMessage.PayloadSegment);
    Console.WriteLine($"Recibido en {topic}: {payload}");
    await Task.CompletedTask;
});
```

---

## 11. Mejores Prácticas Aprendidas

1. **Topics descriptivos:** Usa jerarquías claras y descriptivas
2. **QoS apropiado:** No uses QoS 2 para todo, balancea velocidad y confiabilidad
3. **Retain con cuidado:** Solo para estados/configuraciones, no para datos continuos
4. **ClientId único:** Cada cliente debe tener un ID único y descriptivo
5. **Clean Session:** Usa false solo si realmente necesitas mensajes offline
6. **Wildcards eficientes:** Evita suscribirte a `#` (todos los topics)
7. **Desconexión limpia:** Siempre llama a `DisconnectAsync()` antes de cerrar

---

## Próximos Pasos

En la **Fase 2**, aplicaremos estos conceptos para crear simuladores realistas de sensores que publiquen:
- Temperatura (15-35°C)
- Humedad (30-90%)
- CO2 (300-1500 ppm)
- Luz (0-100%)

Con topics estructurados como:
```
greenhouse/sensors/temperature/sensor-01
greenhouse/sensors/humidity/sensor-01
greenhouse/sensors/co2/sensor-01
greenhouse/sensors/light/sensor-01
```
