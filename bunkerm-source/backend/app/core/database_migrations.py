from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script.revision import MultipleHeads
from alembic.util.exc import CommandError
from sqlalchemy import inspect

from core.database_url import get_async_database_url
from core.sync_database import create_sync_engine_for_url


CONTROL_PLANE_TABLE_NAMES = {
    "broker_desired_state",
    "broker_desired_state_audit",
    "broker_reconcile_secret",
    "alert_config",
    "alert_delivery_channel",
    "alert_delivery_event",
    "alert_delivery_attempt",
}

LEGACY_BOOTSTRAP_CONTROL_PLANE_TABLE_NAMES = {
    "broker_desired_state",
    "broker_desired_state_audit",
}

ALERT_CONFIG_BOOTSTRAP_CONTROL_PLANE_TABLE_NAMES = (
    LEGACY_BOOTSTRAP_CONTROL_PLANE_TABLE_NAMES | {"alert_config"}
)

ALERT_DELIVERY_BOOTSTRAP_CONTROL_PLANE_TABLE_NAMES = (
    ALERT_CONFIG_BOOTSTRAP_CONTROL_PLANE_TABLE_NAMES
    | {"alert_delivery_channel", "alert_delivery_event", "alert_delivery_attempt"}
)

RECONCILE_SECRET_BOOTSTRAP_CONTROL_PLANE_TABLE_NAMES = (
    ALERT_DELIVERY_BOOTSTRAP_CONTROL_PLANE_TABLE_NAMES | {"broker_reconcile_secret"}
)


def _app_root() -> Path:
    return Path(__file__).resolve().parents[1]


def control_plane_alembic_ini_path() -> Path:
    return _app_root() / "alembic.ini"


def _escape_config_parser_value(value: str) -> str:
    return value.replace("%", "%%")


def create_control_plane_alembic_config(database_url: str) -> Config:
    alembic_ini = control_plane_alembic_ini_path()
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(_app_root() / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _escape_config_parser_value(get_async_database_url(database_url)))
    return cfg


def upgrade_control_plane_database_sync(database_url: str, revision: str = "head") -> None:
    cfg = create_control_plane_alembic_config(database_url)
    engine = create_sync_engine_for_url(database_url)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    has_version_table = (
        "alembic_version" in table_names
        or "alembic_version" in set(inspector.get_table_names(schema="control_plane"))
    )
    existing_control_plane_tables = CONTROL_PLANE_TABLE_NAMES & table_names
    if not has_version_table and existing_control_plane_tables:
        if existing_control_plane_tables == LEGACY_BOOTSTRAP_CONTROL_PLANE_TABLE_NAMES:
            command.stamp(cfg, "001_control_plane_initial")
            if revision != "001_control_plane_initial":
                command.upgrade(cfg, revision)
            return

        if existing_control_plane_tables == ALERT_CONFIG_BOOTSTRAP_CONTROL_PLANE_TABLE_NAMES:
            command.stamp(cfg, "002_control_plane_alert_config")
            if revision != "002_control_plane_alert_config":
                command.upgrade(cfg, revision)
            return

        if existing_control_plane_tables == ALERT_DELIVERY_BOOTSTRAP_CONTROL_PLANE_TABLE_NAMES:
            command.stamp(cfg, "003_alert_delivery_outbox")
            if revision != "003_alert_delivery_outbox":
                command.upgrade(cfg, revision)
            return

        if existing_control_plane_tables == RECONCILE_SECRET_BOOTSTRAP_CONTROL_PLANE_TABLE_NAMES:
            command.stamp(cfg, "004_broker_reconcile_secret")
            if revision != "004_broker_reconcile_secret":
                command.upgrade(cfg, revision)
            return

        if not existing_control_plane_tables.issubset(RECONCILE_SECRET_BOOTSTRAP_CONTROL_PLANE_TABLE_NAMES):
            raise RuntimeError(
                "Control-plane schema is partially present without alembic_version; manual reconciliation is required."
            )

        raise RuntimeError(
            "Control-plane schema is partially present without alembic_version; manual reconciliation is required."
        )

    try:
        command.upgrade(cfg, revision)
    except MultipleHeads:
        # If multiple heads exist in the alembic history (e.g. parallel branches),
        # retry upgrading to all heads so migrations are applied across branches.
        command.upgrade(cfg, "heads")
    except CommandError as exc:
        # Some alembic versions raise a CommandError wrapping the MultipleHeads
        # situation; detect and retry with 'heads', otherwise re-raise.
        msg = str(exc)
        if "Multiple head" in msg or "Multiple heads" in msg:
            command.upgrade(cfg, "heads")
        else:
            raise


async def upgrade_control_plane_database(database_url: str, revision: str = "head") -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, upgrade_control_plane_database_sync, database_url, revision)