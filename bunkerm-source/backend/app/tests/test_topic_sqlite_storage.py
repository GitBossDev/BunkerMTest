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


def test_get_latest_topics_ignores_topics_without_publishes(tmp_path):
    db_path = tmp_path / "topic-history.db"
    storage = SQLiteTopicHistoryStorage(
        database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        bucket_minutes=3,
        retention_days=30,
    )

    now = datetime.now(timezone.utc)
    storage.record_subscribe("plant/tank9/subscribe-only", event_ts=now)
    storage.record_publish("plant/tank1/level", payload_bytes=8, payload_value="42", event_ts=now)

    latest = storage.get_latest_topics(limit=20)
    topics = {entry["topic"] for entry in latest}

    assert "plant/tank1/level" in topics
    assert "plant/tank9/subscribe-only" not in topics


def test_record_publish_preserves_retained_until_explicit_clear(tmp_path):
    db_path = tmp_path / "topic-history.db"
    storage = SQLiteTopicHistoryStorage(
        database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        bucket_minutes=3,
        retention_days=30,
    )

    now = datetime.now(timezone.utc)
    topic = "plant/tank1/status"

    storage.record_publish(topic, payload_bytes=4, payload_value="True", retained=True, event_ts=now)
    storage.record_publish(topic, payload_bytes=5, payload_value="False", retained=False, event_ts=now + timedelta(seconds=1))

    latest_before_clear = next(t for t in storage.get_latest_topics(limit=10) if t["topic"] == topic)
    assert latest_before_clear["retained"] is True

    storage.record_publish(topic, payload_bytes=0, payload_value="", retained=True, event_ts=now + timedelta(seconds=2))
    latest_after_clear = next(t for t in storage.get_latest_topics(limit=10) if t["topic"] == topic)
    assert latest_after_clear["retained"] is False