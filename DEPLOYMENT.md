# DEPLOYMENT GUIDE - BunkerM Extended

**Versión**: 0.1.0  
**Fecha**: 25 de marzo de 2026  
**Fase**: Fase 1 - Preparación del Entorno Base

---

## Tabla de Contenidos

1. [Prerrequisitos](#prerrequisitos)
2. [Instalación Inicial](#instalación-inicial)
3. [Configuración](#configuración)
4. [Despliegue](#despliegue)
5. [Verificación](#verificación)
6. [Troubleshooting](#troubleshooting)
7. [Comandos Útiles](#comandos-útiles)
8. [Próximos Pasos](#próximos-pasos)

---

## Prerrequisitos

### Software Requerido

| Software | Versión Mínima | Propósito |
|----------|----------------|-----------|
| **Docker** | 20.10+ | Contenedores |
| **Docker Compose** | 2.0+ | Orquestación de servicios |
| **Python** | 3.10+ | Scripts de utilidad |
| **Git** | 2.30+ | Control de versiones |
| **Mosquitto Client** | Latest | Testing MQTT (opcional) |
| **curl** | Latest | Health checks |

### Requisitos del Sistema

**Mínimo (Desarrollo):**
- CPU: 2 cores
- RAM: 4 GB
- Disk: 10 GB libre
- OS: Windows 10/11, Linux, macOS

**Recomendado (Desarrollo + Simulación):**
- CPU: 4 cores
- RAM: 8 GB
- Disk: 20 GB libre
- OS: Linux (mejor performance para Docker)

### Verificar Instalaciones

```powershell
# Verificar Docker
docker --version
docker-compose --version

# Verificar Python
python --version

# Verificar Git
git --version
```

---

## Instalación Inicial

### 1. Clonar el Repositorio

```powershell
# Si ya está clonado, ir al directorio
cd d:\Projects\BunkerMTest\BunkerMTest

# Si no está clonado, clonar el fork
# git clone https://github.com/TU-USUARIO/BunkerM-Extended.git
# cd BunkerM-Extended
```

### 2. Verificar Estructura de Directorios

```powershell
# Verificar que existen estos directorios
Get-ChildItem -Directory

# Deberías ver:
# - config/
# - data/
# - scripts/
# - ROADMAP.md
# - docker-compose.dev.yml
# - .env.dev.example
```

### 3. Generar Secrets

```powershell
# Generar archivo .env.dev con secrets seguros
python scripts/generate-secrets.py

# Verificar que se creó el archivo
Get-Content .env.dev | Select-String "POSTGRES_PASSWORD"
```

**[!] IMPORTANTE**: El archivo `.env.dev` contiene secrets sensibles y **NUNCA** debe subirse a Git.

### 4. Personalizar Configuración (Opcional)

Editar `.env.dev` para configurar:

- **Email notifications**: Actualizar `SMTP_*` variables
- **SMS notifications**: Actualizar `TWILIO_*` variables
- **Puertos**: Cambiar si ya están en uso en tu sistema

```powershell
# Abrir con tu editor preferido
code .env.dev
# o
notepad .env.dev
```

---

## Configuración

### Configuración de Mosquitto

El archivo `config/mosquitto/dynamic-security.json` contiene la configuración inicial de ACL.

**Actualizar password del admin:**

```powershell
# Generar hash de password (requiere mosquitto_passwd)
# El password está en .env.dev como MQTT_PASSWORD
$MQTT_PASSWORD = (Get-Content .env.dev | Select-String "MQTT_PASSWORD=").Line.Split('=')[1]

# Crear hash (en Linux/Mac)
# mosquitto_passwd -b /tmp/pass admin $MQTT_PASSWORD
# cat /tmp/pass

# El hash debe actualizarse manualmente en:
# config/mosquitto/dynamic-security.json
```

**Nota**: Por simplicidad inicial, el password hash en `dynamic-security.json` debe actualizarse después de levantar Mosquitto la primera vez usando la API de BunkerM.

### Configuración de PostgreSQL

No requiere configuración adicional. Las tablas se crean automáticamente con el script `config/postgres/init.sql`.

### Configuración de Nginx

El archivo `config/nginx/nginx.conf` está preconfigurado. Ajustar solo si:
- Cambias los puertos de backend/frontend
- Necesitas configuraciones SSL/TLS personalizadas

---

## Despliegue

### Opción 1: Despliegue Rápido (Servicios Base)

```powershell
# Levantar PostgreSQL, Mosquitto y Nginx
docker-compose -f docker-compose.dev.yml up -d postgres mosquitto nginx

# Ver logs en tiempo real
docker-compose -f docker-compose.dev.yml logs -f
```

### Opción 2: Despliegue Completo (Cuando Backend/Frontend estén listos)

```powershell
# Levantar todos los servicios
docker-compose -f docker-compose.dev.yml up -d

# Ver logs
docker-compose -f docker-compose.dev.yml logs -f
```

### Opción 3: Despliegue con pgAdmin

```powershell
# Levantar servicios incluyendo pgAdmin
docker-compose -f docker-compose.dev.yml --profile tools up -d

# pgAdmin estará disponible en http://localhost:5050
```

### Primeros Pasos Post-Despliegue

1. **Esperar a que los servicios estén listos** (30-60 segundos)

```powershell
# Verificar que todos los contenedores están running
docker ps
```

2. **Ejecutar Health Check**

```powershell
# En Windows (PowerShell con Git Bash o WSL)
bash scripts/check-health.sh

# O manualmente verificar cada servicio
curl http://localhost:2000/health
```

3. **Ejecutar Migraciones de Base de Datos**

```powershell
# Crear tablas en PostgreSQL
python scripts/migrate-to-postgres.py
```

---

## Verificación

### 1. Verificar Contenedores Docker

```powershell
# Listar contenedores en ejecución
docker ps

# Deberías ver:
# - bunkerm-postgres (puerto 5432)
# - bunkerm-mosquitto (puertos 1900, 9001)
# - bunkerm-nginx (puerto 2000)
```

### 2. Verificar PostgreSQL

```powershell
# Conectar a PostgreSQL
docker exec -it bunkerm-postgres psql -U bunkerm -d bunkerm_db

# Dentro de psql, ejecutar:
# \dt           # Listar tablas
# \d tenants    # Ver estructura de tabla tenants
# \q            # Salir
```

**Tablas esperadas:**
- `tenants`
- `message_metadata`
- `metrics_aggregates`
- `anomalies`
- `alerts`

### 3. Verificar Mosquitto

```powershell
# Verificar logs de Mosquitto
docker logs bunkerm-mosquitto

# Suscribirse a topics del sistema (requiere mosquitto_sub instalado)
mosquitto_sub -h localhost -p 1900 -t '$SYS/#' -v

# O dentro del contenedor
docker exec -it bunkerm-mosquitto mosquitto_sub -t '$SYS/#' -C 10
```

### 4. Verificar Nginx

```powershell
# Acceder a la página de bienvenida
curl http://localhost:2000

# O abrir en navegador
Start-Process http://localhost:2000
```

Deberías ver una página HTML de bienvenida con información del proyecto.

### 5. Verificar pgAdmin (si está activo)

```powershell
# Abrir pgAdmin en navegador
Start-Process http://localhost:5050

# Credenciales (definidas en .env.dev):
# Email: admin@bunkerm.local
# Password: [Ver PGADMIN_DEFAULT_PASSWORD en .env.dev]

# Agregar servidor en pgAdmin:
# Host: postgres
# Port: 5432
# Database: bunkerm_db
# Username: bunkerm
# Password: [Ver POSTGRES_PASSWORD en .env.dev]
```

---

## Troubleshooting

### Problema: Puertos ya en uso

**Error**: `bind: address already in use`

**Solución**:
```powershell
# Verificar qué proceso usa el puerto
netstat -ano | findstr :2000

# Cambiar el puerto en .env.dev
# Ejemplo: NGINX_PORT=3000

# Reiniciar servicios
docker-compose -f docker-compose.dev.yml down
docker-compose -f docker-compose.dev.yml up -d
```

### Problema: PostgreSQL no inicia

**Error**: `database system was shut down`

**Solución**:
```powershell
# Ver logs detallados
docker logs bunkerm-postgres

# Si el volumen está corrupto, eliminar y recrear
docker-compose -f docker-compose.dev.yml down -v
Remove-Item -Recurse -Force data/postgres/*
docker-compose -f docker-compose.dev.yml up -d postgres
```

### Problema: Mosquitto no acepta conexiones

**Error**: `Connection refused`

**Solución**:
```powershell
# Verificar logs
docker logs bunkerm-mosquitto

# Verificar que el puerto está expuesto
docker ps | findstr mosquitto

# Verificar configuración
docker exec -it bunkerm-mosquitto cat /mosquitto/config/mosquitto.conf

# Reiniciar Mosquitto
docker-compose -f docker-compose.dev.yml restart mosquitto
```

### Problema: Secrets no se generaron correctamente

**Error**: `CHANGE_ME_*` aparece en logs

**Solución**:
```powershell
# Regenerar secrets
python scripts/generate-secrets.py

# Verificar contenido
Get-Content .env.dev

# Recrear contenedores con nuevos secrets
docker-compose -f docker-compose.dev.yml down
docker-compose -f docker-compose.dev.yml up -d
```

### Problema: Permisos en Linux

**Error**: `Permission denied` al crear volúmenes

**Solución**:
```bash
# Crear directorios con permisos adecuados
sudo mkdir -p data/{mosquitto,postgres,logs,backups}
sudo chown -R $USER:$USER data/

# O ejecutar Docker con sudo
sudo docker-compose -f docker-compose.dev.yml up -d
```

---

## Comandos Útiles

### Docker Compose

```powershell
# Levantar servicios en background
docker-compose -f docker-compose.dev.yml up -d

# Levantar servicios y ver logs en tiempo real
docker-compose -f docker-compose.dev.yml up

# Detener servicios (mantener volúmenes)
docker-compose -f docker-compose.dev.yml down

# Detener servicios y eliminar volúmenes
docker-compose -f docker-compose.dev.yml down -v

# Reiniciar un servicio específico
docker-compose -f docker-compose.dev.yml restart mosquitto

# Ver logs de un servicio
docker-compose -f docker-compose.dev.yml logs -f postgres

# Ver logs de todos los servicios
docker-compose -f docker-compose.dev.yml logs -f

# Ver estado de servicios
docker-compose -f docker-compose.dev.yml ps

# Ejecutar comando en contenedor
docker-compose -f docker-compose.dev.yml exec postgres psql -U bunkerm

# Rebuild de imágenes
docker-compose -f docker-compose.dev.yml build

# Rebuild sin cache
docker-compose -f docker-compose.dev.yml build --no-cache
```

### Docker

```powershell
# Ver contenedores en ejecución
docker ps

# Ver todos los contenedores (incluidos detenidos)
docker ps -a

# Ver logs de un contenedor
docker logs bunkerm-postgres
docker logs -f bunkerm-mosquitto  # follow mode

# Ejecutar comando en contenedor
docker exec -it bunkerm-postgres bash

# Inspeccionar contenedor
docker inspect bunkerm-mosquitto

# Ver uso de recursos
docker stats

# Limpiar recursos no usados
docker system prune -a
```

### PostgreSQL

```powershell
# Conectar a psql
docker exec -it bunkerm-postgres psql -U bunkerm -d bunkerm_db

# Backup de base de datos
docker exec bunkerm-postgres pg_dump -U bunkerm bunkerm_db > backup.sql

# Restore de base de datos
Get-Content backup.sql | docker exec -i bunkerm-postgres psql -U bunkerm -d bunkerm_db
```

### Mosquitto

```powershell
# Publicar mensaje MQTT
docker exec bunkerm-mosquitto mosquitto_pub -h localhost -t test/topic -m "Hello MQTT"

# Suscribirse a topic
docker exec bunkerm-mosquitto mosquitto_sub -h localhost -t test/# -v

# Ver topics del sistema
docker exec bunkerm-mosquitto mosquitto_sub -h localhost -t '$SYS/#' -C 10
```

---

## Próximos Pasos

Una vez que el entorno base está desplegado y verificado:

### [OK] Fase 1 Completada

1. [x] Docker Compose configurado
2. [x] PostgreSQL funcionando
3. [x] Mosquitto funcionando
4. [x] Nginx funcionando
5. [x] Health checks pasando

### → Continuar con Fase 2: Simulación Industrial

Consultar [ROADMAP.md](./ROADMAP.md) para los siguientes pasos:

1. **Diseñar simulación de planta de tratamiento de aguas**
2. **Implementar dispositivos IoT simulados**
3. **Configurar ACL y usuarios MQTT**
4. **Dockerizar el simulador**

### → Integrar Backend y Frontend de BunkerM

Si tienes el código fuente de BunkerM:

1. **Copiar código de BunkerM al directorio del proyecto**
2. **Descomentary configurar servicios en `docker-compose.dev.yml`**
3. **Crear Dockerfiles para backend y frontend**
4. **Integrar con PostgreSQL**
5. **Acceder a UI completa en http://localhost:2000**

---

## Soporte

- **Documentación completa**: Ver [ROADMAP.md](./ROADMAP.md)
- **Issues de BunkerM original**: https://github.com/bunkeriot/BunkerM/issues
- **Logs del proyecto**: `data/logs/`

---

## Checklist de Despliegue

Usar este checklist para verificar que todo está configurado correctamente:

### Pre-Despliegue
- [ ] Docker y Docker Compose instalados y funcionando
- [ ] Repository clonado localmente
- [ ] `.env.dev` generado con secrets seguros
- [ ] Puertos 1900, 2000, 5432, 9001 disponibles

### Despliegue
- [ ] Comando `docker-compose up -d` ejecutado sin errores
- [ ] 3 contenedores running: postgres, mosquitto, nginx
- [ ] Logs sin errores críticos

### Post-Despliegue
- [ ] Health check script pasa todas las verificaciones
- [ ] PostgreSQL acepta conexiones
- [ ] Mosquitto responde a subscripciones
- [ ] Nginx muestra página de bienvenida en localhost:2000
- [ ] Tablas creadas en PostgreSQL (tenants, message_metadata, etc.)

### Opcional
- [ ] pgAdmin accesible y conectado a PostgreSQL
- [ ] Mosquitto client instalado y probado
- [ ] Backup inicial creado

---

**Estado del Despliegue**: [OK] Fase 1 Lista para Pruebas

**Última actualización**: 25 de marzo de 2026
