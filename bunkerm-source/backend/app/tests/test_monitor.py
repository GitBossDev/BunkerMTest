"""
Tests de regresion para el router Monitor (/api/v1/monitor).

El monitor usa mqtt_stats (singleton en memoria) y nonce_manager para
validacion anti-replay. No requiere DB. Los tests verifican el comportamiento
de los endpoints sin conectarse al broker MQTT real.
"""
import time
import uuid

import pytest
import services.monitor_service as monitor_svc
import routers.monitor as monitor_router


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
    assert "subscribed_clients" in body
    assert "publisher_clients" in body


async def test_stats_sanitizes_disconnected_counter(client, monkeypatch):
    """Disconnected debe derivarse desde total-connected si el contador raw se corrompe."""
    original = {
        "connected_clients": monitor_svc.mqtt_stats.connected_clients,
        "clients_total": monitor_svc.mqtt_stats.clients_total,
        "clients_maximum": monitor_svc.mqtt_stats.clients_maximum,
        "clients_disconnected": monitor_svc.mqtt_stats.clients_disconnected,
        "clients_expired": monitor_svc.mqtt_stats.clients_expired,
        "subscriptions": monitor_svc.mqtt_stats.subscriptions,
    }

    monkeypatch.setattr(monitor_svc, "read_max_connections", lambda: 10000)
    monitor_svc.mqtt_stats.connected_clients = 6
    monitor_svc.mqtt_stats.clients_total = 11
    monitor_svc.mqtt_stats.clients_maximum = 11
    monitor_svc.mqtt_stats.clients_disconnected = 4294967293
    monitor_svc.mqtt_stats.clients_expired = 2
    monitor_svc.mqtt_stats.subscriptions = 2

    try:
        params = {"nonce": str(uuid.uuid4()), "timestamp": time.time()}
        resp = await client.get("/api/v1/monitor/stats", params=params)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_connected_clients"] == 5
        assert body["clients_total"] == 10
        assert body["clients_maximum"] == 10
        assert body["clients_disconnected"] == 5
        assert body["clients_expired"] == 2
        assert body["client_max_connections"] == 10000
    finally:
        monitor_svc.mqtt_stats.connected_clients = original["connected_clients"]
        monitor_svc.mqtt_stats.clients_total = original["clients_total"]
        monitor_svc.mqtt_stats.clients_maximum = original["clients_maximum"]
        monitor_svc.mqtt_stats.clients_disconnected = original["clients_disconnected"]
        monitor_svc.mqtt_stats.clients_expired = original["clients_expired"]
        monitor_svc.mqtt_stats.subscriptions = original["subscriptions"]


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


async def test_stats_daily_summary_returns_200(client):
    """El resumen diario persistido debe exponer una colección de días sin fallar."""
    resp = await client.get("/api/v1/monitor/stats/daily-summary", params={"days": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert "days" in body


async def test_stats_health_requires_auth(raw_client):
    """Sin autenticacion, /stats/health retorna 401 o 403."""
    resp = await raw_client.get("/api/v1/monitor/stats/health")
    assert resp.status_code in (401, 403)


async def test_stats_resources_returns_shared_broker_stats(client, monkeypatch):
    """El endpoint debe exponer stats del broker standalone cuando el archivo existe."""
    monkeypatch.setattr(
        monitor_router,
        "read_broker_resource_stats",
        lambda: {
            "cpu_pct": 12.5,
            "memory_bytes": 10485760,
            "memory_limit_bytes": 20971520,
            "memory_pct": 50.0,
            "cpu_limit_cores": 1.5,
            "timestamp": "2026-04-13T10:00:00Z",
        },
    )
    resp = await client.get("/api/v1/monitor/stats/resources")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mosquitto_cpu_pct"] == 12.5
    assert body["mosquitto_rss_bytes"] == 10485760
    assert body["mosquitto_memory_limit_bytes"] == 20971520
    assert body["mosquitto_memory_pct"] == 50.0
    assert body["mosquitto_cpu_limit_cores"] == 1.5
    assert body["resource_timestamp"] == "2026-04-13T10:00:00Z"


# ---------------------------------------------------------------------------
# GET /api/v1/health  (endpoint global del servidor unificado)
# ---------------------------------------------------------------------------

async def test_unified_health_endpoint(raw_client):
    """El endpoint raiz /api/v1/health es publico y confirma que el servidor responde."""
    resp = await raw_client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "ok"
