# BunkerM Extended — BrokerPanel CIC

**Plataforma de Gestion Avanzada de Broker MQTT**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Docker](https://img.shields.io/badge/Docker%2FPodman-Compatible-blue.svg)](https://podman.io/)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)

Fork de [BunkerM](https://github.com/bunkeriot/BunkerM) extendido con funcionalidades propias de panel, roles de usuario, simulacion industrial y mejoras en logs y configuracion de broker.

---

## Descripcion

Plataforma monolitica de gestion de broker MQTT que combina las capacidades de BunkerM con extensiones propias:

- **Panel de control** con autenticacion JWT por roles (admin / usuario de solo lectura)
- **Gestion de usuarios del panel** con credenciales propias independientes de MQTT
- **Client Logs mejorados**: eventos Subscribe, Publish, Auth Failure, filtrado por tipo
- **Connected Clients**: reconstruccion correcta, filtrado de conexiones internas
- **Broker Config UI**: formulario estructurado para listeners, websocket, inflight, queued
- **ACL Test**: test de acceso a topics con soporte de wildcards MQTT (+ y #)
- **Deteccion de anomalias** (smart-anomaly, SQLite)
- **Simulador de planta de tratamiento de aguas** (Docker Compose separado)

---

## Arquitectura

```
Navegador
    |
    v
Nginx (puerto 2000)
    |           |
    v           v
Next.js      FastAPI Services
(SSR/API)    (puertos 1000-1005, 8100)
    |               |
    v               v
SQLite         Mosquitto MQTT
(usuarios,     Broker (1900 interno / 1901 externo)
 anomalias)
```

**Todo corre en un unico contenedor** `bunkerm-platform` gestionado por supervisord.

### Servicios internos

| Servicio | Puerto | Descripcion |
|----------|--------|-------------|
| Next.js frontend | nginx → 2000 | UI + API Routes + Proxy |
| Dynsec API | 1000 | Usuarios, roles, grupos MQTT |
| Monitor API | 1001 | Metricas del broker |
| Client Logs | 1002 | Logs de eventos de clientes |
| AWS Bridge | 1003 | Bridge IoT Core |
| Azure Bridge | 1004 | Bridge IoT Hub |
| Config API | 1005 | Configuracion del broker |
| Smart Anomaly | 8100 | Deteccion de anomalias (SQLite) |

### Base de datos

BunkerM usa **SQLite** internamente para todas sus funcionalidades actuales:
- `/nextjs/data/users.json` — usuarios del panel (roles admin/user)
- `/nextjs/data/smart-anomaly.db` — base de datos de anomalias
- `/nextjs/data/.api_key` — clave de API activa

**PostgreSQL esta reservado para Fase 3-4** (nuevos microservicios propios).  
Se activa con `.\deploy.ps1 -Action start -WithTools`.

### Stack Tecnologico

| Componente | Tecnologia |
|------------|-----------|
| Backend | Python 3.12 + FastAPI |
| Frontend | Next.js 14 + shadcn/ui |
| Broker MQTT | Eclipse Mosquitto |
| Base de datos activa | SQLite (aiosqlite) |
| Base de datos futura | PostgreSQL 16 (Fase 3-4) |
| Despliegue | Docker Compose / Podman |
| Simulacion | Python + paho-mqtt |

---

## Quick Start

### Prerrequisitos

- Podman 4+ (recomendado) o Docker 20.10+
- Python 3.10+
- 4GB RAM minimo

### Instalacion

```powershell
# 1. Clonar el repositorio
git clone https://github.com/GitBossDev/BunkerMTest.git
cd BunkerMTest

# 2. Configuracion inicial (genera .env.dev y directorios)
.\deploy.ps1 -Action setup

# 3. Construir imagen
.\deploy.ps1 -Action build

# 4. Iniciar
.\deploy.ps1 -Action start
```

**Acceder**: http://localhost:2000

---

## Credenciales por defecto

| Tipo | Usuario | Contrasena |
|------|---------|-----------|
| Panel (admin) | `admin@brokerpanel.com` | `Usuario@1` |
| MQTT broker | `bunker` | (generada en setup) |

> Cambiar credenciales en **Settings > Panel Users** tras el primer login.

---

## Estado del Proyecto

### Fase 1: Preparacion del Entorno Base [COMPLETO]

- [x] Fork de BunkerM integrado en repositorio propio (GitBossDev/BunkerMTest)
- [x] Docker Compose configurado (Podman compatible)
- [x] Scripts automatizados (deploy.ps1, generate-secrets.py)
- [x] Entorno desplegado en localhost:2000

### Fase 2: Simulacion Industrial [COMPLETO]

- [x] Simulador de planta de tratamiento de aguas (water-plant-simulator/)
- [x] 12 dispositivos IoT (8 sensores + 4 actuadores)
- [x] Logica de control automatico
- [x] Generador de anomalias (freeze, spike, drift, disconnect)
- [x] Script simulator.ps1 con gestor completo

### Mejoras propias [COMPLETO]

- [x] Panel users con roles admin/user y JWT
- [x] Gestion de usuarios del panel (Settings > Panel Users)
- [x] Registro publico deshabilitado
- [x] Client Logs: eventos Subscribe, Publish, Auth Failure con filtros
- [x] Filtrado de conexiones internas auto-UUID de mosquitto_ctrl
- [x] Connected Clients: reconstruccion correcta desde logs del broker
- [x] Broker Config UI: listeners, websocket, max_inflight, max_queued
- [x] ACL Test con wildcards MQTT (+ y #)
- [x] Metadatos UI: "BrokerPanel - Para CIC"

### Fase 3: Integracion y Pruebas [Pendiente]

- [ ] Suite de pruebas de conectividad completa
- [ ] Validacion ACL y seguridad con simulador
- [ ] Deteccion de anomalias validada end-to-end
- [ ] Stress testing con metricas

### Fase 4: Funcionalidades Propias [Pendiente]

- [ ] Dashboards personalizables (drag-and-drop)
- [ ] Sistema de alertas avanzado (email, webhooks)
- [ ] Backup/restore automatico
- [ ] Versionado de ACL con historial
- [ ] Nuevos microservicios con PostgreSQL
- [ ] Simulador de carga integrado

---

## Comandos Utiles

```powershell
# Despliegue
.\deploy.ps1 -Action setup           # Configuracion inicial
.\deploy.ps1 -Action build           # Construir imagen
.\deploy.ps1 -Action start           # Iniciar (sin postgres)
.\deploy.ps1 -Action start -WithTools  # Con PostgreSQL + pgAdmin
.\deploy.ps1 -Action stop            # Detener
.\deploy.ps1 -Action status          # Estado y health checks
.\deploy.ps1 -Action logs -Follow    # Logs en tiempo real
.\deploy.ps1 -Action patch-backend   # Hot-patch Python (sin rebuild)
.\deploy.ps1 -Action patch-frontend  # Hot-patch Next.js (sin rebuild)

# Simulador
.\simulator.ps1 start
.\simulator.ps1 stop
.\simulator.ps1 status
```

---

## Documentacion

| Documento | Descripcion |
|-----------|-------------|
| [ROADMAP.md](./ROADMAP.md) | Plan, fases y especificaciones |
| [QUICKSTART.md](./QUICKSTART.md) | Inicio rapido |
| [ACL_GUIDE.md](./ACL_GUIDE.md) | Guia de ACL MQTT |

---

## Licencia

Fork de [BunkerM](https://github.com/bunkeriot/BunkerM) bajo licencia **Apache 2.0**.

---

**Estado**: En Desarrollo Activo | **Fases completadas**: 1, 2 + mejoras propias  
**Ultima actualizacion**: 31 de marzo de 2026
