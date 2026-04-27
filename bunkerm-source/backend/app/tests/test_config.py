"""
Tests de regresion para el router Config Mosquitto (/api/v1/config).

parse_mosquitto_conf() lee el archivo de configuracion real del broker,
que no esta disponible en el entorno de test. Se mockea a nivel del modulo
del router para devolver una estructura minima valida.
"""
import pytest
import routers.config_mosquitto as config_router
import routers.config_dynsec as config_dynsec_router
import services.broker_desired_state_service as desired_state_svc
import services.broker_reconciler as broker_reconciler
import services.dynsec_service as dynsec_svc
import config.mosquitto_config as mosquitto_config_module
import config.dynsec_config as dynsec_config_module


# Respuesta minima valida de parse_mosquitto_conf()
SAMPLE_CONFIG = {
    "config": {"listener": "1900", "allow_anonymous": "false"},
    "listeners": [],
    "certs": [],
}


# ---------------------------------------------------------------------------
# GET /api/v1/config/mosquitto-config
# ---------------------------------------------------------------------------

async def test_get_config_returns_200(client, monkeypatch):
    """El endpoint retorna 200 con la configuracion parseada."""
    monkeypatch.setattr(
        desired_state_svc,
        "get_observed_mosquitto_config",
        lambda: {
            "config": SAMPLE_CONFIG["config"],
            "listeners": SAMPLE_CONFIG["listeners"],
            "max_inflight_messages": None,
            "max_queued_messages": None,
            "tls": None,
            "content": "listener 1900\nallow_anonymous false\n",
        },
    )
    monkeypatch.setattr(desired_state_svc, "get_observed_tls_cert_store", lambda: {"certs": []})
    resp = await client.get("/api/v1/config/mosquitto-config")
    assert resp.status_code == 200
    body = resp.json()
    # El router devuelve success=True cuando puede parsear la config
    assert body.get("success") is True


async def test_get_config_requires_auth(raw_client, monkeypatch):
    """Sin autenticacion retorna 401 o 403."""
    monkeypatch.setattr(
        desired_state_svc,
        "get_observed_mosquitto_config",
        lambda: {
            "config": SAMPLE_CONFIG["config"],
            "listeners": SAMPLE_CONFIG["listeners"],
            "max_inflight_messages": None,
            "max_queued_messages": None,
            "tls": None,
            "content": "listener 1900\nallow_anonymous false\n",
        },
    )
    monkeypatch.setattr(desired_state_svc, "get_observed_tls_cert_store", lambda: {"certs": []})
    resp = await raw_client.get("/api/v1/config/mosquitto-config")
    assert resp.status_code in (401, 403)


async def test_get_config_parse_failure(client, monkeypatch):
    """
    Si parse_mosquitto_conf devuelve config vacia, el router retorna
    success=False (degrada con gracia, no lanza 500).
    """
    monkeypatch.setattr(
        desired_state_svc,
        "get_observed_mosquitto_config",
        lambda: {
            "config": {},
            "listeners": [],
            "max_inflight_messages": None,
            "max_queued_messages": None,
            "tls": None,
            "content": "",
        },
    )
    monkeypatch.setattr(desired_state_svc, "get_observed_tls_cert_store", lambda: {"certs": []})
    resp = await client.get("/api/v1/config/mosquitto-config")
    assert resp.status_code == 200
    assert resp.json().get("success") is False


