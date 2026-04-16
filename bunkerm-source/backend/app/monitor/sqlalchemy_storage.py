from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.database_url import is_sqlite_url
from core.sync_database import create_sync_engine_for_url, ensure_tables, iso_utc, normalize_datetime, session_scope, utc_now
from models.orm import BrokerDailySummary, BrokerMetricTick, BrokerRuntimeState
from monitor.data_storage import PERIODS


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


class SQLAlchemyMonitorHistoryStorage:
    """Broker history storage backed by SQLAlchemy-compatible databases."""

    def __init__(self, database_url: str, legacy_json_path: str | None = None):
        self._legacy_json_path = legacy_json_path
        self._lock = threading.Lock()
        self._engine = create_sync_engine_for_url(database_url)
        if is_sqlite_url(database_url):
            ensure_tables(
                self._engine,
                [
                    BrokerMetricTick.__table__,
                    BrokerRuntimeState.__table__,
                    BrokerDailySummary.__table__,
                ],
            )
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._bootstrap_from_legacy_json()

    def _bootstrap_from_legacy_json(self) -> None:
        if not self._legacy_json_path or not os.path.exists(self._legacy_json_path):
            return
        with self._session_factory() as session:
            existing = session.scalar(select(func.count()).select_from(BrokerMetricTick))
        if existing:
            return
        try:
            with open(self._legacy_json_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return

        bytes_ticks = {entry.get("ts"): entry for entry in data.get("bytes_ticks", []) if entry.get("ts")}
        msg_ticks = {entry.get("ts"): entry for entry in data.get("msg_ticks", []) if entry.get("ts")}
        for ts in sorted(set(bytes_ticks.keys()) | set(msg_ticks.keys())):
            try:
                tick_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            bt = bytes_ticks.get(ts, {})
            mt = msg_ticks.get(ts, {})
            self.add_tick_snapshot(
                BrokerTickSnapshot(
                    ts=tick_ts,
                    bytes_received_rate=float(bt.get("rx", 0.0) or 0.0),
                    bytes_sent_rate=float(bt.get("tx", 0.0) or 0.0),
                    messages_received_delta=int(mt.get("rx", 0) or 0),
                    messages_sent_delta=int(mt.get("tx", 0) or 0),
                    connected_clients=0,
                    disconnected_clients=0,
                    active_sessions=0,
                    max_concurrent=0,
                    total_subscriptions=0,
                    retained_messages=0,
                    messages_inflight=0,
                    latency_ms=-1.0,
                    broker_uptime="",
                    messages_received_total=0,
                    messages_sent_total=0,
                )
            )

    def get_last_tick_time(self) -> datetime | None:
        with self._session_factory() as session:
            row = session.scalar(select(BrokerMetricTick).order_by(BrokerMetricTick.ts.desc()).limit(1))
        if row is None:
            return None
        return row.ts.replace(tzinfo=timezone.utc) if row.ts.tzinfo is None else row.ts.astimezone(timezone.utc)

    def add_tick_snapshot(self, snapshot: BrokerTickSnapshot) -> None:
        tick_ts = normalize_datetime(snapshot.ts)
        day = tick_ts.date()
        latency_value = snapshot.latency_ms if snapshot.latency_ms >= 0 else 0.0
        latency_samples = 1 if snapshot.latency_ms >= 0 else 0

        with self._lock:
            with session_scope(self._session_factory) as session:
                tick = session.scalar(select(BrokerMetricTick).where(BrokerMetricTick.ts == tick_ts))
                if tick is None:
                    tick = BrokerMetricTick(ts=tick_ts)
                    session.add(tick)
                tick.bytes_received_rate = snapshot.bytes_received_rate
                tick.bytes_sent_rate = snapshot.bytes_sent_rate
                tick.messages_received_delta = snapshot.messages_received_delta
                tick.messages_sent_delta = snapshot.messages_sent_delta
                tick.connected_clients = snapshot.connected_clients
                tick.disconnected_clients = snapshot.disconnected_clients
                tick.active_sessions = snapshot.active_sessions
                tick.max_concurrent = snapshot.max_concurrent
                tick.total_subscriptions = snapshot.total_subscriptions
                tick.retained_messages = snapshot.retained_messages
                tick.messages_inflight = snapshot.messages_inflight
                tick.latency_ms = snapshot.latency_ms
                tick.cpu_pct = snapshot.cpu_pct
                tick.memory_bytes = snapshot.memory_bytes
                tick.memory_pct = snapshot.memory_pct

                runtime = session.get(BrokerRuntimeState, 1)
                previous_runtime = runtime
                if runtime is None:
                    runtime = BrokerRuntimeState(id=1)
                    session.add(runtime)
                current_max = self._compute_current_max(previous_runtime, snapshot)
                lifetime_max = max(snapshot.max_concurrent, int((previous_runtime.lifetime_max_concurrent if previous_runtime else 0) or 0))
                runtime.last_tick_ts = tick_ts
                runtime.last_broker_uptime = snapshot.broker_uptime
                runtime.current_max_concurrent = current_max
                runtime.lifetime_max_concurrent = lifetime_max
                runtime.last_messages_received_total = snapshot.messages_received_total
                runtime.last_messages_sent_total = snapshot.messages_sent_total

                summary = session.get(BrokerDailySummary, day)
                if summary is None:
                    summary = BrokerDailySummary(
                        day=day,
                        peak_connected_clients=0,
                        peak_active_sessions=0,
                        peak_max_concurrent=0,
                        total_messages_received=0,
                        total_messages_sent=0,
                        bytes_received_rate_sum=0.0,
                        bytes_sent_rate_sum=0.0,
                        latency_samples=0,
                        latency_sum=0.0,
                    )
                    session.add(summary)
                summary.peak_connected_clients = max(summary.peak_connected_clients, snapshot.connected_clients)
                summary.peak_active_sessions = max(summary.peak_active_sessions, snapshot.active_sessions)
                summary.peak_max_concurrent = max(summary.peak_max_concurrent, snapshot.max_concurrent)
                summary.total_messages_received += snapshot.messages_received_delta
                summary.total_messages_sent += snapshot.messages_sent_delta
                summary.bytes_received_rate_sum += snapshot.bytes_received_rate
                summary.bytes_sent_rate_sum += snapshot.bytes_sent_rate
                summary.latency_samples += latency_samples
                summary.latency_sum += latency_value

                self._prune_locked(session)

    def _compute_current_max(self, runtime: BrokerRuntimeState | None, snapshot: BrokerTickSnapshot) -> int:
        if runtime is None:
            return snapshot.max_concurrent
        if self._looks_like_broker_restart(runtime.last_broker_uptime, snapshot.broker_uptime):
            return snapshot.max_concurrent
        return max(int(runtime.current_max_concurrent or 0), snapshot.max_concurrent)

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
            with session_scope(self._session_factory) as session:
                self._prune_locked(session, raw_retention_days=raw_retention_days, daily_retention_days=daily_retention_days)

    def _prune_locked(self, session: Session, raw_retention_days: int = 30, daily_retention_days: int = 365) -> None:
        raw_cutoff = normalize_datetime(utc_now() - timedelta(days=raw_retention_days))
        daily_cutoff = (utc_now() - timedelta(days=daily_retention_days)).date()
        session.execute(delete(BrokerMetricTick).where(BrokerMetricTick.ts < raw_cutoff))
        session.execute(delete(BrokerDailySummary).where(BrokerDailySummary.day < daily_cutoff))

    def get_bytes_for_period(self, period: str) -> Dict[str, list]:
        minutes = PERIODS.get(period, 60)
        cutoff = normalize_datetime(utc_now() - timedelta(minutes=minutes))
        with self._session_factory() as session:
            rows = session.scalars(
                select(BrokerMetricTick)
                .where(BrokerMetricTick.ts >= cutoff)
                .order_by(BrokerMetricTick.ts.asc())
            ).all()
        return {
            "timestamps": [iso_utc(row.ts) for row in rows],
            "bytes_received": [row.bytes_received_rate for row in rows],
            "bytes_sent": [row.bytes_sent_rate for row in rows],
        }

    def get_messages_for_period(self, period: str) -> Dict[str, list]:
        minutes = PERIODS.get(period, 60)
        cutoff = normalize_datetime(utc_now() - timedelta(minutes=minutes))
        with self._session_factory() as session:
            rows = session.scalars(
                select(BrokerMetricTick)
                .where(BrokerMetricTick.ts >= cutoff)
                .order_by(BrokerMetricTick.ts.asc())
            ).all()
        return {
            "timestamps": [iso_utc(row.ts) for row in rows],
            "msg_received": [row.messages_received_delta for row in rows],
            "msg_sent": [row.messages_sent_delta for row in rows],
        }

    def get_hourly_data(self) -> Dict[str, list]:
        return self.get_bytes_for_period("1d")

    def get_runtime_state(self) -> Dict[str, Any]:
        with self._session_factory() as session:
            row = session.get(BrokerRuntimeState, 1)
        if row is None:
            return {}
        return {
            "id": row.id,
            "last_tick_ts": iso_utc(row.last_tick_ts),
            "last_broker_uptime": row.last_broker_uptime,
            "current_max_concurrent": row.current_max_concurrent,
            "lifetime_max_concurrent": row.lifetime_max_concurrent,
            "last_messages_received_total": row.last_messages_received_total,
            "last_messages_sent_total": row.last_messages_sent_total,
        }

    def get_total_message_count(self, days: int = 7) -> int:
        cutoff = (utc_now() - timedelta(days=days)).date()
        with self._session_factory() as session:
            total = session.scalar(
                select(func.coalesce(func.sum(BrokerDailySummary.total_messages_received), 0)).where(BrokerDailySummary.day >= cutoff)
            )
        return int(total or 0)

    def get_daily_message_stats(self, days: int = 7, pending_today: int = 0) -> Dict[str, list]:
        cutoff = (utc_now() - timedelta(days=days)).date()
        with self._session_factory() as session:
            rows = session.scalars(
                select(BrokerDailySummary)
                .where(BrokerDailySummary.day >= cutoff)
                .order_by(BrokerDailySummary.day.asc())
            ).all()

        counts_by_day = {row.day.isoformat(): int(row.total_messages_received) for row in rows}
        today = utc_now().date().isoformat()
        if pending_today > 0:
            counts_by_day[today] = counts_by_day.get(today, 0) + pending_today
        ordered_days = sorted(counts_by_day.keys())
        return {"dates": ordered_days, "counts": [counts_by_day[day] for day in ordered_days]}

    def get_daily_summary(self, days: int = 7) -> Dict[str, list[Dict[str, Any]]]:
        cutoff = (utc_now() - timedelta(days=days)).date()
        with self._session_factory() as session:
            rows = session.scalars(
                select(BrokerDailySummary)
                .where(BrokerDailySummary.day >= cutoff)
                .order_by(BrokerDailySummary.day.asc())
            ).all()

        summary: list[Dict[str, Any]] = []
        for row in rows:
            avg_latency = round(float(row.latency_sum or 0.0) / row.latency_samples, 2) if row.latency_samples else None
            summary.append(
                {
                    "day": row.day.isoformat(),
                    "peak_connected_clients": int(row.peak_connected_clients),
                    "peak_active_sessions": int(row.peak_active_sessions),
                    "peak_max_concurrent": int(row.peak_max_concurrent),
                    "total_messages_received": int(row.total_messages_received),
                    "total_messages_sent": int(row.total_messages_sent),
                    "bytes_received_rate_sum": float(row.bytes_received_rate_sum),
                    "bytes_sent_rate_sum": float(row.bytes_sent_rate_sum),
                    "latency_samples": int(row.latency_samples),
                    "avg_latency_ms": avg_latency,
                }
            )
        return {"days": summary}