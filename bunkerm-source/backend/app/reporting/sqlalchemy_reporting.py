from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Iterable, Sequence

from sqlalchemy import delete, func, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from core.database_url import is_sqlite_url
from core.sync_database import create_sync_engine_for_url, ensure_tables, iso_utc, normalize_datetime, parse_iso, session_scope, utc_now
from models.orm import (
    BrokerDailySummary,
    BrokerMetricTick,
    ClientDailyDistinctTopic,
    ClientDailySummary,
    ClientMQTTEvent,
    ClientRegistry,
    TopicPublishBucket,
    TopicSubscribeBucket,
)


class SQLAlchemyReportingStorage:
    """Phase-4 reporting queries over SQLAlchemy-backed operational history."""

    def __init__(
        self,
        database_url: str,
        client_retention_days: int = 30,
        topic_retention_days: int = 30,
        broker_raw_retention_days: int = 30,
        broker_daily_retention_days: int = 365,
    ):
        self._client_retention_days = client_retention_days
        self._topic_retention_days = topic_retention_days
        self._broker_raw_retention_days = broker_raw_retention_days
        self._broker_daily_retention_days = broker_daily_retention_days
        self._engine = create_sync_engine_for_url(database_url)
        if is_sqlite_url(database_url):
            ensure_tables(
                self._engine,
                [
                    BrokerMetricTick.__table__,
                    BrokerDailySummary.__table__,
                    ClientRegistry.__table__,
                    ClientMQTTEvent.__table__,
                    ClientDailySummary.__table__,
                    ClientDailyDistinctTopic.__table__,
                    TopicPublishBucket.__table__,
                    TopicSubscribeBucket.__table__,
                ],
            )
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)

    def get_broker_daily_report(self, days: int = 30) -> dict[str, Any]:
        days = max(1, min(days, self._broker_daily_retention_days))
        cutoff = (utc_now() - timedelta(days=days)).date()
        if not self._has_table(BrokerDailySummary.__tablename__):
            return {"period": {"kind": "daily", "days": days}, "items": [], "totals": {"days": 0, "total_messages_received": 0, "total_messages_sent": 0, "peak_connected_clients": 0, "peak_active_sessions": 0, "peak_max_concurrent": 0, "bytes_received_rate_sum": 0.0, "bytes_sent_rate_sum": 0.0, "avg_latency_ms": None}}
        with self._session_factory() as session:
            rows = session.scalars(
                select(BrokerDailySummary)
                .where(BrokerDailySummary.day >= cutoff)
                .order_by(BrokerDailySummary.day.asc())
            ).all()

        items: list[dict[str, Any]] = []
        totals = {
            "days": 0,
            "total_messages_received": 0,
            "total_messages_sent": 0,
            "peak_connected_clients": 0,
            "peak_active_sessions": 0,
            "peak_max_concurrent": 0,
            "bytes_received_rate_sum": 0.0,
            "bytes_sent_rate_sum": 0.0,
            "latency_samples": 0,
            "latency_sum": 0.0,
        }
        for row in rows:
            latency_samples = int(row.latency_samples or 0)
            avg_latency_ms = round(float(row.latency_sum or 0.0) / latency_samples, 2) if latency_samples else None
            item = {
                "day": row.day.isoformat(),
                "peak_connected_clients": int(row.peak_connected_clients or 0),
                "peak_active_sessions": int(row.peak_active_sessions or 0),
                "peak_max_concurrent": int(row.peak_max_concurrent or 0),
                "total_messages_received": int(row.total_messages_received or 0),
                "total_messages_sent": int(row.total_messages_sent or 0),
                "bytes_received_rate_sum": float(row.bytes_received_rate_sum or 0.0),
                "bytes_sent_rate_sum": float(row.bytes_sent_rate_sum or 0.0),
                "latency_samples": latency_samples,
                "avg_latency_ms": avg_latency_ms,
            }
            items.append(item)
            totals["days"] += 1
            totals["total_messages_received"] += item["total_messages_received"]
            totals["total_messages_sent"] += item["total_messages_sent"]
            totals["peak_connected_clients"] = max(totals["peak_connected_clients"], item["peak_connected_clients"])
            totals["peak_active_sessions"] = max(totals["peak_active_sessions"], item["peak_active_sessions"])
            totals["peak_max_concurrent"] = max(totals["peak_max_concurrent"], item["peak_max_concurrent"])
            totals["bytes_received_rate_sum"] += item["bytes_received_rate_sum"]
            totals["bytes_sent_rate_sum"] += item["bytes_sent_rate_sum"]
            totals["latency_samples"] += latency_samples
            totals["latency_sum"] += float(row.latency_sum or 0.0)

        avg_latency = round(totals["latency_sum"] / totals["latency_samples"], 2) if totals["latency_samples"] else None
        return {
            "period": {"kind": "daily", "days": days},
            "items": items,
            "totals": {
                "days": totals["days"],
                "total_messages_received": totals["total_messages_received"],
                "total_messages_sent": totals["total_messages_sent"],
                "peak_connected_clients": totals["peak_connected_clients"],
                "peak_active_sessions": totals["peak_active_sessions"],
                "peak_max_concurrent": totals["peak_max_concurrent"],
                "bytes_received_rate_sum": round(totals["bytes_received_rate_sum"], 2),
                "bytes_sent_rate_sum": round(totals["bytes_sent_rate_sum"], 2),
                "avg_latency_ms": avg_latency,
            },
        }

    def get_broker_weekly_report(self, weeks: int = 8) -> dict[str, Any]:
        weeks = max(1, min(weeks, 52))
        cutoff = utc_now().date() - timedelta(days=weeks * 7)
        daily = self.get_broker_daily_report(days=max(weeks * 7, 1))["items"]
        buckets: dict[str, dict[str, Any]] = {}
        for item in daily:
            day_value = date.fromisoformat(item["day"])
            if day_value < cutoff:
                continue
            week_start = day_value - timedelta(days=day_value.weekday())
            key = week_start.isoformat()
            bucket = buckets.setdefault(
                key,
                {
                    "week_start": key,
                    "week_end": (week_start + timedelta(days=6)).isoformat(),
                    "days_covered": 0,
                    "peak_connected_clients": 0,
                    "peak_active_sessions": 0,
                    "peak_max_concurrent": 0,
                    "total_messages_received": 0,
                    "total_messages_sent": 0,
                    "bytes_received_rate_sum": 0.0,
                    "bytes_sent_rate_sum": 0.0,
                    "latency_weight_sum": 0.0,
                    "latency_samples": 0,
                },
            )
            bucket["days_covered"] += 1
            bucket["peak_connected_clients"] = max(bucket["peak_connected_clients"], item["peak_connected_clients"])
            bucket["peak_active_sessions"] = max(bucket["peak_active_sessions"], item["peak_active_sessions"])
            bucket["peak_max_concurrent"] = max(bucket["peak_max_concurrent"], item["peak_max_concurrent"])
            bucket["total_messages_received"] += item["total_messages_received"]
            bucket["total_messages_sent"] += item["total_messages_sent"]
            bucket["bytes_received_rate_sum"] += item["bytes_received_rate_sum"]
            bucket["bytes_sent_rate_sum"] += item["bytes_sent_rate_sum"]
            latency_samples = int(item["latency_samples"] or 0)
            if latency_samples and item["avg_latency_ms"] is not None:
                bucket["latency_samples"] += latency_samples
                bucket["latency_weight_sum"] += float(item["avg_latency_ms"]) * latency_samples

        items = []
        for key in sorted(buckets.keys()):
            bucket = buckets[key]
            avg_latency = round(bucket["latency_weight_sum"] / bucket["latency_samples"], 2) if bucket["latency_samples"] else None
            items.append(
                {
                    "week_start": bucket["week_start"],
                    "week_end": bucket["week_end"],
                    "days_covered": bucket["days_covered"],
                    "peak_connected_clients": bucket["peak_connected_clients"],
                    "peak_active_sessions": bucket["peak_active_sessions"],
                    "peak_max_concurrent": bucket["peak_max_concurrent"],
                    "total_messages_received": bucket["total_messages_received"],
                    "total_messages_sent": bucket["total_messages_sent"],
                    "bytes_received_rate_sum": round(bucket["bytes_received_rate_sum"], 2),
                    "bytes_sent_rate_sum": round(bucket["bytes_sent_rate_sum"], 2),
                    "avg_latency_ms": avg_latency,
                }
            )
        return {
            "period": {"kind": "weekly", "weeks": weeks},
            "items": items,
            "totals": {
                "weeks": len(items),
                "total_messages_received": sum(item["total_messages_received"] for item in items),
                "total_messages_sent": sum(item["total_messages_sent"] for item in items),
                "peak_connected_clients": max((item["peak_connected_clients"] for item in items), default=0),
                "peak_active_sessions": max((item["peak_active_sessions"] for item in items), default=0),
                "peak_max_concurrent": max((item["peak_max_concurrent"] for item in items), default=0),
            },
        }

    def get_client_timeline(
        self,
        username: str,
        days: int = 30,
        limit: int = 200,
        event_types: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        days = max(1, min(days, self._client_retention_days))
        limit = max(1, min(limit, 1000))
        cutoff = normalize_datetime(utc_now() - timedelta(days=days))
        normalized = {value.strip().lower() for value in (event_types or []) if value and value.strip()}
        with self._session_factory() as session:
            registry = session.get(ClientRegistry, username)
            all_rows = session.scalars(
                select(ClientMQTTEvent)
                .where(ClientMQTTEvent.username == username, ClientMQTTEvent.event_ts >= cutoff)
                .order_by(ClientMQTTEvent.event_ts.desc())
                .limit(limit)
            ).all()

        events = [self._mqtt_event_to_timeline(row) for row in all_rows]
        if normalized:
            events = [event for event in events if str(event["event_type"]).lower() in normalized]
        events.sort(key=lambda item: item["event_ts"], reverse=True)
        return {
            "client": self._registry_to_dict(registry) if registry else None,
            "filters": {"days": days, "limit": limit, "event_types": sorted(normalized)},
            "timeline": events[:limit],
        }

    def get_client_incidents(
        self,
        days: int = 30,
        limit: int = 200,
        username: str | None = None,
        incident_types: Sequence[str] | None = None,
        reconnect_window_minutes: int = 30,
        reconnect_threshold: int = 3,
    ) -> dict[str, Any]:
        days = max(1, min(days, self._client_retention_days))
        limit = max(1, min(limit, 1000))
        reconnect_window_minutes = max(1, min(reconnect_window_minutes, 1440))
        reconnect_threshold = max(2, min(reconnect_threshold, 50))
        normalized = {value.strip().lower() for value in (incident_types or []) if value and value.strip()}
        if not normalized:
            normalized = {"ungraceful_disconnect", "auth_failure", "reconnect_loop"}
        cutoff = normalize_datetime(utc_now() - timedelta(days=days))
        with self._session_factory() as session:
            query = (
                select(ClientMQTTEvent)
                .where(
                    ClientMQTTEvent.event_ts >= cutoff,
                    ClientMQTTEvent.event_type.in_(["Client Connection", "Client Disconnection", "Auth Failure"]),
                )
                .order_by(ClientMQTTEvent.username.asc(), ClientMQTTEvent.event_ts.asc())
            )
            if username:
                query = query.where(ClientMQTTEvent.username == username)
            session_rows = session.scalars(query).all()

        incidents: list[dict[str, Any]] = []
        connects_by_user: dict[str, list[ClientMQTTEvent]] = defaultdict(list)
        for row in session_rows:
            row_user = row.username or "(unknown)"
            if row.event_type == "Client Connection":
                connects_by_user[row_user].append(row)
            if row.event_type == "Client Disconnection" and row.disconnect_kind == "ungraceful" and "ungraceful_disconnect" in normalized:
                incidents.append(
                    {
                        "incident_type": "ungraceful_disconnect",
                        "username": row_user,
                        "client_id": row.client_id,
                        "event_ts": iso_utc(row.event_ts),
                        "details": {
                            "disconnect_kind": row.disconnect_kind,
                            "reason_code": row.reason_code,
                            "ip_address": row.ip_address,
                            "port": row.port,
                        },
                    }
                )
            if row.event_type == "Auth Failure" and "auth_failure" in normalized:
                incidents.append(
                    {
                        "incident_type": "auth_failure",
                        "username": row_user,
                        "client_id": row.client_id,
                        "event_ts": iso_utc(row.event_ts),
                        "details": {
                            "reason_code": row.reason_code,
                            "ip_address": row.ip_address,
                            "port": row.port,
                        },
                    }
                )

        if "reconnect_loop" in normalized:
            reconnect_window = timedelta(minutes=reconnect_window_minutes)
            for row_user, rows in connects_by_user.items():
                cluster: list[ClientMQTTEvent] = []
                for row in rows:
                    if not cluster:
                        cluster = [row]
                        continue
                    first_ts = cluster[0].event_ts
                    if row.event_ts - first_ts <= reconnect_window:
                        cluster.append(row)
                        continue
                    if len(cluster) >= reconnect_threshold:
                        incidents.append(self._build_reconnect_incident(row_user, cluster))
                    cluster = [row]
                if len(cluster) >= reconnect_threshold:
                    incidents.append(self._build_reconnect_incident(row_user, cluster))

        incidents.sort(key=lambda item: item["event_ts"], reverse=True)
        return {
            "filters": {
                "days": days,
                "limit": limit,
                "username": username,
                "incident_types": sorted(normalized),
                "reconnect_window_minutes": reconnect_window_minutes,
                "reconnect_threshold": reconnect_threshold,
            },
            "incidents": incidents[:limit],
            "total": len(incidents),
        }

    def _build_reconnect_incident(self, username: str, rows: Sequence[ClientMQTTEvent]) -> dict[str, Any]:
        return {
            "incident_type": "reconnect_loop",
            "username": username,
            "client_id": rows[-1].client_id,
            "event_ts": iso_utc(rows[-1].event_ts),
            "details": {
                "attempts": len(rows),
                "start_ts": iso_utc(rows[0].event_ts),
                "end_ts": iso_utc(rows[-1].event_ts),
            },
        }

    def get_retention_status(self) -> dict[str, Any]:
        now = utc_now()
        broker_raw_cutoff = normalize_datetime(now - timedelta(days=self._broker_raw_retention_days))
        broker_daily_cutoff = (now - timedelta(days=self._broker_daily_retention_days)).date()
        client_cutoff = normalize_datetime(now - timedelta(days=self._client_retention_days))
        client_day_cutoff = (now - timedelta(days=self._client_retention_days)).date()
        topic_cutoff = normalize_datetime(now - timedelta(days=self._topic_retention_days))
        counts = {
            "broker_metric_ticks": self._count_older_than(BrokerMetricTick.__tablename__, BrokerMetricTick, BrokerMetricTick.ts, broker_raw_cutoff),
            "broker_daily_summary": self._count_older_than(BrokerDailySummary.__tablename__, BrokerDailySummary, BrokerDailySummary.day, broker_daily_cutoff),
            "client_mqtt_events": self._count_older_than(ClientMQTTEvent.__tablename__, ClientMQTTEvent, ClientMQTTEvent.event_ts, client_cutoff),
            "client_daily_summary": self._count_older_than(ClientDailySummary.__tablename__, ClientDailySummary, ClientDailySummary.day, client_day_cutoff),
            "client_daily_distinct_topics": self._count_older_than(ClientDailyDistinctTopic.__tablename__, ClientDailyDistinctTopic, ClientDailyDistinctTopic.day, client_day_cutoff),
            "topic_publish_buckets": self._count_older_than(TopicPublishBucket.__tablename__, TopicPublishBucket, TopicPublishBucket.bucket_start, topic_cutoff),
            "topic_subscribe_buckets": self._count_older_than(TopicSubscribeBucket.__tablename__, TopicSubscribeBucket, TopicSubscribeBucket.bucket_start, topic_cutoff),
        }
        return {
            "retention_days": {
                "broker_raw": self._broker_raw_retention_days,
                "broker_daily": self._broker_daily_retention_days,
                "client": self._client_retention_days,
                "topic": self._topic_retention_days,
            },
            "rows_past_retention": counts,
            "total_rows_past_retention": sum(counts.values()),
        }

    def execute_retention_purge(self) -> dict[str, Any]:
        before = self.get_retention_status()
        now = utc_now()
        broker_raw_cutoff = normalize_datetime(now - timedelta(days=self._broker_raw_retention_days))
        broker_daily_cutoff = (now - timedelta(days=self._broker_daily_retention_days)).date()
        client_cutoff = normalize_datetime(now - timedelta(days=self._client_retention_days))
        client_day_cutoff = (now - timedelta(days=self._client_retention_days)).date()
        topic_cutoff = normalize_datetime(now - timedelta(days=self._topic_retention_days))
        with session_scope(self._session_factory) as session:
            self._delete_older_than(session, BrokerMetricTick.__tablename__, BrokerMetricTick, BrokerMetricTick.ts, broker_raw_cutoff)
            self._delete_older_than(session, BrokerDailySummary.__tablename__, BrokerDailySummary, BrokerDailySummary.day, broker_daily_cutoff)
            self._delete_older_than(session, ClientMQTTEvent.__tablename__, ClientMQTTEvent, ClientMQTTEvent.event_ts, client_cutoff)
            self._delete_older_than(session, ClientDailySummary.__tablename__, ClientDailySummary, ClientDailySummary.day, client_day_cutoff)
            self._delete_older_than(session, ClientDailyDistinctTopic.__tablename__, ClientDailyDistinctTopic, ClientDailyDistinctTopic.day, client_day_cutoff)
            self._delete_older_than(session, TopicPublishBucket.__tablename__, TopicPublishBucket, TopicPublishBucket.bucket_start, topic_cutoff)
            self._delete_older_than(session, TopicSubscribeBucket.__tablename__, TopicSubscribeBucket, TopicSubscribeBucket.bucket_start, topic_cutoff)
        after = self.get_retention_status()
        return {
            "status": "purged",
            "deleted_rows": before["total_rows_past_retention"] - after["total_rows_past_retention"],
            "before": before,
            "after": after,
        }

    def _delete_older_than(self, session, table_name: str, model, column, cutoff: Any) -> None:
        if not self._has_table(table_name):
            return
        try:
            session.execute(delete(model).where(column < cutoff))
        except SQLAlchemyError:
            return

    def _count_older_than(self, table_name: str, model, column, cutoff: Any) -> int:
        if not self._has_table(table_name):
            return 0
        try:
            with self._session_factory() as session:
                total = session.scalar(select(func.count()).select_from(model).where(column < cutoff))
            return int(total or 0)
        except SQLAlchemyError:
            return 0

    def _has_table(self, table_name: str) -> bool:
        return inspect(self._engine).has_table(table_name)

    @staticmethod
    def _registry_to_dict(row: ClientRegistry) -> dict[str, Any]:
        return {
            "username": row.username,
            "textname": row.textname,
            "disabled": bool(row.disabled),
            "created_at": iso_utc(row.created_at),
            "deleted_at": iso_utc(row.deleted_at),
            "last_dynsec_sync_at": iso_utc(row.last_dynsec_sync_at),
        }

    @staticmethod
    def _mqtt_event_to_timeline(row: ClientMQTTEvent) -> dict[str, Any]:
        return {
            "event_ts": iso_utc(row.event_ts),
            "event_type": row.event_type,
            "client_id": row.client_id,
            "ip_address": row.ip_address,
            "port": row.port,
            "protocol_level": row.protocol_level,
            "clean_session": row.clean_session,
            "keep_alive": row.keep_alive,
            "disconnect_kind": row.disconnect_kind,
            "reason_code": row.reason_code,
            "topic": row.topic,
            "qos": row.qos,
            "payload_bytes": row.payload_bytes,
            "retained": row.retained,
        }

    @staticmethod
    def to_csv_bytes(rows: Iterable[dict[str, Any]], fieldnames: Sequence[str]) -> bytes:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})
        return buffer.getvalue().encode("utf-8")