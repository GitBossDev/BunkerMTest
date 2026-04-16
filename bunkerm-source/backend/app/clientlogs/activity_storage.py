from __future__ import annotations

from core.config import settings
from core.database_url import ensure_postgres_url, get_sync_database_url
from clientlogs.sqlalchemy_activity_storage import SQLAlchemyClientActivityStorage


def create_client_activity_storage() -> SQLAlchemyClientActivityStorage:
    database_url = settings.resolved_history_database_url
    ensure_postgres_url(database_url, "HISTORY_DATABASE_URL")
    return SQLAlchemyClientActivityStorage(get_sync_database_url(database_url))


class _LazyClientActivityStorage:
    def __init__(self) -> None:
        self._storage: SQLAlchemyClientActivityStorage | None = None

    def _get_storage(self) -> SQLAlchemyClientActivityStorage:
        if self._storage is None:
            self._storage = create_client_activity_storage()
        return self._storage

    def __getattr__(self, name: str):
        return getattr(self._get_storage(), name)


client_activity_storage = _LazyClientActivityStorage()