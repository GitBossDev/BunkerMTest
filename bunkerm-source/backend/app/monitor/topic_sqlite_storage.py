from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from core.config import settings
from core.database_url import ensure_sqlite_url
from monitor.data_storage import PERIODS


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _bucket_start(value: datetime, minutes: int) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    bucket_minute = (value.minute // minutes) * minutes
    return value.replace(minute=bucket_minute, second=0, microsecond=0)


def _resolve_sqlite_target(database_url: str) -> tuple[str, bool]:
    ensure_sqlite_url(database_url, "HISTORY_DATABASE_URL")
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    target = database_url
    for prefix in prefixes:
        if database_url.startswith(prefix):
            target = database_url[len(prefix):]
            break
    if target == ":memory:":
        return ("file:bunkerm-topic-history?mode=memory&cache=shared", True)
    return (target, target.startswith("file:"))


class SQLiteTopicHistoryStorage:
    """Persistent publish/subscribe buckets for topology and subscription history."""

    def __init__(self, database_url: str, bucket_minutes: int = 3, retention_days: int = 30):
        self._db_target, self._use_uri = _resolve_sqlite_target(database_url)
        self._bucket_minutes = bucket_minutes
        self._retention_days = retention_days
        self._lock = threading.Lock()
        self._keeper_conn: sqlite3.Connection | None = None
        if self._use_uri and "mode=memory" in self._db_target:
            self._keeper_conn = sqlite3.connect(self._db_target, uri=True, check_same_thread=False)
        else:
            os.makedirs(os.path.dirname(self._db_target), exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_target, uri=self._use_uri, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS topic_registry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL DEFAULT 'user',
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_topic_registry_topic ON topic_registry(topic);

                CREATE TABLE IF NOT EXISTS topic_publish_buckets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bucket_start TEXT NOT NULL,
                    bucket_minutes INTEGER NOT NULL DEFAULT 3,
                    topic_id INTEGER NOT NULL,
                    publish_count INTEGER NOT NULL DEFAULT 0,
                    bytes_sum INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(bucket_start, bucket_minutes, topic_id)
                );
                CREATE INDEX IF NOT EXISTS idx_topic_publish_buckets_start ON topic_publish_buckets(bucket_start);
                CREATE INDEX IF NOT EXISTS idx_topic_publish_buckets_topic ON topic_publish_buckets(topic_id);

                CREATE TABLE IF NOT EXISTS topic_subscribe_buckets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bucket_start TEXT NOT NULL,
                    bucket_minutes INTEGER NOT NULL DEFAULT 3,
                    topic_id INTEGER NOT NULL,
                    subscribe_count INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(bucket_start, bucket_minutes, topic_id)
                );
                CREATE INDEX IF NOT EXISTS idx_topic_subscribe_buckets_start ON topic_subscribe_buckets(bucket_start);
                CREATE INDEX IF NOT EXISTS idx_topic_subscribe_buckets_topic ON topic_subscribe_buckets(topic_id);

                CREATE TABLE IF NOT EXISTS topic_message_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id INTEGER NOT NULL,
                    event_ts TEXT NOT NULL,
                    payload_text TEXT NOT NULL DEFAULT '',
                    payload_bytes INTEGER NOT NULL DEFAULT 0,
                    qos INTEGER NOT NULL DEFAULT 0,
                    retained INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_topic_message_events_topic_ts ON topic_message_events(topic_id, event_ts DESC);
                """
            )
            conn.commit()

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
        event_ts = event_ts or _utc_now()
        bucket = _bucket_start(event_ts, self._bucket_minutes)
        with self._lock:
            with self._connect() as conn:
                topic_id = self._ensure_topic_locked(conn, topic, event_ts)
                last_retained_row = conn.execute(
                    """
                    SELECT retained
                    FROM topic_message_events
                    WHERE topic_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (topic_id,),
                ).fetchone()
                last_retained = bool(last_retained_row["retained"]) if last_retained_row else False
                is_retained_clear = bool(retained) and max(0, payload_bytes) == 0 and not (payload_value or "")
                effective_retained = False if is_retained_clear else (bool(retained) or last_retained)
                conn.execute(
                    """
                    INSERT INTO topic_publish_buckets (bucket_start, bucket_minutes, topic_id, publish_count, bytes_sum)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(bucket_start, bucket_minutes, topic_id) DO UPDATE SET
                        publish_count = publish_count + 1,
                        bytes_sum = bytes_sum + excluded.bytes_sum
                    """,
                    (_iso_utc(bucket), self._bucket_minutes, topic_id, max(0, payload_bytes)),
                )
                conn.execute(
                    """
                    INSERT INTO topic_message_events (topic_id, event_ts, payload_text, payload_bytes, qos, retained)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        topic_id,
                        _iso_utc(event_ts),
                        payload_value or "",
                        max(0, payload_bytes),
                        max(0, min(2, int(qos))),
                        1 if effective_retained else 0,
                    ),
                )
                self._prune_locked(conn)
                conn.commit()

    def record_subscribe(self, topic: str, event_ts: datetime | None = None) -> None:
        if not topic or topic.startswith("$"):
            return
        event_ts = event_ts or _utc_now()
        bucket = _bucket_start(event_ts, self._bucket_minutes)
        with self._lock:
            with self._connect() as conn:
                topic_id = self._ensure_topic_locked(conn, topic, event_ts)
                conn.execute(
                    """
                    INSERT INTO topic_subscribe_buckets (bucket_start, bucket_minutes, topic_id, subscribe_count)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(bucket_start, bucket_minutes, topic_id) DO UPDATE SET
                        subscribe_count = subscribe_count + 1
                    """,
                    (_iso_utc(bucket), self._bucket_minutes, topic_id),
                )
                self._prune_locked(conn)
                conn.commit()

    def _ensure_topic_locked(self, conn: sqlite3.Connection, topic: str, event_ts: datetime) -> int:
        ts = _iso_utc(event_ts)
        kind = "system" if topic.startswith("$") else "user"
        row = conn.execute("SELECT id FROM topic_registry WHERE topic = ?", (topic,)).fetchone()
        if row:
            conn.execute("UPDATE topic_registry SET last_seen_at = ? WHERE id = ?", (ts, int(row["id"])))
            return int(row["id"])
        cursor = conn.execute(
            "INSERT INTO topic_registry (topic, kind, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?)",
            (topic, kind, ts, ts),
        )
        return int(cursor.lastrowid)

    def _prune_locked(self, conn: sqlite3.Connection) -> None:
        cutoff = _iso_utc(_utc_now() - timedelta(days=self._retention_days))
        conn.execute("DELETE FROM topic_publish_buckets WHERE bucket_start < ?", (cutoff,))
        conn.execute("DELETE FROM topic_subscribe_buckets WHERE bucket_start < ?", (cutoff,))
        conn.execute("DELETE FROM topic_message_events WHERE event_ts < ?", (cutoff,))

    def get_topic_messages(self, topic: str, limit: int = 120) -> Dict[str, Any]:
        topic = (topic or "").strip()
        if not topic:
            return {"topic": "", "history": [], "total": 0}

        clamped_limit = max(1, min(limit, 500))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT tme.id, tme.event_ts, tme.payload_text, tme.payload_bytes, tme.qos, tme.retained
                FROM topic_message_events tme
                JOIN topic_registry tr ON tr.id = tme.topic_id
                WHERE tr.topic = ?
                ORDER BY tme.event_ts DESC, tme.id DESC
                LIMIT ?
                """,
                (topic, clamped_limit),
            ).fetchall()

            total_row = conn.execute(
                """
                SELECT COUNT(tme.id) AS total
                FROM topic_message_events tme
                JOIN topic_registry tr ON tr.id = tme.topic_id
                WHERE tr.topic = ?
                """,
                (topic,),
            ).fetchone()

        history = [
            {
                "id": int(row["id"]),
                "topic": topic,
                "value": row["payload_text"] or "",
                "timestamp": row["event_ts"] or "",
                "payload_bytes": int(row["payload_bytes"] or 0),
                "qos": int(row["qos"] or 0),
                "retained": bool(row["retained"]),
                "kind": "message",
            }
            for row in rows
        ]
        return {
            "topic": topic,
            "history": history,
            "total": int(total_row["total"] if total_row else 0),
        }

    def get_latest_topics(self, limit: int = 5000) -> list[dict[str, Any]]:
        clamped_limit = max(1, min(limit, 10000))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT tr.topic,
                       tr.last_seen_at,
                       latest.payload_text,
                       latest.event_ts,
                       latest.qos,
                       latest.retained,
                       COALESCE(stats.message_count, 0) AS message_count
                FROM topic_registry tr
                LEFT JOIN (
                    SELECT tme.topic_id, tme.payload_text, tme.event_ts, tme.qos, tme.retained
                    FROM topic_message_events tme
                    JOIN (
                        SELECT topic_id, MAX(id) AS latest_id
                        FROM topic_message_events
                        GROUP BY topic_id
                    ) latest_idx
                      ON latest_idx.topic_id = tme.topic_id AND latest_idx.latest_id = tme.id
                ) latest ON latest.topic_id = tr.id
                LEFT JOIN (
                    SELECT topic_id, COUNT(*) AS message_count
                    FROM topic_message_events
                    GROUP BY topic_id
                ) stats ON stats.topic_id = tr.id
                WHERE tr.kind = 'user' AND COALESCE(stats.message_count, 0) > 0
                ORDER BY tr.topic ASC
                LIMIT ?
                """,
                (clamped_limit,),
            ).fetchall()

        return [
            {
                "topic": row["topic"],
                "value": row["payload_text"] or "",
                "timestamp": row["event_ts"] or row["last_seen_at"] or "",
                "count": int(row["message_count"] or 0),
                "retained": bool(row["retained"]) if row["retained"] is not None else False,
                "qos": int(row["qos"] or 0),
            }
            for row in rows
        ]

    def get_top_published(self, limit: int = 15, period: str = "7d") -> Dict[str, Any]:
        minutes = PERIODS.get(period, PERIODS["7d"])
        cutoff = _iso_utc(_utc_now() - timedelta(minutes=minutes))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT tr.topic, SUM(tpb.publish_count) AS count, MAX(tr.last_seen_at) AS last_seen_at
                FROM topic_publish_buckets tpb
                JOIN topic_registry tr ON tr.id = tpb.topic_id
                WHERE tpb.bucket_start >= ? AND tr.kind = 'user'
                GROUP BY tr.topic
                ORDER BY count DESC, tr.topic ASC
                LIMIT ?
                """,
                (cutoff, limit),
            ).fetchall()
            distinct_row = conn.execute(
                """
                SELECT COUNT(DISTINCT tr.topic) AS total
                FROM topic_publish_buckets tpb
                JOIN topic_registry tr ON tr.id = tpb.topic_id
                WHERE tpb.bucket_start >= ? AND tr.kind = 'user'
                """,
                (cutoff,),
            ).fetchone()
        return {
            "top_topics": [
                {
                    "topic": row["topic"],
                    "value": "",
                    "count": int(row["count"] or 0),
                    "retained": False,
                    "qos": 0,
                    "timestamp": row["last_seen_at"] or "",
                }
                for row in rows
            ],
            "total_distinct_topics": int(distinct_row["total"] if distinct_row else 0),
        }

    def get_top_subscribed(self, limit: int = 15, period: str = "7d") -> Dict[str, Any]:
        minutes = PERIODS.get(period, PERIODS["7d"])
        cutoff = _iso_utc(_utc_now() - timedelta(minutes=minutes))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT tr.topic, SUM(tsb.subscribe_count) AS count
                FROM topic_subscribe_buckets tsb
                JOIN topic_registry tr ON tr.id = tsb.topic_id
                WHERE tsb.bucket_start >= ? AND tr.kind = 'user'
                GROUP BY tr.topic
                ORDER BY count DESC, tr.topic ASC
                LIMIT ?
                """,
                (cutoff, limit),
            ).fetchall()
            distinct_row = conn.execute(
                """
                SELECT COUNT(DISTINCT tr.topic) AS total
                FROM topic_subscribe_buckets tsb
                JOIN topic_registry tr ON tr.id = tsb.topic_id
                WHERE tsb.bucket_start >= ? AND tr.kind = 'user'
                """,
                (cutoff,),
            ).fetchone()
        return {
            "top_subscribed": [{"topic": row["topic"], "count": int(row["count"] or 0)} for row in rows],
            "total_distinct_subscribed": int(distinct_row["total"] if distinct_row else 0),
        }


class _LazySQLiteTopicHistoryStorage:
    def __init__(self) -> None:
        self._storage: SQLiteTopicHistoryStorage | None = None

    def _get_storage(self) -> SQLiteTopicHistoryStorage:
        if self._storage is None:
            self._storage = SQLiteTopicHistoryStorage(settings.resolved_history_database_url)
        return self._storage

    def __getattr__(self, name: str):
        return getattr(self._get_storage(), name)


topic_history_storage = _LazySQLiteTopicHistoryStorage()