from datetime import datetime, timedelta, timezone

from clientlogs.sqlalchemy_activity_storage import SQLAlchemyClientActivityStorage
from monitor.sqlalchemy_storage import BrokerTickSnapshot, SQLAlchemyMonitorHistoryStorage
from monitor.topic_sqlalchemy_storage import SQLAlchemyTopicHistoryStorage
from reporting.sqlalchemy_reporting import SQLAlchemyReportingStorage
from services.clientlogs_service import MQTTEvent


def _event_kwargs() -> dict[str, object]:
    return {
        "protocol_level": "MQTT v5.0",
        "clean_session": False,
        "keep_alive": 60,
        "ip_address": "10.0.0.10",
        "port": 1883,
    }


def test_sqlalchemy_monitor_history_storage_persists_ticks_and_rollups(tmp_path):
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'monitor-history.db').as_posix()}"
    storage = SQLAlchemyMonitorHistoryStorage(database_url=db_url)

    base_ts = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=6)
    storage.add_tick_snapshot(
        BrokerTickSnapshot(
            ts=base_ts,
            bytes_received_rate=100.0,
            bytes_sent_rate=50.0,
            messages_received_delta=10,
            messages_sent_delta=5,
            connected_clients=4,
            disconnected_clients=1,
            active_sessions=5,
            max_concurrent=4,
            total_subscriptions=7,
            retained_messages=2,
            messages_inflight=1,
            latency_ms=12.5,
            broker_uptime="120 seconds",
            messages_received_total=10,
            messages_sent_total=5,
            cpu_pct=15.0,
            memory_bytes=2048,
            memory_pct=10.0,
        )
    )
    storage.add_tick_snapshot(
        BrokerTickSnapshot(
            ts=base_ts + timedelta(minutes=3),
            bytes_received_rate=120.0,
            bytes_sent_rate=70.0,
            messages_received_delta=12,
            messages_sent_delta=8,
            connected_clients=6,
            disconnected_clients=2,
            active_sessions=8,
            max_concurrent=6,
            total_subscriptions=9,
            retained_messages=3,
            messages_inflight=2,
            latency_ms=20.0,
            broker_uptime="300 seconds",
            messages_received_total=22,
            messages_sent_total=13,
            cpu_pct=18.0,
            memory_bytes=4096,
            memory_pct=20.0,
        )
    )

    bytes_data = storage.get_bytes_for_period("1h")
    msg_data = storage.get_messages_for_period("1h")
    runtime = storage.get_runtime_state()
    daily_messages = storage.get_daily_message_stats(days=7)
    daily_summary = storage.get_daily_summary(days=7)
    total_messages = storage.get_total_message_count(days=7)

    assert len(bytes_data["timestamps"]) == 2
    assert bytes_data["bytes_received"] == [100.0, 120.0]
    assert bytes_data["bytes_sent"] == [50.0, 70.0]
    assert msg_data["msg_received"] == [10, 12]
    assert msg_data["msg_sent"] == [5, 8]
    assert runtime["current_max_concurrent"] == 6
    assert runtime["lifetime_max_concurrent"] == 6
    assert runtime["last_messages_received_total"] == 22
    assert runtime["last_messages_sent_total"] == 13
    assert total_messages == 22
    assert daily_messages["counts"] == [22]
    assert daily_summary["days"][0]["total_messages_received"] == 22
    assert daily_summary["days"][0]["peak_max_concurrent"] == 6


def test_sqlalchemy_topic_history_storage_persists_publish_and_subscribe_buckets(tmp_path):
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'topic-history.db').as_posix()}"
    storage = SQLAlchemyTopicHistoryStorage(database_url=db_url, bucket_minutes=3, retention_days=30)

    base_ts = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=6)
    storage.record_publish("plant/tank1/level", payload_bytes=10, event_ts=base_ts)
    storage.record_publish("plant/tank1/level", payload_bytes=20, event_ts=base_ts + timedelta(seconds=30))
    storage.record_publish("plant/tank2/level", payload_bytes=15, event_ts=base_ts + timedelta(minutes=3))
    storage.record_subscribe("plant/tank1/level", event_ts=base_ts)
    storage.record_subscribe("plant/tank1/level", event_ts=base_ts + timedelta(minutes=3))
    storage.record_subscribe("plant/tank2/level", event_ts=base_ts + timedelta(minutes=3))

    published = storage.get_top_published(limit=5, period="7d")
    subscribed = storage.get_top_subscribed(limit=5, period="7d")

    assert published["total_distinct_topics"] == 2
    assert published["top_topics"][0]["topic"] == "plant/tank1/level"
    assert published["top_topics"][0]["count"] == 2
    assert subscribed["total_distinct_subscribed"] == 2
    assert subscribed["top_subscribed"][0]["topic"] == "plant/tank1/level"
    assert subscribed["top_subscribed"][0]["count"] == 2


