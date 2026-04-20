"""
Guardrails de arquitectura (Fase D).

Estos tests protegen las decisiones de diseno tomadas en las Fases 1-4 para que
no sean revertidas inadvertidamente en cambios futuros.

Invariantes que se verifican:
  - El backend unificado escucha en el puerto 9001 (no en los puertos legacy 1000-1005).
    - Los routers activos del backend unificado estan registrados en main.py.
  - No hay imports circulares en el paquete core/.
  - core/config.py puede instanciarse con variables minimas sin explotar.
"""
import importlib
import sys
import pathlib


def _compose_service_block(compose_text: str, service_name: str) -> str:
    lines = compose_text.splitlines()
    block: list[str] = []
    capturing = False
    service_header = f"  {service_name}:"

    for line in lines:
        if line.startswith(service_header):
            capturing = True
        elif capturing and line.startswith("  ") and not line.startswith("    "):
            break

        if capturing:
            block.append(line)

    return "\n".join(block)


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
    "routers.notifications",
    "routers.security",
    "routers.config_mosquitto",
    "routers.config_dynsec",
]


def test_all_routers_registered_in_main():
    """
    Importa main.py y verifica que los routers activos del backend unificado
    estan incluidos en la aplicacion FastAPI.
    """
    from main import app

    # Recopilar prefijos de todas las rutas registradas
    registered_prefixes = {route.path.split("/")[1] for route in app.routes if hasattr(route, "path")}

    # Los tags declarados en cada router deben aparecer en alguna ruta
    expected_tags = {"dynsec", "monitor", "clientlogs", "notifications", "security", "config-mosquitto", "config-dynsec"}
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


def test_compose_baseline_includes_dedicated_bhm_reconciler_service():
    """Protege que el baseline Compose-first incluya el daemon broker-facing dedicado."""
    compose_path = pathlib.Path(__file__).parents[4] / "docker-compose.dev.yml"
    assert compose_path.exists(), f"Compose file not found: {compose_path}"

    compose_text = compose_path.read_text(encoding="utf-8")
    assert "bhm-reconciler:" in compose_text
    assert "container_name: bunkerm-reconciler" in compose_text
    assert "services.broker_reconcile_daemon" in compose_text


def test_compose_web_service_uses_daemon_mode_and_read_only_broker_mounts():
    """Protege el siguiente recorte: el web container no debe escribir mounts broker-facing."""
    compose_path = pathlib.Path(__file__).parents[4] / "docker-compose.dev.yml"
    compose_text = compose_path.read_text(encoding="utf-8")
    bunkerm_block = _compose_service_block(compose_text, "bunkerm")

    assert "BROKER_RECONCILE_MODE=daemon" in compose_text
    assert "BROKER_OBSERVABILITY_URL=http://bhm-broker-observability:9102" in compose_text
    assert "CONTROL_PLANE_DATABASE_URL=${CONTROL_PLANE_DATABASE_URL}" in bunkerm_block
    assert "HISTORY_DATABASE_URL=${HISTORY_DATABASE_URL}" in bunkerm_block
    assert "REPORTING_DATABASE_URL=${REPORTING_DATABASE_URL}" in bunkerm_block
    assert "mosquitto-data:/var/lib/mosquitto:ro" not in bunkerm_block
    assert "mosquitto-conf:/etc/mosquitto:ro" not in bunkerm_block
    assert "mosquitto-log:/var/log/mosquitto:ro" not in bunkerm_block


def test_compose_reconciler_receives_domain_database_urls_for_phase4():
    """Protege que el control-plane broker-facing pueda apuntar a PostgreSQL por dominio en Compose."""
    compose_path = pathlib.Path(__file__).parents[4] / "docker-compose.dev.yml"
    compose_text = compose_path.read_text(encoding="utf-8")
    reconciler_block = _compose_service_block(compose_text, "bhm-reconciler")

    assert "CONTROL_PLANE_DATABASE_URL=${CONTROL_PLANE_DATABASE_URL}" in reconciler_block
    assert "HISTORY_DATABASE_URL=${HISTORY_DATABASE_URL}" in reconciler_block
    assert "REPORTING_DATABASE_URL=${REPORTING_DATABASE_URL}" in reconciler_block


def test_compose_baseline_includes_broker_observability_service():
    """Protege el recorte donde config/monitor consumen observabilidad broker-owned por HTTP interno."""
    compose_path = pathlib.Path(__file__).parents[4] / "docker-compose.dev.yml"
    compose_text = compose_path.read_text(encoding="utf-8")
    observability_block = _compose_service_block(compose_text, "bhm-broker-observability")

    assert "bhm-broker-observability:" in compose_text
    assert "container_name: bunkerm-broker-observability" in compose_text
    assert "services.broker_observability_api:app" in compose_text
    assert "mosquitto-data:/var/lib/mosquitto:ro" in observability_block
    assert "mosquitto-conf:/etc/mosquitto:ro" in observability_block
    assert "mosquitto-log:/var/log/mosquitto:ro" in observability_block


def test_web_surfaces_no_longer_read_shared_broker_files_directly():
    """Protege que las lecturas broker-facing del web pasen por observabilidad o estado observado."""
    app_root = pathlib.Path(__file__).parents[1]
    config_text = (app_root / "routers" / "config_mosquitto.py").read_text(encoding="utf-8")
    monitor_text = (app_root / "routers" / "monitor.py").read_text(encoding="utf-8")
    dynsec_text = (app_root / "routers" / "dynsec.py").read_text(encoding="utf-8")
    clientlogs_text = (app_root / "routers" / "clientlogs.py").read_text(encoding="utf-8")

    assert "broker_observability_client" in config_text
    assert "broker_observability_client" in monitor_text
    assert "get_cached_observed_dynsec_index" in dynsec_text
    assert "get_cached_observed_dynsec_capability_map" in clientlogs_text
    assert "settings.mosquitto_conf_path" not in monitor_text
    assert 'open(log_path' not in config_text
    assert "read_dynsec()" not in dynsec_text


def test_legacy_bridge_and_dynsec_surfaces_no_longer_embed_broker_writes():
    """Protege que las superficies legacy retiradas no vuelvan a contener writers broker-facing."""
    app_root = pathlib.Path(__file__).parents[1]
    files_to_check = [
        app_root / "routers" / "aws_bridge.py",
        app_root / "routers" / "azure_bridge.py",
        app_root / "dynsec" / "main.py",
    ]
    forbidden_markers = (
        "mosquitto_ctrl",
        "/var/lib/mosquitto/.reload",
        "dynamic-security.json",
        "MOSQUITTO_CONF_PATH",
        "MOSQUITTO_CERT_PATH",
        "DYNSEC_PATH =",
    )

    for file_path in files_to_check:
        text = file_path.read_text(encoding="utf-8")
        assert all(marker not in text for marker in forbidden_markers), file_path
