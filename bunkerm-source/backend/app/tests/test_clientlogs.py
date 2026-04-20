"""
Tests de regresion para el router ClientLogs (/api/v1/clientlogs).

ClientLogs usa mqtt_monitor (deque en memoria). Sin broker activo el deque
esta vacio, pero los endpoints deben responder con la estructura correcta.
"""
import time
from datetime import datetime, timezone

import pytest

import routers.clientlogs as clientlogs_router
import services.clientlogs_service as clientlogs_service
from services.clientlogs_service import mqtt_monitor


@pytest.fixture(autouse=True)
def reset_mqtt_monitor_state():
    mqtt_monitor.connected_clients.clear()
    mqtt_monitor.events.clear()
    mqtt_monitor._subscription_counts.clear()
    mqtt_monitor._last_seen.clear()
    mqtt_monitor._subscriber_clients_seen.clear()
    mqtt_monitor._publisher_clients_seen.clear()
    mqtt_monitor._pending_ip.clear()
    mqtt_monitor._last_connection_info.clear()
    mqtt_monitor._last_publish_ts.clear()
    mqtt_monitor._client_usernames.clear()
    mqtt_monitor._pending_subscribe_client = None
    yield
    mqtt_monitor.connected_clients.clear()
    mqtt_monitor.events.clear()
    mqtt_monitor._subscription_counts.clear()
    mqtt_monitor._last_seen.clear()
    mqtt_monitor._subscriber_clients_seen.clear()
    mqtt_monitor._publisher_clients_seen.clear()
    mqtt_monitor._pending_ip.clear()
    mqtt_monitor._last_connection_info.clear()
    mqtt_monitor._last_publish_ts.clear()
    mqtt_monitor._client_usernames.clear()
    mqtt_monitor._pending_subscribe_client = None


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


async def test_source_status_returns_200_with_sources_map(client):
    """El endpoint /source-status expone el estado de las fuentes de ClientLogs."""
    resp = await client.get("/api/v1/clientlogs/source-status")
    assert resp.status_code == 200
    body = resp.json()
    assert "sources" in body
    assert "logTail" in body["sources"]
    assert "mqttPublish" in body["sources"]


async def test_connected_clients_infers_greenhouse_username_from_subscribe_activity(client):
    """Los clientes activos del simulador deben reconciliarse al username DynSec aunque falte CONNECT."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    event = mqtt_monitor.parse_subscription_log(
        f"{ts}: greenhouse-publisher-42 1 lab/device/100000042/temperatura"
    )
    assert event is not None

    resp = await client.get("/api/v1/clientlogs/connected-clients")
    assert resp.status_code == 200
    body = resp.json()
    clients = body["clients"]

    greenhouse = next((item for item in clients if item["client_id"] == "greenhouse-publisher-42"), None)
    assert greenhouse is not None
    assert greenhouse["username"] == "42"
    assert greenhouse["details"] == "Active (inferred from subscribe activity)"


def test_process_line_parses_verbose_subscribe_sequence(monkeypatch):
    """Mosquitto verbose subscribe logs deben alimentar top-subscribed y actividad."""
    class _StubActivityStorage:
        @staticmethod
        def record_event(event):
            return None

    class _StubTopicHistoryStorage:
        @staticmethod
        def record_subscribe(topic, event_ts=None):
            return None

    monkeypatch.setattr(clientlogs_service, "client_activity_storage", _StubActivityStorage())
    monkeypatch.setattr(clientlogs_service, "topic_history_storage", _StubTopicHistoryStorage())

    mqtt_monitor.process_line("2026-04-20T10:01:00: Received SUBSCRIBE from greenhouse-publisher-7")
    mqtt_monitor.process_line("2026-04-20T10:01:00:     lab/device/100000007/estado (QoS 1)")

    assert mqtt_monitor._subscription_counts["lab/device/100000007/estado"] == 1
    assert mqtt_monitor._client_usernames["greenhouse-publisher-7"] == "7"
    assert "7" in mqtt_monitor._subscriber_clients_seen


def test_build_activity_summary_uses_inferred_active_clients_and_capabilities(monkeypatch):
    """El resumen debe contar usuarios activos inferidos, no solo connected_clients perfectos."""
    now = time.time()
    mqtt_monitor._last_seen["greenhouse-publisher-5"] = now
    mqtt_monitor._subscriber_clients_seen["5"] = now
    mqtt_monitor._publisher_clients_seen["5"] = now

    monkeypatch.setattr(
        clientlogs_router.desired_state_svc,
        "get_cached_observed_dynsec_capability_map",
        lambda: {"5": {"publish": True, "subscribe": True}},
    )

    summary = clientlogs_router.build_activity_summary(window_seconds=600)

    assert summary["subscribed_clients"] == 1
    assert summary["publisher_clients"] == 1
