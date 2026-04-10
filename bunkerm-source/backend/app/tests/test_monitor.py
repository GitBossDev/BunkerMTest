"""
Tests de regresion para el router Monitor (/api/v1/monitor).

El monitor usa mqtt_stats (singleton en memoria) y nonce_manager para
validacion anti-replay. No requiere DB. Los tests verifican el comportamiento
de los endpoints sin conectarse al broker MQTT real.
"""
import time
import uuid

import pytest


# ---------------------------------------------------------------------------
# GET /api/v1/monitor/health  (sin autenticacion)
# ---------------------------------------------------------------------------

async def test_monitor_health_public(raw_client):
    """El endpoint /health del monitor es publico y debe retornar 200."""
    resp = await raw_client.get("/api/v1/monitor/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


# ---------------------------------------------------------------------------
# GET /api/v1/monitor/stats  (requiere nonce + timestamp + auth)
# ---------------------------------------------------------------------------

async def test_stats_missing_nonce_returns_422(client):
    """Llamar a /stats sin nonce ni timestamp retorna 422 (parametros requeridos)."""
    resp = await client.get("/api/v1/monitor/stats")
    assert resp.status_code == 422


async def test_stats_missing_timestamp_returns_422(client):
    """Llamar a /stats con nonce pero sin timestamp retorna 422."""
    resp = await client.get("/api/v1/monitor/stats", params={"nonce": str(uuid.uuid4())})
    assert resp.status_code == 422


async def test_stats_with_valid_params(client):
    """
    Llamar a /stats con nonce y timestamp validos retorna 200.
    El cuerpo de respuesta puede indicar mqtt_connected=False en entorno de test
    (no hay broker), pero la estructura del payload debe estar presente.
    """
    params = {"nonce": str(uuid.uuid4()), "timestamp": time.time()}
    resp = await client.get("/api/v1/monitor/stats", params=params)
    assert resp.status_code == 200
    body = resp.json()
    # Campos minimos que el frontend consume
    assert "mqtt_connected" in body
    assert "total_connected_clients" in body
    assert "total_messages_received" in body


async def test_stats_requires_auth(raw_client):
    """Sin X-API-Key, /stats retorna 401 o 403."""
    params = {"nonce": str(uuid.uuid4()), "timestamp": time.time()}
    resp = await raw_client.get("/api/v1/monitor/stats", params=params)
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /api/v1/monitor/stats/health  (requiere auth)
# ---------------------------------------------------------------------------

async def test_stats_health_returns_200(client):
    """El endpoint /stats/health retorna 200 con un campo de estado del sistema."""
    resp = await client.get("/api/v1/monitor/stats/health")
    assert resp.status_code == 200


async def test_stats_health_requires_auth(raw_client):
    """Sin autenticacion, /stats/health retorna 401 o 403."""
    resp = await raw_client.get("/api/v1/monitor/stats/health")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /api/v1/health  (endpoint global del servidor unificado)
# ---------------------------------------------------------------------------

async def test_unified_health_endpoint(raw_client):
    """El endpoint raiz /api/v1/health es publico y confirma que el servidor responde."""
    resp = await raw_client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "ok"
