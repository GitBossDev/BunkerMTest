# QUICK START - Despliegue Rápido

**Tiempo estimado**: 5-10 minutos  
**Sistema**: Windows (PowerShell)

---

## Método 1: Usando Script Automatizado (Recomendado)

### Paso 1: Setup Inicial

```powershell
# Navegar al directorio del proyecto
cd d:\Projects\BunkerMTest\BunkerMTest

# Ejecutar setup (genera .env.dev y crea directorios)
.\deploy.ps1 -Action setup
```

### Paso 2: Iniciar Servicios

```powershell
# Iniciar servicios base (PostgreSQL, Mosquitto, Nginx)
.\deploy.ps1 -Action start

# O con pgAdmin incluido
.\deploy.ps1 -Action start -WithTools
```

### Paso 3: Verificar Estado

```powershell
# Verificar que todo está funcionando
.\deploy.ps1 -Action status
```

### Paso 4: Acceder a la Plataforma

- **Web UI**: http://localhost:2000
- **pgAdmin**: http://localhost:5050 (si usaste `-WithTools`)

---

## Método 2: Manual (Paso a Paso)

### Paso 1: Generar Configuración

```powershell
cd d:\Projects\BunkerMTest\BunkerMTest
python scripts/generate-secrets.py
```

### Paso 2: Crear Directorios de Datos

```powershell
New-Item -ItemType Directory -Path data/mosquitto/data -Force
New-Item -ItemType Directory -Path data/mosquitto/log -Force
New-Item -ItemType Directory -Path data/postgres -Force
New-Item -ItemType Directory -Path data/logs -Force
New-Item -ItemType Directory -Path data/backups -Force
```

### Paso 3: Iniciar Servicios

```powershell
# Servicios base
docker-compose -f docker-compose.dev.yml up -d

# Con pgAdmin (opcional)
docker-compose -f docker-compose.dev.yml --profile tools up -d
```

### Paso 4: Ver Logs

```powershell
# Ver logs de todos los servicios
docker-compose -f docker-compose.dev.yml logs -f

# Ver logs de un servicio específico
docker-compose -f docker-compose.dev.yml logs -f postgres
```

### Paso 5: Verificar Salud

```powershell
# Manual check
curl http://localhost:2000/health

# Verificar PostgreSQL
docker exec -it bunkerm-postgres psql -U bunkerm -d bunkerm_db -c "\dt"

# Verificar Mosquitto
docker exec -it bunkerm-mosquitto mosquitto_sub -t '$SYS/#' -C 5
```

---

## Comandos Útiles

### Gestión de Servicios

```powershell
# Detener servicios
.\deploy.ps1 -Action stop
# o manualmente:
docker-compose -f docker-compose.dev.yml down

# Reiniciar servicios
.\deploy.ps1 -Action restart

# Ver logs en tiempo real
.\deploy.ps1 -Action logs -Follow

# Limpiar todo (CUIDADO: borra todos los datos)
.\deploy.ps1 -Action clean
```

### Acceso a Contenedores

```powershell
# PostgreSQL
docker exec -it bunkerm-postgres psql -U bunkerm -d bunkerm_db

# Mosquitto
docker exec -it bunkerm-mosquitto sh

# Ver logs de un servicio
docker logs -f bunkerm-postgres
```

### Testing MQTT

```powershell
# Publicar mensaje
docker exec bunkerm-mosquitto mosquitto_pub -t test/topic -m "Hello World"

# Suscribirse a topics
docker exec bunkerm-mosquitto mosquitto_sub -t test/# -v
```

---

## Troubleshooting Rápido

### Error: "Puerto ya en uso"

```powershell
# Verificar qué proceso usa el puerto
netstat -ano | findstr :2000

# Cambiar puerto en .env.dev
# NGINX_PORT=3000

# Reiniciar
.\deploy.ps1 -Action restart
```

### Error: "Docker no responde"

```powershell
# Asegurarse que Docker Desktop está corriendo
Get-Process "Docker Desktop" -ErrorAction SilentlyContinue

# Si no está corriendo, iniciarlo manualmente
```

### Error: "Permisos insuficientes"

```powershell
# Ejecutar PowerShell como Administrador
# Click derecho en PowerShell → "Ejecutar como administrador"
```

---

## Próximos Pasos

Una vez que todo está funcionando:

1. **Acceder a http://localhost:2000** para ver la página de bienvenida
2. **Revisar [DEPLOYMENT.md](./DEPLOYMENT.md)** para configuración detallada
3. **Revisar [ROADMAP.md](./ROADMAP.md)** para ver el plan completo
4. **Continuar con Fase 2**: Simulación Industrial

---

## URLs de Acceso

| Servicio | URL | Credenciales |
|----------|-----|--------------|
| **Web UI** | http://localhost:2000 | - |
| **PostgreSQL** | localhost:5432 | Ver `.env.dev` |
| **Mosquitto MQTT** | localhost:1900 | Ver `.env.dev` |
| **pgAdmin** | http://localhost:5050 | Ver `.env.dev` |
| **Health Check** | http://localhost:2000/health | - |

---

## Comandos del Script deploy.ps1

```powershell
.\deploy.ps1 -Action setup      # Setup inicial
.\deploy.ps1 -Action start      # Iniciar servicios
.\deploy.ps1 -Action stop       # Detener servicios
.\deploy.ps1 -Action restart    # Reiniciar servicios
.\deploy.ps1 -Action status     # Ver estado
.\deploy.ps1 -Action logs       # Ver logs
.\deploy.ps1 -Action clean      # Limpiar todo

# Opciones adicionales:
.\deploy.ps1 -Action start -WithTools  # Incluir pgAdmin
.\deploy.ps1 -Action logs -Follow      # Seguir logs en tiempo real
```

---

**¿Necesitas ayuda?** Revisa [DEPLOYMENT.md](./DEPLOYMENT.md) para guía detallada.
