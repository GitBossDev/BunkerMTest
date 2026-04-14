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
    monkeypatch.setattr(config_router, "parse_mosquitto_conf", lambda: SAMPLE_CONFIG)
    resp = await client.get("/api/v1/config/mosquitto-config")
    assert resp.status_code == 200
    body = resp.json()
    # El router devuelve success=True cuando puede parsear la config
    assert body.get("success") is True


async def test_get_config_requires_auth(raw_client, monkeypatch):
    """Sin autenticacion retorna 401 o 403."""
    monkeypatch.setattr(config_router, "parse_mosquitto_conf", lambda: SAMPLE_CONFIG)
    resp = await raw_client.get("/api/v1/config/mosquitto-config")
    assert resp.status_code in (401, 403)


async def test_get_config_parse_failure(client, monkeypatch):
    """
    Si parse_mosquitto_conf devuelve config vacia, el router retorna
    success=False (degrada con gracia, no lanza 500).
    """
    empty_config = {"config": {}, "listeners": [], "certs": []}
    monkeypatch.setattr(config_router, "parse_mosquitto_conf", lambda: empty_config)
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
    monkeypatch.setattr(config_router, "_signal_mosquitto_reload", lambda: None)
    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_reload", lambda: None)
    monkeypatch.setattr(config_router, "parse_mosquitto_conf", lambda: SAMPLE_CONFIG)

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
    monkeypatch.setattr(config_router, "_signal_mosquitto_reload", lambda: None)
    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_reload", lambda: None)

    resp = await client.post("/api/v1/config/remove-mosquitto-listener", json={"port": 9001})
    assert resp.status_code == 200
    body = resp.json()
    assert body["controlPlane"]["status"] == "applied"

    written = conf_path.read_text(encoding="utf-8")
    assert "listener 9001" not in written
    assert "listener 1900" in written


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
    monkeypatch.setattr(config_router, "_signal_mosquitto_reload", lambda: None)
    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_reload", lambda: None)
    monkeypatch.setattr(config_router, "parse_mosquitto_conf", lambda: SAMPLE_CONFIG)

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
    monkeypatch.setattr(config_router, "parse_mosquitto_conf", lambda: SAMPLE_CONFIG)

    signal_calls = {"count": 0}

    def fail_then_succeed():
        signal_calls["count"] += 1
        if signal_calls["count"] == 1:
            raise RuntimeError("reload failed")

    monkeypatch.setattr(config_router, "_signal_mosquitto_reload", fail_then_succeed)
    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_reload", fail_then_succeed)

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
        "clients": [{"username": "sensor-55", "roles": [], "groups": []}],
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
