from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from core.database_url import get_async_database_url
from core.sync_database import create_sync_engine_for_url


CONTROL_PLANE_TABLE_NAMES = {
    "broker_desired_state",
    "broker_desired_state_audit",
}


def _app_root() -> Path:
    return Path(__file__).resolve().parents[1]


def control_plane_alembic_ini_path() -> Path:
    return _app_root() / "alembic.ini"


def create_control_plane_alembic_config(database_url: str) -> Config:
    alembic_ini = control_plane_alembic_ini_path()
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(_app_root() / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_async_database_url(database_url))
    return cfg


def upgrade_control_plane_database_sync(database_url: str, revision: str = "head") -> None:
    cfg = create_control_plane_alembic_config(database_url)
    engine = create_sync_engine_for_url(database_url)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    has_version_table = "alembic_version" in table_names
    existing_control_plane_tables = CONTROL_PLANE_TABLE_NAMES & table_names
    if not has_version_table and existing_control_plane_tables:
        if existing_control_plane_tables != CONTROL_PLANE_TABLE_NAMES:
            raise RuntimeError(
                "Control-plane schema is partially present without alembic_version; manual reconciliation is required."
            )
        command.stamp(cfg, revision)
        return

    command.upgrade(cfg, revision)


async def upgrade_control_plane_database(database_url: str, revision: str = "head") -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, upgrade_control_plane_database_sync, database_url, revision)