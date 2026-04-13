from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from monitor.data_storage import PERIODS


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso_utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


def _resolve_sqlite_target(database_url: str) -> tuple[str, bool]:
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    target = database_url
    for prefix in prefixes:
        if database_url.startswith(prefix):
            target = database_url[len(prefix):]
            break
    if target == ":memory:":
        return ("file:bunkerm-monitor-history?mode=memory&cache=shared", True)
    return (target, target.startswith("file:"))


@dataclass(slots=True)
class BrokerTickSnapshot:
    ts: datetime
    bytes_received_rate: float
    bytes_sent_rate: float
    messages_received_delta: int
    messages_sent_delta: int
    connected_clients: int
    disconnected_clients: int
    active_sessions: int
    max_concurrent: int
    total_subscriptions: int
    retained_messages: int
    messages_inflight: int
    latency_ms: float
    broker_uptime: str
    messages_received_total: int
    messages_sent_total: int
    cpu_pct: float | None = None
    memory_bytes: int | None = None
    memory_pct: float | None = None


class SQLiteMonitorHistoryStorage:
    """Phase-1 broker history storage backed by SQLite."""

    def __init__(self, database_url: str, legacy_json_path: str | None = None):
        self._db_target, self._use_uri = _resolve_sqlite_target(database_url)
        self._legacy_json_path = legacy_json_path
        self._lock = threading.Lock()
        self._keeper_conn: sqlite3.Connection | None = None
        if self._use_uri and "mode=memory" in self._db_target:
            self._keeper_conn = sqlite3.connect(self._db_target, uri=True, check_same_thread=False)
        else:
            os.makedirs(os.path.dirname(self._db_target), exist_ok=True)
        self._ensure_schema()
        self._bootstrap_from_legacy_json()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_target, uri=self._use_uri, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS broker_metric_ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL UNIQUE,
                    bytes_received_rate REAL NOT NULL DEFAULT 0,
                    bytes_sent_rate REAL NOT NULL DEFAULT 0,
                    messages_received_delta INTEGER NOT NULL DEFAULT 0,
                    messages_sent_delta INTEGER NOT NULL DEFAULT 0,
                    connected_clients INTEGER NOT NULL DEFAULT 0,
                    disconnected_clients INTEGER NOT NULL DEFAULT 0,
                    active_sessions INTEGER NOT NULL DEFAULT 0,
                    max_concurrent INTEGER NOT NULL DEFAULT 0,
                    total_subscriptions INTEGER NOT NULL DEFAULT 0,
                    retained_messages INTEGER NOT NULL DEFAULT 0,
                    messages_inflight INTEGER NOT NULL DEFAULT 0,
                    latency_ms REAL NOT NULL DEFAULT -1,
                    cpu_pct REAL,
                    memory_bytes INTEGER,
                    memory_pct REAL
                );
                CREATE INDEX IF NOT EXISTS idx_broker_metric_ticks_ts ON broker_metric_ticks(ts);

                CREATE TABLE IF NOT EXISTS broker_runtime_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_tick_ts TEXT,
                    last_broker_uptime TEXT,
                    current_max_concurrent INTEGER NOT NULL DEFAULT 0,
                    lifetime_max_concurrent INTEGER NOT NULL DEFAULT 0,
                    last_messages_received_total INTEGER NOT NULL DEFAULT 0,
                    last_messages_sent_total INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS broker_daily_summary (
                    day TEXT PRIMARY KEY,
                    peak_connected_clients INTEGER NOT NULL DEFAULT 0,
                    peak_active_sessions INTEGER NOT NULL DEFAULT 0,
                    peak_max_concurrent INTEGER NOT NULL DEFAULT 0,
                    total_messages_received INTEGER NOT NULL DEFAULT 0,
                    total_messages_sent INTEGER NOT NULL DEFAULT 0,
                    bytes_received_rate_sum REAL NOT NULL DEFAULT 0,
                    bytes_sent_rate_sum REAL NOT NULL DEFAULT 0,
                    latency_samples INTEGER NOT NULL DEFAULT 0,
                    latency_sum REAL NOT NULL DEFAULT 0
                );
                """
            )
            conn.commit()

    def _bootstrap_from_legacy_json(self) -> None:
        if not self._legacy_json_path or not os.path.exists(self._legacy_json_path):
            return
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM broker_metric_ticks").fetchone()
            if row and row["count"]:
                return
        try:
            with open(self._legacy_json_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            return

        bytes_ticks = {entry.get("ts"): entry for entry in data.get("bytes_ticks", []) if entry.get("ts")}
        msg_ticks = {entry.get("ts"): entry for entry in data.get("msg_ticks", []) if entry.get("ts")}
        merged_ts = sorted(set(bytes_ticks.keys()) | set(msg_ticks.keys()))
        if not merged_ts:
            return

        with self._lock:
            with self._connect() as conn:
                for ts in merged_ts:
                    bt = bytes_ticks.get(ts, {})
                    mt = msg_ticks.get(ts, {})
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO broker_metric_ticks (
                            ts, bytes_received_rate, bytes_sent_rate,
                            messages_received_delta, messages_sent_delta
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            ts,
                            float(bt.get("rx", 0.0) or 0.0),
                            float(bt.get("tx", 0.0) or 0.0),
                            int(mt.get("rx", 0) or 0),
                            int(mt.get("tx", 0) or 0),
                        ),
                    )
                conn.commit()

    def get_last_tick_time(self) -> datetime | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT ts FROM broker_metric_ticks ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        try:
            return _parse_iso_utc(row["ts"])
        except Exception:
            return None

    def add_tick_snapshot(self, snapshot: BrokerTickSnapshot) -> None:
        ts_iso = _iso_utc(snapshot.ts)
        day = snapshot.ts.astimezone(timezone.utc).date().isoformat()
        latency_value = snapshot.latency_ms if snapshot.latency_ms >= 0 else 0.0
        latency_samples = 1 if snapshot.latency_ms >= 0 else 0

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO broker_metric_ticks (
                        ts, bytes_received_rate, bytes_sent_rate,
                        messages_received_delta, messages_sent_delta,
                        connected_clients, disconnected_clients, active_sessions,
                        max_concurrent, total_subscriptions, retained_messages,
                        messages_inflight, latency_ms, cpu_pct, memory_bytes, memory_pct
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ts_iso,
                        snapshot.bytes_received_rate,
                        snapshot.bytes_sent_rate,
                        snapshot.messages_received_delta,
                        snapshot.messages_sent_delta,
                        snapshot.connected_clients,
                        snapshot.disconnected_clients,
                        snapshot.active_sessions,
                        snapshot.max_concurrent,
                        snapshot.total_subscriptions,
                        snapshot.retained_messages,
                        snapshot.messages_inflight,
                        snapshot.latency_ms,
                        snapshot.cpu_pct,
                        snapshot.memory_bytes,
                        snapshot.memory_pct,
                    ),
                )

                current_row = conn.execute(
                    "SELECT last_broker_uptime, current_max_concurrent, lifetime_max_concurrent FROM broker_runtime_state WHERE id = 1"
                ).fetchone()
                current_max = snapshot.max_concurrent
                lifetime_max = snapshot.max_concurrent
                if current_row:
                    current_max = max(int(current_row["current_max_concurrent"]), snapshot.max_concurrent)
                    lifetime_max = max(int(current_row["lifetime_max_concurrent"]), snapshot.max_concurrent)

                conn.execute(
                    """
                    INSERT INTO broker_runtime_state (
                        id, last_tick_ts, last_broker_uptime,
                        current_max_concurrent, lifetime_max_concurrent,
                        last_messages_received_total, last_messages_sent_total
                    ) VALUES (1, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        last_tick_ts = excluded.last_tick_ts,
                        last_broker_uptime = excluded.last_broker_uptime,
                        current_max_concurrent = excluded.current_max_concurrent,
                        lifetime_max_concurrent = excluded.lifetime_max_concurrent,
                        last_messages_received_total = excluded.last_messages_received_total,
                        last_messages_sent_total = excluded.last_messages_sent_total
                    """,
                    (
                        ts_iso,
                        snapshot.broker_uptime,
                        self._compute_current_max(current_row, snapshot),
                        lifetime_max,
                        snapshot.messages_received_total,
                        snapshot.messages_sent_total,
                    ),
                )

                conn.execute(
                    """
                    INSERT INTO broker_daily_summary (
                        day, peak_connected_clients, peak_active_sessions, peak_max_concurrent,
                        total_messages_received, total_messages_sent,
                        bytes_received_rate_sum, bytes_sent_rate_sum,
                        latency_samples, latency_sum
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(day) DO UPDATE SET
                        peak_connected_clients = MAX(peak_connected_clients, excluded.peak_connected_clients),
                        peak_active_sessions = MAX(peak_active_sessions, excluded.peak_active_sessions),
                        peak_max_concurrent = MAX(peak_max_concurrent, excluded.peak_max_concurrent),
                        total_messages_received = total_messages_received + excluded.total_messages_received,
                        total_messages_sent = total_messages_sent + excluded.total_messages_sent,
                        bytes_received_rate_sum = bytes_received_rate_sum + excluded.bytes_received_rate_sum,
                        bytes_sent_rate_sum = bytes_sent_rate_sum + excluded.bytes_sent_rate_sum,
                        latency_samples = latency_samples + excluded.latency_samples,
                        latency_sum = latency_sum + excluded.latency_sum
                    """,
                    (
                        day,
                        snapshot.connected_clients,
                        snapshot.active_sessions,
                        snapshot.max_concurrent,
                        snapshot.messages_received_delta,
                        snapshot.messages_sent_delta,
                        snapshot.bytes_received_rate,
                        snapshot.bytes_sent_rate,
                        latency_samples,
                        latency_value,
                    ),
                )

                self._prune_locked(conn)
                conn.commit()

    def _compute_current_max(self, current_row: sqlite3.Row | None, snapshot: BrokerTickSnapshot) -> int:
        if not current_row:
            return snapshot.max_concurrent
        previous_uptime = current_row["last_broker_uptime"]
        if self._looks_like_broker_restart(previous_uptime, snapshot.broker_uptime):
            return snapshot.max_concurrent
        return max(int(current_row["current_max_concurrent"]), snapshot.max_concurrent)

    def _looks_like_broker_restart(self, previous_uptime: Any, current_uptime: str) -> bool:
        prev_seconds = self._parse_uptime_seconds(previous_uptime)
        curr_seconds = self._parse_uptime_seconds(current_uptime)
        if prev_seconds is None or curr_seconds is None:
            return False
        return curr_seconds < prev_seconds

    @staticmethod
    def _parse_uptime_seconds(raw: Any) -> int | None:
        if not isinstance(raw, str):
            return None
        parts = raw.strip().split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].startswith("second"):
            return int(parts[0])
        return None

    def prune_old_data(self, raw_retention_days: int = 30, daily_retention_days: int = 365) -> None:
        with self._lock:
            with self._connect() as conn:
                self._prune_locked(conn, raw_retention_days=raw_retention_days, daily_retention_days=daily_retention_days)
                conn.commit()

    def _prune_locked(self, conn: sqlite3.Connection, raw_retention_days: int = 30, daily_retention_days: int = 365) -> None:
        raw_cutoff = _iso_utc(_utc_now() - timedelta(days=raw_retention_days))
        daily_cutoff = (_utc_now() - timedelta(days=daily_retention_days)).date().isoformat()
        conn.execute("DELETE FROM broker_metric_ticks WHERE ts < ?", (raw_cutoff,))
        conn.execute("DELETE FROM broker_daily_summary WHERE day < ?", (daily_cutoff,))

    def get_bytes_for_period(self, period: str) -> Dict[str, list]:
        minutes = PERIODS.get(period, 60)
        cutoff = _iso_utc(_utc_now() - timedelta(minutes=minutes))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ts, bytes_received_rate, bytes_sent_rate
                FROM broker_metric_ticks
                WHERE ts >= ?
                ORDER BY ts ASC
                """,
                (cutoff,),
            ).fetchall()
        return {
            "timestamps": [row["ts"] for row in rows],
            "bytes_received": [row["bytes_received_rate"] for row in rows],
            "bytes_sent": [row["bytes_sent_rate"] for row in rows],
        }

    def get_messages_for_period(self, period: str) -> Dict[str, list]:
        minutes = PERIODS.get(period, 60)
        cutoff = _iso_utc(_utc_now() - timedelta(minutes=minutes))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ts, messages_received_delta, messages_sent_delta
                FROM broker_metric_ticks
                WHERE ts >= ?
                ORDER BY ts ASC
                """,
                (cutoff,),
            ).fetchall()
        return {
            "timestamps": [row["ts"] for row in rows],
            "msg_received": [row["messages_received_delta"] for row in rows],
            "msg_sent": [row["messages_sent_delta"] for row in rows],
        }

    def get_hourly_data(self) -> Dict[str, list]:
        return self.get_bytes_for_period("1d")

    def get_runtime_state(self) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM broker_runtime_state WHERE id = 1"
            ).fetchone()
        return dict(row) if row else {}

    def get_total_message_count(self, days: int = 7) -> int:
        cutoff = (_utc_now() - timedelta(days=days)).date().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(total_messages_received), 0) AS total FROM broker_daily_summary WHERE day >= ?",
                (cutoff,),
            ).fetchone()
        return int(row["total"] if row else 0)

    def get_daily_message_stats(self, days: int = 7, pending_today: int = 0) -> Dict[str, list]:
        cutoff = (_utc_now() - timedelta(days=days)).date().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT day, total_messages_received
                FROM broker_daily_summary
                WHERE day >= ?
                ORDER BY day ASC
                """,
                (cutoff,),
            ).fetchall()

        counts_by_day = {row["day"]: int(row["total_messages_received"]) for row in rows}
        today = _utc_now().date().isoformat()
        if pending_today > 0:
            counts_by_day[today] = counts_by_day.get(today, 0) + pending_today

        days_sorted = sorted(counts_by_day.keys())
        return {
            "dates": days_sorted,
            "counts": [counts_by_day[day] for day in days_sorted],
        }

    def get_daily_summary(self, days: int = 7) -> Dict[str, list[Dict[str, Any]]]:
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
        summary = []
        for row in rows:
            latency_samples = int(row["latency_samples"])
            avg_latency = round(float(row["latency_sum"]) / latency_samples, 2) if latency_samples > 0 else None
            summary.append(
                {
                    "day": row["day"],
                    "peak_connected_clients": int(row["peak_connected_clients"]),
                    "peak_active_sessions": int(row["peak_active_sessions"]),
                    "peak_max_concurrent": int(row["peak_max_concurrent"]),
                    "total_messages_received": int(row["total_messages_received"]),
                    "total_messages_sent": int(row["total_messages_sent"]),
                    "bytes_received_rate_sum": float(row["bytes_received_rate_sum"]),
                    "bytes_sent_rate_sum": float(row["bytes_sent_rate_sum"]),
                    "latency_samples": latency_samples,
                    "avg_latency_ms": avg_latency,
                }
            )
        return {"days": summary}