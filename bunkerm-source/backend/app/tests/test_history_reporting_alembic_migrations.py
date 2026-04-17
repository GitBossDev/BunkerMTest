from __future__ import annotations

from sqlalchemy import inspect, text

from core.history_reporting_database_migrations import (
    HISTORY_REPORTING_VERSION_TABLE,
    create_history_reporting_alembic_config,
    upgrade_history_reporting_database_sync,
)
from core.sync_database import create_sync_engine_for_url
from models.orm import BrokerMetricTick, BrokerRuntimeState
from core.database import Base


def test_history_reporting_alembic_upgrade_creates_expected_tables(tmp_path):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'history-reporting-migrations.db').as_posix()}"

    upgrade_history_reporting_database_sync(database_url)

    engine = create_sync_engine_for_url(database_url)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    assert HISTORY_REPORTING_VERSION_TABLE in table_names
    assert "broker_metric_ticks" in table_names
    assert "broker_runtime_state" in table_names
    assert "broker_daily_summary" in table_names
    assert "topic_registry" in table_names
    assert "client_registry" in table_names
    assert "client_session_events" in table_names


def test_history_reporting_alembic_config_accepts_percent_encoded_password():
    cfg = create_history_reporting_alembic_config(
        "postgresql://bunkerm:jHD%3DimxUb%3DqJw8wJyAh.~Tv5@postgres:5432/bunkerm_db"
    )

    assert (
        cfg.get_main_option("sqlalchemy.url")
        == "postgresql+asyncpg://bunkerm:jHD%3DimxUb%3DqJw8wJyAh.~Tv5@postgres:5432/bunkerm_db"
    )


def test_history_reporting_alembic_upgrade_accepts_partially_bootstrapped_schema(tmp_path):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'history-reporting-bootstrap.db').as_posix()}"
    engine = create_sync_engine_for_url(database_url)

    Base.metadata.create_all(bind=engine, tables=[BrokerMetricTick.__table__, BrokerRuntimeState.__table__])

    upgrade_history_reporting_database_sync(database_url)

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert HISTORY_REPORTING_VERSION_TABLE in table_names
    assert "client_daily_summary" in table_names

    with engine.begin() as connection:
        stamped_revision = connection.execute(
            text(f"SELECT version_num FROM {HISTORY_REPORTING_VERSION_TABLE}")
        ).scalar_one()

    assert stamped_revision == "001_history_reporting_initial"