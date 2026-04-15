from __future__ import annotations

from core.config import settings
from core.database_url import get_sync_database_url
from core.database_url import is_sqlite_url
from monitor.sqlalchemy_storage import BrokerTickSnapshot, SQLAlchemyMonitorHistoryStorage
from monitor.sqlite_storage import BrokerTickSnapshot, SQLiteMonitorHistoryStorage


def create_monitor_history_storage(
    legacy_json_path: str | None = None,
) -> SQLiteMonitorHistoryStorage | SQLAlchemyMonitorHistoryStorage:
    database_url = settings.resolved_history_database_url
    if is_sqlite_url(database_url):
        return SQLiteMonitorHistoryStorage(database_url=database_url, legacy_json_path=legacy_json_path)
    return SQLAlchemyMonitorHistoryStorage(
        database_url=get_sync_database_url(database_url),
        legacy_json_path=legacy_json_path,
    )


__all__ = [
    "BrokerTickSnapshot",
    "SQLiteMonitorHistoryStorage",
    "SQLAlchemyMonitorHistoryStorage",
    "create_monitor_history_storage",
]