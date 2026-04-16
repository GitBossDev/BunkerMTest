from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

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
    ensure_sqlite_url(database_url, "HISTORY_DATABASE_URL")
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    target = database_url
    for prefix in prefixes:
        if database_url.startswith(prefix):
            target = database_url[len(prefix):]
            break
    if target == ":memory:":
        return ("file:bunkerm-client-activity?mode=memory&cache=shared", True)
    return (target, target.startswith("file:"))


class SQLiteClientActivityStorage:
    """Persistent 30-day client activity and registry storage."""

    def __init__(self, database_url: str, retention_days: int = 30):
        self._db_target, self._use_uri = _resolve_sqlite_target(database_url)
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
                CREATE TABLE IF NOT EXISTS client_registry (
                    username TEXT PRIMARY KEY,
                    textname TEXT,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    deleted_at TEXT,
                    last_dynsec_sync_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS client_session_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    client_id TEXT NOT NULL,
                    event_ts TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    disconnect_kind TEXT,
                    reason_code TEXT,
                    ip_address TEXT,
                    port INTEGER,
                    protocol_level TEXT,
                    clean_session INTEGER,
                    keep_alive INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_client_session_events_user_ts ON client_session_events(username, event_ts);
                CREATE TABLE IF NOT EXISTS client_topic_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    client_id TEXT NOT NULL,
                    event_ts TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    qos INTEGER,
                    payload_bytes INTEGER,
                    retained INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_client_topic_events_user_ts ON client_topic_events(username, event_ts);
                CREATE TABLE IF NOT EXISTS client_subscription_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    qos INTEGER,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    source TEXT NOT NULL DEFAULT 'clientlogs',
                    UNIQUE(username, topic)
                );
                CREATE TABLE IF NOT EXISTS client_daily_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    day TEXT NOT NULL,
                    connects INTEGER NOT NULL DEFAULT 0,
                    disconnects_graceful INTEGER NOT NULL DEFAULT 0,
                    disconnects_ungraceful INTEGER NOT NULL DEFAULT 0,
                    auth_failures INTEGER NOT NULL DEFAULT 0,
                    publishes INTEGER NOT NULL DEFAULT 0,
                    subscribes INTEGER NOT NULL DEFAULT 0,
                    distinct_publish_topics INTEGER NOT NULL DEFAULT 0,
                    distinct_subscribe_topics INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(username, day)
                );
                CREATE TABLE IF NOT EXISTS client_daily_distinct_topics (
                    username TEXT NOT NULL,
                    day TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    PRIMARY KEY(username, day, event_type, topic)
                );
                """
            )
            conn.commit()

    def upsert_client(self, username: str, textname: str | None = None, disabled: bool = False) -> None:
        if not username:
            return
        now = _iso_utc(_utc_now())
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT created_at FROM client_registry WHERE username = ?", (username,)).fetchone()
                created_at = row["created_at"] if row else now
                conn.execute(
                    """
                    INSERT INTO client_registry (username, textname, disabled, created_at, deleted_at, last_dynsec_sync_at)
                    VALUES (?, ?, ?, ?, NULL, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        textname = excluded.textname,
                        disabled = excluded.disabled,
                        deleted_at = NULL,
                        last_dynsec_sync_at = excluded.last_dynsec_sync_at
                    """,
                    (username, textname, int(disabled), created_at, now),
                )
                conn.commit()

    def mark_client_deleted(self, username: str) -> None:
        if not username:
            return
        now = _iso_utc(_utc_now())
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE client_registry SET deleted_at = ?, last_dynsec_sync_at = ? WHERE username = ?",
                    (now, now, username),
                )
                conn.commit()

    def reconcile_dynsec_clients(self, clients: list[dict[str, Any]]) -> None:
        seen: set[str] = set()
        with self._lock:
            with self._connect() as conn:
                now = _iso_utc(_utc_now())
                for client in clients or []:
                    username = client.get("username")
                    if not isinstance(username, str) or not username:
                        continue
                    seen.add(username)
                    row = conn.execute("SELECT created_at FROM client_registry WHERE username = ?", (username,)).fetchone()
                    created_at = row["created_at"] if row else now
                    conn.execute(
                        """
                        INSERT INTO client_registry (username, textname, disabled, created_at, deleted_at, last_dynsec_sync_at)
                        VALUES (?, ?, ?, ?, NULL, ?)
                        ON CONFLICT(username) DO UPDATE SET
                            textname = excluded.textname,
                            disabled = excluded.disabled,
                            deleted_at = NULL,
                            last_dynsec_sync_at = excluded.last_dynsec_sync_at
                        """,
                        (username, client.get("textname"), int(bool(client.get("disabled", False))), created_at, now),
                    )
                if seen:
                    placeholders = ",".join("?" for _ in seen)
                    conn.execute(
                        f"UPDATE client_registry SET deleted_at = ?, last_dynsec_sync_at = ? WHERE username NOT IN ({placeholders}) AND deleted_at IS NULL",
                        (now, now, *sorted(seen)),
                    )
                conn.commit()

    def record_event(self, event: Any) -> None:
        event_ts = _parse_iso(getattr(event, "timestamp", None)) or _utc_now()
        username = getattr(event, "username", None)
        client_id = getattr(event, "client_id", "")
        event_type = getattr(event, "event_type", "")
        if username and username not in ("unknown", "(broker-observed)"):
            self.upsert_client(username)

        with self._lock:
            with self._connect() as conn:
                day = event_ts.date().isoformat()
                if event_type in ("Client Connection", "Client Disconnection", "Auth Failure"):
                    disconnect_kind = getattr(event, "disconnect_kind", None)
                    reason_code = getattr(event, "reason_code", None)
                    conn.execute(
                        """
                        INSERT INTO client_session_events (
                            username, client_id, event_ts, event_type, disconnect_kind, reason_code,
                            ip_address, port, protocol_level, clean_session, keep_alive
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            username,
                            client_id,
                            _iso_utc(event_ts),
                            event_type,
                            disconnect_kind,
                            reason_code,
                            getattr(event, "ip_address", None),
                            getattr(event, "port", None),
                            getattr(event, "protocol_level", None),
                            int(bool(getattr(event, "clean_session", False))) if getattr(event, "clean_session", None) is not None else None,
                            getattr(event, "keep_alive", None),
                        ),
                    )
                    self._upsert_daily_summary_locked(conn, username, day, event_type, disconnect_kind)

                if event_type in ("Subscribe", "Publish") and getattr(event, "topic", None):
                    conn.execute(
                        """
                        INSERT INTO client_topic_events (
                            username, client_id, event_ts, event_type, topic, qos, payload_bytes, retained
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            username,
                            client_id,
                            _iso_utc(event_ts),
                            event_type.lower(),
                            getattr(event, "topic", None),
                            getattr(event, "qos", None),
                            getattr(event, "payload_bytes", None),
                            int(bool(getattr(event, "retained", False))) if getattr(event, "retained", None) is not None else None,
                        ),
                    )
                    if username:
                        self._upsert_subscription_state_locked(conn, username, event)
                        self._upsert_daily_summary_locked(conn, username, day, event_type, None, topic=getattr(event, "topic", None))

                self._prune_locked(conn)
                conn.commit()

    def _upsert_subscription_state_locked(self, conn: sqlite3.Connection, username: str, event: Any) -> None:
        if getattr(event, "event_type", "") != "Subscribe":
            return
        topic = getattr(event, "topic", None)
        if not topic:
            return
        ts = getattr(event, "timestamp", None) or _iso_utc(_utc_now())
        conn.execute(
            """
            INSERT INTO client_subscription_state (username, topic, qos, first_seen_at, last_seen_at, is_active, source)
            VALUES (?, ?, ?, ?, ?, 1, 'clientlogs')
            ON CONFLICT(username, topic) DO UPDATE SET
                qos = excluded.qos,
                last_seen_at = excluded.last_seen_at,
                is_active = 1,
                source = excluded.source
            """,
            (username, topic, getattr(event, "qos", None), ts, ts),
        )

    def _upsert_daily_summary_locked(self, conn: sqlite3.Connection, username: str | None, day: str, event_type: str, disconnect_kind: str | None, topic: str | None = None) -> None:
        if not username:
            return
        row = conn.execute(
            "SELECT id FROM client_daily_summary WHERE username = ? AND day = ?",
            (username, day),
        ).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO client_daily_summary (
                    username, day, connects, disconnects_graceful, disconnects_ungraceful,
                    auth_failures, publishes, subscribes, distinct_publish_topics, distinct_subscribe_topics
                ) VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, 0)
                """,
                (username, day),
            )

        update_sql = None
        if event_type == "Client Connection":
            update_sql = "UPDATE client_daily_summary SET connects = connects + 1 WHERE username = ? AND day = ?"
            conn.execute(update_sql, (username, day))
        elif event_type == "Client Disconnection":
            column = "disconnects_graceful" if disconnect_kind == "graceful" else "disconnects_ungraceful"
            conn.execute(f"UPDATE client_daily_summary SET {column} = {column} + 1 WHERE username = ? AND day = ?", (username, day))
        elif event_type == "Auth Failure":
            conn.execute("UPDATE client_daily_summary SET auth_failures = auth_failures + 1 WHERE username = ? AND day = ?", (username, day))
        elif event_type == "Publish":
            conn.execute("UPDATE client_daily_summary SET publishes = publishes + 1 WHERE username = ? AND day = ?", (username, day))
            self._track_distinct_topic_locked(conn, username, day, "publish", topic)
        elif event_type == "Subscribe":
            conn.execute("UPDATE client_daily_summary SET subscribes = subscribes + 1 WHERE username = ? AND day = ?", (username, day))
            self._track_distinct_topic_locked(conn, username, day, "subscribe", topic)

    def _track_distinct_topic_locked(self, conn: sqlite3.Connection, username: str, day: str, event_type: str, topic: str | None) -> None:
        if not topic:
            return
        existing = conn.execute(
            "SELECT 1 FROM client_daily_distinct_topics WHERE username = ? AND day = ? AND event_type = ? AND topic = ?",
            (username, day, event_type, topic),
        ).fetchone()
        if existing:
            return
        conn.execute(
            "INSERT INTO client_daily_distinct_topics (username, day, event_type, topic) VALUES (?, ?, ?, ?)",
            (username, day, event_type, topic),
        )
        column = "distinct_publish_topics" if event_type == "publish" else "distinct_subscribe_topics"
        conn.execute(f"UPDATE client_daily_summary SET {column} = {column} + 1 WHERE username = ? AND day = ?", (username, day))

    def _prune_locked(self, conn: sqlite3.Connection) -> None:
        cutoff = _iso_utc(_utc_now() - timedelta(days=self._retention_days))
        cutoff_day = (_utc_now() - timedelta(days=self._retention_days)).date().isoformat()
        conn.execute("DELETE FROM client_session_events WHERE event_ts < ?", (cutoff,))
        conn.execute("DELETE FROM client_topic_events WHERE event_ts < ?", (cutoff,))
        conn.execute("DELETE FROM client_daily_distinct_topics WHERE day < ?", (cutoff_day,))
        conn.execute("DELETE FROM client_daily_summary WHERE day < ?", (cutoff_day,))

    def get_client_activity(self, username: str, days: int = 30, limit: int = 200) -> Dict[str, Any]:
        days = max(1, min(days, self._retention_days))
        limit = max(1, min(limit, 1000))
        cutoff = _iso_utc(_utc_now() - timedelta(days=days))
        cutoff_day = (_utc_now() - timedelta(days=days)).date().isoformat()
        with self._connect() as conn:
            registry = conn.execute("SELECT * FROM client_registry WHERE username = ?", (username,)).fetchone()
            session_rows = conn.execute(
                "SELECT * FROM client_session_events WHERE username = ? AND event_ts >= ? ORDER BY event_ts DESC LIMIT ?",
                (username, cutoff, limit),
            ).fetchall()
            topic_rows = conn.execute(
                "SELECT * FROM client_topic_events WHERE username = ? AND event_ts >= ? ORDER BY event_ts DESC LIMIT ?",
                (username, cutoff, limit),
            ).fetchall()
            subs_rows = conn.execute(
                "SELECT topic, qos, first_seen_at, last_seen_at, is_active, source FROM client_subscription_state WHERE username = ? ORDER BY topic ASC",
                (username,),
            ).fetchall()
            summary_rows = conn.execute(
                "SELECT * FROM client_daily_summary WHERE username = ? AND day >= ? ORDER BY day DESC",
                (username, cutoff_day),
            ).fetchall()
        return {
            "client": dict(registry) if registry else None,
            "session_events": [dict(row) for row in session_rows],
            "topic_events": [dict(row) for row in topic_rows],
            "subscriptions": [dict(row) for row in subs_rows],
            "daily_summary": [dict(row) for row in summary_rows],
        }


class _LazySQLiteClientActivityStorage:
    def __init__(self) -> None:
        self._storage: SQLiteClientActivityStorage | None = None

    def _get_storage(self) -> SQLiteClientActivityStorage:
        if self._storage is None:
            self._storage = SQLiteClientActivityStorage(settings.resolved_history_database_url)
        return self._storage

    def __getattr__(self, name: str):
        return getattr(self._get_storage(), name)


client_activity_storage = _LazySQLiteClientActivityStorage()