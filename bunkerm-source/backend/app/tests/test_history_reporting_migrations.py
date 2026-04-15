from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from core.history_reporting_migrations import migrate_history_reporting_sqlite_sync
from core.sync_database import create_sync_engine_for_url
from models.orm import BrokerDailySummary, BrokerMetricTick, ClientDailySummary, ClientRegistry


def _sqlite_url(path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


def test_history_reporting_migration_copies_operational_tables_between_sqlite_datastores(tmp_path):
    source_url = _sqlite_url(tmp_path / "source.db")
    target_url = _sqlite_url(tmp_path / "target.db")
    source_engine = create_sync_engine_for_url(source_url)

    with source_engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE broker_metric_ticks (id INTEGER PRIMARY KEY AUTOINCREMENT, ts DATETIME NOT NULL, bytes_received_rate FLOAT DEFAULT 0.0, bytes_sent_rate FLOAT DEFAULT 0.0, messages_received_delta INTEGER DEFAULT 0, messages_sent_delta INTEGER DEFAULT 0, connected_clients INTEGER DEFAULT 0, disconnected_clients INTEGER DEFAULT 0, active_sessions INTEGER DEFAULT 0, max_concurrent INTEGER DEFAULT 0, total_subscriptions INTEGER DEFAULT 0, retained_messages INTEGER DEFAULT 0, messages_inflight INTEGER DEFAULT 0, latency_ms FLOAT DEFAULT -1.0, cpu_pct FLOAT, memory_bytes INTEGER, memory_pct FLOAT)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE broker_runtime_state (id INTEGER PRIMARY KEY, last_tick_ts DATETIME, last_broker_uptime VARCHAR(128), current_max_concurrent INTEGER DEFAULT 0, lifetime_max_concurrent INTEGER DEFAULT 0, last_messages_received_total INTEGER DEFAULT 0, last_messages_sent_total INTEGER DEFAULT 0)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE broker_daily_summary (day DATE PRIMARY KEY, peak_connected_clients INTEGER DEFAULT 0, peak_active_sessions INTEGER DEFAULT 0, peak_max_concurrent INTEGER DEFAULT 0, total_messages_received INTEGER DEFAULT 0, total_messages_sent INTEGER DEFAULT 0, bytes_received_rate_sum FLOAT DEFAULT 0.0, bytes_sent_rate_sum FLOAT DEFAULT 0.0, latency_samples INTEGER DEFAULT 0, latency_sum FLOAT DEFAULT 0.0)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE topic_registry (id INTEGER PRIMARY KEY AUTOINCREMENT, topic VARCHAR(512) NOT NULL UNIQUE, kind VARCHAR(32), first_seen_at DATETIME NOT NULL, last_seen_at DATETIME NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE topic_publish_buckets (id INTEGER PRIMARY KEY AUTOINCREMENT, bucket_start DATETIME NOT NULL, bucket_minutes INTEGER NOT NULL, topic_id INTEGER NOT NULL, publish_count INTEGER DEFAULT 0, bytes_sum INTEGER DEFAULT 0)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE topic_subscribe_buckets (id INTEGER PRIMARY KEY AUTOINCREMENT, bucket_start DATETIME NOT NULL, bucket_minutes INTEGER NOT NULL, topic_id INTEGER NOT NULL, subscribe_count INTEGER DEFAULT 0)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE client_registry (username VARCHAR(128) PRIMARY KEY, textname VARCHAR(256), disabled BOOLEAN, created_at DATETIME NOT NULL, deleted_at DATETIME, last_dynsec_sync_at DATETIME NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE client_session_events (id INTEGER PRIMARY KEY AUTOINCREMENT, username VARCHAR(128), client_id VARCHAR(256) NOT NULL, event_ts DATETIME NOT NULL, event_type VARCHAR(64) NOT NULL, disconnect_kind VARCHAR(64), reason_code VARCHAR(128), ip_address VARCHAR(64), port INTEGER, protocol_level VARCHAR(64), clean_session BOOLEAN, keep_alive INTEGER)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE client_topic_events (id INTEGER PRIMARY KEY AUTOINCREMENT, username VARCHAR(128), client_id VARCHAR(256) NOT NULL, event_ts DATETIME NOT NULL, event_type VARCHAR(32) NOT NULL, topic VARCHAR(512) NOT NULL, qos INTEGER, payload_bytes INTEGER, retained BOOLEAN)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE client_subscription_state (id INTEGER PRIMARY KEY AUTOINCREMENT, username VARCHAR(128) NOT NULL, topic VARCHAR(512) NOT NULL, qos INTEGER, first_seen_at DATETIME NOT NULL, last_seen_at DATETIME NOT NULL, is_active BOOLEAN, source VARCHAR(64))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE client_daily_summary (id INTEGER PRIMARY KEY AUTOINCREMENT, username VARCHAR(128) NOT NULL, day DATE NOT NULL, connects INTEGER DEFAULT 0, disconnects_graceful INTEGER DEFAULT 0, disconnects_ungraceful INTEGER DEFAULT 0, auth_failures INTEGER DEFAULT 0, publishes INTEGER DEFAULT 0, subscribes INTEGER DEFAULT 0, distinct_publish_topics INTEGER DEFAULT 0, distinct_subscribe_topics INTEGER DEFAULT 0)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE client_daily_distinct_topics (username VARCHAR(128) NOT NULL, day DATE NOT NULL, event_type VARCHAR(32) NOT NULL, topic VARCHAR(512) NOT NULL, PRIMARY KEY (username, day, event_type, topic))"
        )

        connection.exec_driver_sql("INSERT INTO broker_metric_ticks (id, ts, messages_received_delta, messages_sent_delta) VALUES (1, '2026-04-15 12:00:00', 4, 2)")
        connection.exec_driver_sql("INSERT INTO broker_runtime_state (id, last_tick_ts, current_max_concurrent, lifetime_max_concurrent, last_messages_received_total, last_messages_sent_total) VALUES (1, '2026-04-15 12:00:00', 2, 3, 4, 2)")
        connection.exec_driver_sql("INSERT INTO broker_daily_summary (day, total_messages_received, total_messages_sent) VALUES ('2026-04-15', 4, 2)")
        connection.exec_driver_sql("INSERT INTO topic_registry (id, topic, kind, first_seen_at, last_seen_at) VALUES (1, 'phase4/test', 'user', '2026-04-15 12:00:00', '2026-04-15 12:00:00')")
        connection.exec_driver_sql("INSERT INTO topic_publish_buckets (id, bucket_start, bucket_minutes, topic_id, publish_count, bytes_sum) VALUES (1, '2026-04-15 12:00:00', 3, 1, 1, 16)")
        connection.exec_driver_sql("INSERT INTO topic_subscribe_buckets (id, bucket_start, bucket_minutes, topic_id, subscribe_count) VALUES (1, '2026-04-15 12:00:00', 3, 1, 1)")
        connection.exec_driver_sql("INSERT INTO client_registry (username, textname, disabled, created_at, deleted_at, last_dynsec_sync_at) VALUES ('pump-1', 'Pump 1', 0, '2026-04-15 12:00:00', NULL, '2026-04-15 12:00:00')")
        connection.exec_driver_sql("INSERT INTO client_session_events (id, username, client_id, event_ts, event_type) VALUES (1, 'pump-1', 'pump-1-cid', '2026-04-15 12:00:00', 'Client Connection')")
        connection.exec_driver_sql("INSERT INTO client_topic_events (id, username, client_id, event_ts, event_type, topic, qos, payload_bytes, retained) VALUES (1, 'pump-1', 'pump-1-cid', '2026-04-15 12:00:00', 'publish', 'phase4/test', 1, 16, 0)")
        connection.exec_driver_sql("INSERT INTO client_subscription_state (id, username, topic, qos, first_seen_at, last_seen_at, is_active, source) VALUES (1, 'pump-1', 'phase4/test', 1, '2026-04-15 12:00:00', '2026-04-15 12:00:00', 1, 'clientlogs')")
        connection.exec_driver_sql("INSERT INTO client_daily_summary (id, username, day, connects, publishes) VALUES (1, 'pump-1', '2026-04-15', 1, 1)")
        connection.exec_driver_sql("INSERT INTO client_daily_distinct_topics (username, day, event_type, topic) VALUES ('pump-1', '2026-04-15', 'publish', 'phase4/test')")

    result = migrate_history_reporting_sqlite_sync(
        source_url=source_url,
        history_target_url=target_url,
        reporting_target_url=target_url,
        truncate_target=False,
        dry_run=False,
    )

    assert result["reporting_mode"] == "shared-history-target"
    assert result["history_tables"]["broker_metric_ticks"] == 1
    assert result["history_tables"]["client_registry"] == 1

    target_engine = create_sync_engine_for_url(target_url)
    session_factory = sessionmaker(bind=target_engine, expire_on_commit=False)
    with session_factory() as session:
        assert session.scalar(select(BrokerMetricTick.messages_received_delta)) == 4
        assert session.scalar(select(BrokerDailySummary.total_messages_received)) == 4
        assert session.scalar(select(ClientRegistry.username)) == "pump-1"
        assert session.scalar(select(ClientDailySummary.publishes)) == 1