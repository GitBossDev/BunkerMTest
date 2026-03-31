# Hoja de Ruta - Proyecto Invernadero MQTT

## CONVENCIONES DEL PROYECTO

**IMPORTANTE:**
- **Variables, métodos, clases:** Siempre en inglés
- **Comentarios y documentación:** Siempre en español
- **Sin emojis:** Mantener código y documentación profesional

---

## STACK TECNOLÓGICO

### Backend:
- **C# .NET 8** (versión LTS más reciente)
- **MQTTnet** - Librería MQTT más popular y mantenida en .NET
- **Proyectos separados:**
  - `Greenhouse.Sensors` - Simulador de sensores (publisher)
  - `Greenhouse.Controller` - Servidor de control (subscriber + publisher)
  - `Greenhouse.Shared` - Modelos y configuraciones compartidas

### Frontend:
- **Blazor Server**
  - Todo en C#, sin necesidad de React/Angular
  - Tiempo real nativo (perfecto para MQTT)
  - Menos complejidad que SPA separada
  - Ideal para dashboards

### Infraestructura:
- **Eclipse Mosquitto** - Broker MQTT
- **Docker Compose** - Orquestación de contenedores

---

## FASES DEL PROYECTO

### FASE 0: Setup del Entorno

**Objetivo:** Preparar el entorno de desarrollo .NET

**Tareas:**
1. Instalar .NET SDK 8
2. Configurar VS Code o Visual Studio
3. Familiarización básica con C# (comparativa con Java)
4. Crear estructura inicial del proyecto

**Conceptos a aprender:**
- Estructura de proyectos .NET
- NuGet (equivalente a Maven/Gradle)
- Namespaces vs Packages
- Compilación y ejecución

**Entregable:**
- Documento `SETUP.md` con guía paso a paso
- Estructura de carpetas creada
- Proyectos .NET inicializados

---

### FASE 1: Fundamentos MQTT

**Objetivo:** Entender el protocolo y conectarse al broker

**Conceptos MQTT a aprender:**
- Arquitectura Pub/Sub vs Request/Response
- Broker, Publisher, Subscriber
- Estructura de Topics (hierarchy)
- Conexión básica
- Calidad de servicio (QoS) - introducción

**Tareas:**
1. Configurar Mosquitto en Docker
2. Crear cliente básico que se conecta al broker
3. Publicar mensaje simple
4. Subscribirse y recibir mensajes
5. Probar diferentes QoS levels

**Topics a utilizar:**
```
test/hello
test/response
```

**Entregable:**
- Docker Compose funcional con Mosquitto
- Cliente de consola que publica/recibe mensajes de prueba
- Documentación básica de conceptos MQTT

---

### FASE 2: Simulador de Sensores

**Objetivo:** Publicar datos simulados con cierto realismo

**Conceptos MQTT a aprender:**
- Diseño de Topics jerárquicos
- Formato de payload (JSON)
- Frecuencia de publicación
- QoS apropiado para sensores

**Topics a diseñar:**
```
greenhouse/sensors/temperature/{id}
greenhouse/sensors/humidity/{id}
greenhouse/sensors/co2/{id}
greenhouse/sensors/light/{id}
```

**Tareas:**
1. Crear 4 simuladores de sensores:
   - **Temperatura**: 15-35°C (ideal: 20-25°C)
   - **Humedad**: 30-90% (ideal: 60-80%)
   - **CO2**: 300-1500 ppm (ideal: 400-800 ppm)
   - **Luz**: 0-100% (ideal: 70-90% día, 0% noche)

2. Generación aleatoria con variaciones graduales (no saltos bruscos)
3. Publicación cada 5 segundos
4. Formato JSON estandarizado

**Modelo de datos:**
```json
{
  "sensorId": "temp-01",
  "sensorType": "temperature",
  "value": 22.5,
  "unit": "celsius",
  "timestamp": "2026-03-17T10:30:00Z"
}
```

**Entregable:**
- Aplicación de consola que simula los 4 sensores
- Publicación continua a MQTT
- Valores con comportamiento realista

---

### FASE 3: Servidor de Control (Básico)

**Objetivo:** Leer sensores y tomar decisiones automáticas

**Conceptos MQTT a aprender:**
- Subscribers con wildcards (`+`, `#`)
- QoS Levels (0, 1, 2) - diferencias y casos de uso
- Procesamiento de mensajes en paralelo
- Manejo de errores de conexión

**Wildcards MQTT:**
```
greenhouse/sensors/#          -> todos los sensores
greenhouse/sensors/+/temp-01  -> todos los tipos para temp-01
```

