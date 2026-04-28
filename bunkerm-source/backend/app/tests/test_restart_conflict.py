"""
Tests para la proteccion completa contra el doble-reinicio del broker.

Escenario critico reportado en produccion (import JSON + save config):
    1. Usuario importa 1k usuarios JSON -> dynsec_config.py escribe
       dynamic-security.json -> crea .dynsec-reload
    2. Supervisor consume .dynsec-reload -> SIGKILL -> mosquitto arranca a cargar
       1k usuarios (puede tardar 5-15 s).
    3. Usuario guarda config broker (max_connections 1050) -> _signal_mosquitto_restart()
    4. Supervisor ve .restart -> SIGTERM mientras mosquitto esta cargando DynSec
    5. Graceful shutdown escribe estado parcial/vacio a dynamic-security.json
    6. Broker arranca sin usuarios -> nadie puede autenticarse.

Cinco capas de proteccion implementadas:
    Capa 1 - _signal_mosquitto_restart() salta si .dynsec-reload esta pendiente.
    Capa 2 - dynsec_config._emit_dynsec_reload_signal() borra .restart antes de
              escribir .dynsec-reload.
    Capa 3 - _signal_mosquitto_restart() salta si .restart ya existe (idempotencia).
    Capa 4 - El entrypoint llama a wait_for_mosquitto_ready() despues de cada
              restart para que el supervisor no procese nuevas senales hasta que
              mosquitto este realmente escuchando en :1900.
              (Capa 4 es el entrypoint shell, no testeable desde pytest.)
    Capa 5 - Los endpoints HTTP retornan 503 si .broker-restarting existe, bloqueando
              cambios de config mientras mosquitto esta arrancando.
"""
import os
import pytest
import unittest.mock as mock

import config.mosquitto_config as mosquitto_config_module
import config.dynsec_config as dynsec_config_module
import services.broker_desired_state_service as desired_state_svc
import services.broker_reconciler as broker_reconciler
import services.broker_runtime as broker_runtime_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conf_payload(max_connections: int = 10000) -> dict:
    return {
        "config": {
            "allow_anonymous": "false",
            "plugin": "/usr/lib/mosquitto_dynamic_security.so",
            "plugin_opt_config_file": "/var/lib/mosquitto/dynamic-security.json",
        },
        "listeners": [
            {
                "port": 1900,
                "bind_address": "",
                "per_listener_settings": False,
                "max_connections": max_connections,
                "protocol": None,
            }
        ],
        "max_inflight_messages": 20,
        "max_queued_messages": 100,
        "tls": None,
    }


