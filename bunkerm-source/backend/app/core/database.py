"""
Motor SQLAlchemy async compartido por todos los módulos del backend unificado.
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import settings
from core.database_url import get_async_engine_connect_args

_engine_kwargs: dict[str, object] = {"echo": False}
_connect_args = get_async_engine_connect_args(settings.resolved_control_plane_database_url)
if _connect_args:
    _engine_kwargs["connect_args"] = _connect_args

engine = create_async_engine(settings.resolved_control_plane_database_url, **_engine_kwargs)

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

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
