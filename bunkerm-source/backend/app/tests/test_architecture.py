"""
Guardrails de arquitectura (Fase D).

Estos tests protegen las decisiones de diseno tomadas en las Fases 1-4 para que
no sean revertidas inadvertidamente en cambios futuros.

Invariantes que se verifican:
  - El backend unificado escucha en el puerto 9001 (no en los puertos legacy 1000-1005).
  - Los 7 routers del backend unificado estan registrados en main.py.
  - No hay imports circulares en el paquete core/.
  - core/config.py puede instanciarse con variables minimas sin explotar.
"""
import importlib
import sys


# ---------------------------------------------------------------------------
# D1.1 — Puerto unificado
# ---------------------------------------------------------------------------

def test_unified_port_in_supervisord(tmp_path):
    """
    Verifica que supervisord-next.conf arranca uvicorn en el puerto 9001 y NO
    en ninguno de los puertos legacy (1000-1005).

    Busca el archivo en dos ubicaciones conocidas:
    - /etc/supervisor/conf.d/supervisord.conf  (dentro del contenedor)
    - bunkerm-source/supervisord-next.conf     (desarrollo local, relativo al repo)
    """
    import pathlib

    # Candidatos ordenados por preferencia
    candidates = [
        pathlib.Path("/etc/supervisor/conf.d/supervisord.conf"),  # contenedor
        pathlib.Path(__file__).parents[1].parent.parent / "supervisord-next.conf",  # local: bunkerm-source/
    ]

    conf_path = next((p for p in candidates if p.exists()), None)
    assert conf_path is not None, (
        "supervisord config not found. Looked in: "
        + str([str(p) for p in candidates])
    )

    text = conf_path.read_text(encoding="utf-8")

    # Debe declarar el puerto unificado
    assert "--port 9001" in text, "uvicorn must listen on port 9001"

    # No debe existir ningun proceso en los puertos legacy
    legacy_ports = [1000, 1001, 1002, 1003, 1004, 1005]
    for port in legacy_ports:
        assert f"--port {port}" not in text, (
            f"Legacy port {port} found in supervisord config — "
            "the backend must be a single unified process on 9001"
        )


# ---------------------------------------------------------------------------
# D1.1 — Todos los routers registrados en main.py
# ---------------------------------------------------------------------------

EXPECTED_ROUTERS = [
    "routers.dynsec",
    "routers.monitor",
    "routers.clientlogs",
    "routers.config_mosquitto",
    "routers.config_dynsec",
    "routers.aws_bridge",
    "routers.azure_bridge",
]


def test_all_routers_registered_in_main():
    """
    Importa main.py y verifica que los 7 routers del backend unificado
    estan incluidos en la aplicacion FastAPI.
    """
    from main import app

    # Recopilar prefijos de todas las rutas registradas
    registered_prefixes = {route.path.split("/")[1] for route in app.routes if hasattr(route, "path")}

    # Los tags declarados en cada router deben aparecer en alguna ruta
    expected_tags = {"dynsec", "monitor", "clientlogs", "config-mosquitto", "config-dynsec", "aws-bridge", "azure-bridge"}
    registered_tags: set[str] = set()
    for route in app.routes:
        if hasattr(route, "tags") and route.tags:
            registered_tags.update(route.tags)

    for tag in expected_tags:
        assert tag in registered_tags, (
            f"Router with tag '{tag}' is not registered in main.py. "
            "Add app.include_router(...) for this router."
        )


# ---------------------------------------------------------------------------
# D1.1 — Sin imports circulares en core/
# ---------------------------------------------------------------------------

CORE_MODULES = [
    "core.config",
    "core.auth",
    "core.database",
]


def test_no_circular_imports_in_core():
    """
    Importa cada modulo de core/ de forma aislada y verifica que ninguno
    produce un ImportError por dependencia circular.
    """
    for module_name in CORE_MODULES:
        # Remover del cache para forzar reimport limpio si ya fue importado
        for key in list(sys.modules.keys()):
            if key == module_name or key.startswith(module_name + "."):
                del sys.modules[key]

        try:
            importlib.import_module(module_name)
        except ImportError as exc:
            raise AssertionError(
                f"Circular or broken import detected in {module_name}: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# D1.2 — core/config.py se instancia con variables minimas
# ---------------------------------------------------------------------------

def test_config_instantiates_with_minimal_env(monkeypatch):
    """
    Verifica que Settings() puede construirse con solo las variables minimas,
    sin necesitar un archivo .env y sin lanzar excepciones.

    Esto protege contra la introduccion de campos requeridos sin valor por
    defecto que romperian el arranque del contenedor.
    """
    # Proveer solo las variables que no tienen valor por defecto en Settings
    # (actualmente todas tienen defaults; este test detecta si alguien añade
    # un campo requerido sin default en el futuro)
    minenv = {
        "API_KEY": "test-key",
        "JWT_SECRET": "test-jwt-secret",
        "AUTH_SECRET": "test-auth-secret",
    }
    for key, val in minenv.items():
        monkeypatch.setenv(key, val)

    # Limpiar cache de lru_cache para forzar reinstanciacion
    try:
        from core.config import get_settings
        get_settings.cache_clear()
    except AttributeError:
        pass

    # Limpiar del cache de modulos para que pydantic-settings lea el entorno fresco
    for key in list(sys.modules.keys()):
        if key.startswith("core.config"):
            del sys.modules[key]

    try:
        from core.config import Settings
        instance = Settings()
        assert instance is not None
    except Exception as exc:
        raise AssertionError(
            f"core/config.py Settings() failed to instantiate with minimal env: {exc}\n"
            "If you added a required field (no default), add a sensible default or "
            "document it in scripts/validate-env.py."
        ) from exc
    finally:
        # Restaurar estado de modulos para no afectar otros tests
        for key in list(sys.modules.keys()):
            if key.startswith("core.config"):
                del sys.modules[key]
        try:
            from core.config import get_settings
            get_settings.cache_clear()
        except Exception:
            pass
