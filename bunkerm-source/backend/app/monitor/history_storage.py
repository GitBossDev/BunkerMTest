from __future__ import annotations

from core.config import settings
from core.database_url import ensure_postgres_url, get_sync_database_url
from monitor.sqlalchemy_storage import BrokerTickSnapshot, SQLAlchemyMonitorHistoryStorage


def create_monitor_history_storage(
    legacy_json_path: str | None = None,
) -> SQLAlchemyMonitorHistoryStorage:
    database_url = settings.resolved_history_database_url
    ensure_postgres_url(database_url, "HISTORY_DATABASE_URL")
    return SQLAlchemyMonitorHistoryStorage(
        database_url=get_sync_database_url(database_url),
        legacy_json_path=legacy_json_path,
    )


__all__ = [
    "BrokerTickSnapshot",
    "SQLAlchemyMonitorHistoryStorage",
    "create_monitor_history_storage",
]