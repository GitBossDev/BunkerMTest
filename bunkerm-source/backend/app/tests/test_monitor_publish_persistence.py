"""
Prueba de persistencia de publishes MQTT hacia base de datos.

Objetivo:
- Simular la llegada de un mensaje MQTT no-$SYS.
- Verificar que el monitor lo inserta en la tabla de historial de tópicos.
"""

from types import SimpleNamespace
from datetime import datetime, timezone

import services.monitor_service as monitor_svc
from monitor.topic_sqlalchemy_storage import SQLAlchemyTopicHistoryStorage


def test_on_message_persiste_publish_en_base_de_datos(tmp_path, monkeypatch):
    """Al recibir un publish, el monitor debe persistirlo en DB."""
    db_path = tmp_path / "topic-history.db"
    storage = SQLAlchemyTopicHistoryStorage(
        database_url=f"sqlite+pysqlite:///{db_path.as_posix()}",
        bucket_minutes=3,
        retention_days=30,
    )

    # Aislar singletons globales para que la prueba sea determinista.
    monkeypatch.setattr(monitor_svc, "topic_history_storage", storage)
    monkeypatch.setattr(monitor_svc, "topic_store", monitor_svc.TopicStore())

    topic = "lab/device/100000007/Estatus_conexion"
    payload = "Conectado"
    msg = SimpleNamespace(
        topic=topic,
        payload=payload.encode("utf-8"),
        qos=1,
        retain=False,
    )

    monitor_svc.on_message(None, None, msg)

    latest_topics = storage.get_latest_topics(limit=10)
    history = storage.get_topic_messages(topic, limit=10)

    assert any(t["topic"] == topic for t in latest_topics)
    persisted = next(t for t in latest_topics if t["topic"] == topic)
    assert persisted["value"] == payload
    assert persisted["count"] == 1
    assert persisted["qos"] == 1
    assert persisted["retained"] is False

    assert history["total"] == 1
    assert len(history["history"]) == 1
    assert history["history"][0]["topic"] == topic
    assert history["history"][0]["value"] == payload
    assert history["history"][0]["qos"] == 1
    assert history["history"][0]["retained"] is False


def test_sqlalchemy_latest_topics_ignores_subscribe_only_topics(tmp_path):
    db_path = tmp_path / "topic-history.db"
    storage = SQLAlchemyTopicHistoryStorage(
        database_url=f"sqlite+pysqlite:///{db_path.as_posix()}",
        bucket_minutes=3,
        retention_days=30,
    )

    now = datetime.now(timezone.utc)
    storage.record_subscribe("lab/device/100000777/subscribe-only", event_ts=now)
    storage.record_publish(
        "lab/device/100000777/Estatus_conexion",
        payload_bytes=9,
        payload_value="Conectado",
        qos=0,
        retained=True,
        event_ts=now,
    )

    latest_topics = storage.get_latest_topics(limit=20)
    topics = {entry["topic"] for entry in latest_topics}

    assert "lab/device/100000777/Estatus_conexion" in topics
    assert "lab/device/100000777/subscribe-only" not in topics


def test_sqlalchemy_record_publish_preserves_retained_until_explicit_clear(tmp_path):
    db_path = tmp_path / "topic-history.db"
    storage = SQLAlchemyTopicHistoryStorage(
        database_url=f"sqlite+pysqlite:///{db_path.as_posix()}",
        bucket_minutes=3,
        retention_days=30,
    )

    now = datetime.now(timezone.utc)
    topic = "lab/device/100000888/CO2/status"

    storage.record_publish(topic, payload_bytes=4, payload_value="True", qos=0, retained=True, event_ts=now)
    storage.record_publish(topic, payload_bytes=5, payload_value="False", qos=0, retained=False, event_ts=now)

    latest_before_clear = next(t for t in storage.get_latest_topics(limit=10) if t["topic"] == topic)
    assert latest_before_clear["retained"] is True

    storage.record_publish(topic, payload_bytes=0, payload_value="", qos=0, retained=True, event_ts=now)
    latest_after_clear = next(t for t in storage.get_latest_topics(limit=10) if t["topic"] == topic)
    assert latest_after_clear["retained"] is False
