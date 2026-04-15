from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from clientlogs.sqlalchemy_activity_storage import SQLAlchemyClientActivityStorage
from core.sync_database import create_sync_engine_for_url
from models.orm import BrokerDailySummary, BrokerMetricTick, ClientDailyDistinctTopic, ClientDailySummary, ClientRegistry, ClientSessionEvent, ClientTopicEvent, TopicPublishBucket, TopicSubscribeBucket
from monitor.sqlalchemy_storage import BrokerTickSnapshot, SQLAlchemyMonitorHistoryStorage
from reporting.sqlalchemy_reporting import SQLAlchemyReportingStorage
from services.clientlogs_service import MQTTEvent
from tests.postgres_integration_support import require_real_postgres


def _event_kwargs() -> dict[str, object]:
    return {
        "protocol_level": "MQTT v5.0",
        "clean_session": False,
        "keep_alive": 60,
        "ip_address": "10.0.0.10",
        "port": 1883,
    }


@pytest.mark.integration
def test_reporting_storage_queries_real_postgres_data():
    database_url = require_real_postgres("BHM_REAL_REPORTING_DATABASE_URL")
    monitor_storage = SQLAlchemyMonitorHistoryStorage(database_url=database_url)
    client_storage = SQLAlchemyClientActivityStorage(database_url=database_url, retention_days=60)
    reporting = SQLAlchemyReportingStorage(database_url=database_url)
    engine = create_sync_engine_for_url(database_url)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    test_id = uuid4().hex[:8]
    username = f"report-{test_id}"
    client_id = f"{username}-cid"
    old_username = f"report-old-{test_id}"
    old_client_id = f"{old_username}-cid"
    future_anchor = datetime(2099, 1, 15, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=int(test_id[:2], 16))
    old_event_ts = datetime.now(timezone.utc) - timedelta(days=35)

    def ts(days_ago: int = 0, minutes_offset: int = 0) -> datetime:
        base = future_anchor - timedelta(days=days_ago)
        return base + timedelta(minutes=minutes_offset)

    tick_rows = [ts(days_ago=10), ts(days_ago=3), ts(days_ago=1)]
    tick_days = {value.date() for value in tick_rows}

    events = [
        MQTTEvent(id=f"{test_id}-1", timestamp=ts(days_ago=1, minutes_offset=0).isoformat(), event_type="Client Connection", client_id=client_id, details="Connected", status="success", username=username, **_event_kwargs()),
        MQTTEvent(id=f"{test_id}-2", timestamp=ts(days_ago=1, minutes_offset=5).isoformat(), event_type="Client Connection", client_id=client_id, details="Connected again", status="success", username=username, **_event_kwargs()),
        MQTTEvent(id=f"{test_id}-3", timestamp=ts(days_ago=1, minutes_offset=10).isoformat(), event_type="Client Connection", client_id=client_id, details="Connected third time", status="success", username=username, **_event_kwargs()),
        MQTTEvent(id=f"{test_id}-4", timestamp=ts(days_ago=1, minutes_offset=12).isoformat(), event_type="Client Disconnection", client_id=client_id, details="Disconnected", status="warning", username=username, disconnect_kind="ungraceful", reason_code="network_error", **_event_kwargs()),
        MQTTEvent(id=f"{test_id}-5", timestamp=ts(days_ago=1, minutes_offset=14).isoformat(), event_type="Auth Failure", client_id=client_id, details="Auth failure", status="error", username=username, reason_code="not_authorised", **_event_kwargs()),
        MQTTEvent(id=f"{test_id}-6", timestamp=ts(days_ago=1, minutes_offset=16).isoformat(), event_type="Publish", client_id=client_id, details="Published", status="info", username=username, topic=f"phase4/{test_id}/status", qos=1, payload_bytes=128, **_event_kwargs()),
        MQTTEvent(id=f"{test_id}-7", timestamp=ts(days_ago=1, minutes_offset=18).isoformat(), event_type="Subscribe", client_id=client_id, details="Subscribed", status="info", username=username, topic=f"phase4/{test_id}/cmd", qos=1, **_event_kwargs()),
        MQTTEvent(id=f"{test_id}-8", timestamp=old_event_ts.isoformat(), event_type="Publish", client_id=old_client_id, details="Old publish", status="info", username=old_username, topic=f"phase4/{test_id}/old", qos=0, payload_bytes=32, **_event_kwargs()),
    ]

    try:
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
        for event in events:
            client_storage.record_event(event)

        daily = reporting.get_broker_daily_report(days=14)
        weekly = reporting.get_broker_weekly_report(weeks=4)
        timeline = reporting.get_client_timeline(username=username, days=30, limit=20)
        incidents = reporting.get_client_incidents(days=30, username=username)
        status = reporting.get_retention_status()
        purge = reporting.execute_retention_purge()

        assert len(daily["items"]) == 3
        assert daily["totals"]["total_messages_received"] >= 125
        assert len(weekly["items"]) >= 1
        assert timeline["client"]["username"] == username
        assert {item["event_type"] for item in timeline["timeline"]} >= {"Client Connection", "Publish", "Subscribe"}
        incident_types = {item["incident_type"] for item in incidents["incidents"]}
        assert {"ungraceful_disconnect", "auth_failure", "reconnect_loop"}.issubset(incident_types)
        assert status["rows_past_retention"]["client_topic_events"] >= 1
        assert purge["status"] == "purged"
        assert purge["before"]["total_rows_past_retention"] >= purge["after"]["total_rows_past_retention"]
    finally:
        with session_factory() as session:
            session.execute(delete(ClientDailyDistinctTopic).where(ClientDailyDistinctTopic.username.in_([username, old_username])))
            session.execute(delete(ClientDailySummary).where(ClientDailySummary.username.in_([username, old_username])))
            session.execute(delete(ClientTopicEvent).where(ClientTopicEvent.username.in_([username, old_username])))
            session.execute(delete(ClientSessionEvent).where(ClientSessionEvent.username.in_([username, old_username])))
            session.execute(delete(ClientRegistry).where(ClientRegistry.username.in_([username, old_username])))
            session.execute(delete(TopicPublishBucket).where(TopicPublishBucket.bucket_start.in_([value.replace(tzinfo=None) for value in tick_rows])))
            session.execute(delete(TopicSubscribeBucket).where(TopicSubscribeBucket.bucket_start.in_([value.replace(tzinfo=None) for value in tick_rows])))
            session.execute(delete(BrokerMetricTick).where(BrokerMetricTick.ts.in_([value.replace(tzinfo=None) for value in tick_rows])))
            session.execute(delete(BrokerDailySummary).where(BrokerDailySummary.day.in_(list(tick_days))))
            session.commit()