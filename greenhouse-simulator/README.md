# Proyecto Invernadero MQTT

Proyecto de aprendizaje de MQTT simulando un invernadero inteligente con sensores y actuadores.

## Descripción

Este proyecto simula un sistema de invernadero con:
- Sensores de temperatura, humedad, CO2 y luz
- Sistema de control automático
- Actuadores para ventilación, riego e iluminación
- Dashboard web en tiempo real

## Stack Tecnológico

- **.NET 8.0** - Framework principal
- **C# 12** - Lenguaje de programación
- **MQTTnet** - Cliente/Servidor MQTT
- **Eclipse Mosquitto** - Broker MQTT
- **Blazor Server** - Dashboard web (Fase 5)
- **Docker Compose** - Orquestación de contenedores

## Estructura del Proyecto

```
InvernaderoMQTT/
├── src/
│   ├── Greenhouse.Shared/          # Modelos y configuración compartida
│   ├── Greenhouse.Sensors/         # Simulador de sensores
│   ├── Greenhouse.Controller/      # Servidor de control
│   └── Greenhouse.Dashboard/       # Dashboard web (Fase 5)
├── mosquitto/
│   └── config/
│       └── mosquitto.conf          # Configuración del broker
├── docs/
│   ├── SETUP.md                    # Guía de instalación
│   ├── MQTT-CONCEPTS.md           # Conceptos MQTT (en desarrollo)
│   └── ARCHITECTURE.md            # Arquitectura del sistema (en desarrollo)
├── ROADMAP.md                      # Hoja de ruta del proyecto
└── docker-compose.yml              # Orquestación de servicios
```

## Requisitos Previos

- .NET SDK 8.0 o superior
- Docker Desktop
- Editor: VS Code o Visual Studio 2022

## Instalación

### 1. Verificar instalación de .NET

```bash
dotnet --version
```

### 2. Restaurar dependencias

```bash
dotnet restore
```

### 3. Compilar solución

```bash
dotnet build
```

### 4. Levantar broker MQTT

```bash
docker-compose up -d
```

## Ejecución

### Ejecutar sensores

```bash
dotnet run --project src/Greenhouse.Sensors
```

### Ejecutar controlador

```bash
dotnet run --project src/Greenhouse.Controller
```

## Fases del Proyecto

- **Fase 0**: Setup del Entorno - COMPLETADA
- **Fase 1**: Fundamentos MQTT - En desarrollo
- **Fase 2**: Simulador de Sensores
- **Fase 3**: Servidor de Control
- **Fase 4**: Actuadores y Feedback Loop
- **Fase 5**: Dashboard Visual
- **Fase 6**: Conceptos Avanzados MQTT
- **Fase 7**: Persistencia y Análisis (Opcional)

Para más detalles ver [ROADMAP.md](ROADMAP.md)

## Convenciones del Proyecto

- **Variables, métodos, clases**: En inglés
- **Comentarios y documentación**: En español
- **Sin emojis**: Código profesional

## Conceptos MQTT a Aprender

- Arquitectura Pub/Sub
- Broker, Publisher, Subscriber
- Topics y jerarquías
- QoS Levels (0, 1, 2)
- Retained Messages
- Last Will and Testament (LWT)
- Clean vs Persistent Sessions
- Autenticación y seguridad

## Comandos Útiles

### .NET

```bash
# Compilar
dotnet build

# Ejecutar tests
dotnet test

# Limpiar compilaciones
dotnet clean

# Agregar paquete NuGet
dotnet add package NombrePaquete

# Listar proyectos en solución
dotnet sln list
```

### Docker

```bash
# Levantar servicios
docker-compose up -d

# Ver logs
docker-compose logs -f

# Detener servicios
docker-compose down

# Reconstruir imágenes
docker-compose build
```

## Recursos

- [Documentación .NET](https://docs.microsoft.com/dotnet/)
- [MQTTnet Documentation](https://github.com/dotnet/MQTTnet)
- [Eclipse Mosquitto](https://mosquitto.org/)
- [MQTT Protocol Specification](https://mqtt.org/)

## Autor

Proyecto de aprendizaje para dominar MQTT y .NET

## Licencia

Proyecto educativo sin licencia específica
