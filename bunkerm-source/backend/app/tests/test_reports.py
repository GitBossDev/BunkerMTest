from datetime import datetime, timedelta, timezone
import sqlite3

import routers.reporting as reporting_router
from clientlogs.sqlite_activity_storage import SQLiteClientActivityStorage
from monitor.sqlite_storage import BrokerTickSnapshot, SQLiteMonitorHistoryStorage
from reporting.sqlite_reporting import SQLiteReportingStorage
from services.clientlogs_service import MQTTEvent


def _ts(days_ago: int = 0, minutes_offset: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago) + timedelta(minutes=minutes_offset)


def _event_kwargs() -> dict[str, object]:
    return {
        "protocol_level": "MQTT v5.0",
        "clean_session": False,
        "keep_alive": 60,
        "ip_address": "10.0.0.11",
        "port": 1883,
    }


async def test_reports_endpoints_return_broker_client_and_incident_views(client, tmp_path, monkeypatch):
    headers = {"host": "localhost"}
    db_path = tmp_path / "reports-api.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monitor_storage = SQLiteMonitorHistoryStorage(database_url=db_url)
    client_storage = SQLiteClientActivityStorage(database_url=db_url, retention_days=30)
    report_storage = SQLiteReportingStorage(database_url=db_url)

    monitor_storage.add_tick_snapshot(
        BrokerTickSnapshot(
            ts=_ts(days_ago=0),
            bytes_received_rate=200.0,
            bytes_sent_rate=150.0,
            messages_received_delta=15,
            messages_sent_delta=12,
            connected_clients=4,
            disconnected_clients=1,
            active_sessions=4,
            max_concurrent=6,
            total_subscriptions=3,
            retained_messages=0,
            messages_inflight=0,
            latency_ms=4.5,
            broker_uptime="5000 seconds",
            messages_received_total=215,
            messages_sent_total=212,
        )
    )
    client_storage.record_event(
        MQTTEvent(
            id="1",
            timestamp=_ts(days_ago=0).isoformat(),
            event_type="Client Connection",
            client_id="sensor-9-cid",
            details="Connected",
            status="success",
            username="sensor-9",
            **_event_kwargs(),
        )
    )
    client_storage.record_event(
        MQTTEvent(
            id="2",
            timestamp=_ts(days_ago=0, minutes_offset=3).isoformat(),
            event_type="Auth Failure",
            client_id="sensor-9-cid",
            details="Auth failed",
            status="error",
            username="sensor-9",
            reason_code="not_authorised",
            **_event_kwargs(),
        )
    )

    monkeypatch.setattr(reporting_router, "reporting_storage", report_storage)

    daily_resp = await client.get("/api/v1/reports/broker/daily", params={"days": 7}, headers=headers)
    timeline_resp = await client.get("/api/v1/reports/clients/sensor-9/timeline", params={"days": 7}, headers=headers)
    incidents_resp = await client.get("/api/v1/reports/incidents/clients", params={"days": 7, "username": "sensor-9"}, headers=headers)
    export_resp = await client.get("/api/v1/reports/export/broker", params={"scope": "daily", "days": 7, "export_format": "csv"}, headers=headers)

    assert daily_resp.status_code == 200
    assert daily_resp.json()["totals"]["total_messages_received"] == 15
    assert timeline_resp.status_code == 200
    assert len(timeline_resp.json()["timeline"]) == 2
    assert incidents_resp.status_code == 200
    incident_types = {item["incident_type"] for item in incidents_resp.json()["incidents"]}
    assert "auth_failure" in incident_types
    assert export_resp.status_code == 200
    assert export_resp.headers["content-type"].startswith("text/csv")
    assert "day,peak_connected_clients" in export_resp.text


async def test_reports_protected_endpoints_require_auth(raw_client):
    daily_resp = await raw_client.get("/api/v1/reports/broker/daily")
    retention_resp = await raw_client.get("/api/v1/reports/retention/status")
    purge_resp = await raw_client.post("/api/v1/reports/retention/purge")

    assert daily_resp.status_code in (401, 403)
    assert retention_resp.status_code in (401, 403)
    assert purge_resp.status_code in (401, 403)


async def test_reports_retention_endpoints_and_client_export_remain_available(client, tmp_path, monkeypatch):
    headers = {"host": "localhost"}
    db_path = tmp_path / "reports-retention-api.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monitor_storage = SQLiteMonitorHistoryStorage(database_url=db_url)
    client_storage = SQLiteClientActivityStorage(database_url=db_url, retention_days=30)
    report_storage = SQLiteReportingStorage(database_url=db_url)

    monitor_storage.add_tick_snapshot(
        BrokerTickSnapshot(
            ts=_ts(days_ago=0),
            bytes_received_rate=120.0,
            bytes_sent_rate=90.0,
            messages_received_delta=8,
            messages_sent_delta=6,
            connected_clients=3,
            disconnected_clients=0,
            active_sessions=3,
            max_concurrent=4,
            total_subscriptions=2,
            retained_messages=0,
            messages_inflight=0,
            latency_ms=3.0,
            broker_uptime="3000 seconds",
            messages_received_total=108,
            messages_sent_total=106,
        )
    )
    client_storage.record_event(
        MQTTEvent(
            id="ret-1",
            timestamp=_ts(days_ago=0).isoformat(),
            event_type="Publish",
            client_id="sensor-10-cid",
            details="Published",
            status="info",
            username="sensor-10",
            topic="plant/sensor-10/status",
            qos=1,
            payload_bytes=64,
            **_event_kwargs(),
        )
    )
    with sqlite3.connect(db_path.as_posix()) as conn:
        conn.execute(
            """
            INSERT INTO client_topic_events (
                username, client_id, event_ts, event_type, topic, qos, payload_bytes, retained
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("sensor-10", "sensor-10-cid", _ts(days_ago=40).isoformat(), "publish", "plant/sensor-10/old", 0, 32, 0),
        )
        conn.commit()

    monkeypatch.setattr(reporting_router, "reporting_storage", report_storage)

    retention_resp = await client.get("/api/v1/reports/retention/status", headers=headers)
    purge_resp = await client.post("/api/v1/reports/retention/purge", headers=headers)
    export_resp = await client.get(
        "/api/v1/reports/export/client-activity/sensor-10",
        params={"days": 45, "export_format": "json"},
        headers=headers,
    )

    assert retention_resp.status_code == 200
    assert retention_resp.json()["rows_past_retention"]["client_topic_events"] >= 1

    assert purge_resp.status_code == 200
    purge_payload = purge_resp.json()
    assert purge_payload["status"] == "purged"
    assert purge_payload["before"]["total_rows_past_retention"] >= purge_payload["after"]["total_rows_past_retention"]

    assert export_resp.status_code == 200
    assert export_resp.headers["content-type"].startswith("application/json")
    export_payload = export_resp.json()
    assert export_payload["client"]["username"] == "sensor-10"
    assert len(export_payload["timeline"]) >= 1