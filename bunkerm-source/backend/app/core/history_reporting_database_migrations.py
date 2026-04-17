from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config

from core.database_url import get_async_database_url, is_sqlite_url


HISTORY_REPORTING_TABLE_NAMES = {
    "broker_metric_ticks",
    "broker_runtime_state",
    "broker_daily_summary",
    "topic_registry",
    "topic_publish_buckets",
    "topic_subscribe_buckets",
    "client_registry",
    "client_session_events",
    "client_topic_events",
    "client_subscription_state",
    "client_daily_summary",
    "client_daily_distinct_topics",
}

HISTORY_REPORTING_VERSION_TABLE = "alembic_version_history_reporting"


def _app_root() -> Path:
    return Path(__file__).resolve().parents[1]


def history_reporting_alembic_ini_path() -> Path:
    return _app_root() / "history_reporting_alembic.ini"


def _escape_config_parser_value(value: str) -> str:
    return value.replace("%", "%%")


def create_history_reporting_alembic_config(database_url: str) -> Config:
    alembic_ini = history_reporting_alembic_ini_path()
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(_app_root() / "history_reporting_alembic"))
    cfg.set_main_option("sqlalchemy.url", _escape_config_parser_value(get_async_database_url(database_url)))
    cfg.set_main_option("version_table", HISTORY_REPORTING_VERSION_TABLE)
    return cfg


def upgrade_history_reporting_database_sync(database_url: str, revision: str = "head") -> None:
    cfg = create_history_reporting_alembic_config(database_url)
    command.upgrade(cfg, revision)


@lru_cache(maxsize=16)
def ensure_history_reporting_database_sync(database_url: str, revision: str = "head") -> None:
    upgrade_history_reporting_database_sync(database_url, revision)


async def upgrade_history_reporting_database(database_url: str, revision: str = "head") -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, ensure_history_reporting_database_sync, database_url, revision)


async def upgrade_history_reporting_databases(database_urls: list[str], revision: str = "head") -> None:
    seen: set[str] = set()
    for database_url in database_urls:
        if database_url in seen or is_sqlite_url(database_url):
            continue
        seen.add(database_url)
        await upgrade_history_reporting_database(database_url, revision)