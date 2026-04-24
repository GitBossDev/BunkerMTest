# BHM — Broker Health Manager

**Monitoreo y gestión de broker MQTT para entornos IoT industriales**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Docker](https://img.shields.io/badge/Docker%2FPodman-Compatible-blue.svg)](https://podman.io/)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)
[![C#](https://img.shields.io/badge/C%23-10.0+-239120.svg)](https://docs.microsoft.com/en-us/dotnet/csharp/)

BHM (Broker Health Manager) es una plataforma web de gestión y monitoreo de brokers MQTT diseñada para equipos que trabajan con dispositivos IoT industriales. La plataforma mide el pulso de tu infraestructura de mensajería: conexiones activas, latencia, caudal de mensajes, fallos de autenticación y capacidad del broker, todo en tiempo real desde un único panel.

> Nota de naming: el nombre activo del producto es BHM o Broker Health Manager. Identificadores técnicos heredados como `bunkerm-source`, `bunkerm-platform`, `bunkerm-mosquitto`, `bunkerm-*` volúmenes, imágenes y rutas históricas de SQLite se mantienen por compatibilidad operativa hasta ejecutar una fase dedicada de renombre técnico.

El objetivo es proporcionar una herramienta de operaciones completa que cubra el ciclo entero: desde la configuración del broker y la gestión de credenciales MQTT hasta la detección de anomalías y alertas tempranas ante comportamientos anómalos.

---

## Funcionalidades principales

- **Panel de control en tiempo real** — métricas de broker (latencia RTT, clientes conectados, tasa de mensajes) con actualización automática cada 5 s
- **Gestión de clientes MQTT** — crear, deshabilitar y eliminar usuarios del broker con roles y grupos ACL; usuario administrador protegido. Muestra clientes en vivo y permite desconectar clientes
- **Broker Config UI** — formulario estructurado para ajustar listeners, WebSocket, max_connections, in-flight y queued messages sin editar ficheros
- **Sistema de alertas configurable** — Detección de anomalias para broker offline, latencia alta, saturación de clientes, bucles de reconexión y fallos de auth. Permite configurar umbrales y recibir notificaciones en el panel
- **Client y Broker Logs** — histórico de eventos (Connect, Disconnect, Subscribe, Publish, Auth Failure) con filtros por tipo y búsqueda
- **Simulador industrial** — herramienta externa de carga MQTT (greenhouse-simulator, no forma parte del stack de producción)

---

## Tecnologías

### Aplicación

| Capa | Tecnología |
|------|-----------|
| Frontend | Next.js 14 · React · TypeScript · Tailwind CSS · shadcn/ui |
| Backend APIs | Python 3.12 · FastAPI · paho-mqtt · SQLAlchemy async |
| Identity Service | Python 3.12 · FastAPI · bcrypt · asyncpg |
| Broker MQTT | Eclipse Mosquitto 2 · Dynamic Security Plugin |
| Autenticacion | Next.js BFF · JWT cookies · bcrypt |
| Base de datos | PostgreSQL 16 (schemas: control_plane, history, reporting, identity) |
| Reverse proxy | Nginx |
| Despliegue | Kubernetes (kind) con Podman Desktop |

> El repositorio incluye también un simulador de invernadero C# (greenhouse-simulator/) usado exclusivamente para pruebas de carga MQTT externas. No forma parte del aplicativo.

---

## Estado de avance

**Fase 5 completada** — arquitectura de microservicios Compose-first + laboratorio Kubernetes kind operativo.

| Area | Estado |
|------|--------|
| Monitoreo y gestion del broker MQTT | Completo |
| Persistencia en PostgreSQL (4 schemas) | Completo |
| Servicio de identidad standalone (bhm-identity) | Completo |
| Image split (bhm-frontend / bhm-api / bhm-identity / bhm-mosquitto) | Completo |
| Laboratorio Kubernetes kind (bhm-lab) | Completo |
| K8s Ingress nginx | Completo |
| Simulador externo de carga MQTT (greenhouse-simulator/) | Solo para pruebas |
| Pruebas de estres validadas a 25 k clientes | En progreso |

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

# 2. Setup: genera .env.dev con credenciales seguras aleatorias
.\deploy.ps1 -Action setup

# 3. Build: construye las tres imagenes (bhm-frontend, bhm-api, bhm-identity) + Mosquitto
.\deploy.ps1 -Action build
.\deploy.ps1 -Action build-mosquitto

# 4. Start
.\deploy.ps1 -Action start
```

Acceder en **http://localhost:2000**

Ver [QUICKSTART.md](./QUICKSTART.md) para instrucciones detalladas incluyendo Kubernetes,
acceso a PostgreSQL y migracion de datos.

---

## Credenciales

Las credenciales del admin del panel y del broker MQTT se generan aleatoriamente en `setup`:

```powershell
Get-Content .env.dev | Select-String 'ADMIN_INITIAL|MQTT_PASSWORD'
```

Ver [QUICKSTART.md](./QUICKSTART.md) para instrucciones de acceso.

---

## Documentacion

| Documento | Descripcion |
|-----------|-------------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Topologia, imagenes, schemas, decisiones de diseno inmutables |
| [QUICKSTART.md](./QUICKSTART.md) | Guia detallada: Compose, Kubernetes, PostgreSQL, tests |
| [ROADMAP.md](./ROADMAP.md) | Funcionalidades planeadas y especificaciones tecnicas |
| [QUALITY_PLAN.md](./QUALITY_PLAN.md) | Capas de proteccion: tests, linting, architecture guards |
| [BHM_BACKEND_KUBERNETES_STUDY_GUIDE.md](./BHM_BACKEND_KUBERNETES_STUDY_GUIDE.md) | Guia de estudio Kubernetes para el equipo |
| [docs/adr/](./docs/adr/) | Registro de decisiones de arquitectura (ADRs) |
| [docs/_legacy/](./docs/_legacy/) | Planes de trabajo y migracion concluidos (archivo historico) |

---

## Licencia

Fork de [BunkerM](https://github.com/bunkeriot/BunkerM) bajo licencia **Apache 2.0**.  
Extensiones y modificaciones propias © 2025-2026.

---

**Ultima actualizacion**: 22 de abril de 2026
