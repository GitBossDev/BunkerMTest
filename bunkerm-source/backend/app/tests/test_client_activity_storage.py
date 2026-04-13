from datetime import datetime, timezone

from clientlogs.sqlite_activity_storage import SQLiteClientActivityStorage
from services.clientlogs_service import MQTTEvent


def test_client_activity_storage_records_registry_events_and_summary(tmp_path):
    db_path = tmp_path / "client-activity.db"
    storage = SQLiteClientActivityStorage(
        database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        retention_days=30,
    )

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
    assert len(activity["topic_events"]) == 2
    assert len(activity["subscriptions"]) == 1
    assert len(activity["daily_summary"]) == 1
    summary = activity["daily_summary"][0]
    assert summary["connects"] == 1
    assert summary["disconnects_ungraceful"] == 1
    assert summary["publishes"] == 1
    assert summary["subscribes"] == 1
    assert summary["distinct_publish_topics"] == 1
    assert summary["distinct_subscribe_topics"] == 1