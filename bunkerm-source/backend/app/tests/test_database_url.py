from core.config import Settings
from core.database_url import (
    ensure_sqlite_url,
    get_async_engine_connect_args,
    get_sync_database_url,
    get_sync_engine_connect_args,
    is_sqlite_url,
)


def test_sqlite_url_detection_and_connect_args():
    sqlite_url = "sqlite+aiosqlite:////tmp/bunkerm.db"

    assert is_sqlite_url(sqlite_url) is True
    assert get_async_engine_connect_args(sqlite_url) == {"check_same_thread": False}
    assert get_sync_database_url(sqlite_url) == "sqlite+pysqlite:////tmp/bunkerm.db"
    assert get_sync_engine_connect_args(sqlite_url) == {"check_same_thread": False}


def test_non_sqlite_url_skips_sqlite_connect_args():
    postgres_url = "postgresql+asyncpg://bhm:secret@localhost:5432/bhm"

    assert is_sqlite_url(postgres_url) is False
    assert get_async_engine_connect_args(postgres_url) == {"timeout": 5, "command_timeout": 30}
    assert get_sync_database_url(postgres_url) == "postgresql+psycopg2://bhm:secret@localhost:5432/bhm"
    assert get_sync_engine_connect_args(postgres_url) == {"connect_timeout": 5}


def test_settings_resolve_domain_database_urls():
    settings = Settings(
        database_url="sqlite+aiosqlite:////tmp/bunkerm.db",
        control_plane_database_url="postgresql+asyncpg://bhm:secret@localhost:5432/bhm_control",
        history_database_url="sqlite+aiosqlite:////tmp/bunkerm-history.db",
    )

    assert settings.resolved_control_plane_database_url.endswith("bhm_control")
    assert settings.resolved_history_database_url.endswith("bunkerm-history.db")
    assert settings.resolved_reporting_database_url.endswith("bunkerm-history.db")


def test_ensure_sqlite_url_rejects_postgres_for_sqlite_only_components():
    postgres_url = "postgresql+asyncpg://bhm:secret@localhost:5432/bhm"

    try:
        ensure_sqlite_url(postgres_url, "HISTORY_DATABASE_URL")
    except ValueError as exc:
        assert "HISTORY_DATABASE_URL" in str(exc)
    else:
        raise AssertionError("ensure_sqlite_url should reject non-sqlite URLs")