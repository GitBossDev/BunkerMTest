from __future__ import annotations

import asyncio

from alembic import context
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
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(_database_url())
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()