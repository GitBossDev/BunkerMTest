# BHM — Plan de Calidad para Desarrollo Limpio

> **Contexto**: Tras completar las Fases 1-4 de reestructuracion y la limpieza del workspace (Partes V y C
> de WORK_PLAN.md), este documento define las capas de proteccion necesarias para que los proximos cambios
> no rompan funcionalidades existentes.
>
> **Problema raiz observado**: Al implementar cambios nuevos se rompian cosas ya establecidas porque no
> existia ningun mecanismo automatico que lo detectara antes de llegar al contenedor en ejecucion.
>
> **Motor de contenedores**: Podman Desktop (`podman` / `podman compose`)
> **Ultima actualizacion**: 2026-04-10

---

## Progreso general

| Fase | Estado | Descripcion |
|------|--------|-------------|
| **Fase T** | Completado | Suite de tests — base de todo lo demas |
| **Fase A** | Completado | Automatizacion del ciclo editar-test-patch |
| **Fase C** | Completado | Contrato tipado frontend-backend |
| **Fase E** | Completado | Validacion de entorno antes de arrancar |
| **Fase D** | Completado | Guardrails de arquitectura |

---

## Fase T — Suite de tests

*Sin esta fase, todas las demas son de menor valor. Es el prerequisito del resto.*

Los tests de `smart-anomaly` ya existen y sirven como patron a replicar.
El resto del backend unificado y todo el frontend carecen de tests.

### T1 — Infraestructura de tests del backend unificado

| # | Estado | Accion |
|---|--------|--------|
| T1.1 | Completado | Crear `bunkerm-source/backend/app/pytest.ini` con `asyncio_mode = auto` y `testpaths = tests` |
| T1.2 | Completado | Crear `bunkerm-source/backend/app/tests/__init__.py` |
| T1.3 | Completado | Crear `bunkerm-source/backend/app/tests/conftest.py` replicando el patron de `smart-anomaly/tests/conftest.py`: SQLite in-memory + override de `get_db` + `AsyncClient` con `ASGITransport` |
| T1.4 | Completado | Verificar que `pytest pytest-asyncio httpx aiosqlite` estan en las dependencias del stage de build (`Dockerfile.next`). Si no, añadirlos al bloque `pip install` de test. |

### T2 — Tests del router `dynsec`

Cubre los endpoints mas criticos: cualquier cambio en `dynsec_service.py` o en el JSON de DynSec se detecta aqui.

| # | Estado | Accion |
|---|--------|--------|
| T2.1 | Completado | `tests/test_dynsec.py` — `POST /api/v1/dynsec/clients` crea cliente y retorna 200 |
| T2.2 | Completado | `tests/test_dynsec.py` — `GET /api/v1/dynsec/clients` retorna lista (200) |
| T2.3 | Completado | `tests/test_dynsec.py` — `POST /api/v1/dynsec/roles` crea rol y retorna 200 |
| T2.4 | Completado | `tests/test_dynsec.py` — Peticion sin `X-API-Key` retorna 401/403 |
| T2.5 | Completado | `tests/test_dynsec.py` — `GET /api/v1/dynsec/clients/{inexistente}` retorna 404 |

### T3 — Tests del router `monitor`

| # | Estado | Accion |
|---|--------|--------|
| T3.1 | Completado | `tests/test_monitor.py` — `GET /api/v1/monitor/stats/health` retorna 200 sin autenticacion |
| T3.2 | Completado | `tests/test_monitor.py` — `GET /api/v1/monitor/stats` sin `nonce`+`timestamp` retorna 422 |
| T3.3 | Completado | `tests/test_monitor.py` — `GET /api/v1/monitor/stats` con parametros validos retorna 200 y cuerpo con campos `cpu`, `memory`, `connections` |

### T4 — Tests de los routers restantes

