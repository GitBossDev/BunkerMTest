from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from clientlogs.sqlalchemy_activity_storage import SQLAlchemyClientActivityStorage
from core.sync_database import create_sync_engine_for_url, normalize_datetime
from models.orm import (
    BrokerDailySummary,
    BrokerMetricTick,
    BrokerRuntimeState,
    ClientDailyDistinctTopic,
    ClientDailySummary,
    ClientRegistry,
    ClientSessionEvent,
    ClientSubscriptionState,
    ClientTopicEvent,
    TopicPublishBucket,
    TopicMessageEvent,
    TopicRegistry,
    TopicSubscribeBucket,
)
from monitor.sqlalchemy_storage import BrokerTickSnapshot, SQLAlchemyMonitorHistoryStorage
from monitor.topic_sqlalchemy_storage import SQLAlchemyTopicHistoryStorage
from services.clientlogs_service import MQTTEvent
from tests.postgres_integration_support import require_real_postgres


@pytest.mark.integration
def test_phase4_cut2_storages_persist_real_postgres_data():
    database_url = require_real_postgres("BHM_REAL_HISTORY_DATABASE_URL")
    test_id = uuid4().hex[:8]
    tick_ts = datetime(2099, 1, 1, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=int(test_id[:2], 16) % 10)
    topic_a = f"phase4/{test_id}/alpha"
    topic_b = f"phase4/{test_id}/beta"
    username = f"phase4-{test_id}"
    client_id = f"{username}-cid"

    monitor_storage = SQLAlchemyMonitorHistoryStorage(database_url=database_url)
    topic_storage = SQLAlchemyTopicHistoryStorage(database_url=database_url, bucket_minutes=3, retention_days=30)
    client_storage = SQLAlchemyClientActivityStorage(database_url=database_url, retention_days=30)

    engine = create_sync_engine_for_url(database_url)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    runtime_before: BrokerRuntimeState | None = None

    with session_factory() as session:
        runtime_before = session.get(BrokerRuntimeState, 1)
        if runtime_before is not None:
            session.expunge(runtime_before)

    try:
        monitor_storage.add_tick_snapshot(
            BrokerTickSnapshot(
                ts=tick_ts,
                bytes_received_rate=321.5,
                bytes_sent_rate=210.25,
                messages_received_delta=17,
                messages_sent_delta=11,
                connected_clients=5,
                disconnected_clients=1,
                active_sessions=6,
                max_concurrent=5,
                total_subscriptions=9,
                retained_messages=2,
                messages_inflight=1,
                latency_ms=8.5,
                broker_uptime="600 seconds",
                messages_received_total=170,
                messages_sent_total=110,
                cpu_pct=12.0,
                memory_bytes=4096,
                memory_pct=18.0,
            )
        )

        topic_storage.record_publish(topic_a, payload_bytes=10, payload_value='{"temp": 22.3}', qos=1, retained=False, event_ts=tick_ts)
        topic_storage.record_publish(topic_a, payload_bytes=15, payload_value='{"temp": 22.8}', qos=1, retained=False, event_ts=tick_ts + timedelta(seconds=40))
        topic_storage.record_publish(topic_b, payload_bytes=20, payload_value='{"status": "ok"}', qos=0, retained=True, event_ts=tick_ts + timedelta(minutes=3))
        topic_storage.record_subscribe(topic_a, event_ts=tick_ts)
        topic_storage.record_subscribe(topic_b, event_ts=tick_ts + timedelta(minutes=3))

        client_storage.upsert_client(username, disabled=False)
        events = [
            MQTTEvent(
                id=f"{test_id}-1",
                timestamp=tick_ts.isoformat(),
                event_type="Client Connection",
                client_id=client_id,
                details="Connected",
                status="success",
                protocol_level="MQTT v5.0",
                clean_session=False,
                keep_alive=60,
                username=username,
                ip_address="10.10.0.5",
                port=1883,
            ),
            MQTTEvent(
                id=f"{test_id}-2",
                timestamp=(tick_ts + timedelta(seconds=20)).isoformat(),
                event_type="Subscribe",
                client_id=client_id,
                details="Subscribed",
                status="info",
                protocol_level="MQTT v5.0",
                clean_session=False,
                keep_alive=60,
                username=username,
                ip_address="10.10.0.5",
                port=1883,
                topic=topic_a,
                qos=1,
            ),
            MQTTEvent(
                id=f"{test_id}-3",
                timestamp=(tick_ts + timedelta(seconds=40)).isoformat(),
                event_type="Publish",
                client_id=client_id,
                details="Published",
                status="info",
                protocol_level="MQTT v5.0",
                clean_session=False,
                keep_alive=60,
                username=username,
                ip_address="10.10.0.5",
                port=1883,
                topic=topic_a,
                qos=1,
                payload_bytes=24,
            ),
            MQTTEvent(
                id=f"{test_id}-4",
                timestamp=(tick_ts + timedelta(seconds=60)).isoformat(),
                event_type="Client Disconnection",
                client_id=client_id,
                details="Disconnected",
                status="warning",
                protocol_level="MQTT v5.0",
                clean_session=False,
                keep_alive=60,
                username=username,
                ip_address="10.10.0.5",
                port=1883,
                disconnect_kind="graceful",
            ),
        ]
        for event in events:
            client_storage.record_event(event)

        activity = client_storage.get_client_activity(username, days=30, limit=20)
        assert activity["client"] is not None
        assert len(activity["session_events"]) == 2
        assert len(activity["topic_events"]) == 2
        assert len(activity["subscriptions"]) == 1
        assert len(activity["daily_summary"]) == 1

        topic_a_history = topic_storage.get_topic_messages(topic_a, limit=10)
        assert topic_a_history["topic"] == topic_a
        assert topic_a_history["total"] >= 2
        assert len(topic_a_history["history"]) >= 2
        assert topic_a_history["history"][0]["kind"] == "message"
        assert topic_a_history["history"][0]["qos"] == 1
        assert '"temp"' in topic_a_history["history"][0]["value"]

        normalized_tick_ts = normalize_datetime(tick_ts)
        with session_factory() as session:
            tick_row = session.scalar(select(BrokerMetricTick).where(BrokerMetricTick.ts == normalized_tick_ts))
            assert tick_row is not None
            assert tick_row.messages_received_delta == 17
            assert tick_row.messages_sent_delta == 11

            summary_row = session.get(BrokerDailySummary, tick_ts.date())
            assert summary_row is not None
            assert summary_row.total_messages_received == 17
            assert summary_row.total_messages_sent == 11

            registry_rows = session.scalars(
                select(TopicRegistry).where(TopicRegistry.topic.in_([topic_a, topic_b]))
            ).all()
            assert {row.topic for row in registry_rows} == {topic_a, topic_b}

            topic_rows_by_name = {row.topic: row for row in registry_rows}
            publish_a = session.scalar(
                select(TopicPublishBucket).where(TopicPublishBucket.topic_id == topic_rows_by_name[topic_a].id)
            )
            publish_b = session.scalar(
                select(TopicPublishBucket).where(TopicPublishBucket.topic_id == topic_rows_by_name[topic_b].id)
            )
            subscribe_a = session.scalar(
                select(TopicSubscribeBucket).where(TopicSubscribeBucket.topic_id == topic_rows_by_name[topic_a].id)
            )
            topic_messages_count = session.scalar(
                select(TopicMessageEvent.id).where(TopicMessageEvent.topic_id == topic_rows_by_name[topic_a].id)
            )
            assert publish_a is not None
            assert publish_b is not None
            assert subscribe_a is not None
            assert topic_messages_count is not None
            assert publish_a.publish_count == 2
            assert publish_a.bytes_sum == 25
            assert publish_b.publish_count == 1
            assert subscribe_a.subscribe_count == 1

            client_row = session.get(ClientRegistry, username)
            assert client_row is not None
            assert client_row.deleted_at is None

            session_events = session.scalars(
                select(ClientSessionEvent).where(ClientSessionEvent.username == username)
            ).all()
            topic_events = session.scalars(
                select(ClientTopicEvent).where(ClientTopicEvent.username == username)
            ).all()
            subscription_state = session.scalar(
                select(ClientSubscriptionState).where(ClientSubscriptionState.username == username)
            )
            daily_summary = session.scalar(
                select(ClientDailySummary).where(
                    ClientDailySummary.username == username,
                    ClientDailySummary.day == tick_ts.date(),
                )
            )
            distinct_topics = session.scalars(
                select(ClientDailyDistinctTopic).where(ClientDailyDistinctTopic.username == username)
            ).all()

            assert len(session_events) == 2
            assert len(topic_events) == 2
            assert subscription_state is not None
            assert subscription_state.topic == topic_a
            assert daily_summary is not None
            assert daily_summary.connects == 1
            assert daily_summary.disconnects_graceful == 1
            assert daily_summary.publishes == 1
            assert daily_summary.subscribes == 1
            assert daily_summary.distinct_publish_topics == 1
            assert daily_summary.distinct_subscribe_topics == 1
            assert len(distinct_topics) == 2
    finally:
        with session_factory() as session:
            session.execute(delete(ClientDailyDistinctTopic).where(ClientDailyDistinctTopic.username == username))
            session.execute(delete(ClientDailySummary).where(ClientDailySummary.username == username))
            session.execute(delete(ClientSubscriptionState).where(ClientSubscriptionState.username == username))
            session.execute(delete(ClientTopicEvent).where(ClientTopicEvent.username == username))
            session.execute(delete(ClientSessionEvent).where(ClientSessionEvent.username == username))
            session.execute(delete(ClientRegistry).where(ClientRegistry.username == username))

            topic_ids = session.scalars(select(TopicRegistry.id).where(TopicRegistry.topic.in_([topic_a, topic_b]))).all()
            if topic_ids:
                session.execute(delete(TopicMessageEvent).where(TopicMessageEvent.topic_id.in_(topic_ids)))
                session.execute(delete(TopicPublishBucket).where(TopicPublishBucket.topic_id.in_(topic_ids)))
                session.execute(delete(TopicSubscribeBucket).where(TopicSubscribeBucket.topic_id.in_(topic_ids)))
            session.execute(delete(TopicRegistry).where(TopicRegistry.topic.in_([topic_a, topic_b])))

            session.execute(delete(BrokerMetricTick).where(BrokerMetricTick.ts == normalize_datetime(tick_ts)))
            session.execute(delete(BrokerDailySummary).where(BrokerDailySummary.day == tick_ts.date()))

            runtime = session.get(BrokerRuntimeState, 1)
            if runtime_before is None:
                if runtime is not None:
                    session.delete(runtime)
            else:
                if runtime is None:
                    session.add(
                        BrokerRuntimeState(
                            id=runtime_before.id,
                            last_tick_ts=runtime_before.last_tick_ts,
                            last_broker_uptime=runtime_before.last_broker_uptime,
                            current_max_concurrent=runtime_before.current_max_concurrent,
                            lifetime_max_concurrent=runtime_before.lifetime_max_concurrent,
                            last_messages_received_total=runtime_before.last_messages_received_total,
                            last_messages_sent_total=runtime_before.last_messages_sent_total,
                        )
                    )
                else:
                    runtime.last_tick_ts = runtime_before.last_tick_ts
                    runtime.last_broker_uptime = runtime_before.last_broker_uptime
                    runtime.current_max_concurrent = runtime_before.current_max_concurrent
                    runtime.lifetime_max_concurrent = runtime_before.lifetime_max_concurrent
                    runtime.last_messages_received_total = runtime_before.last_messages_received_total
                    runtime.last_messages_sent_total = runtime_before.last_messages_sent_total
            session.commit()