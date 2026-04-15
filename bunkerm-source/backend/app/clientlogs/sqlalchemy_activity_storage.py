from __future__ import annotations

import threading
from datetime import timedelta
from typing import Any, Dict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from core.sync_database import create_sync_engine_for_url, ensure_tables, iso_utc, normalize_datetime, parse_iso, session_scope, utc_now
from models.orm import (
    ClientDailyDistinctTopic,
    ClientDailySummary,
    ClientRegistry,
    ClientSessionEvent,
    ClientSubscriptionState,
    ClientTopicEvent,
)


class SQLAlchemyClientActivityStorage:
    """Persistent 30-day client activity and registry storage over SQLAlchemy."""

    def __init__(self, database_url: str, retention_days: int = 30):
        self._retention_days = retention_days
        self._lock = threading.Lock()
        self._engine = create_sync_engine_for_url(database_url)
        ensure_tables(
            self._engine,
            [
                ClientRegistry.__table__,
                ClientSessionEvent.__table__,
                ClientTopicEvent.__table__,
                ClientSubscriptionState.__table__,
                ClientDailySummary.__table__,
                ClientDailyDistinctTopic.__table__,
            ],
        )
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)

    def upsert_client(self, username: str, textname: str | None = None, disabled: bool = False) -> None:
        if not username:
            return
        now = normalize_datetime(utc_now())
        with self._lock:
            with session_scope(self._session_factory) as session:
                registry = session.get(ClientRegistry, username)
                if registry is None:
                    registry = ClientRegistry(
                        username=username,
                        textname=textname,
                        disabled=disabled,
                        created_at=now,
                        deleted_at=None,
                        last_dynsec_sync_at=now,
                    )
                    session.add(registry)
                    return
                registry.textname = textname
                registry.disabled = disabled
                registry.deleted_at = None
                registry.last_dynsec_sync_at = now

    def mark_client_deleted(self, username: str) -> None:
        if not username:
            return
        now = normalize_datetime(utc_now())
        with self._lock:
            with session_scope(self._session_factory) as session:
                registry = session.get(ClientRegistry, username)
                if registry is None:
                    return
                registry.deleted_at = now
                registry.last_dynsec_sync_at = now

    def reconcile_dynsec_clients(self, clients: list[dict[str, Any]]) -> None:
        now = normalize_datetime(utc_now())
        seen: set[str] = set()
        with self._lock:
            with session_scope(self._session_factory) as session:
                for client in clients or []:
                    username = client.get("username")
                    if not isinstance(username, str) or not username:
                        continue
                    seen.add(username)
                    registry = session.get(ClientRegistry, username)
                    if registry is None:
                        registry = ClientRegistry(
                            username=username,
                            textname=client.get("textname"),
                            disabled=bool(client.get("disabled", False)),
                            created_at=now,
                            deleted_at=None,
                            last_dynsec_sync_at=now,
                        )
                        session.add(registry)
                        continue
                    registry.textname = client.get("textname")
                    registry.disabled = bool(client.get("disabled", False))
                    registry.deleted_at = None
                    registry.last_dynsec_sync_at = now

                if seen:
                    stale_clients = session.scalars(
                        select(ClientRegistry).where(
                            ClientRegistry.deleted_at.is_(None),
                            ClientRegistry.username.not_in(sorted(seen)),
                        )
                    ).all()
                    for registry in stale_clients:
                        registry.deleted_at = now
                        registry.last_dynsec_sync_at = now

    def record_event(self, event: Any) -> None:
        event_ts = normalize_datetime(parse_iso(getattr(event, "timestamp", None)) or utc_now())
        username = getattr(event, "username", None)
        client_id = getattr(event, "client_id", "")
        event_type = getattr(event, "event_type", "")
        if username and username not in ("unknown", "(broker-observed)"):
            self.upsert_client(username)

        with self._lock:
            with session_scope(self._session_factory) as session:
                day = event_ts.date()
                if event_type in ("Client Connection", "Client Disconnection", "Auth Failure"):
                    session.add(
                        ClientSessionEvent(
                            username=username,
                            client_id=client_id,
                            event_ts=event_ts,
                            event_type=event_type,
                            disconnect_kind=getattr(event, "disconnect_kind", None),
                            reason_code=getattr(event, "reason_code", None),
                            ip_address=getattr(event, "ip_address", None),
                            port=getattr(event, "port", None),
                            protocol_level=getattr(event, "protocol_level", None),
                            clean_session=getattr(event, "clean_session", None),
                            keep_alive=getattr(event, "keep_alive", None),
                        )
                    )
                    self._upsert_daily_summary_locked(
                        session,
                        username,
                        day,
                        event_type,
                        getattr(event, "disconnect_kind", None),
                    )

                if event_type in ("Subscribe", "Publish") and getattr(event, "topic", None):
                    session.add(
                        ClientTopicEvent(
                            username=username,
                            client_id=client_id,
                            event_ts=event_ts,
                            event_type=event_type.lower(),
                            topic=getattr(event, "topic", ""),
                            qos=getattr(event, "qos", None),
                            payload_bytes=getattr(event, "payload_bytes", None),
                            retained=getattr(event, "retained", None),
                        )
                    )
                    if username:
                        self._upsert_subscription_state_locked(session, username, event, event_ts)
                        self._upsert_daily_summary_locked(
                            session,
                            username,
                            day,
                            event_type,
                            None,
                            topic=getattr(event, "topic", None),
                        )

                self._prune_locked(session)

    def _upsert_subscription_state_locked(self, session: Session, username: str, event: Any, event_ts) -> None:
        if getattr(event, "event_type", "") != "Subscribe":
            return
        topic = getattr(event, "topic", None)
        if not topic:
            return
        state = session.scalar(
            select(ClientSubscriptionState).where(
                ClientSubscriptionState.username == username,
                ClientSubscriptionState.topic == topic,
            )
        )
        if state is None:
            session.add(
                ClientSubscriptionState(
                    username=username,
                    topic=topic,
                    qos=getattr(event, "qos", None),
                    first_seen_at=event_ts,
                    last_seen_at=event_ts,
                    is_active=True,
                    source="clientlogs",
                )
            )
            return
        state.qos = getattr(event, "qos", None)
        state.last_seen_at = event_ts
        state.is_active = True
        state.source = "clientlogs"

    def _upsert_daily_summary_locked(
        self,
        session: Session,
        username: str | None,
        day,
        event_type: str,
        disconnect_kind: str | None,
        topic: str | None = None,
    ) -> None:
        if not username:
            return
        summary = session.scalar(
            select(ClientDailySummary).where(
                ClientDailySummary.username == username,
                ClientDailySummary.day == day,
            )
        )
        if summary is None:
            summary = ClientDailySummary(username=username, day=day)
            session.add(summary)
            session.flush()

        if event_type == "Client Connection":
            summary.connects += 1
        elif event_type == "Client Disconnection":
            if disconnect_kind == "graceful":
                summary.disconnects_graceful += 1
            else:
                summary.disconnects_ungraceful += 1
        elif event_type == "Auth Failure":
            summary.auth_failures += 1
        elif event_type == "Publish":
            summary.publishes += 1
            self._track_distinct_topic_locked(session, summary, "publish", topic)
        elif event_type == "Subscribe":
            summary.subscribes += 1
            self._track_distinct_topic_locked(session, summary, "subscribe", topic)

    def _track_distinct_topic_locked(
        self,
        session: Session,
        summary: ClientDailySummary,
        event_type: str,
        topic: str | None,
    ) -> None:
        if not topic:
            return
        existing = session.get(
            ClientDailyDistinctTopic,
            {
                "username": summary.username,
                "day": summary.day,
                "event_type": event_type,
                "topic": topic,
            },
        )
        if existing is not None:
            return
        session.add(
            ClientDailyDistinctTopic(
                username=summary.username,
                day=summary.day,
                event_type=event_type,
                topic=topic,
            )
        )
        if event_type == "publish":
            summary.distinct_publish_topics += 1
        else:
            summary.distinct_subscribe_topics += 1

    def _prune_locked(self, session: Session) -> None:
        cutoff = normalize_datetime(utc_now() - timedelta(days=self._retention_days))
        cutoff_day = (utc_now() - timedelta(days=self._retention_days)).date()
        session.execute(delete(ClientSessionEvent).where(ClientSessionEvent.event_ts < cutoff))
        session.execute(delete(ClientTopicEvent).where(ClientTopicEvent.event_ts < cutoff))
        session.execute(delete(ClientDailyDistinctTopic).where(ClientDailyDistinctTopic.day < cutoff_day))
        session.execute(delete(ClientDailySummary).where(ClientDailySummary.day < cutoff_day))

    def get_client_activity(self, username: str, days: int = 30, limit: int = 200) -> Dict[str, Any]:
        days = max(1, min(days, self._retention_days))
        limit = max(1, min(limit, 1000))
        cutoff = normalize_datetime(utc_now() - timedelta(days=days))
        cutoff_day = (utc_now() - timedelta(days=days)).date()
        with self._session_factory() as session:
            registry = session.get(ClientRegistry, username)
            session_rows = session.scalars(
                select(ClientSessionEvent)
                .where(ClientSessionEvent.username == username, ClientSessionEvent.event_ts >= cutoff)
                .order_by(ClientSessionEvent.event_ts.desc())
                .limit(limit)
            ).all()
            topic_rows = session.scalars(
                select(ClientTopicEvent)
                .where(ClientTopicEvent.username == username, ClientTopicEvent.event_ts >= cutoff)
                .order_by(ClientTopicEvent.event_ts.desc())
                .limit(limit)
            ).all()
            subs_rows = session.scalars(
                select(ClientSubscriptionState)
                .where(ClientSubscriptionState.username == username)
                .order_by(ClientSubscriptionState.topic.asc())
            ).all()
            summary_rows = session.scalars(
                select(ClientDailySummary)
                .where(ClientDailySummary.username == username, ClientDailySummary.day >= cutoff_day)
                .order_by(ClientDailySummary.day.desc())
            ).all()

        return {
            "client": self._registry_to_dict(registry) if registry else None,
            "session_events": [self._session_event_to_dict(row) for row in session_rows],
            "topic_events": [self._topic_event_to_dict(row) for row in topic_rows],
            "subscriptions": [self._subscription_to_dict(row) for row in subs_rows],
            "daily_summary": [self._daily_summary_to_dict(row) for row in summary_rows],
        }

    @staticmethod
    def _registry_to_dict(row: ClientRegistry) -> Dict[str, Any]:
        return {
            "username": row.username,
            "textname": row.textname,
            "disabled": bool(row.disabled),
            "created_at": iso_utc(row.created_at),
            "deleted_at": iso_utc(row.deleted_at),
            "last_dynsec_sync_at": iso_utc(row.last_dynsec_sync_at),
        }

    @staticmethod
    def _session_event_to_dict(row: ClientSessionEvent) -> Dict[str, Any]:
        return {
            "id": row.id,
            "username": row.username,
            "client_id": row.client_id,
            "event_ts": iso_utc(row.event_ts),
            "event_type": row.event_type,
            "disconnect_kind": row.disconnect_kind,
            "reason_code": row.reason_code,
            "ip_address": row.ip_address,
            "port": row.port,
            "protocol_level": row.protocol_level,
            "clean_session": row.clean_session,
            "keep_alive": row.keep_alive,
        }

    @staticmethod
    def _topic_event_to_dict(row: ClientTopicEvent) -> Dict[str, Any]:
        return {
            "id": row.id,
            "username": row.username,
            "client_id": row.client_id,
            "event_ts": iso_utc(row.event_ts),
            "event_type": row.event_type,
            "topic": row.topic,
            "qos": row.qos,
            "payload_bytes": row.payload_bytes,
            "retained": row.retained,
        }

    @staticmethod
    def _subscription_to_dict(row: ClientSubscriptionState) -> Dict[str, Any]:
        return {
            "topic": row.topic,
            "qos": row.qos,
            "first_seen_at": iso_utc(row.first_seen_at),
            "last_seen_at": iso_utc(row.last_seen_at),
            "is_active": bool(row.is_active),
            "source": row.source,
        }

    @staticmethod
    def _daily_summary_to_dict(row: ClientDailySummary) -> Dict[str, Any]:
        return {
            "id": row.id,
            "username": row.username,
            "day": row.day.isoformat(),
            "connects": row.connects,
            "disconnects_graceful": row.disconnects_graceful,
            "disconnects_ungraceful": row.disconnects_ungraceful,
            "auth_failures": row.auth_failures,
            "publishes": row.publishes,
            "subscribes": row.subscribes,
            "distinct_publish_topics": row.distinct_publish_topics,
            "distinct_subscribe_topics": row.distinct_subscribe_topics,
        }