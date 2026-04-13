from datetime import datetime, timedelta, timezone

from monitor.sqlite_storage import BrokerTickSnapshot, SQLiteMonitorHistoryStorage


def test_sqlite_monitor_history_persists_ticks_and_rollups(tmp_path):
    db_path = tmp_path / "monitor-history.db"
    storage = SQLiteMonitorHistoryStorage(
        database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        legacy_json_path=None,
    )

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