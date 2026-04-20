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
async def get_broker_logs(
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int | None = Query(default=None, ge=0),
) -> dict:
    return observability_svc.read_broker_logs(limit=limit, offset=offset)


@app.get("/internal/broker/logs/source-status")
async def get_broker_logs_source_status() -> dict:
    return {"source": observability_svc.get_broker_log_source_status()}


@app.get("/internal/broker/resource-stats")
async def get_broker_resource_stats() -> dict:
    return observability_svc.read_broker_resource_stats_payload()


@app.get("/internal/broker/resource-stats/source-status")
async def get_broker_resource_stats_source_status() -> dict:
    return {"source": observability_svc.get_broker_resource_source_status()}


@app.get("/internal/broker/dynsec")
async def get_broker_dynsec() -> dict:
    return observability_svc.read_broker_dynsec_payload()


@app.get("/internal/broker/dynsec/source-status")
async def get_broker_dynsec_source_status() -> dict:
    return {"source": observability_svc.get_broker_dynsec_source_status()}


@app.get("/internal/broker/mosquitto-config")
async def get_broker_mosquitto_config() -> dict:
    return observability_svc.read_broker_mosquitto_config_payload()


@app.get("/internal/broker/mosquitto-config/source-status")
async def get_broker_mosquitto_config_source_status() -> dict:
    return {"source": observability_svc.get_broker_mosquitto_config_source_status()}


@app.get("/internal/broker/passwd")
async def get_broker_passwd() -> dict:
    return observability_svc.read_broker_passwd_payload()


@app.get("/internal/broker/passwd/source-status")
async def get_broker_passwd_source_status() -> dict:
    return {"source": observability_svc.get_broker_passwd_source_status()}


@app.get("/internal/broker/tls-certs")
async def get_broker_tls_certs() -> dict:
    return observability_svc.read_broker_tls_certs_payload()


@app.get("/internal/broker/tls-certs/source-status")
async def get_broker_tls_certs_source_status() -> dict:
    return {"source": observability_svc.get_broker_tls_certs_source_status()}