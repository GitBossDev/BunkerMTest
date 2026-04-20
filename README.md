# BHM — Broker Health Manager

**Monitoreo y gestión de broker MQTT para entornos IoT industriales**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Docker](https://img.shields.io/badge/Docker%2FPodman-Compatible-blue.svg)](https://podman.io/)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)
[![C#](https://img.shields.io/badge/C%23-10.0+-239120.svg)](https://docs.microsoft.com/en-us/dotnet/csharp/)

BHM (Broker Health Manager) es una plataforma web de gestión y monitoreo de brokers MQTT diseñada para equipos que trabajan con dispositivos IoT industriales. La plataforma mide el pulso de tu infraestructura de mensajería: conexiones activas, latencia, caudal de mensajes, fallos de autenticación y capacidad del broker, todo en tiempo real desde un único panel.

> Nota de naming: el nombre activo del producto es BHM o Broker Health Manager. Identificadores técnicos heredados como `bunkerm-source`, `bunkerm-platform`, `bunkerm-mosquitto`, `bunkerm-*` volúmenes, imágenes y rutas históricas de SQLite se mantienen por compatibilidad operativa hasta ejecutar una fase dedicada de renombre técnico.

El objetivo es proporcionar una herramienta de operaciones completa que cubra el ciclo entero: desde la configuración del broker y la gestión de credenciales MQTT hasta la detección de anomalías, pruebas de estrés con simuladores industriales y alertas tempranas ante comportamientos anómalos.

---

## Funcionalidades principales

- **Panel de control en tiempo real** — métricas de broker (latencia RTT, clientes conectados, tasa de mensajes) con actualización automática cada 5 s
- **Gestión de clientes MQTT** — crear, deshabilitar y eliminar usuarios del broker con roles y grupos ACL; usuario administrador protegido. Muestra clientes en vivo y permite desconectar clientes
- **Broker Config UI** — formulario estructurado para ajustar listeners, WebSocket, max_connections, in-flight y queued messages sin editar ficheros
- **Sistema de alertas configurable** — Detección de anomalias para broker offline, latencia alta, saturación de clientes, bucles de reconexión y fallos de auth. Permite configurar umbrales y recibir notificaciones en el panel
- **Client y Broker Logs** — histórico de eventos (Connect, Disconnect, Subscribe, Publish, Auth Failure) con filtros por tipo y búsqueda
- **Simulador industrial** — generador de carga con hasta 25 000 clientes simultáneos para pruebas de estrés y validación de capacidad

---

## Tecnologías

### Aplicación

| Capa | Tecnología |
|------|-----------|
| Frontend | Next.js 14 · React · TypeScript · Tailwind CSS · shadcn/ui |
| Backend APIs | Python 3.12 · FastAPI · paho-mqtt · aiosqlite |
| Broker MQTT | Eclipse Mosquitto 2 · Dynamic Security Plugin |
| Autenticación | NextAuth.js · bcrypt · JWT |
| Base de datos | SQLite (usuarios, anomalías, estadísticas) |
| Reverse proxy | Nginx |
| Supervisor procesos | supervisord |
| Despliegue | Docker Compose / Podman Compose |

### Simulador industrial

| Componente | Tecnología |
|------------|-----------|
| Greenhouse Simulator | C# · .NET · MQTTnet |
| Orquestación | Docker Compose (perfil separado) |
| Scripting | PowerShell (`simulator.ps1`) |

---

## Estado de avance

**80 %** de las funcionalidades principales implementadas y testeadas en entorno local.

| Área | Estado |
|------|--------|
| Revisión de estado del arte | Completo |
| Test de brokers MQTT (Mosquitto, EMQX, HiveMQ) | Completo |
| Diseño de aplicativo | Completo |
| Diseño de simulador industrial | Completo |
| Implementación inicial de proyecto | Completo |
| Implementación de funcionalidades adicionales | Completo |
| Pruebas de estrés iniciales a menos de 10 k clientes | Completo |
| Migración de arquitectura monolítica a microservicios | Completo |
| Corrección de bugs y optimización de rendimiento post-migración | En progreso |
| Pruebas de estrés validadas a 25 k clientes | En progreso |

---

## Mejoras identificadas

- **Historial de conexiones por cliente** — persistir y consultar el historial completo de conexiones/desconexiones por username, no solo el último evento
- **Historial de topics** — métricas de uso de topics a lo largo del tiempo (volumen, frecuencia, clientes suscritos) con gráficas temporales
- **Alertas por email / webhook** — envío de notificaciones a Telegram, Slack, correo SMTP o webhooks genéricos cuando se disparan los umbrales configurados
- **Alertas en dispositivos móviles** — app PWA o notificaciones push para recibir alertas del broker en cualquier dispositivo
- **Dashboard personalizable** — widgets drag-and-drop para que cada operador configure su vista de métricas

---

## Quick Start

```powershell
# 1. Clonar el repositorio
git clone https://github.com/GitBossDev/BunkerMTest.git
cd BunkerMTest

# 2. Setup: genera .env.dev con credenciales y parchea el seed de Mosquitto
.\deploy.ps1 -Action setup

# 3. Build: construye las imágenes de BHM y Mosquitto
.\deploy.ps1 -Action build

# 4. Start
.\deploy.ps1 -Action start
```

Acceder en **http://localhost:2000**

---

## Credenciales

| Tipo | Usuario | Contraseña |
|------|---------|-----------|
| Panel (admin) | `admin@bhm.local` | `Usuario@1` |
| Broker MQTT | `admin` | *(generada en `setup`, ver `.env.dev`)* |

> Las credenciales del broker se generan aleatoriamente en cada `setup` y se sincronizan automáticamente con el broker al iniciar el contenedor.
> Al redeplegar **sin** `clean`, las credenciales del volumen existente se actualizan en cada `start` — no es necesario borrar datos.
> Para conectarse externamente (MQTT Explorer, etc.) usa el usuario `admin` y la contraseña que aparece en `.env.dev` como `MQTT_PASSWORD`.

---

## Comandos útiles

```powershell
.\deploy.ps1 -Action setup             # Configuración inicial
.\deploy.ps1 -Action build             # Construir imágenes (BHM + Mosquitto)
.\deploy.ps1 -Action start             # Iniciar servicios
.\deploy.ps1 -Action stop              # Detener
.\deploy.ps1 -Action restart           # Reiniciar
.\deploy.ps1 -Action status            # Estado y health checks
.\deploy.ps1 -Action logs -Follow      # Logs en tiempo real
.\deploy.ps1 -Action clean             # Limpieza completa (requiere confirmación)
.\deploy.ps1 -Action patch-backend     # Hot-patch Python (sin rebuild)
.\deploy.ps1 -Action patch-frontend    # Hot-patch Next.js (sin rebuild)

.\simulator.ps1 start                  # Ejecutar simulador de invernadero (greenhouse MQTT stresser)
.\simulator.ps1 stop
.\simulator.ps1 status
```

---

## Documentación

| Documento | Descripción |
|-----------|-------------|
| [BHM_MICROSERVICES_MIGRATION_PLAN.md](./BHM_MICROSERVICES_MIGRATION_PLAN.md) | Documento canónico para la migración actual a microservicios |
| [BHM_TEAM_COLLABORATION_PLAN.md](./BHM_TEAM_COLLABORATION_PLAN.md) | Guía viva de coordinación entre trabajo de arquitectura y trabajo de funcionalidades |
| [docs/adr/README.md](./docs/adr/README.md) | Registro de decisiones de arquitectura de BHM |
| [ROADMAP.md](./ROADMAP.md) | Plan, fases y especificaciones |
| [QUICKSTART.md](./QUICKSTART.md) | Inicio rápido detallado |
| [ACL_GUIDE.md](./ACL_GUIDE.md) | Guía de ACL MQTT |

---

## Licencia

Fork de [BunkerM](https://github.com/bunkeriot/BunkerM) bajo licencia **Apache 2.0**.  
Extensiones y modificaciones propias © 2025-2026.

---

**Última actualización**: 9 de abril de 2026