| # | Estado | Accion |
|---|--------|--------|
| T4.1 | Completado | `tests/test_config.py` — `GET /api/v1/config/mosquitto-config` con API key retorna 200 |
| T4.2 | Completado | `tests/test_clientlogs.py` — `GET /api/v1/clientlogs/events` con API key retorna 200 y lista |
| T4.3 | N/A | `tests/test_ai.py` — cubierto por los 30 tests de `smart-anomaly/tests/` existentes |
| T4.4 | Completado | `tests/test_bridges.py` — aws_bridge + azure_bridge: auth 401/403 + campos faltantes 422 |

### T5 — Verificar tests de `smart-anomaly` en el contenedor

| # | Estado | Accion |
|---|--------|--------|
| T5.1 | Completado | `podman exec bunkerm-platform pytest /app/smart-anomaly/tests -v` — **30 passed** |
| T5.2 | Completado | Dependencias ya presentes en el venv (pre-instaladas via smart-anomaly). Añadidas tambien a `Dockerfile.next` para builds futuros. |

---

## Fase A — Automatizacion del ciclo editar-test-patch

*Usa los tests de Fase T. Implementar despues de T1-T4.*

### A1 — Accion `test` en `deploy.ps1`

Corre los tests del backend dentro del contenedor en ejecucion.
Permite verificar rapidamente que un cambio no rompe nada antes de hacer un patch.

| # | Estado | Accion |
|---|--------|--------|
| A1.1 | Completado | `deploy.ps1 -Action test` — ejecuta `pytest /app/tests -v` dentro de `bunkerm-platform` |
| A1.2 | Completado | `deploy.ps1 -Action test -TestPath smart-anomaly` — sufijo opcional para correr solo un subset |

### A2 — Accion `smoke` en `deploy.ps1`

Version automatizada de las comprobaciones manuales V3. No requiere abrir un navegador.

| # | Estado | Accion |
|---|--------|--------|
| A2.1 | Completado | `deploy.ps1 -Action smoke` -- verifica los 5 endpoints criticos del stack: MQTT 1900, Web UI, Auth API, backend publico /api/monitor/health, backend autenticado /api/dynsec/clients |
| A2.2 | Completado | La accion falla con `exit 1` si algun check falla (util para scripting) |

### A3 — Smoke automatico al final de `Invoke-Start`

| # | Estado | Accion |
|---|--------|--------|
| A3.1 | Completado | Llamar a `Invoke-Smoke` al final de `Invoke-Start`, tras el hot-patch (espera 8s para que Next.js arranque) |
| A3.2 | Completado | Si el smoke falla, mostrar aviso en amarillo pero no detener el proceso (el stack sigue corriendo para debug manual) |

---

## Fase C — Contrato tipado frontend-backend

*Elimina la clase de bugs "el campo llego undefined" sin necesidad de tests E2E.*

El riesgo actual: cambiar el nombre de un campo en un schema Pydantic no produce ningun error
en TypeScript hasta que el usuario hace clic en el dashboard.

### C1 — Generar tipos TypeScript desde OpenAPI

| # | Estado | Accion |
|---|--------|--------|
| C1.1 | Completado | Añadir `openapi-typescript` como dev dependency en `bunkerm-source/frontend/package.json` |
| C1.2 | Completado | Añadir script `"gen-types": "openapi-typescript http://localhost:2000/api/openapi.json -o types/api.generated.ts"` en `package.json` |
| C1.3 | Completado | Añadir `types/api.generated.ts` al `.gitignore` del frontend (se regenera, no se versiona) |

### C2 — Tipar el proxy generico

| # | Estado | Accion |
|---|--------|--------|
| C2.1 | Completado | En `lib/api.ts`: reemplazar `any`/`unknown` por tipos de `api.generated.ts` en `createClient`, `getClientsPaginated`, `azureApi.saveConfig`, `monitorApi.getStats`, `configApi.getMosquittoConfig` |
| C2.2 | Completado | Añadir `npm run gen-types` como paso en las instrucciones de QUICKSTART.md para nuevos devs y post-cambio de schema |

---

## Fase E — Validacion de entorno antes de arrancar

