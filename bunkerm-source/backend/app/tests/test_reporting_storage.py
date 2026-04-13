from datetime import datetime, timedelta, timezone
import sqlite3

from clientlogs.sqlite_activity_storage import SQLiteClientActivityStorage
from monitor.sqlite_storage import BrokerTickSnapshot, SQLiteMonitorHistoryStorage
from reporting.sqlite_reporting import SQLiteReportingStorage
from services.clientlogs_service import MQTTEvent


def _ts(days_ago: int = 0, minutes_offset: int = 0) -> datetime:
    base = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return base + timedelta(minutes=minutes_offset)


def _event_kwargs() -> dict[str, object]:
    return {
        "protocol_level": "MQTT v5.0",
        "clean_session": False,
        "keep_alive": 60,
        "ip_address": "10.0.0.10",
        "port": 1883,
    }


def test_reporting_storage_builds_broker_reports_timeline_incidents_and_purge(tmp_path):
    db_path = tmp_path / "reporting.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    monitor_storage = SQLiteMonitorHistoryStorage(database_url=db_url)
    client_storage = SQLiteClientActivityStorage(database_url=db_url, retention_days=30)
    reporting = SQLiteReportingStorage(database_url=db_url)

    for days_ago, rx, tx, latency in ((10, 25, 20, 5.0), (3, 40, 35, 7.0), (1, 60, 55, 9.0)):
        monitor_storage.add_tick_snapshot(
            BrokerTickSnapshot(
                ts=_ts(days_ago=days_ago),
                bytes_received_rate=100.0 + rx,
                bytes_sent_rate=80.0 + tx,
                messages_received_delta=rx,
                messages_sent_delta=tx,
                connected_clients=5 + days_ago,
                disconnected_clients=1,
                active_sessions=4 + days_ago,
                max_concurrent=8 + days_ago,
                total_subscriptions=2,
                retained_messages=1,
                messages_inflight=0,
                latency_ms=latency,
                broker_uptime=f"{1000 + days_ago} seconds",
                messages_received_total=100 + rx,
                messages_sent_total=100 + tx,
            )
        )

    connect1 = MQTTEvent(
        id="1",
        timestamp=_ts(days_ago=1, minutes_offset=0).isoformat(),
        event_type="Client Connection",
        client_id="pump-1-cid",
        details="Connected",
        status="success",
        username="pump-1",
        **_event_kwargs(),
    )
    connect2 = MQTTEvent(
        id="2",
        timestamp=_ts(days_ago=1, minutes_offset=5).isoformat(),
        event_type="Client Connection",
        client_id="pump-1-cid",
        details="Connected again",
        status="success",
        username="pump-1",
        **_event_kwargs(),
    )
    connect3 = MQTTEvent(
        id="3",
        timestamp=_ts(days_ago=1, minutes_offset=10).isoformat(),
        event_type="Client Connection",
        client_id="pump-1-cid",
        details="Connected third time",
        status="success",
        username="pump-1",
        **_event_kwargs(),
    )
    ungraceful = MQTTEvent(
        id="4",
        timestamp=_ts(days_ago=1, minutes_offset=12).isoformat(),
        event_type="Client Disconnection",
        client_id="pump-1-cid",
        details="Disconnected",
        status="warning",
        username="pump-1",
        disconnect_kind="ungraceful",
        reason_code="network_error",
        **_event_kwargs(),
    )
    auth_fail = MQTTEvent(
        id="5",
        timestamp=_ts(days_ago=1, minutes_offset=14).isoformat(),
        event_type="Auth Failure",
        client_id="pump-1-cid",
        details="Auth failure",
        status="error",
        username="pump-1",
        reason_code="not_authorised",
        **_event_kwargs(),
    )
    publish = MQTTEvent(
        id="6",
        timestamp=_ts(days_ago=1, minutes_offset=16).isoformat(),
        event_type="Publish",
        client_id="pump-1-cid",
        details="Published",
        status="info",
        username="pump-1",
        topic="plant/pump-1/status",
        qos=1,
        payload_bytes=128,
        **_event_kwargs(),
    )
    subscribe = MQTTEvent(
        id="7",
        timestamp=_ts(days_ago=1, minutes_offset=18).isoformat(),
        event_type="Subscribe",
        client_id="pump-1-cid",
        details="Subscribed",
        status="info",
        username="pump-1",
        topic="plant/pump-1/cmd",
        qos=1,
        **_event_kwargs(),
    )
    for event in (connect1, connect2, connect3, ungraceful, auth_fail, publish, subscribe):
        client_storage.record_event(event)

    with sqlite3.connect(db_path.as_posix()) as conn:
        conn.execute(
            """
            INSERT INTO client_topic_events (
                username, client_id, event_ts, event_type, topic, qos, payload_bytes, retained
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("pump-1", "pump-1-cid", _ts(days_ago=35).isoformat(), "publish", "plant/old", 0, 32, 0),
        )
        conn.commit()

    daily = reporting.get_broker_daily_report(days=14)
    weekly = reporting.get_broker_weekly_report(weeks=4)
    timeline = reporting.get_client_timeline(username="pump-1", days=30, limit=20)
    incidents = reporting.get_client_incidents(days=30, username="pump-1")
    status = reporting.get_retention_status()
    purge = reporting.execute_retention_purge()

    assert len(daily["items"]) == 3
    assert daily["totals"]["total_messages_received"] == 125
    assert len(weekly["items"]) >= 1
    assert timeline["client"]["username"] == "pump-1"
    assert {item["event_type"] for item in timeline["timeline"]} >= {"Client Connection", "Publish", "Subscribe"}
    incident_types = {item["incident_type"] for item in incidents["incidents"]}
    assert {"ungraceful_disconnect", "auth_failure", "reconnect_loop"}.issubset(incident_types)
    assert status["rows_past_retention"]["client_topic_events"] >= 1
    assert purge["status"] == "purged"
    assert purge["before"]["total_rows_past_retention"] >= purge["after"]["total_rows_past_retention"]
