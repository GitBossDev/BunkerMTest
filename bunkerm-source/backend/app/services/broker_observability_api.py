"""API interna de observabilidad broker-owned para artefactos compartidos."""
from __future__ import annotations

from fastapi import FastAPI, Query

from services import broker_observability_service as observability_svc

app = FastAPI(
    title="BHM Broker Observability Internal API",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy"}


@app.get("/internal/broker/logs")
async def get_broker_logs(limit: int = Query(default=1000, ge=1, le=5000)) -> dict:
    return observability_svc.read_broker_logs(limit=limit)


@app.get("/internal/broker/logs/source-status")
async def get_broker_logs_source_status() -> dict:
    return {"source": observability_svc.get_broker_log_source_status()}


@app.get("/internal/broker/resource-stats")
async def get_broker_resource_stats() -> dict:
    return observability_svc.read_broker_resource_stats_payload()


@app.get("/internal/broker/resource-stats/source-status")
async def get_broker_resource_stats_source_status() -> dict:
    return {"source": observability_svc.get_broker_resource_source_status()}