*Evita el tipo de problema vivido con `ADMIN_INITIAL_PASSWORD`: variable omitida en el compose
que solo se descubre en runtime al intentar hacer login.*

### E1 — Script `scripts/validate-env.py`

| # | Estado | Accion |
|---|--------|--------|
| E1.1 | Completado | Crear `scripts/validate-env.py` que lea todas las variables de `core/config.py` Settings sin valor por defecto y verifique que existen en `.env.dev` |
| E1.2 | Completado | El script imprime las variables faltantes y sale con codigo 1 si hay alguna |
| E1.3 | Completado | Tambien verificar que las variables declaradas en `docker-compose.dev.yml` bajo `environment:` tienen correspondencia en `.env.dev` o tienen fallback `:-valor` |

### E2 — Integrar la validacion en `deploy.ps1`

| # | Estado | Accion |
|---|--------|--------|
| E2.1 | Completado | Llamar a `python scripts/validate-env.py` al inicio de `Invoke-Start` antes de levantar contenedores |
| E2.2 | Completado | Si la validacion falla, detener el deploy con mensaje claro sobre que variable falta |

### E3 — Documentar variables requeridas en `docker-compose.dev.yml`

| # | Estado | Accion |
|---|--------|--------|
| E3.1 | Completado | Añadir bloque de comentarios `# Variables requeridas (sin fallback)` y `# Variables con fallback seguro` en la seccion `environment:` del servicio `bunkerm` |

---

## Fase D — Guardrails de arquitectura

*Protege las decisiones de diseño tomadas en las Fases 1-4 para que no sean revertidas
inadvertidamente en el futuro.*

### D1 — Test de invariantes de arquitectura

| # | Estado | Accion |
|---|--------|--------|
| D1.1 | Completado | Crear `tests/test_architecture.py` que verifica: el backend escucha en puerto 9001 (no 1000-1005), todos los routers estan registrados en `main.py`, no hay imports circulares en `core/` |
| D1.2 | Completado | Test que verifica que `core/config.py` puede instanciarse con variables minimas (no explota al arrancar sin `.env`) |

### D2 — Guardia post-patch en `Invoke-PatchBackend`

| # | Estado | Accion |
|---|--------|--------|
| D2.1 | Completado | Tras el SIGHUP, esperar 3 segundos y verificar que el proceso `uvicorn.*9001` sigue vivo en `ps aux` |
| D2.2 | Completado | Si no aparece, mostrar los ultimos 30 lineas de log de uvicorn y advertir que el backend no esta respondiendo |

### D3 — Documento `ARCHITECTURE.md`

| # | Estado | Accion |
|---|--------|--------|
| D3.1 | Completado | Crear `ARCHITECTURE.md` en la raiz del workspace con: diagrama de puertos (texto ASCII), flujo de autenticacion (Next.js -> nginx -> uvicorn -> dynsec/mosquitto), decisiones inamovibles ("el backend es siempre un solo proceso en 9001"), y tabla de volumenes compartidos |

---

## Orden de ejecucion

```
T1 -> T2 -> T3 -> T4 -> T5    tests del backend
               |
               v
         A1 (ya completado) -> A2 -> A3    automatizacion
               |
               v
         C1 -> C2              contrato de tipos
               |
               v
         E1 -> E2 -> E3        validacion de entorno
               |
               v
         D1 -> D2 -> D3        guardrails de arquitectura
```

---

## Referencia: ciclo de trabajo recomendado tras esta fase

Una vez completadas las fases T y A, el flujo de desarrollo para cualquier nueva funcionalidad es:

```
1. Editar codigo fuente en bunkerm-source/
2. .\deploy.ps1 -Action patch-backend   (o patch-frontend)
3. .\deploy.ps1 -Action test            (confirmar que los tests siguen en verde)
4. .\deploy.ps1 -Action smoke           (confirmar que los endpoints responden)
5. Si todo verde: commit
```

Si en el paso 3 o 4 algo falla, el problema se detecta antes de hacer commit
y antes de que afecte a otras partes del sistema.
