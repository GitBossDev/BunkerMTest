"""
Tests de regresion para el router ClientLogs (/api/v1/clientlogs).

ClientLogs usa mqtt_monitor (deque en memoria). Sin broker activo el deque
esta vacio, pero los endpoints deben responder con la estructura correcta.
"""
import pytest


# ---------------------------------------------------------------------------
# GET /api/v1/clientlogs/events
# ---------------------------------------------------------------------------

async def test_events_returns_200_with_list(client):
    """El endpoint /events retorna 200 con el campo 'events' como lista."""
    resp = await client.get("/api/v1/clientlogs/events")
    assert resp.status_code == 200
    body = resp.json()
    assert "events" in body
    assert isinstance(body["events"], list)


async def test_events_requires_auth(raw_client):
    """Sin autenticacion retorna 401 o 403."""
    resp = await raw_client.get("/api/v1/clientlogs/events")
    assert resp.status_code in (401, 403)


async def test_events_respects_limit_param(client):
    """El parametro limit es aceptado sin error (no retorna 422)."""
    resp = await client.get("/api/v1/clientlogs/events", params={"limit": 10})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/clientlogs/connected-clients
# ---------------------------------------------------------------------------

async def test_connected_clients_returns_200(client):
    """El endpoint /connected-clients retorna 200 con el campo 'clients'."""
    resp = await client.get("/api/v1/clientlogs/connected-clients")
    assert resp.status_code == 200
    body = resp.json()
    assert "clients" in body
    assert isinstance(body["clients"], list)


async def test_connected_clients_requires_auth(raw_client):
    """Sin autenticacion retorna 401 o 403."""
    resp = await raw_client.get("/api/v1/clientlogs/connected-clients")
    assert resp.status_code in (401, 403)
