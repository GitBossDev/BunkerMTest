from __future__ import annotations

from core.config import settings
from core.database_url import get_sync_database_url
from core.database_url import is_sqlite_url
from monitor.topic_sqlalchemy_storage import SQLAlchemyTopicHistoryStorage
from monitor.topic_sqlite_storage import SQLiteTopicHistoryStorage


def create_topic_history_storage() -> SQLiteTopicHistoryStorage | SQLAlchemyTopicHistoryStorage:
    database_url = settings.resolved_history_database_url
    if is_sqlite_url(database_url):
        return SQLiteTopicHistoryStorage(database_url)
    return SQLAlchemyTopicHistoryStorage(get_sync_database_url(database_url))


topic_history_storage = create_topic_history_storage()