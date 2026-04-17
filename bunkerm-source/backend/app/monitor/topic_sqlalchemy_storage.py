from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.sync_database import create_sync_engine_for_url, ensure_tables, iso_utc, normalize_datetime, session_scope, utc_now
from models.orm import TopicMessageEvent, TopicPublishBucket, TopicRegistry, TopicSubscribeBucket
from monitor.data_storage import PERIODS


def _bucket_start(value: datetime, minutes: int) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    bucket_minute = (value.minute // minutes) * minutes
    return value.replace(minute=bucket_minute, second=0, microsecond=0, tzinfo=None)


class SQLAlchemyTopicHistoryStorage:
    """Persistent publish/subscribe buckets for topology and subscription history."""

    def __init__(self, database_url: str, bucket_minutes: int = 3, retention_days: int = 30):
        self._bucket_minutes = bucket_minutes
        self._retention_days = retention_days
        self._lock = threading.Lock()
        self._engine = create_sync_engine_for_url(database_url)
        # Keep storage resilient across mixed deployments: if migrations lag
        # behind code, ensure required history tables exist before first write.
        ensure_tables(
            self._engine,
            [
                TopicRegistry.__table__,
                TopicPublishBucket.__table__,
                TopicSubscribeBucket.__table__,
                TopicMessageEvent.__table__,
            ],
        )
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)

    def record_publish(
        self,
        topic: str,
        payload_bytes: int = 0,
        payload_value: str = "",
        qos: int = 0,
        retained: bool = False,
        event_ts: datetime | None = None,
    ) -> None:
        if not topic or topic.startswith("$"):
            return
        event_ts = event_ts or utc_now()
        bucket = _bucket_start(event_ts, self._bucket_minutes)
        with self._lock:
            with session_scope(self._session_factory) as session:
                topic_row = self._ensure_topic_locked(session, topic, event_ts)
                bucket_row = session.scalar(
                    select(TopicPublishBucket).where(
                        TopicPublishBucket.bucket_start == bucket,
                        TopicPublishBucket.bucket_minutes == self._bucket_minutes,
                        TopicPublishBucket.topic_id == topic_row.id,
                    )
                )
                if bucket_row is None:
                    bucket_row = TopicPublishBucket(
                        bucket_start=bucket,
                        bucket_minutes=self._bucket_minutes,
                        topic_id=topic_row.id,
                        publish_count=0,
                        bytes_sum=0,
                    )
                    session.add(bucket_row)
                bucket_row.publish_count += 1
                bucket_row.bytes_sum += max(0, payload_bytes)
                session.add(
                    TopicMessageEvent(
                        topic_id=topic_row.id,
                        event_ts=normalize_datetime(event_ts),
                        payload_text=payload_value or "",
                        payload_bytes=max(0, payload_bytes),
                        qos=max(0, min(2, int(qos))),
                        retained=bool(retained),
                    )
                )
                self._prune_locked(session)

    def record_subscribe(self, topic: str, event_ts: datetime | None = None) -> None:
        if not topic or topic.startswith("$"):
            return
        event_ts = event_ts or utc_now()
        bucket = _bucket_start(event_ts, self._bucket_minutes)
        with self._lock:
            with session_scope(self._session_factory) as session:
                topic_row = self._ensure_topic_locked(session, topic, event_ts)
                bucket_row = session.scalar(
                    select(TopicSubscribeBucket).where(
                        TopicSubscribeBucket.bucket_start == bucket,
                        TopicSubscribeBucket.bucket_minutes == self._bucket_minutes,
                        TopicSubscribeBucket.topic_id == topic_row.id,
                    )
                )
                if bucket_row is None:
                    bucket_row = TopicSubscribeBucket(
                        bucket_start=bucket,
                        bucket_minutes=self._bucket_minutes,
                        topic_id=topic_row.id,
                        subscribe_count=0,
                    )
                    session.add(bucket_row)
                bucket_row.subscribe_count += 1
                self._prune_locked(session)

    def _ensure_topic_locked(self, session: Session, topic: str, event_ts: datetime) -> TopicRegistry:
        topic_row = session.scalar(select(TopicRegistry).where(TopicRegistry.topic == topic))
        normalized_ts = normalize_datetime(event_ts)
        if topic_row is None:
            topic_row = TopicRegistry(
                topic=topic,
                kind="system" if topic.startswith("$") else "user",
                first_seen_at=normalized_ts,
                last_seen_at=normalized_ts,
            )
            session.add(topic_row)
            session.flush()
            return topic_row
        topic_row.last_seen_at = normalized_ts
        return topic_row

    def _prune_locked(self, session: Session) -> None:
        cutoff = normalize_datetime(utc_now() - timedelta(days=self._retention_days))
        session.execute(delete(TopicPublishBucket).where(TopicPublishBucket.bucket_start < cutoff))
        session.execute(delete(TopicSubscribeBucket).where(TopicSubscribeBucket.bucket_start < cutoff))
        session.execute(delete(TopicMessageEvent).where(TopicMessageEvent.event_ts < cutoff))

    def get_topic_messages(self, topic: str, limit: int = 120) -> Dict[str, Any]:
        topic = (topic or "").strip()
        if not topic:
            return {"topic": "", "history": [], "total": 0}

        clamped_limit = max(1, min(limit, 500))
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    TopicMessageEvent.id,
                    TopicMessageEvent.event_ts,
                    TopicMessageEvent.payload_text,
                    TopicMessageEvent.payload_bytes,
                    TopicMessageEvent.qos,
                    TopicMessageEvent.retained,
                )
                .join(TopicRegistry, TopicRegistry.id == TopicMessageEvent.topic_id)
                .where(TopicRegistry.topic == topic)
                .order_by(TopicMessageEvent.event_ts.desc(), TopicMessageEvent.id.desc())
                .limit(clamped_limit)
            ).all()

            total = session.scalar(
                select(func.count(TopicMessageEvent.id))
                .join(TopicRegistry, TopicRegistry.id == TopicMessageEvent.topic_id)
                .where(TopicRegistry.topic == topic)
            )

        history = [
            {
                "id": int(row.id),
                "topic": topic,
                "value": row.payload_text or "",
                "timestamp": iso_utc(row.event_ts) or "",
                "payload_bytes": int(row.payload_bytes or 0),
                "qos": int(row.qos or 0),
                "retained": bool(row.retained),
                "kind": "message",
            }
            for row in rows
        ]
        return {
            "topic": topic,
            "history": history,
            "total": int(total or 0),
        }

    def get_top_published(self, limit: int = 15, period: str = "7d") -> Dict[str, Any]:
        minutes = PERIODS.get(period, PERIODS["7d"])
        cutoff = normalize_datetime(utc_now() - timedelta(minutes=minutes))
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    TopicRegistry.topic,
                    func.sum(TopicPublishBucket.publish_count).label("count"),
                    func.max(TopicRegistry.last_seen_at).label("last_seen_at"),
                )
                .join(TopicPublishBucket, TopicPublishBucket.topic_id == TopicRegistry.id)
                .where(TopicPublishBucket.bucket_start >= cutoff, TopicRegistry.kind == "user")
                .group_by(TopicRegistry.topic)
                .order_by(desc("count"), TopicRegistry.topic.asc())
                .limit(limit)
            ).all()
            distinct_total = session.scalar(
                select(func.count(func.distinct(TopicRegistry.topic)))
                .join(TopicPublishBucket, TopicPublishBucket.topic_id == TopicRegistry.id)
                .where(TopicPublishBucket.bucket_start >= cutoff, TopicRegistry.kind == "user")
            )
        return {
            "top_topics": [
                {
                    "topic": row.topic,
                    "value": "",
                    "count": int(row.count or 0),
                    "retained": False,
                    "qos": 0,
                    "timestamp": iso_utc(row.last_seen_at) or "",
                }
                for row in rows
            ],
            "total_distinct_topics": int(distinct_total or 0),
        }

    def get_top_subscribed(self, limit: int = 15, period: str = "7d") -> Dict[str, Any]:
        minutes = PERIODS.get(period, PERIODS["7d"])
        cutoff = normalize_datetime(utc_now() - timedelta(minutes=minutes))
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    TopicRegistry.topic,
                    func.sum(TopicSubscribeBucket.subscribe_count).label("count"),
                )
                .join(TopicSubscribeBucket, TopicSubscribeBucket.topic_id == TopicRegistry.id)
                .where(TopicSubscribeBucket.bucket_start >= cutoff, TopicRegistry.kind == "user")
                .group_by(TopicRegistry.topic)
                .order_by(desc("count"), TopicRegistry.topic.asc())
                .limit(limit)
            ).all()
            distinct_total = session.scalar(
                select(func.count(func.distinct(TopicRegistry.topic)))
                .join(TopicSubscribeBucket, TopicSubscribeBucket.topic_id == TopicRegistry.id)
                .where(TopicSubscribeBucket.bucket_start >= cutoff, TopicRegistry.kind == "user")
            )
        return {
            "top_subscribed": [{"topic": row.topic, "count": int(row.count or 0)} for row in rows],
            "total_distinct_subscribed": int(distinct_total or 0),
        }