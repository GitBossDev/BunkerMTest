# QUICK START — Despliegue Rapido

**Tiempo estimado**: 5-10 minutos  
**Sistema**: Windows (PowerShell)  
**Ultima revision**: 31 de marzo de 2026

---

## Metodo 1: Script Automatizado (Recomendado)

### Paso 1: Setup Inicial

```powershell
cd c:\Projects\BunkerMTest\BunkerMTest

# Genera .env.dev con secrets aleatorios y crea directorios de datos
.\deploy.ps1 -Action setup
```

### Paso 2: Construir imagen

```powershell
# Primera vez o cuando haya cambios en el codigo fuente
.\deploy.ps1 -Action build
```

### Paso 3: Iniciar servicios

```powershell
# Iniciar plataforma BunkerM (sin PostgreSQL — no es necesario)
.\deploy.ps1 -Action start

# Opcional: iniciar con PostgreSQL + pgAdmin (Fase 3-4)
.\deploy.ps1 -Action start -WithTools
```

### Paso 4: Verificar estado

```powershell
.\deploy.ps1 -Action status
```

### Paso 5: Acceder a la plataforma

- **Web UI**: http://localhost:2000
- **Login admin**: `admin@brokerpanel.com` / `Usuario@1`
- **MQTT broker**: `localhost:1901`
- **pgAdmin** (solo con -WithTools): http://localhost:5050

---

## Metodo 2: Hot-patch (sin rebuild)

Para aplicar cambios de codigo a un contenedor ya corriendo sin reconstruir la imagen completa:

```powershell
# Actualizar servicios Python (dynsec, monitor, clientlogs, config)
.\deploy.ps1 -Action patch-backend

# Actualizar frontend Next.js
.\deploy.ps1 -Action patch-frontend
```

---

## Metodo 3: Simulador Industrial

```powershell
# Iniciar simulador de planta de tratamiento de aguas
.\simulator.ps1 start

# Ver estado del simulador
.\simulator.ps1 status

# Ver logs en tiempo real
.\simulator.ps1 logs

# Detener
.\simulator.ps1 stop
```

El simulador se conecta a `localhost:1901` y publica datos de 12 dispositivos IoT.

---

## Gestion de Contenedores

```powershell
# Detener servicios
.\deploy.ps1 -Action stop

# Reiniciar servicios
.\deploy.ps1 -Action restart

# Ver logs en tiempo real
.\deploy.ps1 -Action logs -Follow

# Logs de un contenedor especifico
podman logs bunkerm-platform -f

# Limpiar todo (CUIDADO: borra todos los datos)
.\deploy.ps1 -Action clean
```

---

## Testing MQTT directo

```powershell
# Publicar mensaje en el broker interno
podman exec bunkerm-platform mosquitto_pub -u bunker -P <password> -t test/topic -m "Hello"

# Suscribirse a topics
podman exec bunkerm-platform mosquitto_sub -u bunker -P <password> -t "test/#" -v
```

---

## Troubleshooting Rapido

### Error: "Puerto ya en uso"

```powershell
netstat -ano | findstr :2000
# Detener el proceso con el PID encontrado:
Stop-Process -Id <PID> -Force
```

### Error: "Imagen no encontrada"

```powershell
# Reconstruir imagen
.\deploy.ps1 -Action build
```

### Frontend no actualizado tras patch-frontend

```
# Limpiar cache del navegador: Ctrl+Shift+R
```

### Ver logs de un servicio especifico del contenedor

```powershell
podman exec bunkerm-platform tail -f /var/log/supervisor/dynsec-api.out.log
podman exec bunkerm-platform tail -f /var/log/supervisor/nextjs.out.log
```

---

## Estructura del Proyecto

```
BunkerMTest/
├── deploy.ps1                  # Script de despliegue
├── simulator.ps1               # Script del simulador
├── docker-compose.dev.yml      # Compose principal (bunkerm + postgres opcional)
├── docker-compose.simulator.yml # Compose del simulador
├── .env.dev                    # Variables de entorno (generado por setup)
├── bunkerm-source/             # Codigo fuente (backend + frontend)
│   ├── Dockerfile.next
│   ├── backend/app/            # Servicios FastAPI (Python)
│   └── frontend/               # Aplicacion Next.js
├── config/                     # Configuraciones del broker
│   ├── mosquitto/
│   └── postgres/
├── scripts/                    # Scripts de utilidad
└── water-plant-simulator/      # Simulador industrial
```
