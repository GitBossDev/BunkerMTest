from __future__ import annotations

from core.config import settings
from core.database_url import ensure_postgres_url, get_sync_database_url
from reporting.sqlalchemy_reporting import SQLAlchemyReportingStorage


def create_reporting_storage() -> SQLAlchemyReportingStorage:
    database_url = settings.resolved_reporting_database_url
    ensure_postgres_url(database_url, "REPORTING_DATABASE_URL")
    return SQLAlchemyReportingStorage(get_sync_database_url(database_url))


class _LazyReportingStorage:
    def __init__(self) -> None:
        self._storage: SQLAlchemyReportingStorage | None = None

    def _get_storage(self) -> SQLAlchemyReportingStorage:
        if self._storage is None:
            self._storage = create_reporting_storage()
        return self._storage

    def __getattr__(self, name: str):
        return getattr(self._get_storage(), name)


reporting_storage = _LazyReportingStorage()