async def test_get_mosquitto_config_status_returns_unmanaged_without_desired_state(client, monkeypatch, tmp_path):
    """Sin desired state persistido, el status retorna unmanaged."""
    conf_path = tmp_path / "mosquitto.conf"
    conf_path.write_text("listener 1900\nallow_anonymous false\n", encoding="utf-8")

    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(mosquitto_config_module, "MOSQUITTO_CONF_PATH", str(conf_path))

    resp = await client.get("/api/v1/config/mosquitto-config/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unmanaged"
    assert body["scope"] == "broker.mosquitto_config"


def test_get_observed_mosquitto_config_prefers_observability_in_daemon_mode(monkeypatch, tmp_path):
    """En modo daemon/k8s, la observacion debe venir del broker y no del archivo local del pod web."""
    conf_path = tmp_path / "mosquitto.conf"
    conf_path.write_text("log_dest syslog\n", encoding="utf-8")

    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(desired_state_svc.settings, "broker_reconcile_mode", "daemon")
    monkeypatch.setattr(
        desired_state_svc.broker_observability_client,
        "fetch_broker_mosquitto_config_sync",
        lambda: {
            "config": {"allow_anonymous": "false"},
            "listeners": [
                {
                    "port": 1900,
                    "bind_address": "",
                    "per_listener_settings": False,
                    "max_connections": 500,
                    "protocol": None,
                }
            ],
            "max_inflight_messages": None,
            "max_queued_messages": None,
            "tls": None,
        },
    )

    observed = desired_state_svc.get_observed_mosquitto_config()

    assert observed["listeners"][0]["port"] == 1900
    assert observed["listeners"][0]["max_connections"] == 500
    assert observed["config"]["allow_anonymous"] == "false"


async def test_save_mosquitto_config_uses_desired_state_and_returns_control_plane_metadata(client, monkeypatch, tmp_path):
    """Guardar config pasa por desired state y deja estado aplicado auditable."""
    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    conf_path.write_text("listener 1900\nallow_anonymous false\n", encoding="utf-8")
    backup_dir.mkdir()

    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(desired_state_svc, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(mosquitto_config_module, "MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", lambda: None)
    payload = {
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
                "max_connections": 10000,
                "protocol": None,
            }
        ],
        "max_inflight_messages": 20,
        "max_queued_messages": 100,
        "tls": None,
    }

    resp = await client.post("/api/v1/config/mosquitto-config", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["controlPlane"]["scope"] == "broker.mosquitto_config"
    assert body["controlPlane"]["status"] == "applied"

    status_resp = await client.get("/api/v1/config/mosquitto-config/status")
    status_body = status_resp.json()
    assert status_body["status"] == "applied"
    assert status_body["driftDetected"] is False
    assert "max_inflight_messages 20" in conf_path.read_text(encoding="utf-8")


async def test_save_mosquitto_config_preserves_managed_internal_listener_and_required_defaults(client, monkeypatch, tmp_path):
    """Guardar un cambio parcial no debe borrar el listener interno ni los bloques gestionados del broker."""
    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    conf_path.write_text(
        mosquitto_config_module.DEFAULT_CONFIG,
        encoding="utf-8",
    )
    backup_dir.mkdir()

    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(desired_state_svc, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(mosquitto_config_module, "MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", lambda: None)

    payload = {
        "config": {
            "log_dest": "syslog",
        },
        "listeners": [
            {
                "port": 1900,
                "bind_address": "",
                "per_listener_settings": False,
                "max_connections": 500,
                "protocol": None,
            }
        ],
        "max_inflight_messages": None,
        "max_queued_messages": None,
        "tls": None,
    }

    resp = await client.post("/api/v1/config/mosquitto-config", json=payload)

    assert resp.status_code == 200
    written = conf_path.read_text(encoding="utf-8")
    assert "listener 1900" in written
    assert "max_connections 500" in written
    assert "listener 1901" in written
    assert "max_connections 16" in written
    assert "plugin /usr/lib/mosquitto_dynamic_security.so" in written
    assert "persistence true" in written


async def test_remove_listener_updates_control_plane_state(client, monkeypatch, tmp_path):
    """Eliminar listener genera nuevo desired state y reconcilia el archivo."""
    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    conf_path.write_text(
        "listener 1900\nallow_anonymous false\n\nlistener 9001\nprotocol websockets\n",
        encoding="utf-8",
    )
    backup_dir.mkdir()

    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(desired_state_svc, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(mosquitto_config_module, "MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", lambda: None)

    resp = await client.post("/api/v1/config/remove-mosquitto-listener", json={"port": 9001})
    assert resp.status_code == 200
    body = resp.json()
    assert body["controlPlane"]["status"] == "applied"

    written = conf_path.read_text(encoding="utf-8")
    assert "listener 9001" not in written
    assert "listener 1900" in written


async def test_restart_mosquitto_uses_control_plane_signal(client, monkeypatch):
    """El restart publicado debe delegar la señal al reconciliador broker-facing."""
    calls: list[tuple[tuple, dict]] = []

    async def fake_set_reload_desired(session, payload=None):
        return type(
            "State",
            (),
            {
                "scope": desired_state_svc.BROKER_RELOAD_SCOPE,
                "version": 3,
                "reconcile_status": "pending",
                "drift_detected": False,
                "last_error": None,
            },
        )()

    async def fake_reconcile_or_wait(state, reconcile_action, session, *args, **kwargs):
        calls.append((args, kwargs))
        state.reconcile_status = "applied"
        return state

    monkeypatch.setattr(desired_state_svc, "set_broker_reload_desired", fake_set_reload_desired)
    monkeypatch.setattr(desired_state_svc, "reconcile_or_wait", fake_reconcile_or_wait)

    resp = await client.post("/api/v1/config/restart-mosquitto")

    assert resp.status_code == 200
    assert resp.json()["controlPlane"]["scope"] == desired_state_svc.BROKER_RELOAD_SCOPE
    assert resp.json()["controlPlane"]["status"] == "applied"
    assert calls == [((), {})]


async def test_mosquitto_config_status_detects_drift_after_external_change(client, monkeypatch, tmp_path):
    """Si el archivo cambia fuera del control-plane, el status pasa a drift."""
    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    conf_path.write_text("listener 1900\nallow_anonymous false\n", encoding="utf-8")
    backup_dir.mkdir()

    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(desired_state_svc, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(mosquitto_config_module, "MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", lambda: None)
    payload = {
        "config": {
            "allow_anonymous": "false",
            "plugin": "/usr/lib/mosquitto_dynamic_security.so",
            "plugin_opt_config_file": "/var/lib/mosquitto/dynamic-security.json",
        },
        "listeners": [{"port": 1900, "bind_address": "", "per_listener_settings": False, "max_connections": 10000, "protocol": None}],
        "max_inflight_messages": None,
        "max_queued_messages": None,
        "tls": None,
    }
    save_resp = await client.post("/api/v1/config/mosquitto-config", json=payload)
    assert save_resp.status_code == 200

    conf_path.write_text("listener 1900\nallow_anonymous true\n", encoding="utf-8")

    status_resp = await client.get("/api/v1/config/mosquitto-config/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "drift"
    assert status_resp.json()["driftDetected"] is True


async def test_save_mosquitto_config_returns_500_and_rolls_back_when_reload_fails(client, monkeypatch, tmp_path):
    """Si la recarga falla, el router debe retornar 500 y restaurar el archivo previo."""
    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    original_content = "listener 1900\nallow_anonymous false\n"
    conf_path.write_text(original_content, encoding="utf-8")
    backup_dir.mkdir()

    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(desired_state_svc, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(mosquitto_config_module, "MOSQUITTO_CONF_PATH", str(conf_path))
    signal_calls = {"count": 0}

    def fail_then_succeed():
        signal_calls["count"] += 1
        if signal_calls["count"] == 1:
            raise RuntimeError("reload failed")

    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", fail_then_succeed)

    payload = {
        "config": {
            "allow_anonymous": "false",
            "plugin": "/usr/lib/mosquitto_dynamic_security.so",
            "plugin_opt_config_file": "/var/lib/mosquitto/dynamic-security.json",
        },
        "listeners": [{"port": 1900, "bind_address": "", "per_listener_settings": False, "max_connections": 10000, "protocol": None}],
        "max_inflight_messages": 10,
        "max_queued_messages": 20,
        "tls": None,
    }

    resp = await client.post("/api/v1/config/mosquitto-config", json=payload)
    assert resp.status_code == 500
    assert "rollback applied" in resp.json()["detail"]
    assert conf_path.read_text(encoding="utf-8") == original_content

    status_resp = await client.get("/api/v1/config/mosquitto-config/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "error"



async def test_tls_cert_store_status_returns_unmanaged_without_desired_state(client, monkeypatch, tmp_path):
    """Sin desired state TLS persistido, el status retorna unmanaged."""
    certs_dir = tmp_path / "certs"
    certs_dir.mkdir()
    (certs_dir / "ca.pem").write_text("-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----\n", encoding="utf-8")

    monkeypatch.setattr(desired_state_svc, "_CERTS_DIR", str(certs_dir))
    monkeypatch.setattr(broker_reconciler, "_CERTS_DIR", str(certs_dir))
    monkeypatch.setattr(config_router, "_CERTS_DIR", str(certs_dir))

    resp = await client.get("/api/v1/config/tls-certs/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "broker.tls_certs"
    assert body["status"] == "unmanaged"
    assert body["observed"]["certs"][0]["filename"] == "ca.pem"


async def test_upload_tls_cert_uses_control_plane_and_lists_observed_file(client, monkeypatch, tmp_path):
    """Upload TLS persiste desired state y reconcilia el cert store."""
    certs_dir = tmp_path / "certs"
    certs_dir.mkdir()
    monkeypatch.setattr(desired_state_svc, "_CERTS_DIR", str(certs_dir))
    monkeypatch.setattr(broker_reconciler, "_CERTS_DIR", str(certs_dir))
    monkeypatch.setattr(config_router, "_CERTS_DIR", str(certs_dir))

    files = {"file": ("ca.pem", b"-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----\n", "application/x-pem-file")}
    resp = await client.post("/api/v1/config/tls-certs/upload", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["controlPlane"]["scope"] == "broker.tls_certs"
    assert body["controlPlane"]["status"] == "applied"
    assert (certs_dir / "ca.pem").exists()

    list_resp = await client.get("/api/v1/config/tls-certs")
    assert list_resp.status_code == 200
    assert list_resp.json()["certs"] == ["ca.pem"]


async def test_delete_tls_cert_uses_control_plane_and_removes_file(client, monkeypatch, tmp_path):
    """Delete TLS marca desired delete y reconcilia la ausencia observada."""
    certs_dir = tmp_path / "certs"
    certs_dir.mkdir()
    cert_path = certs_dir / "server.key"
    cert_path.write_text("-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n", encoding="utf-8")

    monkeypatch.setattr(desired_state_svc, "_CERTS_DIR", str(certs_dir))
    monkeypatch.setattr(broker_reconciler, "_CERTS_DIR", str(certs_dir))
    monkeypatch.setattr(config_router, "_CERTS_DIR", str(certs_dir))

    resp = await client.delete("/api/v1/config/tls-certs/server.key")
    assert resp.status_code == 200
    body = resp.json()
    assert body["controlPlane"]["status"] == "applied"
    assert not cert_path.exists()


async def test_tls_cert_status_detects_drift_after_external_change(client, monkeypatch, tmp_path):
    """Si un cert cambia fuera del control-plane, el status TLS pasa a drift."""
    certs_dir = tmp_path / "certs"
    certs_dir.mkdir()
    monkeypatch.setattr(desired_state_svc, "_CERTS_DIR", str(certs_dir))
    monkeypatch.setattr(broker_reconciler, "_CERTS_DIR", str(certs_dir))
    monkeypatch.setattr(config_router, "_CERTS_DIR", str(certs_dir))

    files = {"file": ("ca.pem", b"-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----\n", "application/x-pem-file")}
    upload_resp = await client.post("/api/v1/config/tls-certs/upload", files=files)
    assert upload_resp.status_code == 200

    (certs_dir / "ca.pem").write_text("-----BEGIN CERTIFICATE-----\nxyz\n-----END CERTIFICATE-----\n", encoding="utf-8")

    status_resp = await client.get("/api/v1/config/tls-certs/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "drift"
    assert status_resp.json()["driftDetected"] is True


async def test_upload_tls_cert_returns_500_and_rolls_back_when_reconcile_fails(client, monkeypatch, tmp_path):
    """Si falla la reconciliación TLS, el router debe retornar 500 y revertir el archivo nuevo."""
    certs_dir = tmp_path / "certs"
    certs_dir.mkdir()
    monkeypatch.setattr(desired_state_svc, "_CERTS_DIR", str(certs_dir))
    monkeypatch.setattr(broker_reconciler, "_CERTS_DIR", str(certs_dir))
    monkeypatch.setattr(config_router, "_CERTS_DIR", str(certs_dir))

    original_chmod = broker_reconciler.os.chmod

    def failing_chmod(path, mode):
        if str(path).endswith("ca.pem"):
            raise RuntimeError("chmod failed")
        return original_chmod(path, mode)

    monkeypatch.setattr(broker_reconciler.os, "chmod", failing_chmod)

    files = {"file": ("ca.pem", b"-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----\n", "application/x-pem-file")}
    resp = await client.post("/api/v1/config/tls-certs/upload", files=files)
    assert resp.status_code == 500
    assert "TLS cert store reconciliation failed" in resp.json()["detail"]
    assert not (certs_dir / "ca.pem").exists()

    status_resp = await client.get("/api/v1/config/tls-certs/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "error"


async def test_broker_logs_returns_source_metadata_when_file_missing(client, monkeypatch, tmp_path):
    """El endpoint delega al servicio interno y conserva metadatos de source."""

    async def fake_fetch_broker_logs(limit=1000):
        assert limit == 1000
        return {
            "logs": [],
            "path": str(tmp_path / "missing.log"),
            "error": "Log file not found",
            "source": {
                "path": str(tmp_path / "missing.log"),
                "available": False,
                "mode": "shared-log-file",
            },
        }

    monkeypatch.setattr(config_router.broker_observability_client, "fetch_broker_logs", fake_fetch_broker_logs)

    resp = await client.get("/api/v1/config/broker")
    assert resp.status_code == 200
    body = resp.json()
    assert body["logs"] == []
    assert body["source"]["path"] == str(tmp_path / "missing.log")
    assert body["source"]["available"] is False
    assert body["source"]["mode"] == "shared-log-file"


async def test_broker_log_source_status_returns_200(client, monkeypatch):
    """El endpoint de estado de fuente para logs del broker debe responder siempre."""

    async def fake_fetch_source_status():
        return {"source": {"path": "/var/log/mosquitto/mosquitto.log", "available": True}}

    monkeypatch.setattr(config_router.broker_observability_client, "fetch_broker_log_source_status", fake_fetch_source_status)

    resp = await client.get("/api/v1/config/broker/source-status")
    assert resp.status_code == 200
    body = resp.json()
    assert "source" in body
    assert "path" in body["source"]


async def test_broker_logs_returns_503_when_observability_service_is_unavailable(client, monkeypatch):
    """Si el servicio interno no responde, config/broker debe exponer 503."""

    async def failing_fetch_broker_logs(limit=1000):
        raise config_router.broker_observability_client.BrokerObservabilityUnavailable("dial tcp timeout")

    monkeypatch.setattr(config_router.broker_observability_client, "fetch_broker_logs", failing_fetch_broker_logs)

    resp = await client.get("/api/v1/config/broker")
    assert resp.status_code == 503
    assert "Broker observability service unavailable" in resp.json()["detail"]


async def test_dynsec_json_status_returns_unmanaged_without_desired_state(client, monkeypatch, tmp_path):
    """Sin desired state DynSec persistido, el status retorna unmanaged."""
    from core.database import get_db
    from main import app
    from models.orm import BrokerDesiredState

    dynsec_path = tmp_path / "dynamic-security.json"
    dynsec_path.write_text(
        """
        {
            "defaultACLAccess": {
                "publishClientSend": true,
                "publishClientReceive": true,
                "subscribe": true,
                "unsubscribe": true
            },
            "clients": [],
            "roles": [],
            "groups": []
        }
        """.strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(dynsec_svc.settings, "dynsec_path", str(dynsec_path))

    session_generator = app.dependency_overrides[get_db]()
    session = await anext(session_generator)
    try:
        existing_state = await session.get(BrokerDesiredState, desired_state_svc.DYNSEC_CONFIG_SCOPE)
        if existing_state is not None:
            await session.delete(existing_state)
            await session.commit()
    finally:
        await session_generator.aclose()

    resp = await client.get("/api/v1/config/dynsec-json/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "broker.dynsec_config"
    assert body["status"] == "unmanaged"


async def test_import_dynsec_json_uses_control_plane_and_updates_status(client, monkeypatch, tmp_path):
    """Importar DynSec debe pasar por desired state y dejar estado auditable."""
    dynsec_path = tmp_path / "dynamic-security.json"
    backup_dir = tmp_path / "dynsec-backups"
    backup_dir.mkdir()
    dynsec_path.write_text(
        """
        {
            "defaultACLAccess": {
                "publishClientSend": true,
                "publishClientReceive": true,
                "subscribe": true,
                "unsubscribe": true
            },
            "clients": [{"username": "admin", "roles": [{"rolename": "admin"}]}],
            "roles": [{"rolename": "admin", "acls": []}],
            "groups": []
        }
        """.strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(dynsec_svc.settings, "dynsec_path", str(dynsec_path))
    monkeypatch.setattr(dynsec_config_module, "DYNSEC_JSON_PATH", str(dynsec_path))
    monkeypatch.setattr(dynsec_config_module, "BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_signal_dynsec_reload", lambda: None)

    payload = {
        "defaultACLAccess": {
            "publishClientSend": False,
            "publishClientReceive": True,
            "subscribe": False,
            "unsubscribe": True,
        },
        "clients": [{
            "username": "sensor-55",
            "password": "U2VjdXJlUGFzc3dvcmRIYXNo",
            "salt": "U2FsdFZhbHVl",
            "iterations": 101,
            "roles": [],
            "groups": [],
        }],
        "groups": [],
        "roles": [],
    }

    resp = await client.post(
        "/api/v1/config/import-dynsec-json",
        files={"file": ("dynsec.json", __import__("json").dumps(payload), "application/json")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["controlPlane"]["status"] == "applied"
    assert body["stats"] == {"users": 1, "groups": 0, "roles": 0}

    status_resp = await client.get("/api/v1/config/dynsec-json/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "applied"

    stored = __import__("json").loads(dynsec_path.read_text(encoding="utf-8"))
    assert any(client_entry["username"] == "sensor-55" for client_entry in stored["clients"])


async def test_import_dynsec_json_accepts_broker_managed_clients_without_password_hash(client, monkeypatch, tmp_path):
    """La importación debe aceptar clientes broker-managed sin hash explícito para mantener el round-trip export/import."""
    dynsec_path = tmp_path / "dynamic-security.json"
    backup_dir = tmp_path / "dynsec-backups"
    backup_dir.mkdir()
    dynsec_path.write_text(
        __import__("json").dumps(dynsec_config_module.DEFAULT_CONFIG, indent=2),
        encoding="utf-8",
    )

    monkeypatch.setattr(dynsec_svc.settings, "dynsec_path", str(dynsec_path))
    monkeypatch.setattr(dynsec_config_module, "DYNSEC_JSON_PATH", str(dynsec_path))
    monkeypatch.setattr(dynsec_config_module, "BACKUP_DIR", str(backup_dir))

    payload = {
        "defaultACLAccess": {
            "publishClientSend": False,
            "publishClientReceive": True,
            "subscribe": False,
            "unsubscribe": True,
        },
        "clients": [{"username": "sensor-56", "roles": [], "groups": []}],
        "groups": [],
        "roles": [],
    }

    resp = await client.post(
        "/api/v1/config/import-dynsec-json",
        files={"file": ("dynsec.json", __import__("json").dumps(payload), "application/json")},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["controlPlane"]["status"] == "applied"


async def test_import_dynsec_json_rejects_partial_client_credentials(client, monkeypatch, tmp_path):
    """La importación debe rechazar clientes con credenciales parciales porque el documento quedaría ambiguo."""
    dynsec_path = tmp_path / "dynamic-security.json"
    backup_dir = tmp_path / "dynsec-backups"
    backup_dir.mkdir()
    dynsec_path.write_text(
        __import__("json").dumps(dynsec_config_module.DEFAULT_CONFIG, indent=2),
        encoding="utf-8",
    )

    monkeypatch.setattr(dynsec_svc.settings, "dynsec_path", str(dynsec_path))
    monkeypatch.setattr(dynsec_config_module, "DYNSEC_JSON_PATH", str(dynsec_path))
    monkeypatch.setattr(dynsec_config_module, "BACKUP_DIR", str(backup_dir))

    payload = {
        "defaultACLAccess": {
            "publishClientSend": False,
            "publishClientReceive": True,
            "subscribe": False,
            "unsubscribe": True,
        },
        "clients": [{"username": "sensor-56", "password": "abc", "roles": [], "groups": []}],
        "groups": [],
        "roles": [],
    }

    resp = await client.post(
        "/api/v1/config/import-dynsec-json",
        files={"file": ("dynsec.json", __import__("json").dumps(payload), "application/json")},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "password, salt and iterations together" in body["message"]


async def test_import_dynsec_json_rejects_invalid_merged_document(client, monkeypatch, tmp_path):
    """Si la fusión produce un DynSec inválido, el router debe frenarlo antes del reconciliador."""
    dynsec_path = tmp_path / "dynamic-security.json"
    backup_dir = tmp_path / "dynsec-backups"
    backup_dir.mkdir()
    dynsec_path.write_text(
        __import__("json").dumps(dynsec_config_module.DEFAULT_CONFIG, indent=2),
        encoding="utf-8",
    )

    monkeypatch.setattr(dynsec_svc.settings, "dynsec_path", str(dynsec_path))
    monkeypatch.setattr(dynsec_config_module, "DYNSEC_JSON_PATH", str(dynsec_path))
    monkeypatch.setattr(dynsec_config_module, "BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(
        config_dynsec_router,
        "merge_dynsec_configs",
        lambda imported: {
            **imported,
            "clients": [{"username": "merged-broken", "password": "abc", "roles": [], "groups": []}],
        },
    )

    payload = {
        "defaultACLAccess": {
            "publishClientSend": False,
            "publishClientReceive": True,
            "subscribe": False,
            "unsubscribe": True,
        },
        "clients": [],
        "groups": [],
        "roles": [],
    }

    resp = await client.post(
        "/api/v1/config/import-dynsec-json",
        files={"file": ("dynsec.json", __import__("json").dumps(payload), "application/json")},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "Invalid merged dynamic security JSON format" in body["message"]


async def test_reset_dynsec_json_uses_control_plane(client, monkeypatch, tmp_path):
    """Reset DynSec debe reconciliar el JSON por control-plane y no desde el router."""
    dynsec_path = tmp_path / "dynamic-security.json"
    backup_dir = tmp_path / "dynsec-backups"
    backup_dir.mkdir()
    dynsec_path.write_text(
        """
        {
            "defaultACLAccess": {
                "publishClientSend": false,
                "publishClientReceive": false,
                "subscribe": false,
                "unsubscribe": false
            },
            "clients": [{"username": "sensor-77", "roles": [], "groups": []}],
            "roles": [],
            "groups": []
        }
        """.strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(dynsec_svc.settings, "dynsec_path", str(dynsec_path))
    monkeypatch.setattr(dynsec_config_module, "DYNSEC_JSON_PATH", str(dynsec_path))
    monkeypatch.setattr(dynsec_config_module, "BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_signal_dynsec_reload", lambda: None)

    resp = await client.post("/api/v1/config/reset-dynsec-json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["controlPlane"]["status"] == "applied"

    stored = __import__("json").loads(dynsec_path.read_text(encoding="utf-8"))
    assert stored["clients"][0]["username"] == "admin"
    assert stored["roles"][0]["rolename"] == "admin"


# ---------------------------------------------------------------------------
# Regression tests — Bug: "Duplicate listener port 1900" when conf has
# an explicit `protocol mqtt` line written by a previous save.
# ---------------------------------------------------------------------------

def test_listener_identity_ignores_protocol():
    """Dos listeners con el mismo (port, bind_address) y distinto protocol deben tener
    la misma identidad de merge — el protocol es un atributo, no parte de la clave."""
    from services.broker_desired_state_service import _listener_identity

    with_mqtt   = {"port": 1900, "bind_address": "", "protocol": "mqtt", "max_connections": 10000, "per_listener_settings": False}
    with_none   = {"port": 1900, "bind_address": "", "protocol": None,   "max_connections": 500,  "per_listener_settings": False}
    with_ws     = {"port": 9001, "bind_address": "", "protocol": "websockets", "max_connections": 100, "per_listener_settings": False}

    assert _listener_identity(with_mqtt) == _listener_identity(with_none), \
        "protocol=mqtt y protocol=None deben colapsar a la misma identidad"
    assert _listener_identity(with_mqtt) != _listener_identity(with_ws), \
        "puertos distintos deben tener identidades distintas"


def test_merge_deduplicates_by_port_when_protocols_differ():
    """_merge_listener_payload no debe producir dos entradas para el mismo puerto
    cuando current tiene protocol='mqtt' y requested tiene protocol=None."""
    from services.broker_desired_state_service import _merge_listener_payload

    current   = [{"port": 1900, "bind_address": "", "protocol": "mqtt",   "max_connections": 10000, "per_listener_settings": False}]
    requested = [{"port": 1900, "bind_address": "", "protocol": None,     "max_connections": 500,   "per_listener_settings": False}]

    merged = _merge_listener_payload(current, requested)
    port_1900_entries = [l for l in merged if l["port"] == 1900]

    assert len(port_1900_entries) == 1, \
        f"Se esperaba 1 entrada para puerto 1900, se obtuvieron {len(port_1900_entries)}"
    assert port_1900_entries[0]["max_connections"] == 500, \
        "El valor del requested debe sobrescribir el del current"


def test_merge_always_injects_managed_1901():
    """El listener interno gestionado (1901) siempre debe aparecer en el merged,
    incluso cuando el payload solamente contiene el listener principal."""
    from services.broker_desired_state_service import _merge_listener_payload

    result = _merge_listener_payload(
        [{"port": 1900, "bind_address": "", "protocol": None, "max_connections": 10000, "per_listener_settings": False}],
        [{"port": 1900, "bind_address": "", "protocol": None, "max_connections": 10000, "per_listener_settings": False}],
    )
    ports = [l["port"] for l in result]
    assert 1901 in ports, f"El listener 1901 gestionado debe estar presente; puertos encontrados: {ports}"


def test_merge_managed_listener_cannot_be_overridden():
    """Si el payload intenta redefinir el listener 1901, el managed value debe ganar."""
    from services.broker_desired_state_service import _merge_listener_payload, _MANAGED_MOSQUITTO_INTERNAL_LISTENER

    attempted_override = [
        {"port": 1901, "bind_address": "", "protocol": None, "max_connections": 9999, "per_listener_settings": False}
    ]
    result = _merge_listener_payload([], attempted_override)
    entry_1901 = next((l for l in result if l["port"] == 1901), None)
    assert entry_1901 is not None
    assert entry_1901["max_connections"] == _MANAGED_MOSQUITTO_INTERNAL_LISTENER["max_connections"], \
        "El managed listener debe sobrescribir cualquier intento de override"


def test_merge_requested_wins_over_current():
    """Los valores del requested listener deben sobrescribir los del current para el mismo puerto."""
    from services.broker_desired_state_service import _merge_listener_payload

    current   = [{"port": 1900, "bind_address": "", "protocol": None, "max_connections": 100, "per_listener_settings": False}]
    requested = [{"port": 1900, "bind_address": "", "protocol": None, "max_connections": 888, "per_listener_settings": False}]

    merged = _merge_listener_payload(current, requested)
    entry = next(l for l in merged if l["port"] == 1900)
    assert entry["max_connections"] == 888


async def test_save_mosquitto_config_no_duplicate_when_conf_has_explicit_protocol(
    client, monkeypatch, tmp_path
):
    """Guardar config no debe devolver 'Duplicate listener' cuando el conf actual
    tiene 'protocol mqtt' escrito explícitamente en el listener 1900 (bug recurrente)."""
    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    # Conf de partida: listener con protocol mqtt explícito — estado que queda
    # después de varias iteraciones de guardado anteriores.
    conf_path.write_text(
        "listener 1900\nprotocol mqtt\nallow_anonymous false\n",
        encoding="utf-8",
    )
    backup_dir.mkdir()

    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(desired_state_svc, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(mosquitto_config_module, "MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", lambda: None)

    payload = {
        "config": {"allow_anonymous": "false"},
        "listeners": [
            {"port": 1900, "bind_address": "", "per_listener_settings": False, "max_connections": 10000, "protocol": None}
        ],
        "max_inflight_messages": None,
        "max_queued_messages": None,
        "tls": None,
    }

    resp = await client.post("/api/v1/config/mosquitto-config", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True, f"Se esperaba success=True pero se obtuvo: {body}"
    assert "Duplicate" not in body.get("message", ""), \
        f"El mensaje no debe contener 'Duplicate': {body.get('message', '')}"


async def test_save_mosquitto_config_round_trip_each_port_appears_exactly_once(
    client, monkeypatch, tmp_path
):
    """Tras guardar, cada puerto (1900 y 1901) debe aparecer exactamente una vez
    en el conf generado — nunca duplicado."""
    import re as _re

    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    conf_path.write_text(
        mosquitto_config_module.DEFAULT_CONFIG,
        encoding="utf-8",
    )
    backup_dir.mkdir()

    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(desired_state_svc, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(mosquitto_config_module, "MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", lambda: None)

    payload = {
        "config": {"allow_anonymous": "false"},
        "listeners": [
            {"port": 1900, "bind_address": "", "per_listener_settings": False, "max_connections": 750, "protocol": None},
        ],
        "max_inflight_messages": None,
        "max_queued_messages": None,
        "tls": None,
    }

    resp = await client.post("/api/v1/config/mosquitto-config", json=payload)
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    written = conf_path.read_text(encoding="utf-8")
    occurrences_1900 = len(_re.findall(r"^listener 1900\b", written, _re.MULTILINE))
    occurrences_1901 = len(_re.findall(r"^listener 1901\b", written, _re.MULTILINE))

    assert occurrences_1900 == 1, f"listener 1900 aparece {occurrences_1900} veces (esperado: 1)\n{written}"
    assert occurrences_1901 == 1, f"listener 1901 aparece {occurrences_1901} veces (esperado: 1)\n{written}"
    assert "max_connections 750" in written


def test_validate_listeners_passes_after_merge():
    """validate_listeners no debe detectar duplicados en un payload producido por
    merge_mosquitto_config_payload, incluso cuando current tiene protocol='mqtt'."""
    from services.broker_desired_state_service import merge_mosquitto_config_payload
    from config.mosquitto_config import validate_listeners

    current_payload = {
        "config": {"allow_anonymous": "false"},
        "listeners": [
            {"port": 1900, "bind_address": "", "protocol": "mqtt", "max_connections": 10000, "per_listener_settings": False},
        ],
        "max_inflight_messages": None,
        "max_queued_messages": None,
        "tls": None,
    }
    requested_payload = {
        "config": {"allow_anonymous": "false"},
        "listeners": [
            {"port": 1900, "bind_address": "", "protocol": None, "max_connections": 500, "per_listener_settings": False},
        ],
        "max_inflight_messages": None,
        "max_queued_messages": None,
        "tls": None,
    }

    merged = merge_mosquitto_config_payload(current_payload, requested_payload)
    is_valid, error_msg = validate_listeners(
        current_payload["listeners"],
        merged["listeners"],
    )

    assert is_valid is True, f"validate_listeners rechazó un payload válido: {error_msg}"
    assert error_msg == ""


# ---------------------------------------------------------------------------
# Hardened regression tests — bind_address "0.0.0.0" vs "" mismatch
#
# The production mosquitto.conf uses explicit "listener PORT 0.0.0.0" entries.
# The frontend always sends bind_address:"". Without normalization, both
# (PORT, "0.0.0.0") and (PORT, "") survive as separate dict keys in
# _merge_listener_payload, producing duplicate port entries that fail
# validate_listeners with "Duplicate listener port PORT found in new configuration".
# ---------------------------------------------------------------------------

PRODUCTION_CONF_TEMPLATE = """\
listener 1900 0.0.0.0
protocol mqtt
max_connections 10000
per_listener_settings false

listener 1901 0.0.0.0
protocol mqtt
max_connections 1000

listener 9001 0.0.0.0
protocol websockets
max_connections 10000
"""


def test_normalize_bind_address_treats_zero_zero_as_empty():
    """'0.0.0.0' debe normalizarse a '' ya que ambos significan 'todas las interfaces'."""
    from services.broker_desired_state_service import _normalize_bind_address

    assert _normalize_bind_address("0.0.0.0") == "", "0.0.0.0 debe ser equivalente a empty"
    assert _normalize_bind_address("") == "", "empty queda empty"
    assert _normalize_bind_address(None) == "", "None queda empty"
    assert _normalize_bind_address("::") == "", ":: IPV6 wildcard debe ser empty"
    assert _normalize_bind_address("*") == "", "* wildcard debe ser empty"
    assert _normalize_bind_address("192.168.1.1") == "192.168.1.1", "IP específica se preserva"
    assert _normalize_bind_address("127.0.0.1") == "127.0.0.1", "loopback se preserva"


def test_normalize_listener_entries_collapses_0000_bind():
    """_normalize_listener_entries debe colapsar 0.0.0.0 → '' en cada listener."""
    from services.broker_desired_state_service import _normalize_listener_entries

    raw = [
        {"port": 1900, "bind_address": "0.0.0.0", "protocol": "mqtt", "max_connections": 10000, "per_listener_settings": False},
        {"port": 9001, "bind_address": "0.0.0.0", "protocol": "websockets", "max_connections": 10000, "per_listener_settings": False},
    ]
    result = _normalize_listener_entries(raw)
    for entry in result:
        assert entry["bind_address"] == "", \
            f"bind_address debe ser '' después de normalizar 0.0.0.0, got {entry['bind_address']!r}"


def test_merge_collapses_0000_and_empty_to_single_entry():
    """Cuando current tiene bind='0.0.0.0' y requested tiene bind='', el merge
    (vía la función de alto nivel que normaliza antes) debe producir exactamente
    UNA entrada para ese puerto, no dos."""
    from services.broker_desired_state_service import merge_mosquitto_config_payload

    current_payload = {
        "config": {"allow_anonymous": "false"},
        "listeners": [{"port": 1900, "bind_address": "0.0.0.0", "protocol": "mqtt", "max_connections": 10000, "per_listener_settings": False}],
        "max_inflight_messages": None, "max_queued_messages": None, "tls": None,
    }
    requested_payload = {
        "config": {"allow_anonymous": "false"},
        "listeners": [{"port": 1900, "bind_address": "", "protocol": None, "max_connections": 750, "per_listener_settings": False}],
        "max_inflight_messages": None, "max_queued_messages": None, "tls": None,
    }

    merged = merge_mosquitto_config_payload(current_payload, requested_payload)
    port_1900 = [l for l in merged["listeners"] if l["port"] == 1900]

    assert len(port_1900) == 1, \
        f"Esperado 1 entrada para puerto 1900, obtenido {len(port_1900)}: {port_1900}"
    assert port_1900[0]["max_connections"] == 750, "El requested debe ganar"
    assert port_1900[0]["bind_address"] == "", "bind_address debe normalizarse a ''"


def test_merge_production_conf_three_listeners_0000():
    """Simula el conf de producción real con listener X 0.0.0.0 y el payload del frontend
    con bind_address:''. Todos los puertos deben aparecer exactamente una vez."""
    from services.broker_desired_state_service import _normalize_listener_entries, _merge_listener_payload

    # Estado actual del archivo de producción (parse_mosquitto_conf output)
    current_raw = [
        {"port": 1900, "bind_address": "0.0.0.0", "protocol": "mqtt",       "max_connections": 10000, "per_listener_settings": False},
        {"port": 1901, "bind_address": "0.0.0.0", "protocol": "mqtt",       "max_connections": 1000,  "per_listener_settings": False},
        {"port": 9001, "bind_address": "0.0.0.0", "protocol": "websockets", "max_connections": 10000, "per_listener_settings": False},
    ]
    # Payload del frontend (buildSavePayload con wsEnabled=True)
    requested_raw = [
        {"port": 1900, "bind_address": "", "protocol": None,          "max_connections": 750,   "per_listener_settings": False},
        {"port": 9001, "bind_address": "", "protocol": "websockets",  "max_connections": 750,   "per_listener_settings": False},
    ]

    current   = _normalize_listener_entries(current_raw)
    requested = _normalize_listener_entries(requested_raw)
    merged    = _merge_listener_payload(current, requested)

    ports = [l["port"] for l in merged]
    assert len(ports) == len(set(ports)), f"Se detectaron puertos duplicados en el merge: {ports}"
    assert set(ports) == {1900, 1901, 9001}, f"Puertos esperados {{1900, 1901, 9001}}, obtenidos {set(ports)}"

    entry_1901 = next(l for l in merged if l["port"] == 1901)
    assert entry_1901["max_connections"] == 16, "El managed listener 1901 debe tener max_connections=16"
    assert entry_1901["bind_address"] == "", "El managed listener 1901 debe tener bind_address=''"


async def test_save_mosquitto_config_production_conf_0000_no_duplicate(client, monkeypatch, tmp_path):
    """Caso de fallo real de producción: conf con 'listener PORT 0.0.0.0' y
    frontend enviando bind_address:''. El save NO debe devolver 'Duplicate listener'."""
    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    conf_path.write_text(PRODUCTION_CONF_TEMPLATE, encoding="utf-8")
    backup_dir.mkdir()

    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(desired_state_svc, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(mosquitto_config_module, "MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", lambda: None)

    # Exactamente el payload que buildSavePayload() del frontend genera
    payload = {
        "config": {"allow_anonymous": "false"},
        "listeners": [
            {"port": 1900, "bind_address": "", "per_listener_settings": False, "max_connections": 750, "protocol": None},
            {"port": 9001, "bind_address": "", "per_listener_settings": False, "max_connections": 750, "protocol": "websockets"},
        ],
        "max_inflight_messages": None,
        "max_queued_messages": None,
        "tls": {"enabled": False, "port": 8883, "cafile": None, "certfile": None, "keyfile": None, "require_certificate": False, "tls_version": None},
    }

    resp = await client.post("/api/v1/config/mosquitto-config", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True, f"Se esperaba success=True, obtenido: {body}"
    assert "Duplicate" not in body.get("message", ""), \
        f"El mensaje NO debe contener 'Duplicate': {body.get('message', '')}"


async def test_save_mosquitto_config_second_save_after_production_conf(client, monkeypatch, tmp_path):
    """Segunda iteración de save: después de que BHM escribe el conf (sin 0.0.0.0),
    el siguiente save tampoco debe generar duplicados."""
    import re as _re

    conf_path = tmp_path / "mosquitto.conf"
    backup_dir = tmp_path / "backups"
    conf_path.write_text(PRODUCTION_CONF_TEMPLATE, encoding="utf-8")
    backup_dir.mkdir()

    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(desired_state_svc, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(mosquitto_config_module, "MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", lambda: None)

    base_payload = {
        "config": {"allow_anonymous": "false"},
        "listeners": [
            {"port": 1900, "bind_address": "", "per_listener_settings": False, "max_connections": 750, "protocol": None},
            {"port": 9001, "bind_address": "", "per_listener_settings": False, "max_connections": 750, "protocol": "websockets"},
        ],
        "max_inflight_messages": None,
        "max_queued_messages": None,
        "tls": {"enabled": False, "port": 8883, "cafile": None, "certfile": None, "keyfile": None, "require_certificate": False, "tls_version": None},
    }

    # Primera iteración — conf original con 0.0.0.0
    resp1 = await client.post("/api/v1/config/mosquitto-config", json=base_payload)
    assert resp1.status_code == 200
    assert resp1.json()["success"] is True, f"Primera iteración falló: {resp1.json()}"

    # Segunda iteración — conf ya fue escrito por BHM (sin 0.0.0.0)
    payload2 = {**base_payload, "listeners": [
        {"port": 1900, "bind_address": "", "per_listener_settings": False, "max_connections": 500, "protocol": None},
        {"port": 9001, "bind_address": "", "per_listener_settings": False, "max_connections": 500, "protocol": "websockets"},
    ]}
    resp2 = await client.post("/api/v1/config/mosquitto-config", json=payload2)
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["success"] is True, f"Segunda iteración falló: {body2}"
    assert "Duplicate" not in body2.get("message", ""), f"Duplicate en segunda iteración: {body2}"

    written = conf_path.read_text(encoding="utf-8")
    assert len(_re.findall(r"^listener 1900\b", written, _re.MULTILINE)) == 1, \
        "listener 1900 debe aparecer exactamente 1 vez"
    assert len(_re.findall(r"^listener 1901\b", written, _re.MULTILINE)) == 1, \
        "listener 1901 debe aparecer exactamente 1 vez"
    assert len(_re.findall(r"^listener 9001\b", written, _re.MULTILINE)) == 1, \
        "listener 9001 debe aparecer exactamente 1 vez"
    assert "0.0.0.0" not in written, \
        "El conf generado por BHM no debe contener 0.0.0.0 (bind normalizado a '')"
    assert "max_connections 500" in written, "El nuevo max_connections debe estar en el conf"


def test_save_mosquitto_config_daemon_mode_observed_config_0000_no_duplicate(monkeypatch, tmp_path):
    """En daemon mode (producción), get_observed_mosquitto_config() con el observability
    client devolviendo listeners con bind_address='0.0.0.0' debe normalizar los listeners
    y producir identidades únicas (sin duplicados por diferencia de bind_address)."""
    conf_path = tmp_path / "mosquitto.conf"
    conf_path.write_text(PRODUCTION_CONF_TEMPLATE, encoding="utf-8")

    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_CONF_PATH", str(conf_path))
    monkeypatch.setattr(desired_state_svc.settings, "broker_reconcile_mode", "daemon")
    monkeypatch.setattr(
        desired_state_svc.broker_observability_client,
        "fetch_broker_mosquitto_config_sync",
        lambda: {
            "config": {"allow_anonymous": "false", "plugin": "/usr/lib/mosquitto_dynamic_security.so"},
            "listeners": [
                {"port": 1900, "bind_address": "0.0.0.0", "protocol": "mqtt",       "max_connections": 10000, "per_listener_settings": False},
                {"port": 1901, "bind_address": "0.0.0.0", "protocol": "mqtt",       "max_connections": 1000,  "per_listener_settings": False},
                {"port": 9001, "bind_address": "0.0.0.0", "protocol": "websockets", "max_connections": 10000, "per_listener_settings": False},
            ],
            "max_inflight_messages": None,
            "max_queued_messages": None,
            "tls": None,
        },
    )

    observed = desired_state_svc.get_observed_mosquitto_config()

    # Todos los bind_address deben estar normalizados a ''
    for listener in observed["listeners"]:
        assert listener["bind_address"] == "", \
            f"En daemon mode, bind_address debe ser '' (normalizado desde 0.0.0.0): {listener}"

    # No deben existir puertos duplicados
    ports = [l["port"] for l in observed["listeners"]]
    assert len(ports) == len(set(ports)), f"Existen puertos duplicados en observed: {ports}"

    # El merge posterior no debe producir duplicados con payload frontend
    from services.broker_desired_state_service import merge_mosquitto_config_payload

    requested_payload = {
        "config": {"allow_anonymous": "false"},
        "listeners": [
            {"port": 1900, "bind_address": "", "per_listener_settings": False, "max_connections": 750, "protocol": None},
            {"port": 9001, "bind_address": "", "per_listener_settings": False, "max_connections": 750, "protocol": "websockets"},
        ],
        "max_inflight_messages": None, "max_queued_messages": None, "tls": None,
    }
    merged = merge_mosquitto_config_payload(observed, requested_payload)
    merged_ports = [l["port"] for l in merged["listeners"]]
    assert len(merged_ports) == len(set(merged_ports)), \
        f"Existen puertos duplicados en el merge daemon+frontend: {merged_ports}"


def test_managed_1901_overrides_0000_bind_production_conf():
    """El managed listener 1901 (bind:'') debe sobrescribir el listener 1901 de
    producción (bind:'0.0.0.0') después de la normalización."""
    from services.broker_desired_state_service import (
        _merge_listener_payload, _normalize_listener_entries, _MANAGED_MOSQUITTO_INTERNAL_LISTENER,
    )

    # Estado del conf de producción
    current_raw = [
        {"port": 1901, "bind_address": "0.0.0.0", "protocol": "mqtt", "max_connections": 1000, "per_listener_settings": False},
    ]
    current = _normalize_listener_entries(current_raw)
    result = _merge_listener_payload(current, [])

    entry_1901 = next((l for l in result if l["port"] == 1901), None)
    assert entry_1901 is not None, "El managed listener 1901 debe estar siempre presente"
    assert entry_1901["max_connections"] == _MANAGED_MOSQUITTO_INTERNAL_LISTENER["max_connections"], \
        "El managed listener debe imponer max_connections=16 sobre el 1000 del conf de producción"
    assert entry_1901["bind_address"] == "", \
        "El managed listener usa bind_address='' (no 0.0.0.0)"

    port_1901_count = sum(1 for l in result if l["port"] == 1901)
    assert port_1901_count == 1, "Solo debe haber una entrada para el puerto 1901"
