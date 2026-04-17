import clientlogs.activity_storage as activity_storage_module
import monitor.history_storage as history_storage_module
import monitor.topic_history_storage as topic_history_storage_module
import reporting.storage as reporting_storage_module
import pytest
from core.config import Settings
from clientlogs.activity_storage import create_client_activity_storage
from monitor.history_storage import create_monitor_history_storage
from monitor.topic_history_storage import create_topic_history_storage
from reporting.storage import create_reporting_storage


def test_storage_factories_reject_sqlite_urls(monkeypatch):
    settings = Settings(
        database_url="postgresql://bhm:secret@localhost:5432/bhm_shared",
        history_database_url="sqlite+aiosqlite:////tmp/bunkerm-history.db",
        reporting_database_url="sqlite+aiosqlite:////tmp/bunkerm-reporting.db",
    )

    monkeypatch.setattr("clientlogs.activity_storage.settings", settings)
    monkeypatch.setattr("monitor.history_storage.settings", settings)
    monkeypatch.setattr("monitor.topic_history_storage.settings", settings)
    monkeypatch.setattr("reporting.storage.settings", settings)

    with pytest.raises(ValueError):
        create_client_activity_storage()
    with pytest.raises(ValueError):
        create_monitor_history_storage()
    with pytest.raises(ValueError):
        create_topic_history_storage()
    with pytest.raises(ValueError):
        create_reporting_storage()


def test_storage_factories_select_sqlalchemy_backends_for_postgres_urls(monkeypatch):
    settings = Settings(
        database_url="postgresql://bhm:secret@localhost:5432/bhm_shared",
        history_database_url="postgresql+asyncpg://bhm:secret@localhost:5432/bhm_history",
        reporting_database_url="postgresql+asyncpg://bhm:secret@localhost:5432/bhm_reporting",
    )

    monkeypatch.setattr(activity_storage_module, "settings", settings)
    monkeypatch.setattr(history_storage_module, "settings", settings)
    monkeypatch.setattr(topic_history_storage_module, "settings", settings)
    monkeypatch.setattr(reporting_storage_module, "settings", settings)

    monkeypatch.setattr(activity_storage_module, "SQLAlchemyClientActivityStorage", lambda url: ("client", url))
    monkeypatch.setattr(history_storage_module, "SQLAlchemyMonitorHistoryStorage", lambda database_url, legacy_json_path=None: ("monitor", database_url, legacy_json_path))
    monkeypatch.setattr(topic_history_storage_module, "SQLAlchemyTopicHistoryStorage", lambda url: ("topic", url))
    monkeypatch.setattr(reporting_storage_module, "SQLAlchemyReportingStorage", lambda url: ("reporting", url))

    client_storage = create_client_activity_storage()
    monitor_storage = create_monitor_history_storage()
    topic_storage = create_topic_history_storage()
    reporting_storage = create_reporting_storage()

    assert client_storage == ("client", "postgresql+psycopg://bhm:secret@localhost:5432/bhm_history")
    assert monitor_storage == ("monitor", "postgresql+psycopg://bhm:secret@localhost:5432/bhm_history", None)
    assert topic_storage == ("topic", "postgresql+psycopg://bhm:secret@localhost:5432/bhm_history")
    assert reporting_storage == ("reporting", "postgresql+psycopg://bhm:secret@localhost:5432/bhm_reporting")