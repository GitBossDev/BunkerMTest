from __future__ import annotations

from core.config import settings
from core.database_url import ensure_postgres_url, get_sync_database_url
from monitor.topic_sqlalchemy_storage import SQLAlchemyTopicHistoryStorage


def create_topic_history_storage() -> SQLAlchemyTopicHistoryStorage:
    database_url = settings.resolved_history_database_url
    ensure_postgres_url(database_url, "HISTORY_DATABASE_URL")
    return SQLAlchemyTopicHistoryStorage(get_sync_database_url(database_url))


class _LazyTopicHistoryStorage:
    def __init__(self) -> None:
        self._storage: SQLAlchemyTopicHistoryStorage | None = None

    def _get_storage(self) -> SQLAlchemyTopicHistoryStorage:
        if self._storage is None:
            self._storage = create_topic_history_storage()
        return self._storage

    def __getattr__(self, name: str):
        return getattr(self._get_storage(), name)


topic_history_storage = _LazyTopicHistoryStorage()