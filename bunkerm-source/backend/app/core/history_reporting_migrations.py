from __future__ import annotations

import os
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.sql.sqltypes import Boolean, Date, DateTime

from core.config import Settings
from core.database_url import ensure_sqlite_url, get_host_accessible_database_url
from core.history_reporting_database_migrations import ensure_history_reporting_database_sync
from core.sync_database import create_sync_engine_for_url, ensure_tables
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
    TopicRegistry,
    TopicSubscribeBucket,
)


HISTORY_TABLES = [
    BrokerMetricTick.__table__,
    BrokerRuntimeState.__table__,
    BrokerDailySummary.__table__,
    TopicRegistry.__table__,
    TopicPublishBucket.__table__,
    TopicSubscribeBucket.__table__,
    ClientRegistry.__table__,
    ClientSessionEvent.__table__,
    ClientTopicEvent.__table__,
    ClientSubscriptionState.__table__,
    ClientDailySummary.__table__,
    ClientDailyDistinctTopic.__table__,
]

REPORTING_TABLES = [
    BrokerMetricTick.__table__,
    BrokerDailySummary.__table__,
    TopicPublishBucket.__table__,
    TopicSubscribeBucket.__table__,
    ClientRegistry.__table__,
    ClientSessionEvent.__table__,
    ClientTopicEvent.__table__,
    ClientDailySummary.__table__,
    ClientDailyDistinctTopic.__table__,
]


@dataclass(frozen=True)
class MigrationPlan:
    source_url: str
    history_target_url: str
    reporting_target_url: str


def default_legacy_sqlite_url() -> str:
    return "sqlite+aiosqlite:////nextjs/data/bunkerm.db"


def resolve_history_reporting_plan(
    *,
    source_url: str | None = None,
    history_target_url: str | None = None,
    reporting_target_url: str | None = None,
) -> MigrationPlan:
    settings = Settings()
    return MigrationPlan(
        source_url=source_url
        or os.getenv("HISTORY_SOURCE_DATABASE_URL")
        or default_legacy_sqlite_url(),
        history_target_url=get_host_accessible_database_url(history_target_url or settings.resolved_history_database_url),
        reporting_target_url=get_host_accessible_database_url(reporting_target_url or settings.resolved_reporting_database_url),
    )


def _resolve_sqlite_path(database_url: str) -> str:
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    for prefix in prefixes:
        if database_url.startswith(prefix):
            return database_url[len(prefix):]
    raise ValueError(f"Unsupported SQLite URL: {database_url}")


def _read_sqlite_rows(database_url: str, table_name: str) -> list[dict[str, object]]:
    ensure_sqlite_url(database_url, "HISTORY_SOURCE_DATABASE_URL")
    db_path = _resolve_sqlite_path(database_url)
    if not os.path.exists(db_path):
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if table_name not in tables:
            return []
        rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
    return [dict(row) for row in rows]


def _count_target_rows(target_url: str, tables: Sequence[object]) -> dict[str, int]:
    engine = create_sync_engine_for_url(target_url)
    if target_url.startswith("sqlite"):
        ensure_tables(engine, list(tables))
    else:
        ensure_history_reporting_database_sync(target_url)
    with engine.begin() as connection:
        return {
            table.name: int(connection.execute(select(func.count()).select_from(table)).scalar_one() or 0)
            for table in tables
        }


def _normalize_row_for_table(table, row: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for column in table.columns:
        value = row.get(column.name)
        if value is None:
            normalized[column.name] = None
            continue
        if isinstance(column.type, DateTime) and isinstance(value, str):
            normalized[column.name] = datetime.fromisoformat(value.replace("Z", "+00:00"))
            continue
        if isinstance(column.type, Date) and isinstance(value, str):
            normalized[column.name] = date.fromisoformat(value)
            continue
        if isinstance(column.type, Boolean) and isinstance(value, int):
            normalized[column.name] = bool(value)
            continue
        normalized[column.name] = value
    return normalized


def _copy_tables(
    *,
    source_url: str,
    target_url: str,
    tables: Sequence[object],
    truncate_target: bool,
    dry_run: bool,
) -> dict[str, int]:
    engine = create_sync_engine_for_url(target_url)
    if target_url.startswith("sqlite"):
        ensure_tables(engine, list(tables))
    else:
        ensure_history_reporting_database_sync(target_url)

    source_counts = {table.name: len(_read_sqlite_rows(source_url, table.name)) for table in tables}
    target_counts = _count_target_rows(target_url, tables)

    existing = {name: count for name, count in target_counts.items() if count > 0}
    if dry_run:
        return {
            **{f"source:{name}": count for name, count in source_counts.items()},
            **{f"target:{name}": count for name, count in target_counts.items()},
        }

    if existing and not truncate_target:
        raise RuntimeError(
            f"Target {target_url} already contains rows for {sorted(existing.keys())}; use truncate_target to replace them."
        )

    with engine.begin() as connection:
        if truncate_target:
            for table in reversed(list(tables)):
                connection.execute(table.delete())
        for table in tables:
            rows = _read_sqlite_rows(source_url, table.name)
            if rows:
                connection.execute(table.insert(), [_normalize_row_for_table(table, row) for row in rows])
    return source_counts


def migrate_history_reporting_sqlite_sync(
    *,
    source_url: str,
    history_target_url: str,
    reporting_target_url: str,
    truncate_target: bool = False,
    dry_run: bool = False,
) -> dict[str, dict[str, int] | str]:
    ensure_sqlite_url(source_url, "HISTORY_SOURCE_DATABASE_URL")

    result: dict[str, dict[str, int] | str] = {
        "source": source_url,
        "history_target": history_target_url,
        "reporting_target": reporting_target_url,
    }
    result["history_tables"] = _copy_tables(
        source_url=source_url,
        target_url=history_target_url,
        tables=HISTORY_TABLES,
        truncate_target=truncate_target,
        dry_run=dry_run,
    )
    if reporting_target_url == history_target_url:
        reporting_counts = {table.name: result["history_tables"].get(table.name, 0) for table in REPORTING_TABLES}  # type: ignore[union-attr]
        result["reporting_tables"] = reporting_counts
        result["reporting_mode"] = "shared-history-target"
        return result

    result["reporting_tables"] = _copy_tables(
        source_url=source_url,
        target_url=reporting_target_url,
        tables=REPORTING_TABLES,
        truncate_target=truncate_target,
        dry_run=dry_run,
    )
    result["reporting_mode"] = "dedicated-reporting-target"
    return result