**Tareas:**
1. Subscribirse a todos los topics de sensores
2. Deserializar y parsear datos JSON
3. Implementar lógica de control:
   - Si temperatura > 25°C → activar ventilación
   - Si humedad < 60% → activar riego
   - Si CO2 > 800 ppm → activar ventilación
   - Si luz < 70% (y es de día) → activar luces artificiales

4. Publicar comandos a actuadores

**Topics de actuadores:**
```
greenhouse/actuators/ventilation/command
greenhouse/actuators/irrigation/command
greenhouse/actuators/lighting/command
```

**Entregable:**
- Servidor que se subscribe a sensores
- Lógica de control implementada
- Publicación de comandos a actuadores

---

### FASE 4: Actuadores y Feedback Loop

**Objetivo:** Simular que los actuadores afectan los sensores (sistema cerrado)

**Conceptos MQTT a aprender:**
- Retained Messages (último estado conocido)
- Topic design: comandos vs estado
- Bidireccionalidad en comunicación

**Topics adicionales:**
```
greenhouse/actuators/ventilation/state   (retained)
greenhouse/actuators/irrigation/state    (retained)
greenhouse/actuators/lighting/state      (retained)
```

**Tareas:**
1. Los sensores se subscriben a comandos de actuadores
2. Simular efectos de actuadores:
   - Ventilación ON → temperatura baja 0.5°C por ciclo
   - Riego ON → humedad sube 2% por ciclo
   - Ventilación ON → CO2 baja 50 ppm por ciclo
   - Luces ON → nivel de luz sube 10% por ciclo

3. Implementar inercia (cambios graduales, no instantáneos)
4. Publicar estado de actuadores (retained)
5. Manejar múltiples actuadores simultáneos

**Entregable:**
- Sistema cerrado funcional
- Actuadores modifican lecturas de sensores
- Estados persistentes con retained messages

---

### FASE 5: Dashboard Visual

**Objetivo:** Visualizar datos en tiempo real mediante interfaz web

**Conceptos a aprender:**
- Blazor Server y componentes
- Integración MQTT con aplicaciones web
- Actualización en tiempo real (SignalR implícito)
- Binding de datos

**Tareas:**
1. Crear proyecto Blazor Server
2. Integrar MQTTnet para subscribirse a topics
3. Crear componentes para:
   - Valores actuales de sensores (con indicadores de rango)
   - Estado de actuadores (ON/OFF)
   - Historial básico en memoria (últimos 20 valores)
   - Gráfico simple de líneas

4. Panel de control manual:
   - Botones para forzar actuadores
   - Selector de modo (automático/manual)

**Pantallas:**
- Dashboard principal con todos los sensores
- Vista de control de actuadores
- Historial simple

**Entregable:**
- Web dashboard accesible en `http://localhost:5000`
- Visualización en tiempo real
- Control manual de actuadores

---

### FASE 6: Conceptos Avanzados MQTT

**Objetivo:** Profundizar en features de producción

**Conceptos MQTT a aprender:**
- **Last Will and Testament (LWT)**: Detectar desconexiones inesperadas
- **Clean Session vs Persistent Session**
- **Autenticación** básica en Mosquitto (usuario/contraseña)
- **Retained messages** para estado inicial
- **Keep Alive** y timeouts

**Tareas:**
1. Configurar autenticación en Mosquitto
2. Implementar LWT en sensores:
   ```
   greenhouse/sensors/{type}/{id}/status
   Payload: "offline" (cuando se desconecta inesperadamente)
   ```

3. Usar retained messages para último estado de actuadores
4. Manejar reconexiones automáticas con backoff
5. Implementar heartbeat de sensores
6. Persistent sessions para el servidor de control

**Entregable:**
- Sistema robusto con manejo de errores
- Detección de sensores offline
- Reconexiones automáticas
- Autenticación configurada

---

### FASE 7 (OPCIONAL): Persistencia y Análisis

**Objetivo:** Guardar históricos y generar análisis

**Conceptos adicionales:**
- Integración con bases de datos time-series
- Consultas históricas
- Generación de reportes

**Tareas (si decides avanzar):**
1. Agregar TimescaleDB o InfluxDB al Docker Compose
2. Guardar histórico de sensores
3. Generar gráficos históricos (últimas 24 horas)
4. Implementar sistema de alertas
5. Exportar reportes en CSV

**Entregable:**
- Base de datos con históricos
- Gráficos históricos en dashboard
- Sistema de alertas

---

## ESTRUCTURA DE PROYECTO

