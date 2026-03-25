# BunkerM Extended

**Plataforma de Gestión Avanzada de Broker MQTT**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Docker](https://img.shields.io/badge/Docker-20.10+-blue.svg)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-316192.svg)](https://www.postgresql.org/)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)

Fork de [BunkerM](https://github.com/bunkeriot/BunkerM) extendido con 6 funcionalidades empresariales propias y simulación industrial completa para pruebas realistas.

---

## Descripción

BunkerM Extended es una plataforma de gestión de broker MQTT que combina las capacidades de BunkerM con funcionalidades avanzadas de valor empresarial:

- **Dashboards Personalizables**: Widgets drag-and-drop para visualización en tiempo real
- **Alertas Avanzadas**: Notificaciones por email, SMS y webhooks con cooldown inteligente
- **Multi-tenancy Mejorado**: Aislamiento completo para múltiples organizaciones
- **Backup/Restore Automático**: Backups programados con versionado
- **Versionado de ACL**: Historial de cambios y rollback de configuraciones
- **Simulador de Carga**: Testing integrado de rendimiento y límites

Incluye simulación completa de **planta de tratamiento de aguas** con sensores, actuadores y lógica de control para pruebas realistas.

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                  Nginx Reverse Proxy (2000)                  │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌────────────┐  ┌──────────────┐  ┌──────────────┐
│  Next.js   │  │   FastAPI    │  │  Mosquitto   │
│  Frontend  │  │   Backend    │  │  MQTT Broker │
│            │  │  (1000-1008) │  │   (1900)     │
└────────────┘  └──────┬───────┘  └──────────────┘
                       │
                       ▼
              ┌──────────────┐
              │  PostgreSQL  │
              │    (5432)    │
              └──────────────┘
```

### Stack Tecnológico

| Componente | Tecnología |
|------------|-----------|
| **Backend** | Python 3.12 + FastAPI |
| **Frontend** | Next.js 14 + shadcn/ui |
| **Broker MQTT** | Eclipse Mosquitto |
| **Base de Datos** | PostgreSQL 16 |
| **Despliegue** | Docker Compose |
| **Simulación** | Python + paho-mqtt |

---

## Quick Start

### Prerrequisitos

- Docker 20.10+
- Docker Compose 2.0+
- Python 3.10+
- 8GB RAM recomendado

### Instalación en 3 Pasos

```powershell
# 1. Clonar el repositorio
git clone https://github.com/TU-USUARIO/BunkerM-Extended.git
cd BunkerM-Extended

# 2. Generar configuración
python scripts/generate-secrets.py

# 3. Desplegar servicios
docker-compose -f docker-compose.dev.yml up -d

# Verificar que todo está funcionando
bash scripts/check-health.sh
```

**Acceder a la plataforma**:
- **UI**: http://localhost:2000
- **pgAdmin**: http://localhost:5050 (con `--profile tools`)
- **Mosquitto MQTT**: localhost:1900

Para instrucciones detalladas, ver [DEPLOYMENT.md](./DEPLOYMENT.md).

---

## Documentación

| Documento | Descripción |
|-----------|-------------|
| [ROADMAP.md](./ROADMAP.md) | Plan completo del proyecto, fases y especificaciones técnicas |
| [DEPLOYMENT.md](./DEPLOYMENT.md) | Guía de despliegue paso a paso |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Diagramas y decisiones de arquitectura *(por crear)* |
| [API.md](./API.md) | Documentación de APIs *(por crear)* |

---

## Estado del Proyecto

### Fase 1: Preparación del Entorno Base [OK]

- [x] Fork de BunkerM configurado
- [x] Docker Compose con PostgreSQL, Mosquitto, Nginx
- [x] Scripts de utilidad y migración
- [x] Guías de despliegue

### Fase 2: Simulación Industrial [En progreso]

- [ ] Simulador de planta de tratamiento de aguas
- [ ] 10+ dispositivos IoT (sensores y actuadores)
- [ ] Lógica de control automático
- [ ] Generador de anomalías

### Fase 3: Integración y Pruebas [Pendiente]

- [ ] Pruebas de conectividad completa
- [ ] Validación de ACL y seguridad
- [ ] Detección de anomalías
- [ ] Stress testing

### Fase 4: Funcionalidades Propias [Pendiente]

- [ ] Dashboards personalizables
- [ ] Sistema de alertas avanzado
- [ ] Multi-tenancy mejorado
- [ ] Backup/restore automático
- [ ] Versionado de ACL
- [ ] Simulador de carga

**Progreso global**: 25% (Fase 1 completa)

---

## Funcionalidades Clave

### Valor Agregado vs BunkerM Original

| Feature | BunkerM Original | BunkerM Extended |
|---------|------------------|------------------|
| **Dashboards** | Fijos | [+] Personalizables con drag-and-drop |
| **Alertas** | BunkerAI (pago) | [+] Email, SMS, Webhooks integrados |
| **Multi-tenancy** | Básico | [+] Aislamiento completo por tenant |
| **Backup** | Manual export | [+] Automático programable |
| **ACL Versioning** | No | [+] Historial y rollback |
| **Load Testing** | No | [+] Simulador integrado |
| **Simulación Industrial** | No | [+] Planta de tratamiento completa |
| **Base de Datos** | SQLite | [+] PostgreSQL con concurrencia |

---

## Simulación de Planta de Tratamiento de Aguas

### Componentes Simulados

**Sensores (8):**
- Nivel de tanques
- pH del agua
- Turbidez
- Caudal (entrada/salida)
- Presión de bombas
- Temperatura ambiente

**Actuadores (4):**
- 2 Bombas (control de velocidad)
- 2 Válvulas (control de posición)

**Control Automático:**
- Nivel bajo → encender bomba
- pH fuera de rango → alerta
- Turbidez alta → ajuste de filtración

**Anomalías Simuladas:**
- Valores congelados (sensor fail)
- Spikes repentinos
- Drift gradual
- Desconexiones temporales

---

## Comandos Útiles

### Docker Compose

```powershell
# Levantar servicios
docker-compose -f docker-compose.dev.yml up -d

# Ver logs en tiempo real
docker-compose -f docker-compose.dev.yml logs -f

# Detener servicios
docker-compose -f docker-compose.dev.yml down

# Reiniciar un servicio
docker-compose -f docker-compose.dev.yml restart mosquitto
```

### Health Check

```powershell
# Verificar estado de todos los servicios
bash scripts/check-health.sh

# O manualmente
curl http://localhost:2000/health
```

### PostgreSQL

```powershell
# Conectar a base de datos
docker exec -it bunkerm-postgres psql -U bunkerm -d bunkerm_db

# Backup
docker exec bunkerm-postgres pg_dump -U bunkerm bunkerm_db > backup.sql
```

### MQTT Testing

```powershell
# Publicar mensaje
docker exec bunkerm-mosquitto mosquitto_pub -t test/topic -m "Hello"

# Suscribirse a topic
docker exec bunkerm-mosquitto mosquitto_sub -t test/# -v
```

---

## Testing

### Suite de Pruebas (Fase 3)

```powershell
# Pruebas de conectividad
pytest tests/test_connectivity.py

# Pruebas de ACL
pytest tests/test_acl.py

# Pruebas de anomalías
pytest tests/test_anomaly_detection.py

# Stress testing
python tests/stress_test.py --devices 100 --duration 300
```

---

## Métricas de Rendimiento

### Capacidad Validada (Target Fase 3)

| Métrica | Objetivo | Estado |
|---------|----------|--------|
| **Dispositivos concurrentes** | 500+ | [Pendiente] Por validar |
| **Mensajes/segundo** | 1000+ | [Pendiente] Por validar |
| **Latencia P95** | < 500ms | [Pendiente] Por validar |
| **Uptime** | > 99% | [Pendiente] Por validar |

---

## Contribuir

Este es un proyecto en desarrollo activo. Contribuciones son bienvenidas:

1. Fork el proyecto
2. Crear feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit cambios (`git commit -m 'Add AmazingFeature'`)
4. Push a branch (`git push origin feature/AmazingFeature`)
5. Abrir Pull Request

### Áreas de Contribución

- Bug fixes
- Nuevas funcionalidades
- Documentación
- Tests
- Traducciones
- UI/UX improvements

---

## Licencia

Este proyecto es un fork de [BunkerM](https://github.com/bunkeriot/BunkerM) y mantiene la licencia **Apache 2.0**.

```
Copyright 2026 [Tu organización]

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

---

## Agradecimientos

- **BunkerM Team**: Por la plataforma base excepcional
- **Eclipse Mosquitto**: Por el broker MQTT robusto
- **PostgreSQL Team**: Por la base de datos confiable
- **FastAPI**: Por el framework backend moderno

---

## Contacto y Soporte

- **Issues**: [GitHub Issues](https://github.com/TU-USUARIO/BunkerM-Extended/issues)
- **Documentación BunkerM Original**: https://docs.bunkerm.io
- **MQTT Resources**: https://mqtt.org/

---

## Roadmap Futuro (Post-MVP)

- [ ] Integración con Sparkplug B
- [ ] API REST pública para 3rd-party
- [ ] Reportes automatizados (PDF/Excel)
- [ ] Clustering de Mosquitto para HA
- [ ] Integración con InfluxDB/TimescaleDB
- [ ] Grafana dashboards
- [ ] Bridge con Google Cloud IoT, IBM Watson IoT
- [ ] Mobile app (iOS/Android)

---

**⭐ Si este proyecto te resulta útil, considera darle una estrella!**

**Estado**: 🚧 En Desarrollo Activo | **Fase**: 1/4 Completada

**Última actualización**: 25 de marzo de 2026