def test_sqlalchemy_client_activity_storage_records_registry_events_and_summary(tmp_path):
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'client-activity.db').as_posix()}"
    storage = SQLAlchemyClientActivityStorage(database_url=db_url, retention_days=30)

    storage.upsert_client("sensor-1", disabled=False)
    connect = MQTTEvent(
        id="1",
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type="Client Connection",
        client_id="sensor-1-cid",
        details="Connected",
        status="success",
        protocol_level="MQTT v5.0",
        clean_session=False,
        keep_alive=60,
        username="sensor-1",
        ip_address="10.0.0.5",
        port=1883,
    )
    subscribe = MQTTEvent(
        id="2",
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type="Subscribe",
        client_id="sensor-1-cid",
        details="Subscribed",
        status="info",
        protocol_level="MQTT v5.0",
        clean_session=False,
        keep_alive=60,
        username="sensor-1",
        ip_address="10.0.0.5",
        port=1883,
        topic="plant/line1/temp",
        qos=1,
    )
    publish = MQTTEvent(
        id="3",
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type="Publish",
        client_id="sensor-1-cid",
        details="Published",
        status="info",
        protocol_level="MQTT v5.0",
        clean_session=False,
        keep_alive=60,
        username="sensor-1",
        ip_address="10.0.0.5",
        port=1883,
        topic="plant/line1/temp",
        qos=1,
        payload_bytes=24,
    )
    disconnect = MQTTEvent(
        id="4",
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type="Client Disconnection",
        client_id="sensor-1-cid",
        details="Disconnected",
        status="warning",
        protocol_level="MQTT v5.0",
        clean_session=False,
        keep_alive=60,
        username="sensor-1",
        ip_address="10.0.0.5",
        port=1883,
        disconnect_kind="ungraceful",
    )

    storage.record_event(connect)
    storage.record_event(subscribe)
    storage.record_event(publish)
    storage.record_event(disconnect)

    activity = storage.get_client_activity("sensor-1", days=30, limit=50)

    assert activity["client"] is not None
    assert len(activity["session_events"]) == 2
    assert len(activity["topic_events"]) == 1  # only Subscribe; Publish goes to publish_state
    assert len(activity["subscriptions"]) == 1
    assert len(activity["publish_state"]) == 1  # one topic for Publish
    assert activity["publish_state"][0]["topic"] == "plant/line1/temp"
    assert len(activity["daily_summary"]) == 1
    summary = activity["daily_summary"][0]
    assert summary["connects"] == 1
    assert summary["disconnects_ungraceful"] == 1
    assert summary["publishes"] == 1
    assert summary["subscribes"] == 1
    assert summary["distinct_publish_topics"] == 1
    assert summary["distinct_subscribe_topics"] == 1


def test_sqlalchemy_reporting_storage_builds_broker_reports_timeline_incidents_and_purge(tmp_path):
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'reporting.db').as_posix()}"
    monitor_storage = SQLAlchemyMonitorHistoryStorage(database_url=db_url)
    client_storage = SQLAlchemyClientActivityStorage(database_url=db_url, retention_days=60)
    reporting = SQLAlchemyReportingStorage(database_url=db_url)

    def ts(days_ago: int = 0, minutes_offset: int = 0) -> datetime:
        base = datetime.now(timezone.utc) - timedelta(days=days_ago)
        return base + timedelta(minutes=minutes_offset)

    for days_ago, rx, tx, latency in ((10, 25, 20, 5.0), (3, 40, 35, 7.0), (1, 60, 55, 9.0)):
        monitor_storage.add_tick_snapshot(
            BrokerTickSnapshot(
                ts=ts(days_ago=days_ago),
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

    events = [
        MQTTEvent(id="1", timestamp=ts(days_ago=1, minutes_offset=0).isoformat(), event_type="Client Connection", client_id="pump-1-cid", details="Connected", status="success", username="pump-1", **_event_kwargs()),
        MQTTEvent(id="2", timestamp=ts(days_ago=1, minutes_offset=5).isoformat(), event_type="Client Connection", client_id="pump-1-cid", details="Connected again", status="success", username="pump-1", **_event_kwargs()),
        MQTTEvent(id="3", timestamp=ts(days_ago=1, minutes_offset=10).isoformat(), event_type="Client Connection", client_id="pump-1-cid", details="Connected third time", status="success", username="pump-1", **_event_kwargs()),
        MQTTEvent(id="4", timestamp=ts(days_ago=1, minutes_offset=12).isoformat(), event_type="Client Disconnection", client_id="pump-1-cid", details="Disconnected", status="warning", username="pump-1", disconnect_kind="ungraceful", reason_code="network_error", **_event_kwargs()),
        MQTTEvent(id="5", timestamp=ts(days_ago=1, minutes_offset=14).isoformat(), event_type="Auth Failure", client_id="pump-1-cid", details="Auth failure", status="error", username="pump-1", reason_code="not_authorised", **_event_kwargs()),
        MQTTEvent(id="6", timestamp=ts(days_ago=1, minutes_offset=16).isoformat(), event_type="Publish", client_id="pump-1-cid", details="Published", status="info", username="pump-1", topic="plant/pump-1/status", qos=1, payload_bytes=128, **_event_kwargs()),
        MQTTEvent(id="7", timestamp=ts(days_ago=1, minutes_offset=18).isoformat(), event_type="Subscribe", client_id="pump-1-cid", details="Subscribed", status="info", username="pump-1", topic="plant/pump-1/cmd", qos=1, **_event_kwargs()),
        MQTTEvent(id="8", timestamp=ts(days_ago=35).isoformat(), event_type="Publish", client_id="pump-1-cid", details="Old publish", status="info", username="pump-1", topic="plant/old", qos=0, payload_bytes=32, **_event_kwargs()),
        # Old connection event to trigger client_mqtt_events retention check
        MQTTEvent(id="9", timestamp=ts(days_ago=35).isoformat(), event_type="Client Connection", client_id="pump-1-cid", details="Old connect", status="success", username="pump-1", **_event_kwargs()),
    ]
    for event in events:
        client_storage.record_event(event)

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
    # Publish events go to publish_state only; timeline shows connection/sub/auth events
    assert {item["event_type"] for item in timeline["timeline"]} >= {"Client Connection", "Subscribe"}
    incident_types = {item["incident_type"] for item in incidents["incidents"]}
    assert {"ungraceful_disconnect", "auth_failure", "reconnect_loop"}.issubset(incident_types)
    assert status["rows_past_retention"]["client_mqtt_events"] >= 1
    assert purge["status"] == "purged"
    assert purge["before"]["total_rows_past_retention"] >= purge["after"]["total_rows_past_retention"]