from __future__ import annotations

from core.config import settings
from core.database_url import is_sqlite_url
from core.database_url import get_sync_database_url
from clientlogs.sqlalchemy_activity_storage import SQLAlchemyClientActivityStorage
from clientlogs.sqlite_activity_storage import SQLiteClientActivityStorage


def create_client_activity_storage() -> SQLiteClientActivityStorage | SQLAlchemyClientActivityStorage:
    database_url = settings.resolved_history_database_url
    if is_sqlite_url(database_url):
        return SQLiteClientActivityStorage(database_url)
    return SQLAlchemyClientActivityStorage(get_sync_database_url(database_url))


client_activity_storage = create_client_activity_storage()