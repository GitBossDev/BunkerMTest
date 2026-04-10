"""
Motor SQLAlchemy async compartido por todos los módulos del backend unificado.
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)

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
    Crea todas las tablas definidas en los modelos ORM si no existen.
    Se llama desde el lifespan del app principal.
    """
    from models import orm  # noqa: F401 — importar para que SQLAlchemy registre los modelos

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
