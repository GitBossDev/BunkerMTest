from __future__ import annotations

from typing import TYPE_CHECKING

from core.config import settings
from core.database_url import get_sync_database_url
from core.database_url import is_sqlite_url
from reporting.sqlalchemy_reporting import SQLAlchemyReportingStorage

if TYPE_CHECKING:
    from reporting.sqlite_reporting import SQLiteReportingStorage


def create_reporting_storage() -> SQLiteReportingStorage | SQLAlchemyReportingStorage:
    database_url = settings.resolved_reporting_database_url
    if is_sqlite_url(database_url):
        from reporting.sqlite_reporting import SQLiteReportingStorage

        return SQLiteReportingStorage(database_url)
    return SQLAlchemyReportingStorage(get_sync_database_url(database_url))


reporting_storage = create_reporting_storage()