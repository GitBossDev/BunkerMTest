# Copyright (c) 2025 BunkerM
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
#
# app/main.py
"""
Punto de entrada único del backend BunkerM.
Consolida en un solo proceso uvicorn los 7 microservicios anteriores:
  - dynsec-api       (puerto 1000)
  - monitor-api      (puerto 1001)
  - clientlogs       (puerto 1002)
  - aws-bridge-api   (puerto 1003)
  - azure-bridge-api (puerto 1004)
  - config-api       (puerto 1005)
  - smart-anomaly    (puerto 8100)

Puerto unificado: 9001
"""
from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time as _time

# Agregar el paquete smart-anomaly al path para permitir sus imports internos
# del estilo 'from app.config import settings' sin conflicto con los módulos
# de la capa superior del backend unificado.
sys.path.insert(0, "/app/smart-anomaly")

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from core.config import settings
from core.database import init_db

# Servicios con estado global (deben importarse antes que los routers que los usan)
import services.monitor_service as _monitor_svc
import services.clientlogs_service as _clientlogs_svc
from services.monitor_service import connect_mqtt

# ---------------------------------------------------------------------------
# Configuración de logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Indica si el módulo smart-anomaly se inicializó correctamente
_smart_anomaly_ok: bool = False


# ---------------------------------------------------------------------------
# Lifespan — inicialización y apagado ordenado
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Tablas SQLite del backend unificado
    await init_db()
    logger.info("Base de datos inicializada")

    # 2. Conexión MQTT para el monitor
    client = connect_mqtt()
    _monitor_svc.mqtt_client_instance = client
    client.loop_start()
    logger.info("Cliente MQTT iniciado")

    # 3. Pinger de latencia (round-trip cada 15 s)
    async def _latency_pinger() -> None:
        await asyncio.sleep(5)
        while True:
            try:
                if _monitor_svc.mqtt_client_instance is not None:
                    sent_at = _time.time()
                    with _monitor_svc.mqtt_stats._lock:
                        _monitor_svc.mqtt_stats._ping_sent_at = sent_at
                    _monitor_svc.mqtt_client_instance.publish(
                        "bunkerm/monitor/ping", str(sent_at), qos=0
                    )
            except Exception:
                pass
            await asyncio.sleep(15)

    ping_task = asyncio.create_task(_latency_pinger())

    # 4. Hilos de monitoreo de logs del broker y publicaciones MQTT
    log_thread = threading.Thread(
        target=_clientlogs_svc.monitor_mosquitto_logs, daemon=True, name="log-monitor"
    )
    pub_thread = threading.Thread(
        target=_clientlogs_svc.monitor_mqtt_publishes, daemon=True, name="pub-monitor"
    )
    log_thread.start()
    pub_thread.start()
    logger.info("Hilos de clientlogs iniciados")

    # 5. Smart-anomaly: inicialización de base de datos y tareas de fondo
    sa_tasks: list[asyncio.Task[Any]] = []
    try:
        from app.config import settings as sa_settings  # noqa: F401 — valida import
        from app.database.connection import AsyncSessionLocal as _sa_db, engine as _sa_engine
        from app.database.models import Base as _sa_Base, DEFAULT_TENANT_ID, Tenant
        from app.ingestion.poller import run_events_poller, run_topics_poller
        from app.metrics.engine import run_metrics_loop
        from app.anomaly.detector import run_anomaly_loop
        from sqlalchemy import select as _sa_select

        # Crear tablas SQLite del módulo smart-anomaly
        async with _sa_engine.begin() as conn:
            await conn.run_sync(_sa_Base.metadata.create_all)
        logger.info("Tablas smart-anomaly creadas")

        # Asegurar tenant por defecto
        async with _sa_db() as db:
            result = await db.execute(_sa_select(Tenant).where(Tenant.id == DEFAULT_TENANT_ID))
            if not result.scalars().first():
                db.add(Tenant(id=DEFAULT_TENANT_ID, name="Default Community Tenant", tier="community"))
                await db.commit()
                logger.info("Tenant por defecto creado")

        sa_tasks = [
            asyncio.create_task(run_topics_poller(), name="topics-poller"),
            asyncio.create_task(run_events_poller(), name="events-poller"),
            asyncio.create_task(run_metrics_loop(), name="metrics-loop"),
            asyncio.create_task(run_anomaly_loop(), name="anomaly-loop"),
        ]
        logger.info("Tareas de fondo smart-anomaly iniciadas")

        # Marcar el módulo como disponible una vez que todas las tareas se crearon
        global _smart_anomaly_ok
        _smart_anomaly_ok = True

    except Exception as exc:
        logger.warning("Smart-anomaly no disponible — continuando sin él: %s", exc)

    yield

    # ---------------------------------------------------------------------------
    # Apagado ordenado
    # ---------------------------------------------------------------------------
    ping_task.cancel()
    for task in sa_tasks:
        task.cancel()
    if sa_tasks:
        await asyncio.gather(*sa_tasks, return_exceptions=True)
    client.loop_stop()
    _monitor_svc.mqtt_client_instance = None
    logger.info("Backend unificado detenido")


# ---------------------------------------------------------------------------
# Aplicación FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="BunkerM API",
    version="1.0.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

# Middleware CORS (una sola vez, centralizado)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de hosts de confianza
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts.split(","),
)


# ---------------------------------------------------------------------------
# Registro de routers del backend unificado
# ---------------------------------------------------------------------------

from routers.dynsec import router as dynsec_router
from routers.monitor import router as monitor_router
from routers.clientlogs import router as clientlogs_router
from routers.reporting import router as reporting_router
from routers.config_mosquitto import router as config_mosquitto_router
from routers.config_dynsec import router as config_dynsec_router
from routers.aws_bridge import router as aws_bridge_router
from routers.azure_bridge import router as azure_bridge_router

app.include_router(dynsec_router)
app.include_router(monitor_router)
app.include_router(clientlogs_router)
app.include_router(reporting_router)
app.include_router(config_mosquitto_router)
app.include_router(config_dynsec_router)
app.include_router(aws_bridge_router)
app.include_router(azure_bridge_router)

# Routers de smart-anomaly (montados con prefijo /api/v1/ai)
try:
    from app.ingestion.router import router as ingestion_router
    from app.metrics.router import router as metrics_router
    from app.anomaly.router import router as anomaly_router
    from app.alerts.router import router as alerts_router

    app.include_router(ingestion_router, prefix="/api/v1/ai")
    app.include_router(metrics_router, prefix="/api/v1/ai")
    app.include_router(anomaly_router, prefix="/api/v1/ai")
    app.include_router(alerts_router, prefix="/api/v1/ai")
    logger.info("Routers smart-anomaly registrados bajo /api/v1/ai")

except Exception as exc:
    logger.warning("No se pudieron cargar los routers smart-anomaly: %s", exc)


# ---------------------------------------------------------------------------
# Endpoints de salud del servidor unificado
# ---------------------------------------------------------------------------

@app.get("/api/v1/health", tags=["health"])
async def health() -> dict:
    """Comprueba que el servidor unificado está operativo."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "smart_anomaly": "ok" if _smart_anomaly_ok else "unavailable",
    }
