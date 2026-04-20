"""
Fixtures compartidos para los tests del backend unificado de BHM.

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
import tempfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Clave fija para tests — debe estar antes de cualquier import del modulo core.auth
TEST_API_KEY = "bunkerm-test-api-key-pytest"
os.environ["API_KEY"] = TEST_API_KEY

# Motor SQLite temporal para tests (aislado del volumen de produccion)
TEST_DB_FILE = os.path.join(tempfile.gettempdir(), "bunkerm_backend_test.sqlite3")
if os.path.exists(TEST_DB_FILE):
    os.remove(TEST_DB_FILE)
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"
test_engine = create_async_engine(
    TEST_DB_URL,
    echo=False,
)
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
    from models.orm import Base as ORMBase

    async with test_engine.begin() as conn:
        await conn.run_sync(ORMBase.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(ORMBase.metadata.drop_all)


@pytest.fixture(autouse=True)
def reset_ip_whitelist_runtime_state():
    """Aisla la cache global de whitelist entre tests para evitar fugas de middleware."""
    from services import ip_whitelist_service

    ip_whitelist_service.clear_ip_whitelist_runtime_state()
    yield
    ip_whitelist_service.clear_ip_whitelist_runtime_state()


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
    from models.orm import Base as ORMBase
    from main import app
    import routers.dynsec as dynsec_router
    import routers.config_mosquitto as config_mosquitto_router
    import routers.config_dynsec as config_dynsec_router
    import routers.monitor as monitor_router
    import routers.clientlogs as clientlogs_router
    import routers.reporting as reporting_router

    async with test_engine.begin() as conn:
        await conn.run_sync(ORMBase.metadata.create_all)

    async def override_get_db():
        async with TestSessionLocal() as session:
            yield session

    db_dependencies = {
        dependency
        for dependency in [
            get_db,
            getattr(dynsec_router, "get_db", None),
            getattr(config_mosquitto_router, "get_db", None),
            getattr(config_dynsec_router, "get_db", None),
            getattr(monitor_router, "get_db", None),
            getattr(clientlogs_router, "get_db", None),
            getattr(reporting_router, "get_db", None),
        ]
        if dependency is not None
    }
    for dependency in db_dependencies:
        app.dependency_overrides[dependency] = override_get_db
    app.dependency_overrides[get_api_key] = lambda: TEST_API_KEY

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost",
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
        base_url="http://localhost",
    ) as ac:
        yield ac

    app.dependency_overrides.update(saved_overrides)
