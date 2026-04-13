from datetime import datetime, timedelta, timezone

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