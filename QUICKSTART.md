# QUICK START — Despliegue Rapido

**Tiempo estimado**: 5-10 minutos  
**Sistema**: Windows (PowerShell)  
**Ultima revision**: 10 de abril de 2026

---

## Metodo 1: Script Automatizado (Recomendado)

### Paso 1: Setup Inicial

```powershell
cd c:\Projects\BunkerMTest\BunkerMTest

# Genera .env.dev con secrets aleatorios y crea directorios de datos
.\deploy.ps1 -Action setup

# En caso el archivo esté bloqueado por políticas de seguridad de Windows
Unblock-File deploy.ps1
```

### Paso 2: Construir imagenes

```powershell
# Construir imagen principal de BHM (primera vez o cuando haya cambios de codigo)
.\deploy.ps1 -Action build

# Reconstruir imagen de Mosquitto (solo necesario cuando cambie Dockerfile.mosquitto)
.\deploy.ps1 -Action build-mosquitto
```

### Paso 3: Iniciar servicios

```powershell
# Iniciar plataforma BHM en baseline Compose-first
# Sigue funcionando sobre Podman/Docker sin Kubernetes y PostgreSQL
# ya forma parte del baseline operativo del stack.
.\deploy.ps1 -Action start
```

`deploy.ps1 -Action start` levanta ahora el baseline Compose-first completo, incluyendo
`postgres`, y el smoke test verifica conectividad real a PostgreSQL desde `bunkerm-platform`
y `bhm-reconciler`.

### Paso 4: Verificar estado

```powershell
.\deploy.ps1 -Action status
```

### Paso 5: Acceder a la plataforma

- **Web UI**: http://localhost:2000
- **MQTT broker**: `localhost:1900`
- **PostgreSQL**: `localhost:5432`

Si necesitas `pgAdmin`, levántalo manualmente fuera del flujo normal de deploy:

```powershell
docker compose --env-file .env.dev -f docker-compose.dev.yml --profile tools up -d pgadmin
```

#### Credenciales de la UI web

Las credenciales del administrador se establecen con las variables `ADMIN_INITIAL_EMAIL` y
`ADMIN_INITIAL_PASSWORD` del archivo `.env.dev`, generadas automáticamente con `setup`.

```powershell
# Ver credenciales generadas
Get-Content .env.dev | Select-String 'ADMIN_INITIAL'
```

> **Nota**: Si `.env.dev` no define `ADMIN_INITIAL_PASSWORD`, el sistema genera una contraseña
> aleatoria en el primer arranque y la muestra en el log del contenedor:
> ```powershell
> podman logs bunkerm-platform 2>&1 | Select-String 'Contrasena'
> ```
> Cambia la contraseña desde la UI en **Settings → Account** tras el primer login.

---

## Metodo 2: Hot-patch (sin rebuild)

Para aplicar cambios de codigo a un contenedor ya corriendo sin reconstruir la imagen completa:

```powershell
# Actualizar servicios Python del backend (dynsec, monitor, clientlogs, config, ai)
.\deploy.ps1 -Action patch-backend

# Actualizar frontend Next.js
.\deploy.ps1 -Action patch-frontend
```

> Los endpoints de AI usan el prefijo `/api/v1/ai` (p.ej. `GET /api/v1/ai/health`).

---

## Desarrollo Frontend: Tipos generados desde OpenAPI

After any backend schema change (e.g. new fields in `core/config.py` or a router model), regenerate
the TypeScript types so the compiler catches mismatches at build time:

```powershell
# Requires the stack to be running at localhost:2000
cd bunkerm-source\frontend
npm run gen-types
```

The command fetches `http://localhost:2000/api/openapi.json` and overwrites
`frontend/types/api.generated.ts` with types derived from the live Pydantic schema.

**When to run:**
- After adding or renaming a field in any Pydantic request/response model
- After pulling backend changes from another contributor
- Before opening a pull request that modifies API contracts

> `types/api.generated.ts` is intentionally excluded from version control (`.gitignore`).
> A hand-written placeholder is committed so the project compiles without running the generator.

---

## Metodo 3: Simulador Industrial

```powershell
# Ejecutar simulador de invernadero
.\simulator.ps1 start

# Ver estado del simulador
.\simulator.ps1 status

# Ver logs en tiempo real
.\simulator.ps1 logs

# Detener
.\simulator.ps1 stop
```

El simulador se conecta a `localhost:1900` y publica datos de 12 dispositivos IoT.

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
└── greenhouse-simulator/       # Simulador MQTT de invernadero
```