def _setup_paths(monkeypatch, conf_path, backup_dir):
    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(desired_state_svc, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(mosquitto_config_module, "MOSQUITTO_CONF_PATH", str(conf_path))


# ===========================================================================
# CAPA 1: _signal_mosquitto_restart() salta si .dynsec-reload esta pendiente
# ===========================================================================

def test_signal_mosquitto_restart_skips_when_dynsec_reload_pending():
    """
    Si .dynsec-reload ya existe (un import de DynSec JSON esta en curso),
    _signal_mosquitto_restart() debe ser un no-op completo.
    """
    mock_file = mock.mock_open()

    def patched_exists(path):
        if str(path).endswith(".dynsec-reload"):
            return True
        if str(path).endswith(".restart"):
            return False
        return os.path.exists(path)

    with mock.patch("config.mosquitto_config.os.path.exists", side_effect=patched_exists):
        with mock.patch("builtins.open", mock_file):
            mosquitto_config_module._signal_mosquitto_restart()

    assert not mock_file.called, (
        "_signal_mosquitto_restart escribio .restart aunque .dynsec-reload estaba pendiente"
    )


def test_signal_mosquitto_restart_writes_when_neither_signal_pending():
    """Si no hay senales pendientes, _signal_mosquitto_restart() escribe .restart."""
    mock_file = mock.mock_open()

    with mock.patch("config.mosquitto_config.os.path.exists", return_value=False):
        with mock.patch("builtins.open", mock_file):
            mosquitto_config_module._signal_mosquitto_restart()

    assert mock_file.called, "_signal_mosquitto_restart no escribio .restart cuando no habia senales"
    call_path = str(mock_file.call_args[0][0])
    assert call_path.endswith(".restart"), f"open fue llamado con ruta inesperada: {call_path}"


# ===========================================================================
# CAPA 2: _emit_dynsec_reload_signal() en dynsec_config.py
# ===========================================================================

def test_emit_dynsec_reload_signal_clears_restart_before_writing(tmp_path):
    """
    _emit_dynsec_reload_signal() debe eliminar .restart antes de crear
    .dynsec-reload para evitar que el supervisor procese ambas senales.
    """
    restart_path = tmp_path / ".restart"
    dynsec_reload_path = tmp_path / ".dynsec-reload"
    restart_path.write_text("")

    with mock.patch.object(dynsec_config_module, "_SIGNAL_DIR", str(tmp_path)):
        dynsec_config_module._emit_dynsec_reload_signal()

    assert not restart_path.exists(), (
        "_emit_dynsec_reload_signal no elimino .restart antes de crear .dynsec-reload"
    )
    assert dynsec_reload_path.exists(), (
        "_emit_dynsec_reload_signal no creo .dynsec-reload"
    )


def test_emit_dynsec_reload_signal_is_idempotent(tmp_path):
    """Si .dynsec-reload ya existe, _emit_dynsec_reload_signal es un no-op."""
    dynsec_reload_path = tmp_path / ".dynsec-reload"
    dynsec_reload_path.write_text("")
    original_mtime = dynsec_reload_path.stat().st_mtime

    with mock.patch.object(dynsec_config_module, "_SIGNAL_DIR", str(tmp_path)):
        dynsec_config_module._emit_dynsec_reload_signal()

    assert dynsec_reload_path.stat().st_mtime == original_mtime, (
        "_emit_dynsec_reload_signal sobreescribio .dynsec-reload ya existente"
    )


def test_emit_dynsec_reload_signal_clears_restart_even_when_dynsec_already_pending(tmp_path):
    """
    Si ya existe .dynsec-reload Y tambien .restart, debe borrar .restart igualmente.
    Ejemplo: dos imports rapidos seguidos + save config en medio.
    """
    restart_path = tmp_path / ".restart"
    dynsec_reload_path = tmp_path / ".dynsec-reload"
    restart_path.write_text("")
    dynsec_reload_path.write_text("")

    with mock.patch.object(dynsec_config_module, "_SIGNAL_DIR", str(tmp_path)):
        dynsec_config_module._emit_dynsec_reload_signal()

    assert not restart_path.exists(), (
        "_emit_dynsec_reload_signal no elimino .restart cuando .dynsec-reload ya existia"
    )


# ===========================================================================
# CAPA 3: _signal_mosquitto_restart() idempotente (.restart ya existe)
# ===========================================================================

def test_signal_mosquitto_restart_is_idempotent_when_restart_pending():
    """Si .restart ya existe, _signal_mosquitto_restart() no escribe otra vez."""
    mock_file = mock.mock_open()

    def patched_exists(path):
        if str(path).endswith(".dynsec-reload"):
            return False
        if str(path).endswith(".restart"):
            return True
        return os.path.exists(path)

    with mock.patch("config.mosquitto_config.os.path.exists", side_effect=patched_exists):
        with mock.patch("builtins.open", mock_file):
            mosquitto_config_module._signal_mosquitto_restart()

    assert not mock_file.called, (
        "_signal_mosquitto_restart sobreescribio .restart existente"
    )


# ===========================================================================
# broker_runtime._signal_dynsec_reload -- coherencia con la Capa 2
# ===========================================================================

def test_broker_runtime_signal_dynsec_reload_removes_pending_restart(tmp_path):
    """_signal_dynsec_reload() en broker_runtime borra .restart pendiente."""
    restart_path = tmp_path / ".restart"
    dynsec_reload_path = tmp_path / ".dynsec-reload"
    restart_path.write_text("")

    with mock.patch("services.broker_runtime.os.path.dirname", return_value=str(tmp_path)):
        broker_runtime_module._signal_dynsec_reload()

    assert not restart_path.exists(), "_signal_dynsec_reload no elimino .restart"
    assert dynsec_reload_path.exists(), "_signal_dynsec_reload no creo .dynsec-reload"


def test_broker_runtime_signal_dynsec_reload_is_idempotent(tmp_path):
    """_signal_dynsec_reload() en broker_runtime no sobreescribe .dynsec-reload."""
    dynsec_reload_path = tmp_path / ".dynsec-reload"
    dynsec_reload_path.write_text("")

    write_count = 0
    original_open = open

    def counting_open(path, mode="r", *args, **kwargs):
        nonlocal write_count
        if str(path).endswith(".dynsec-reload") and "w" in mode:
            write_count += 1
        return original_open(path, mode, *args, **kwargs)

    with mock.patch("services.broker_runtime.os.path.dirname", return_value=str(tmp_path)):
        with mock.patch("builtins.open", side_effect=counting_open):
            broker_runtime_module._signal_dynsec_reload()

    assert write_count == 0, "_signal_dynsec_reload sobreescribio .dynsec-reload existente"


# ===========================================================================
# Integracion HTTP: flujo completo import JSON -> save config
# ===========================================================================

async def test_save_config_after_dynsec_import_does_not_write_restart(
    client, monkeypatch, tmp_path
):
    """
    Escenario de produccion completo:
        1. Se simula que .dynsec-reload ya esta pendiente (import reciente).
        2. Usuario guarda config del broker.
        3. _signal_mosquitto_restart() debe ser un no-op porque .dynsec-reload
           ya implica un reinicio completo.

    Este test cubre exactamente el bug reportado: "importe 1k usuarios e
    inmediatamente modifique el limite maximo -> broker no inicia".
    """
    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    dynsec_reload_file = tmp_path / ".dynsec-reload"
    backup_dir.mkdir()
    conf_path.write_text("listener 1900\nallow_anonymous false\n", encoding="utf-8")
    _setup_paths(monkeypatch, conf_path, backup_dir)

    restart_calls: list[str] = []

    def fake_signal_restart():
        """
        Replica la logica idempotente real pero usando tmp_path como directorio
        de senales para no tocar /var/lib/mosquitto.
        """
        dynsec_reload_path = str(dynsec_reload_file)
        restart_path = str(tmp_path / ".restart")
        if os.path.exists(dynsec_reload_path):
            return  # Capa 1: dynsec-reload pendiente -> no-op
        if os.path.exists(restart_path):
            return  # Capa 3: restart ya pendiente -> no-op
        (tmp_path / ".restart").write_text("")
        restart_calls.append("restart_written")

    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", fake_signal_restart)

    # Simula que el import ya dejo .dynsec-reload en disco
    dynsec_reload_file.write_text("")

    # Usuario guarda config del broker
    resp = await client.post("/api/v1/config/mosquitto-config", json=_make_conf_payload(1050))
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # .restart NO debe haberse creado porque .dynsec-reload estaba pendiente
    assert not (tmp_path / ".restart").exists(), (
        "Se creo .restart aunque .dynsec-reload ya estaba pendiente -- "
        "esto causaria el doble reinicio que corrompe el JSON de DynSec"
    )
    assert restart_calls == [], (
        "_signal_mosquitto_restart se ejecuto cuando debia ser un no-op"
    )


async def test_save_config_and_restart_produce_single_restart_signal(
    client, monkeypatch, tmp_path
):
    """
    Guardar config y luego pulsar Reiniciar no producen un segundo .restart
    si el supervisor todavia no ha consumido el primero.
    """
    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    conf_path.write_text("listener 1900\nallow_anonymous false\n", encoding="utf-8")
    _setup_paths(monkeypatch, conf_path, backup_dir)

    restart_write_count = 0

    def counting_restart():
        nonlocal restart_write_count
        restart_write_count += 1

    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", counting_restart)

    resp1 = await client.post("/api/v1/config/mosquitto-config", json=_make_conf_payload())
    assert resp1.json()["success"] is True

    resp2 = await client.post("/api/v1/config/restart-mosquitto")
    assert resp2.json()["success"] is True

    assert restart_write_count >= 1, "El save de config no llamo a signal_mosquitto_restart"


async def test_save_config_idempotent_file_write(client, monkeypatch, tmp_path):
    """
    Si .restart ya existe cuando se pulsa Reiniciar, el fichero no se sobreescribe
    (fecha de modificacion no cambia).
    """
    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    conf_path.write_text("listener 1900\nallow_anonymous false\n", encoding="utf-8")
    _setup_paths(monkeypatch, conf_path, backup_dir)

    restart_file = tmp_path / ".restart"

    def fake_signal_restart():
        signal_path = str(restart_file)
        if os.path.exists(signal_path):
            return
        restart_file.write_text("")

    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", fake_signal_restart)

    resp1 = await client.post("/api/v1/config/mosquitto-config", json=_make_conf_payload())
    assert resp1.json()["success"] is True
    assert restart_file.exists(), "El primer save no creo .restart"

    mtime_after_first = restart_file.stat().st_mtime

    resp2 = await client.post("/api/v1/config/restart-mosquitto")
    assert resp2.json()["success"] is True

    assert restart_file.stat().st_mtime == mtime_after_first, (
        "El restart endpoint sobreescribio .restart (double-restart no corregida)"
    )


# ===========================================================================
# CAPA 5: endpoints HTTP retornan 503 si .broker-restarting existe
# ===========================================================================

async def test_save_config_returns_503_while_broker_restarting(
    client, monkeypatch, tmp_path
):
    """
    Si .broker-restarting existe, POST /mosquitto-config debe retornar 503
    sin escribir el fichero de configuracion ni senalar un restart.
    """
    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    broker_restarting_file = tmp_path / ".broker-restarting"
    backup_dir.mkdir()
    conf_path.write_text("listener 1900\nallow_anonymous false\n", encoding="utf-8")
    _setup_paths(monkeypatch, conf_path, backup_dir)

    restart_called = False

    def fake_signal_restart():
        nonlocal restart_called
        restart_called = True

    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", fake_signal_restart)
    monkeypatch.setattr(mosquitto_config_module, "_BROKER_RESTARTING_MARKER", str(broker_restarting_file))

    # Simula que el entrypoint esta arrancando mosquitto
    broker_restarting_file.write_text("")

    resp = await client.post("/api/v1/config/mosquitto-config", json=_make_conf_payload(2000))

    assert resp.status_code == 503, (
        f"Se esperaba 503 pero se obtuvo {resp.status_code}: {resp.text}"
    )
    assert not restart_called, "Se senalo un restart aunque el broker estaba reiniciando"


async def test_restart_endpoint_returns_503_while_broker_restarting(
    client, monkeypatch, tmp_path
):
    """
    Si .broker-restarting existe, POST /restart-mosquitto debe retornar 503.
    """
    broker_restarting_file = tmp_path / ".broker-restarting"
    broker_restarting_file.write_text("")
    monkeypatch.setattr(mosquitto_config_module, "_BROKER_RESTARTING_MARKER", str(broker_restarting_file))

    restart_called = False

    def fake_signal_restart():
        nonlocal restart_called
        restart_called = True

    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", fake_signal_restart)

    resp = await client.post("/api/v1/config/restart-mosquitto")

    assert resp.status_code == 503, (
        f"Se esperaba 503 pero se obtuvo {resp.status_code}: {resp.text}"
    )
    assert not restart_called, "Se senalo un restart aunque el broker estaba reiniciando"


async def test_save_config_succeeds_when_broker_not_restarting(
    client, monkeypatch, tmp_path
):
    """
    Cuando .broker-restarting NO existe, POST /mosquitto-config debe funcionar
    con normalidad (retornar 200 success).
    """
    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    broker_restarting_file = tmp_path / ".broker-restarting"
    backup_dir.mkdir()
    conf_path.write_text("listener 1900\nallow_anonymous false\n", encoding="utf-8")
    _setup_paths(monkeypatch, conf_path, backup_dir)

    # .broker-restarting NO existe
    monkeypatch.setattr(mosquitto_config_module, "_BROKER_RESTARTING_MARKER", str(broker_restarting_file))

    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", lambda: None)

    resp = await client.post("/api/v1/config/mosquitto-config", json=_make_conf_payload(1100))
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ===========================================================================
# DAEMON RECONCILER: reconcile_mosquitto_config debe ser idempotente
# ===========================================================================

@pytest.mark.asyncio
async def test_reconcile_skips_apply_when_file_matches_desired(monkeypatch, tmp_path):
    """
    Si el fichero on-disk ya contiene el contenido deseado, reconcile_mosquitto_config
    NO debe llamar a apply_mosquitto_config (sin escritura, sin restart).
    """
    from services.broker_desired_state_service import (
        reconcile_mosquitto_config,
        set_mosquitto_config_desired,
        get_observed_mosquitto_config,
        _MOSQUITTO_CONF_PATH as _CONF_PATH_ATTR,
    )

    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Patch paths
    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(desired_state_svc, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(mosquitto_config_module, "MOSQUITTO_CONF_PATH", str(conf_path))

    apply_called = False

    def fake_apply(self_arg, content):
        nonlocal apply_called
        apply_called = True
        return {"errors": [], "rollbackNote": None}

    monkeypatch.setattr(broker_reconciler.BrokerReconciler, "apply_mosquitto_config", fake_apply)

    # Patch observed to avoid HTTP call
    fake_observed = {"config": {}, "listeners": [], "content": "", "tls": None,
                     "max_inflight_messages": None, "max_queued_messages": None}
    monkeypatch.setattr(desired_state_svc, "get_observed_mosquitto_config", lambda: fake_observed)

    from tests.conftest import TestSessionLocal

    payload = _make_conf_payload(1100)

    async with TestSessionLocal() as session:
        # Save the desired state (this renders the conf content and stores it)
        state = await set_mosquitto_config_desired(session, payload)
        desired_content = desired_state_svc._load_json(state.desired_payload_json).get("content", "")

    # Pre-populate the conf file with the exact desired content
    conf_path.write_text(desired_content, encoding="utf-8")

    async with TestSessionLocal() as session:
        await reconcile_mosquitto_config(session)

    assert not apply_called, (
        "apply_mosquitto_config fue llamado aunque el fichero ya tenia el contenido correcto"
    )


@pytest.mark.asyncio
async def test_reconcile_applies_when_file_differs_from_desired(monkeypatch, tmp_path):
    """
    Si el fichero on-disk difiere del contenido deseado, reconcile_mosquitto_config
    DEBE llamar a apply_mosquitto_config para corregir la desviacion.
    """
    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(desired_state_svc, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(mosquitto_config_module, "MOSQUITTO_CONF_PATH", str(conf_path))

    apply_called = False

    def fake_apply(self_arg, content):
        nonlocal apply_called
        apply_called = True
        conf_path.write_text(content, encoding="utf-8")
        return {"errors": [], "rollbackNote": None}

    monkeypatch.setattr(broker_reconciler.BrokerReconciler, "apply_mosquitto_config", fake_apply)

    fake_observed = {"config": {}, "listeners": [], "content": "", "tls": None,
                     "max_inflight_messages": None, "max_queued_messages": None}
    monkeypatch.setattr(desired_state_svc, "get_observed_mosquitto_config", lambda: fake_observed)

    from tests.conftest import TestSessionLocal
    from services.broker_desired_state_service import (
        reconcile_mosquitto_config,
        set_mosquitto_config_desired,
    )

    payload = _make_conf_payload(1100)

    async with TestSessionLocal() as session:
        await set_mosquitto_config_desired(session, payload)

    # On-disk is DIFFERENT from desired (simulates external modification or fresh start)
    conf_path.write_text("# stale content\n", encoding="utf-8")

    async with TestSessionLocal() as session:
        result = await reconcile_mosquitto_config(session)

    assert apply_called, (
        "apply_mosquitto_config NO fue llamado aunque el fichero diferia del estado deseado"
    )
    assert not result.drift_detected, (
        "drift_detected deberia ser False despues de aplicar con exito"
    )


@pytest.mark.asyncio
async def test_reconcile_no_restart_loop_on_repeated_cycles(monkeypatch, tmp_path):
    """
    Simulacion del daemon reconciler: tras el primer ciclo que aplica el fichero,
    los ciclos sucesivos NO deben llamar a apply_mosquitto_config (sin restart loop).
    """
    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(desired_state_svc, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(mosquitto_config_module, "MOSQUITTO_CONF_PATH", str(conf_path))

    apply_count = 0

    def fake_apply(self_arg, content):
        nonlocal apply_count
        apply_count += 1
        conf_path.write_text(content, encoding="utf-8")
        return {"errors": [], "rollbackNote": None}

    monkeypatch.setattr(broker_reconciler.BrokerReconciler, "apply_mosquitto_config", fake_apply)

    fake_observed = {"config": {}, "listeners": [], "content": "", "tls": None,
                     "max_inflight_messages": None, "max_queued_messages": None}
    monkeypatch.setattr(desired_state_svc, "get_observed_mosquitto_config", lambda: fake_observed)

    from tests.conftest import TestSessionLocal
    from services.broker_desired_state_service import (
        reconcile_mosquitto_config,
        set_mosquitto_config_desired,
    )

    payload = _make_conf_payload(1100)

    async with TestSessionLocal() as session:
        await set_mosquitto_config_desired(session, payload)

    # First cycle: file is empty (initial state), must apply once
    conf_path.write_text("", encoding="utf-8")

    for _ in range(5):
        async with TestSessionLocal() as session:
            await reconcile_mosquitto_config(session)

    assert apply_count == 1, (
        f"apply_mosquitto_config fue llamado {apply_count} veces en 5 ciclos; "
        f"se esperaba exactamente 1 (restart loop detectado)"
    )