```
InvernaderoMQTT/
├── ROADMAP.md                          (este archivo)
├── README.md                           (cómo ejecutar el proyecto)
├── docker-compose.yml
├── mosquitto/
│   └── config/
│       └── mosquitto.conf
├── src/
│   ├── Greenhouse.Shared/
│   │   ├── Greenhouse.Shared.csproj
│   │   ├── Models/
│   │   │   ├── SensorReading.cs
│   │   │   ├── ActuatorCommand.cs
│   │   │   ├── ActuatorState.cs
│   │   │   └── SensorType.cs
│   │   └── Configuration/
│   │       └── MqttSettings.cs
│   ├── Greenhouse.Sensors/
│   │   ├── Greenhouse.Sensors.csproj
│   │   ├── Simulators/
│   │   │   ├── BaseSensor.cs
│   │   │   ├── TemperatureSensor.cs
│   │   │   ├── HumiditySensor.cs
│   │   │   ├── CO2Sensor.cs
│   │   │   └── LightSensor.cs
│   │   ├── Services/
│   │   │   └── MqttPublisherService.cs
│   │   └── Program.cs
│   ├── Greenhouse.Controller/
│   │   ├── Greenhouse.Controller.csproj
│   │   ├── Services/
│   │   │   ├── MqttService.cs
│   │   │   ├── ControlLogicService.cs
│   │   │   └── ActuatorManagerService.cs
│   │   └── Program.cs
│   └── Greenhouse.Dashboard/
│       ├── Greenhouse.Dashboard.csproj
│       ├── Pages/
│       │   ├── Index.razor
│       │   ├── Sensors.razor
│       │   └── Actuators.razor
│       ├── Components/
│       │   ├── SensorCard.razor
│       │   └── ActuatorControl.razor
│       ├── Services/
│       │   └── MqttClientService.cs
│       └── Program.cs
└── docs/
    ├── SETUP.md                        (instalación y conceptos C#/.NET)
    ├── MQTT-CONCEPTS.md               (conceptos MQTT aprendidos)
    └── ARCHITECTURE.md                (diagrama y explicación)
```

---

## CONCEPTOS MQTT CUBIERTOS

Al finalizar el proyecto dominarás:

**Básicos:**
- Arquitectura Pub/Sub
- Broker, Publisher, Subscriber
- Topics y jerarquías
- Payloads (JSON)

**Intermedios:**
- Wildcards (`+`, `#`)
- QoS Levels (0, 1, 2)
- Retained Messages
- Clean vs Persistent Sessions

**Avanzados:**
- Last Will and Testament (LWT)
- Autenticación y seguridad
- Manejo de reconexiones
- Heartbeat y health checks

---

## ANALOGÍAS JAVA vs C#

### Gestión de dependencias:
- **Java**: Maven (`pom.xml`) o Gradle (`build.gradle`)
- **C#**: NuGet (`.csproj` con PackageReference)

### Organización de código:
- **Java**: `package com.example.project;`
- **C#**: `namespace Company.Project;`

### Interfaces y clases:
- Muy similares, sintaxis casi idéntica
- C# tiene properties (getters/setters implícitos)

### Async/Await:
- **Java**: `CompletableFuture<T>`
- **C#**: `async/await` con `Task<T>` (más elegante)

### Streams/Colecciones:
- **Java**: `stream().filter().map().collect()`
- **C#**: LINQ con `Where().Select().ToList()`

### Null safety:
- **Java**: `Optional<T>`
- **C#**: `nullable reference types` con `?`

---

## COMANDOS ÚTILES

### .NET CLI:
```bash
# Crear solución
dotnet new sln -n InvernaderoMQTT

# Crear proyecto de consola
dotnet new console -n Greenhouse.Sensors

# Crear proyecto de librería
dotnet new classlib -n Greenhouse.Shared

# Crear proyecto Blazor Server
dotnet new blazorserver -n Greenhouse.Dashboard

# Agregar proyecto a solución
dotnet sln add src/Greenhouse.Sensors/Greenhouse.Sensors.csproj

# Agregar referencia entre proyectos
dotnet add src/Greenhouse.Sensors reference src/Greenhouse.Shared

# Instalar paquete NuGet
dotnet add package MQTTnet

# Compilar
dotnet build

# Ejecutar
dotnet run --project src/Greenhouse.Sensors
```

### Docker:
```bash
# Levantar servicios
docker-compose up -d

# Ver logs
docker-compose logs -f mosquitto

# Detener servicios
docker-compose down

# Reconstruir imágenes
docker-compose build
```

---

## ESTADO ACTUAL

**Fase completada:** FASE 0 - Setup del Entorno
**Fase actual:** FASE 1 - Fundamentos MQTT
**Próximo paso:** Configurar Mosquitto en Docker y crear primer cliente MQTT

---

## NOTAS DE APRENDIZAJE

_(Añadir aquí observaciones y aprendizajes durante el desarrollo)_

### Lecciones aprendidas:
- (Se irá completando durante el proyecto)

### Problemas encontrados:
- (Se irá completando durante el proyecto)

### Mejoras futuras:
- (Se irá completando durante el proyecto)
