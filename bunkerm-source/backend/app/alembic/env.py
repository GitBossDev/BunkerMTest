from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from core.database import Base
from core.database_migrations import CONTROL_PLANE_TABLE_NAMES
from core.database_url import get_async_database_url

config = context.config
target_metadata = Base.metadata


def _include_object(object_, name, type_, reflected, compare_to):
    if type_ == "table":
        return name in CONTROL_PLANE_TABLE_NAMES
    table_name = getattr(getattr(object_, "table", None), "name", None)
    if table_name is not None:
        return table_name in CONTROL_PLANE_TABLE_NAMES
    return True


def _database_url() -> str:
    configured_url = config.get_main_option("sqlalchemy.url")
    return get_async_database_url(configured_url)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
        include_schemas=True,
        version_table="alembic_version",
        version_table_schema="control_plane",
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    # IMPORTANT: Do NOT execute any SQL before context.begin_transaction().
    # Executing SQL here (e.g. CREATE SCHEMA) triggers SQLAlchemy 2.0 autobegin,
    # which causes context.begin_transaction() to use a SAVEPOINT instead of a
    # full transaction. The outer autobegin transaction is then never committed,
    # rolling back all DDL silently. The fix: run all setup SQL *inside* the
    # Alembic-managed transaction so that its __exit__ calls connection.commit().
    #
    # NOTE: No SET search_path here. ORM models have no schema= qualifier so they
    # expect tables in 'public'. Migrations create tables in public by default.
    # The alembic_version table is tracked in control_plane via version_table_schema.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
        include_schemas=True,
        version_table="alembic_version",
        version_table_schema="control_plane",
    )
    with context.begin_transaction():
        # Create the control_plane schema for the alembic_version tracking table.
        # This runs inside Alembic's managed transaction so it commits properly.
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS control_plane"))
        context.run_migrations()


async def run_async_migrations() -> None:
    # Use connectable.begin() (not .connect()) so SQLAlchemy 2.0 auto-commits
    # the transaction on __aexit__ success. With .connect(), the outer autobegin
    # transaction rolls back on exit because it is never explicitly committed —
    # context.begin_transaction() only commits a nested savepoint, not the outer
    # transaction, leaving all DDL rolled back despite migrations appearing to run.
    connectable = create_async_engine(_database_url())
    async with connectable.begin() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()