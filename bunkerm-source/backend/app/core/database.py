"""
Motor SQLAlchemy async compartido por todos los módulos del backend unificado.
"""
import asyncio
import logging
import time

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import settings
from core.database_url import ensure_postgres_url, get_async_database_url, get_async_engine_connect_args

logger = logging.getLogger(__name__)

_async_database_url = get_async_database_url(settings.resolved_control_plane_database_url)

_engine_kwargs: dict[str, object] = {"echo": False}
_connect_args = get_async_engine_connect_args(_async_database_url)
if _connect_args:
    _engine_kwargs["connect_args"] = _connect_args

engine = create_async_engine(_async_database_url, **_engine_kwargs)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """Dependencia FastAPI que provee una sesión de base de datos."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """
    Crea todas las tablas ORM registradas en la base del control-plane.
    Se llama desde el lifespan del app principal.
    """
    from models import orm  # noqa: F401 — importar para que SQLAlchemy registre los modelos

    from core.history_reporting_database_migrations import upgrade_history_reporting_databases
    from core.database_migrations import upgrade_control_plane_database

    ensure_postgres_url(settings.resolved_control_plane_database_url, "CONTROL_PLANE_DATABASE_URL")

    history_database_url = getattr(settings, "resolved_history_database_url", settings.resolved_control_plane_database_url)
    reporting_database_url = getattr(settings, "resolved_reporting_database_url", history_database_url)

    ensure_postgres_url(history_database_url, "HISTORY_DATABASE_URL")
    ensure_postgres_url(reporting_database_url, "REPORTING_DATABASE_URL")

    startup_timeout_seconds = 60.0
    retry_delay_seconds = 2.0
    deadline = time.monotonic() + startup_timeout_seconds
    last_error: Exception | None = None

    while True:
        try:
            await upgrade_control_plane_database(settings.resolved_control_plane_database_url)

            await upgrade_history_reporting_databases(
                [
                    history_database_url,
                    reporting_database_url,
                ]
            )
            return
        except OperationalError as exc:
            last_error = exc
            if time.monotonic() >= deadline:
                raise
            logger.warning(
                "PostgreSQL aun no esta listo para migraciones (%s). Reintentando en %.1f s...",
                exc,
                retry_delay_seconds,
            )
            await asyncio.sleep(retry_delay_seconds)

