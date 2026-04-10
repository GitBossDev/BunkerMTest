"""
Fixtures compartidos para los tests del backend unificado de BunkerM.

Estrategia:
- Base de datos: SQLite en memoria (evita dependencia del volumen /nextjs/data)
- Autenticacion: get_api_key sobreescrito para aceptar TEST_API_KEY sin leer env/archivo
- Lifespan: NO se activa con ASGITransport — MQTT, hilos y smart-anomaly no arrancan
- Dos fixtures de cliente:
    client      — incluye cabecera X-API-Key y sobreescribe get_db (tests normales)
    raw_client  — sin cabeceras ni overrides (para verificar 401/403)
"""
import asyncio
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Clave fija para tests — debe estar antes de cualquier import del modulo core.auth
TEST_API_KEY = "bunkerm-test-api-key-pytest"
os.environ["API_KEY"] = TEST_API_KEY

# Motor SQLite en memoria para tests (aislado del volumen de produccion)
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


# ---------------------------------------------------------------------------
# event_loop (scope session) — compatibilidad con pytest-asyncio >= 0.23 y < 0.23
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
def event_loop():
    """Loop de asyncio compartido por todos los tests de la sesion."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# setup_db (scope session) — crea tablas ORM una vez por sesion de tests
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    """
    Crea todas las tablas ORM del backend unificado en la base de datos de test.
    Los modelos deben importarse aqui para que SQLAlchemy los registre en Base.metadata.
    """
    from models import orm  # noqa: F401 — registra HistoricalTick, AlertConfigEntry, etc.
    from core.database import Base

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# client — cliente autenticado con DB en memoria
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client():
    """
    AsyncClient con:
    - X-API-Key: TEST_API_KEY en cada request
    - get_api_key sobreescrito para bypass de la logica de archivo/env
    - get_db sobreescrito para usar SQLite en memoria
    """
    from core.database import get_db
    from core.auth import get_api_key
    from main import app

    async def override_get_db():
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_api_key] = lambda: TEST_API_KEY

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": TEST_API_KEY},
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# raw_client — cliente sin autenticacion (para verificar 401/403)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def raw_client():
    """
    AsyncClient sin cabeceras de autenticacion ni overrides de dependencias.
    Usar exclusivamente para verificar que los endpoints protegidos rechazan
    peticiones no autenticadas.
    """
    from main import app

    # Guardar overrides activos para no interferir con otros fixtures en paralelo
    saved_overrides = dict(app.dependency_overrides)
    app.dependency_overrides.clear()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.update(saved_overrides)
