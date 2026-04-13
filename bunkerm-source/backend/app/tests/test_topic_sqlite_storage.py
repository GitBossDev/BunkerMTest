from datetime import datetime, timedelta, timezone

from monitor.topic_sqlite_storage import SQLiteTopicHistoryStorage


def test_topic_history_storage_persists_publish_and_subscribe_buckets(tmp_path):
    db_path = tmp_path / "topic-history.db"
    storage = SQLiteTopicHistoryStorage(
        database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        bucket_minutes=3,
        retention_days=30,
    )

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