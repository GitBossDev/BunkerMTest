from __future__ import annotations

import csv
import io
import os
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

from core.config import settings
from core.database_url import ensure_sqlite_url


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


def _resolve_sqlite_target(database_url: str) -> tuple[str, bool]:
    ensure_sqlite_url(database_url, "REPORTING_DATABASE_URL")
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    target = database_url
    for prefix in prefixes:
        if database_url.startswith(prefix):
            target = database_url[len(prefix):]
            break
    if target == ":memory:":
        return ("file:bunkerm-reporting?mode=memory&cache=shared", True)
    return (target, target.startswith("file:"))


class SQLiteReportingStorage:
    """Phase-4 reporting queries over the shared SQLite operational history."""

    def __init__(self, database_url: str, client_retention_days: int = 30, topic_retention_days: int = 30,
                 broker_raw_retention_days: int = 30, broker_daily_retention_days: int = 365):
        self._db_target, self._use_uri = _resolve_sqlite_target(database_url)
        self._client_retention_days = client_retention_days
        self._topic_retention_days = topic_retention_days
        self._broker_raw_retention_days = broker_raw_retention_days
        self._broker_daily_retention_days = broker_daily_retention_days
        self._keeper_conn: sqlite3.Connection | None = None
        if self._use_uri and "mode=memory" in self._db_target:
            self._keeper_conn = sqlite3.connect(self._db_target, uri=True, check_same_thread=False)
        elif self._db_target != ":memory:":
            os.makedirs(os.path.dirname(self._db_target), exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_target, uri=self._use_uri, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def get_broker_daily_report(self, days: int = 30) -> dict[str, Any]:
        days = max(1, min(days, self._broker_daily_retention_days))
        cutoff = (_utc_now() - timedelta(days=days)).date().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT day, peak_connected_clients, peak_active_sessions, peak_max_concurrent,
                       total_messages_received, total_messages_sent,
                       bytes_received_rate_sum, bytes_sent_rate_sum,
                       latency_samples, latency_sum
                FROM broker_daily_summary
                WHERE day >= ?
                ORDER BY day ASC
                """,
                (cutoff,),
            ).fetchall()

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
            latency_samples = int(row["latency_samples"] or 0)
            avg_latency_ms = round(float(row["latency_sum"] or 0.0) / latency_samples, 2) if latency_samples else None
            item = {
                "day": row["day"],
                "peak_connected_clients": int(row["peak_connected_clients"] or 0),
                "peak_active_sessions": int(row["peak_active_sessions"] or 0),
                "peak_max_concurrent": int(row["peak_max_concurrent"] or 0),
                "total_messages_received": int(row["total_messages_received"] or 0),
                "total_messages_sent": int(row["total_messages_sent"] or 0),
                "bytes_received_rate_sum": float(row["bytes_received_rate_sum"] or 0.0),
                "bytes_sent_rate_sum": float(row["bytes_sent_rate_sum"] or 0.0),
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
            totals["latency_sum"] += float(row["latency_sum"] or 0.0)

        avg_latency = None
        if totals["latency_samples"]:
            avg_latency = round(totals["latency_sum"] / totals["latency_samples"], 2)
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
        cutoff = (_utc_now().date() - timedelta(days=weeks * 7))
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

    def get_client_timeline(self, username: str, days: int = 30, limit: int = 200,
                            event_types: Sequence[str] | None = None) -> dict[str, Any]:
        days = max(1, min(days, self._client_retention_days))
        limit = max(1, min(limit, 1000))
        cutoff = _iso_utc(_utc_now() - timedelta(days=days))
        normalized = {value.strip().lower() for value in (event_types or []) if value and value.strip()}
        with self._connect() as conn:
            registry = conn.execute("SELECT * FROM client_registry WHERE username = ?", (username,)).fetchone()
            session_rows = conn.execute(
                """
                SELECT event_ts, event_type, client_id, ip_address, port, protocol_level,
                       clean_session, keep_alive, disconnect_kind, reason_code,
                       NULL AS topic, NULL AS qos, NULL AS payload_bytes, NULL AS retained
                FROM client_session_events
                WHERE username = ? AND event_ts >= ?
                ORDER BY event_ts DESC
                LIMIT ?
                """,
                (username, cutoff, limit),
            ).fetchall()
            topic_rows = conn.execute(
                """
                SELECT event_ts,
                       CASE event_type WHEN 'publish' THEN 'Publish' ELSE 'Subscribe' END AS event_type,
                       client_id, NULL AS ip_address, NULL AS port, NULL AS protocol_level,
                       NULL AS clean_session, NULL AS keep_alive, NULL AS disconnect_kind, NULL AS reason_code,
                       topic, qos, payload_bytes, retained
                FROM client_topic_events
                WHERE username = ? AND event_ts >= ?
                ORDER BY event_ts DESC
                LIMIT ?
                """,
                (username, cutoff, limit),
            ).fetchall()

        events = [dict(row) for row in session_rows] + [dict(row) for row in topic_rows]
        if normalized:
            events = [event for event in events if str(event["event_type"]).lower() in normalized]
        events.sort(key=lambda item: item["event_ts"], reverse=True)
        events = events[:limit]
        return {
            "client": dict(registry) if registry else None,
            "filters": {"days": days, "limit": limit, "event_types": sorted(normalized)},
            "timeline": events,
        }

    def get_client_incidents(self, days: int = 30, limit: int = 200, username: str | None = None,
                             incident_types: Sequence[str] | None = None, reconnect_window_minutes: int = 30,
                             reconnect_threshold: int = 3) -> dict[str, Any]:
        days = max(1, min(days, self._client_retention_days))
        limit = max(1, min(limit, 1000))
        reconnect_window_minutes = max(1, min(reconnect_window_minutes, 1440))
        reconnect_threshold = max(2, min(reconnect_threshold, 50))
        normalized = {value.strip().lower() for value in (incident_types or []) if value and value.strip()}
        if not normalized:
            normalized = {"ungraceful_disconnect", "auth_failure", "reconnect_loop"}
        cutoff = _iso_utc(_utc_now() - timedelta(days=days))
        where = ["event_ts >= ?"]
        params: list[Any] = [cutoff]
        if username:
            where.append("username = ?")
            params.append(username)
        where_sql = " AND ".join(where)

        with self._connect() as conn:
            session_rows = conn.execute(
                f"""
                SELECT username, client_id, event_ts, event_type, disconnect_kind, reason_code,
                       ip_address, port
                FROM client_session_events
                WHERE {where_sql}
                ORDER BY username ASC, event_ts ASC
                """,
                tuple(params),
            ).fetchall()

        incidents: list[dict[str, Any]] = []
        connects_by_user: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for row in session_rows:
            row_user = row["username"] or "(unknown)"
            if row["event_type"] == "Client Connection":
                connects_by_user[row_user].append(row)
            if row["event_type"] == "Client Disconnection" and row["disconnect_kind"] == "ungraceful" and "ungraceful_disconnect" in normalized:
                incidents.append(
                    {
                        "incident_type": "ungraceful_disconnect",
                        "username": row_user,
                        "client_id": row["client_id"],
                        "event_ts": row["event_ts"],
                        "details": {
                            "disconnect_kind": row["disconnect_kind"],
                            "reason_code": row["reason_code"],
                            "ip_address": row["ip_address"],
                            "port": row["port"],
                        },
                    }
                )
            if row["event_type"] == "Auth Failure" and "auth_failure" in normalized:
                incidents.append(
                    {
                        "incident_type": "auth_failure",
                        "username": row_user,
                        "client_id": row["client_id"],
                        "event_ts": row["event_ts"],
                        "details": {
                            "reason_code": row["reason_code"],
                            "ip_address": row["ip_address"],
                            "port": row["port"],
                        },
                    }
                )

        if "reconnect_loop" in normalized:
            reconnect_window = timedelta(minutes=reconnect_window_minutes)
            for row_user, rows in connects_by_user.items():
                cluster: list[sqlite3.Row] = []
                for row in rows:
                    ts = _parse_iso(row["event_ts"])
                    if ts is None:
                        continue
                    if not cluster:
                        cluster = [row]
                        continue
                    first_ts = _parse_iso(cluster[0]["event_ts"])
                    if first_ts is None:
                        cluster = [row]
                        continue
                    if ts - first_ts <= reconnect_window:
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

    def _build_reconnect_incident(self, username: str, rows: Sequence[sqlite3.Row]) -> dict[str, Any]:
        return {
            "incident_type": "reconnect_loop",
            "username": username,
            "client_id": rows[-1]["client_id"],
            "event_ts": rows[-1]["event_ts"],
            "details": {
                "attempts": len(rows),
                "start_ts": rows[0]["event_ts"],
                "end_ts": rows[-1]["event_ts"],
            },
        }

    def get_retention_status(self) -> dict[str, Any]:
        now = _utc_now()
        broker_raw_cutoff = _iso_utc(now - timedelta(days=self._broker_raw_retention_days))
        broker_daily_cutoff = (now - timedelta(days=self._broker_daily_retention_days)).date().isoformat()
        client_cutoff = _iso_utc(now - timedelta(days=self._client_retention_days))
        client_day_cutoff = (now - timedelta(days=self._client_retention_days)).date().isoformat()
        topic_cutoff = _iso_utc(now - timedelta(days=self._topic_retention_days))
        with self._connect() as conn:
            counts = {
                "broker_metric_ticks": self._count_older_than(conn, "broker_metric_ticks", "ts", broker_raw_cutoff),
                "broker_daily_summary": self._count_older_than(conn, "broker_daily_summary", "day", broker_daily_cutoff),
                "client_session_events": self._count_older_than(conn, "client_session_events", "event_ts", client_cutoff),
                "client_topic_events": self._count_older_than(conn, "client_topic_events", "event_ts", client_cutoff),
                "client_daily_summary": self._count_older_than(conn, "client_daily_summary", "day", client_day_cutoff),
                "client_daily_distinct_topics": self._count_older_than(conn, "client_daily_distinct_topics", "day", client_day_cutoff),
                "topic_publish_buckets": self._count_older_than(conn, "topic_publish_buckets", "bucket_start", topic_cutoff),
                "topic_subscribe_buckets": self._count_older_than(conn, "topic_subscribe_buckets", "bucket_start", topic_cutoff),
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
        now = _utc_now()
        broker_raw_cutoff = _iso_utc(now - timedelta(days=self._broker_raw_retention_days))
        broker_daily_cutoff = (now - timedelta(days=self._broker_daily_retention_days)).date().isoformat()
        client_cutoff = _iso_utc(now - timedelta(days=self._client_retention_days))
        client_day_cutoff = (now - timedelta(days=self._client_retention_days)).date().isoformat()
        topic_cutoff = _iso_utc(now - timedelta(days=self._topic_retention_days))
        with self._connect() as conn:
            self._delete_older_than(conn, "broker_metric_ticks", "ts", broker_raw_cutoff)
            self._delete_older_than(conn, "broker_daily_summary", "day", broker_daily_cutoff)
            self._delete_older_than(conn, "client_session_events", "event_ts", client_cutoff)
            self._delete_older_than(conn, "client_topic_events", "event_ts", client_cutoff)
            self._delete_older_than(conn, "client_daily_summary", "day", client_day_cutoff)
            self._delete_older_than(conn, "client_daily_distinct_topics", "day", client_day_cutoff)
            self._delete_older_than(conn, "topic_publish_buckets", "bucket_start", topic_cutoff)
            self._delete_older_than(conn, "topic_subscribe_buckets", "bucket_start", topic_cutoff)
            conn.commit()
        after = self.get_retention_status()
        return {
            "status": "purged",
            "deleted_rows": before["total_rows_past_retention"] - after["total_rows_past_retention"],
            "before": before,
            "after": after,
        }

    def _delete_older_than(self, conn: sqlite3.Connection, table: str, column: str, cutoff: str) -> None:
        try:
            conn.execute(f"DELETE FROM {table} WHERE {column} < ?", (cutoff,))
        except sqlite3.OperationalError:
            return

    def _count_older_than(self, conn: sqlite3.Connection, table: str, column: str, cutoff: str) -> int:
        try:
            row = conn.execute(
                f"SELECT COUNT(*) AS total FROM {table} WHERE {column} < ?",
                (cutoff,),
            ).fetchone()
            return int(row["total"] if row else 0)
        except sqlite3.OperationalError:
            return 0

    @staticmethod
    def to_csv_bytes(rows: Iterable[dict[str, Any]], fieldnames: Sequence[str]) -> bytes:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})
        return buffer.getvalue().encode("utf-8")


reporting_storage = SQLiteReportingStorage(settings.resolved_reporting_database_url)