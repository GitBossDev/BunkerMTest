"""
Tests de regresion para el router DynSec (/api/v1/dynsec).

Cubre los endpoints criticos de gestion de clientes, roles y grupos MQTT.
Los servicios externos (mosquitto_ctrl, dynamic-security.json) se mockean
para que los tests no dependan del broker en ejecucion.
"""
import json
from types import SimpleNamespace

import pytest
from clientlogs.activity_storage import client_activity_storage
import services.dynsec_service as dynsec_svc
from services import broker_desired_state_service as desired_state_svc
import services.broker_reconciler as broker_reconciler
from config.dynsec_config import merge_dynsec_configs, validate_dynsec_json

# Estructura minima valida de dynamic-security.json para los mocks
SAMPLE_DYNSEC = {
    "defaultACLAccess": {
        "publishClientSend": True,
        "publishClientReceive": False,
        "subscribe": False,
        "unsubscribe": True,
    },
    "clients": [
        {
            "username": "admin",
            "textname": "Dynsec admin user",
            "roles": [{"rolename": "admin"}],
            "password": "admin-hash",
            "salt": "admin-salt",
            "iterations": 101,
        },
        {"username": "sensor-01", "textname": "Sensor de prueba", "groups": [], "roles": [{"rolename": "sensors"}]}
    ],
    "roles": [
        {"rolename": "admin", "acls": []},
        {"rolename": "sensors", "acls": []}
    ],
    "groups": [
        {"groupname": "plantas", "roles": [], "clients": []}
    ],
}

# Respuesta exitosa de mosquitto_ctrl
CMD_OK = {"success": True, "output": "Command executed successfully", "error_output": ""}


# ---------------------------------------------------------------------------
# GET /api/v1/dynsec/clients
# ---------------------------------------------------------------------------

async def test_list_clients_returns_200(client, monkeypatch):
    """Lista de clientes: retorna 200 y un array 'clients'."""
    monkeypatch.setattr(desired_state_svc, "get_observed_dynsec_config", lambda: SAMPLE_DYNSEC)
    monkeypatch.setattr(client_activity_storage, "reconcile_dynsec_clients", lambda *_args, **_kwargs: None)
    resp = await client.get("/api/v1/dynsec/clients")
    assert resp.status_code == 200
    body = resp.json()
    assert "clients" in body
    assert any(c["username"] == "sensor-01" for c in body["clients"])
    assert body["total"] == 2


async def test_list_clients_returns_paginated_normalized_shape(client, monkeypatch):
    """El listado normaliza roles/grupos y retorna metadatos de paginación."""
    dynsec = {
        **SAMPLE_DYNSEC,
        "clients": [
            {
                "username": "admin",
                "disabled": False,
                "roles": [{"rolename": "admin"}],
                "groups": [],
            },
            {
                "username": "sensor-01",
                "disabled": False,
                "roles": [{"rolename": "sensors"}],
                "groups": [{"groupname": "plantas"}],
            },
            {
                "username": "sensor-02",
                "disabled": True,
                "roles": ["operators"],
                "groups": ["line-a"],
            },
        ],
        "roles": [
            {"rolename": "admin", "acls": []},
            {"rolename": "sensors", "acls": []},
            {"rolename": "operators", "acls": []},
        ],
        "groups": [
            {"groupname": "plantas", "roles": [], "clients": []},
            {"groupname": "line-a", "roles": [], "clients": []},
        ],
    }
    monkeypatch.setattr(desired_state_svc, "get_observed_dynsec_config", lambda: dynsec)
    monkeypatch.setattr(client_activity_storage, "reconcile_dynsec_clients", lambda *_args, **_kwargs: None)
    resp = await client.get("/api/v1/dynsec/clients?page=1&limit=1&search=sensor")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 1
    assert body["limit"] == 1
    assert body["total"] == 2
    assert body["pages"] == 2
    assert body["clients"][0]["roles"] == ["sensors"]
    assert body["clients"][0]["groups"] == ["plantas"]


async def test_get_clients_disabled_map_returns_all_clients(client, monkeypatch):
    """Connected Clients usa disabled-map para poblar todos los usernames sin N+1."""
    dynsec = {
        **SAMPLE_DYNSEC,
        "clients": [
            {"username": "admin", "disabled": False},
            {"username": "sensor-01", "disabled": False},
            {"username": "sensor-02", "disabled": True},
        ],
    }
    monkeypatch.setattr(desired_state_svc, "get_observed_dynsec_config", lambda: dynsec)
    monkeypatch.setattr(client_activity_storage, "reconcile_dynsec_clients", lambda *_args, **_kwargs: None)
    resp = await client.get("/api/v1/dynsec/clients/disabled-map")
    assert resp.status_code == 200
    body = resp.json()
    assert body["map"] == {"admin": False, "sensor-01": False, "sensor-02": True}
    assert body["usernames"] == ["admin", "sensor-01", "sensor-02"]


async def test_get_default_acl_reads_json_directly(client, monkeypatch):
    """El endpoint no debe depender del parseo textual de mosquitto_ctrl."""
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: SAMPLE_DYNSEC)
    resp = await client.get("/api/v1/dynsec/default-acl")
    assert resp.status_code == 200
    assert resp.json() == SAMPLE_DYNSEC["defaultACLAccess"]


async def test_get_default_acl_status_returns_unmanaged_without_desired_state(client, monkeypatch):
    """Sin estado deseado persistido, el control-plane expone el estado observado actual."""
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: SAMPLE_DYNSEC)
    resp = await client.get("/api/v1/dynsec/default-acl/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unmanaged"
    assert body["observed"] == SAMPLE_DYNSEC["defaultACLAccess"]


async def test_set_default_acl_uses_desired_state_and_returns_control_plane_metadata(client, monkeypatch):
    """El PUT persiste desired state y delega la reconciliación al servicio."""
    dynsec_doc = {
        **SAMPLE_DYNSEC,
        "defaultACLAccess": {
            "publishClientSend": True,
            "publishClientReceive": True,
            "subscribe": True,
            "unsubscribe": True,
        },
    }

    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: dynsec_doc)
    monkeypatch.setattr(dynsec_svc, "execute_mosquitto_command", lambda *a, **kw: CMD_OK)

    def _write_dynsec(data):
        dynsec_doc["defaultACLAccess"] = data["defaultACLAccess"]

    monkeypatch.setattr(dynsec_svc, "write_dynsec", _write_dynsec)

    payload = {
        "publishClientSend": False,
        "publishClientReceive": False,
        "subscribe": True,
        "unsubscribe": False,
    }
    resp = await client.put("/api/v1/dynsec/default-acl", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["config"] == payload
    assert body["controlPlane"]["scope"] == desired_state_svc.DEFAULT_ACL_SCOPE
    assert body["controlPlane"]["status"] == "applied"

    status_resp = await client.get("/api/v1/dynsec/default-acl/status")
    assert status_resp.status_code == 200
    status_body = status_resp.json()
    assert status_body["desired"] == payload
    assert status_body["observed"] == payload
    assert status_body["driftDetected"] is False


async def test_set_default_acl_in_daemon_mode_waits_for_reconcile_settlement(client, monkeypatch):
    """En modo daemon, el PUT debe resolver por espera de settlement y no por aplicación inline."""
    wait_calls: list[tuple[tuple, dict]] = []

    async def fake_set_default_acl_desired(session, updates):
        return SimpleNamespace(
            scope=desired_state_svc.DEFAULT_ACL_SCOPE,
            version=4,
            reconcile_status="pending",
            drift_detected=False,
            last_error=None,
        )

    async def fake_reconcile_or_wait(state, reconcile_action, session, *args, **kwargs):
        wait_calls.append((args, kwargs))
        return SimpleNamespace(
            scope=state.scope,
            version=state.version,
            reconcile_status="applied",
            drift_detected=False,
            last_error=None,
        )

    monkeypatch.setattr(desired_state_svc, "set_default_acl_desired", fake_set_default_acl_desired)
    monkeypatch.setattr(desired_state_svc, "reconcile_or_wait", fake_reconcile_or_wait)

    payload = {
        "publishClientSend": False,
        "publishClientReceive": True,
        "subscribe": False,
        "unsubscribe": True,
    }
    resp = await client.put("/api/v1/dynsec/default-acl", json=payload)

    assert resp.status_code == 200
    assert wait_calls == [((), {})]
    assert resp.json()["controlPlane"]["status"] == "applied"


def test_merge_dynsec_configs_preserves_imported_default_acl(monkeypatch):
    """La importación debe conservar defaultACLAccess del JSON subido."""
    imported = {
        "defaultACLAccess": {
            "publishClientSend": False,
            "publishClientReceive": False,
            "subscribe": True,
            "unsubscribe": False,
        },
        "clients": [{"username": "sensor-01", "roles": [], "groups": []}],
        "groups": [],
        "roles": [],
    }
    monkeypatch.setattr(
        "config.dynsec_config.read_dynsec_json",
        lambda: {"clients": [{"username": "admin", "roles": [{"rolename": "admin"}]}]},
    )
    merged = merge_dynsec_configs(imported)
    assert merged["defaultACLAccess"] == imported["defaultACLAccess"]


def test_merge_dynsec_configs_prefers_observed_admin_user(monkeypatch):
    """En Kubernetes, la importacion debe preservar el admin observado aunque el pod web no monte el JSON local."""
    observed_admin = {
        "username": "admin",
        "textname": "Dynsec admin user",
        "roles": [{"rolename": "admin"}],
        "password": "observed-hash",
        "salt": "observed-salt",
        "iterations": 101,
    }
    imported = {
        "defaultACLAccess": SAMPLE_DYNSEC["defaultACLAccess"],
        "clients": [{"username": "sensor-01", "roles": [], "groups": []}],
        "groups": [],
        "roles": [],
    }

    monkeypatch.setattr(
        "services.broker_observability_client.fetch_broker_dynsec_sync",
        lambda: {"config": {"clients": [observed_admin], "roles": [], "groups": [], "defaultACLAccess": SAMPLE_DYNSEC["defaultACLAccess"]}},
    )
    monkeypatch.setattr("config.dynsec_config.read_dynsec_json", lambda: (_ for _ in ()).throw(FileNotFoundError()))

    merged = merge_dynsec_configs(imported)

    assert merged["clients"][0]["password"] == "observed-hash"
    assert merged["clients"][0]["salt"] == "observed-salt"


def test_get_observed_helpers_fall_back_to_observability_when_local_dynsec_is_unavailable(monkeypatch):
    """Las mutaciones DynSec no deben depender del fichero local dentro del pod web."""
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(
        desired_state_svc,
        "get_observed_dynsec_config",
        lambda: SAMPLE_DYNSEC,
    )

    observed_client = desired_state_svc.get_observed_client("sensor-01")
    observed_role = desired_state_svc.get_observed_role("sensors")
    observed_group = desired_state_svc.get_observed_group("plantas")
    observed_default_acl = desired_state_svc.get_observed_default_acl()

    assert observed_client is not None
    assert observed_client["username"] == "sensor-01"
    assert observed_role is not None
    assert observed_role["rolename"] == "sensors"
    assert observed_group is not None
    assert observed_group["groupname"] == "plantas"
    assert observed_default_acl == SAMPLE_DYNSEC["defaultACLAccess"]


def test_validate_dynsec_json_accepts_broker_managed_clients_without_credentials():
    """Los clientes creados por mosquitto_ctrl pueden no exponer hash en el JSON observado."""
    payload = {
        "defaultACLAccess": {
            "publishClientSend": True,
            "publishClientReceive": True,
            "subscribe": True,
            "unsubscribe": True,
        },
        "clients": [
            {
                "username": "admin",
                "password": "hash",
                "salt": "salt",
                "iterations": 101,
                "roles": [{"rolename": "admin"}],
            },
            {
                "username": "sensor-observed",
                "roles": [],
                "groups": [],
            },
        ],
        "groups": [],
        "roles": [{"rolename": "admin", "acls": []}],
    }

    validated = validate_dynsec_json(payload)
    assert validated["clients"][1]["username"] == "sensor-observed"


def test_validate_dynsec_json_rejects_partial_client_credentials():
    """Si aparecen campos de credenciales, deben venir completos para evitar documentos ambiguos."""
    payload = {
        "defaultACLAccess": {
            "publishClientSend": True,
            "publishClientReceive": True,
            "subscribe": True,
            "unsubscribe": True,
        },
        "clients": [
            {
                "username": "admin",
                "password": "hash",
                "salt": "salt",
                "iterations": 101,
                "roles": [{"rolename": "admin"}],
            },
            {
                "username": "sensor-broken",
                "password": "hash-only",
                "roles": [],
                "groups": [],
            },
        ],
        "groups": [],
        "roles": [{"rolename": "admin", "acls": []}],
    }

    with pytest.raises(ValueError, match="password, salt and iterations together"):
        validate_dynsec_json(payload)


async def test_list_clients_requires_auth(raw_client, monkeypatch):
    """Sin X-API-Key el endpoint debe rechazar la peticion (401 o 403)."""
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: SAMPLE_DYNSEC)
    resp = await raw_client.get("/api/v1/dynsec/clients")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /api/v1/dynsec/clients/{username}
# ---------------------------------------------------------------------------

async def test_get_client_found(client, monkeypatch):
    """Buscar un cliente existente retorna 200 con su username dentro de 'client'."""
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: SAMPLE_DYNSEC)
    resp = await client.get("/api/v1/dynsec/clients/sensor-01")
    assert resp.status_code == 200
    body = resp.json()
    # El router envuelve el resultado en {"client": {...}}
    assert body.get("client", {}).get("username") == "sensor-01"


async def test_get_client_normalizes_role_and_group_entries(client, monkeypatch):
    """El detalle del cliente debe exponer nombres compatibles con la UI."""
    dynsec = {
        **SAMPLE_DYNSEC,
        "clients": [
            {
                "username": "sensor-01",
                "textname": "Sensor",
                "roles": [{"rolename": "sensors", "priority": 7}],
                "groups": [{"groupname": "plantas", "priority": 3}],
            }
        ],
    }
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: dynsec)
    resp = await client.get("/api/v1/dynsec/clients/sensor-01")
    assert resp.status_code == 200
    body = resp.json()["client"]
    assert body["roles"] == [{"rolename": "sensors", "name": "sensors", "priority": 7}]
    assert body["groups"] == [{"groupname": "plantas", "name": "plantas", "priority": 3}]


async def test_get_client_status_returns_unmanaged_without_desired_state(client, monkeypatch):
    """Sin desired state persistido, el estado del cliente refleja solo lo observado."""
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: SAMPLE_DYNSEC)
    resp = await client.get("/api/v1/dynsec/clients/sensor-01/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unmanaged"
    assert body["observed"]["username"] == "sensor-01"
    assert body["observed"]["disabled"] is False


async def test_get_client_not_found(client, monkeypatch):
    """Buscar un cliente inexistente retorna 404."""
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: SAMPLE_DYNSEC)
    resp = await client.get("/api/v1/dynsec/clients/cliente-inexistente-xyz")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/dynsec/clients
# ---------------------------------------------------------------------------

async def test_create_client_success(client, monkeypatch):
    """Crear cliente con datos validos: retorna 201."""
    monkeypatch.setattr(dynsec_svc, "execute_mosquitto_command", lambda *a, **kw: CMD_OK)
    dynsec_doc = {**SAMPLE_DYNSEC, "clients": list(SAMPLE_DYNSEC["clients"])}
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: dynsec_doc)
    monkeypatch.setattr(dynsec_svc, "write_dynsec", lambda data: dynsec_doc.update(data))
    payload = {"username": "nuevo-sensor", "password": "SecurePass123"}
    resp = await client.post("/api/v1/dynsec/clients", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["controlPlane"]["status"] == "applied"

    status_resp = await client.get("/api/v1/dynsec/clients/nuevo-sensor/status")
    assert status_resp.status_code == 200
    status_body = status_resp.json()
    assert status_body["desired"]["username"] == "nuevo-sensor"
    assert status_body["desired"]["disabled"] is False
    assert status_body["observed"]["username"] == "nuevo-sensor"


async def test_create_client_in_daemon_mode_stages_ephemeral_secret_and_waits(client, monkeypatch):
    """En modo daemon, create client debe stagear el secreto efímero en el control-plane."""
    staged: list[tuple[str, int, str]] = []
    wait_calls: list[tuple[tuple, dict]] = []

    async def fake_set_client_desired(session, payload):
        return SimpleNamespace(
            scope=f"{desired_state_svc.CLIENT_SCOPE_PREFIX}{payload['username']}",
            version=7,
            reconcile_status="pending",
            drift_detected=False,
            last_error=None,
        )

    async def fake_reconcile_or_wait(state, reconcile_action, session, *args, **kwargs):
        wait_calls.append((args, kwargs))
        return SimpleNamespace(
            scope=state.scope,
            version=state.version,
            reconcile_status="applied",
            drift_detected=False,
            last_error=None,
        )

    monkeypatch.setattr(desired_state_svc, "is_daemon_reconcile_mode", lambda: True)
    monkeypatch.setattr(desired_state_svc, "set_client_desired", fake_set_client_desired)

    async def fake_stage_client_creation_secret(session, username, version, password):
        staged.append((username, version, password))

    monkeypatch.setattr(
        desired_state_svc,
        "stage_client_creation_secret",
        fake_stage_client_creation_secret,
    )
    monkeypatch.setattr(desired_state_svc, "reconcile_or_wait", fake_reconcile_or_wait)
    monkeypatch.setattr(client_activity_storage, "upsert_client", lambda *args, **kwargs: None)

    resp = await client.post(
        "/api/v1/dynsec/clients",
        json={"username": "daemon-sensor", "password": "SecurePass123"},
    )

    assert resp.status_code == 201
    assert staged == [("daemon-sensor", 7, "SecurePass123")]
    assert wait_calls == [(("daemon-sensor",), {})]
    assert resp.json()["controlPlane"]["status"] == "applied"


async def test_disable_client_updates_desired_state_and_status(client, monkeypatch):
    """Disable debe persistir desired state del cliente y reconciliar el JSON."""
    dynsec_doc = {
        **SAMPLE_DYNSEC,
        "clients": [
            {
                "username": "sensor-01",
                "textname": "Sensor de prueba",
                "groups": [],
                "roles": [{"rolename": "sensors"}],
                "disabled": False,
            }
        ],
    }
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: dynsec_doc)
    monkeypatch.setattr(dynsec_svc, "execute_mosquitto_command", lambda *a, **kw: CMD_OK)
    monkeypatch.setattr(dynsec_svc, "write_dynsec", lambda data: dynsec_doc.update(data))

    resp = await client.put("/api/v1/dynsec/clients/sensor-01/disable")
    assert resp.status_code == 200
    assert resp.json()["controlPlane"]["status"] == "applied"

    status_resp = await client.get("/api/v1/dynsec/clients/sensor-01/status")
    assert status_resp.status_code == 200
    status_body = status_resp.json()
    assert status_body["desired"]["disabled"] is True
    assert status_body["observed"]["disabled"] is True


async def test_add_and_remove_client_role_updates_control_plane_state(client, monkeypatch):
    """La asignacion y remocion de roles debe pasar por desired state del cliente."""
    dynsec_doc = {
        **SAMPLE_DYNSEC,
        "clients": [
            {
                "username": "sensor-01",
                "textname": "Sensor de prueba",
                "groups": [],
                "roles": [{"rolename": "sensors", "priority": 1}],
                "disabled": False,
            }
        ],
    }
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: dynsec_doc)
    monkeypatch.setattr(dynsec_svc, "execute_mosquitto_command", lambda *a, **kw: CMD_OK)
    monkeypatch.setattr(dynsec_svc, "write_dynsec", lambda data: dynsec_doc.update(data))

    add_resp = await client.post(
        "/api/v1/dynsec/clients/sensor-01/roles",
        json={"role_name": "operators", "priority": 5},
    )
    assert add_resp.status_code == 200
    add_status = await client.get("/api/v1/dynsec/clients/sensor-01/status")
    assert add_status.status_code == 200
    add_body = add_status.json()
    assert any(role["rolename"] == "operators" for role in add_body["desired"]["roles"])

    remove_resp = await client.delete("/api/v1/dynsec/clients/sensor-01/roles/operators")
    assert remove_resp.status_code == 200
    remove_status = await client.get("/api/v1/dynsec/clients/sensor-01/status")
    assert remove_status.status_code == 200
    remove_body = remove_status.json()
    assert all(role["rolename"] != "operators" for role in remove_body["desired"]["roles"])


async def test_sync_passwd_to_dynsec_uses_control_plane_and_updates_dynsec_json(client, monkeypatch, tmp_path):
    """El sync desde mosquitto_passwd debe reconciliar DynSec vía control-plane."""
    dynsec_path = tmp_path / "dynamic-security.json"
    passwd_path = tmp_path / "mosquitto_passwd"
    dynsec_path.write_text(json.dumps(SAMPLE_DYNSEC), encoding="utf-8")
    passwd_path.write_text("sensor-01:$7$existing\nsensor-99:$7$newhash\n", encoding="utf-8")

    monkeypatch.setattr(dynsec_svc.settings, "dynsec_path", str(dynsec_path))
    monkeypatch.setattr(dynsec_svc.settings, "mosquitto_passwd_path", str(passwd_path))
    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_PASSWD_PATH", str(passwd_path))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_PASSWD_PATH", str(passwd_path))
    monkeypatch.setattr(broker_reconciler, "_signal_dynsec_reload", lambda: None)
    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", lambda: None)

    resp = await client.post("/api/v1/dynsec/sync-passwd-to-dynsec")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert body["controlPlane"]["scope"] == desired_state_svc.DYNSEC_CONFIG_SCOPE
    assert body["controlPlane"]["status"] == "applied"
    assert body["passwdControlPlane"]["scope"] == desired_state_svc.MOSQUITTO_PASSWD_SCOPE
    assert body["passwdControlPlane"]["status"] == "applied"

    stored = json.loads(dynsec_path.read_text(encoding="utf-8"))
    assert any(client_entry["username"] == "sensor-99" for client_entry in stored["clients"])


async def test_import_password_file_uses_passwd_control_plane_and_exposes_status(client, monkeypatch, tmp_path):
    """La importación del passwd debe reconciliar el archivo y exponer estado auditable propio."""
    dynsec_path = tmp_path / "dynamic-security.json"
    passwd_path = tmp_path / "mosquitto_passwd"
    dynsec_path.write_text(json.dumps(SAMPLE_DYNSEC), encoding="utf-8")

    monkeypatch.setattr(dynsec_svc.settings, "dynsec_path", str(dynsec_path))
    monkeypatch.setattr(dynsec_svc.settings, "mosquitto_passwd_path", str(passwd_path))
    monkeypatch.setattr(desired_state_svc, "_MOSQUITTO_PASSWD_PATH", str(passwd_path))
    monkeypatch.setattr(broker_reconciler, "_MOSQUITTO_PASSWD_PATH", str(passwd_path))
    monkeypatch.setattr(broker_reconciler, "_signal_dynsec_reload", lambda: None)
    monkeypatch.setattr(broker_reconciler, "_signal_mosquitto_restart", lambda: None)

    resp = await client.post(
        "/api/v1/dynsec/import-password-file",
        files={
            "file": (
                "mosquitto_passwd",
                b"sensor-01:$7$existing\nsensor-77:$7$newhash\n",
                "text/plain",
            )
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["controlPlane"]["scope"] == desired_state_svc.MOSQUITTO_PASSWD_SCOPE
    assert body["controlPlane"]["status"] == "applied"
    assert body["dynsecControlPlane"]["scope"] == desired_state_svc.DYNSEC_CONFIG_SCOPE
    assert passwd_path.read_text(encoding="utf-8") == "sensor-01:$7$existing\nsensor-77:$7$newhash\n"

    status_resp = await client.get("/api/v1/dynsec/password-file-status")
    assert status_resp.status_code == 200
    status_body = status_resp.json()
    assert status_body["exists"] is True
    assert status_body["status"] == "applied"
    assert status_body["scope"] == desired_state_svc.MOSQUITTO_PASSWD_SCOPE
    assert status_body["user_count"] == 2


async def test_password_import_restart_mosquitto_uses_control_plane_signal(client, monkeypatch):
    """El restart publicado bajo dynsec debe delegar la señal al reconciliador broker-facing."""
    calls: list[tuple[tuple, dict]] = []

    async def fake_set_reload_desired(session, payload=None):
        return SimpleNamespace(
            scope=desired_state_svc.BROKER_RELOAD_SCOPE,
            version=9,
            reconcile_status="pending",
            drift_detected=False,
            last_error=None,
        )

    async def fake_reconcile_or_wait(state, reconcile_action, session, *args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(
            scope=state.scope,
            version=state.version,
            reconcile_status="applied",
            drift_detected=False,
            last_error=None,
        )

    monkeypatch.setattr(desired_state_svc, "set_broker_reload_desired", fake_set_reload_desired)
    monkeypatch.setattr(desired_state_svc, "reconcile_or_wait", fake_reconcile_or_wait)

    resp = await client.post("/api/v1/dynsec/restart-mosquitto")

    assert resp.status_code == 200
    assert resp.json()["controlPlane"]["scope"] == desired_state_svc.BROKER_RELOAD_SCOPE
    assert resp.json()["controlPlane"]["status"] == "applied"
    assert calls == [((), {})]


async def test_delete_client_marks_desired_state_as_deleted(client, monkeypatch):
    """Delete client debe persistir un desired state borrado y observar ausencia en DynSec."""
    dynsec_doc = {
        **SAMPLE_DYNSEC,
        "clients": [
            {
                "username": "sensor-01",
                "textname": "Sensor de prueba",
                "groups": [],
                "roles": [{"rolename": "sensors", "priority": 1}],
                "disabled": False,
            }
        ],
    }
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: dynsec_doc)
    monkeypatch.setattr(dynsec_svc, "execute_mosquitto_command", lambda *a, **kw: CMD_OK)
    monkeypatch.setattr(dynsec_svc, "write_dynsec", lambda data: dynsec_doc.update(data))

    resp = await client.delete("/api/v1/dynsec/clients/sensor-01")
    assert resp.status_code == 200
    status_resp = await client.get("/api/v1/dynsec/clients/sensor-01/status")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "applied"
    assert body["driftDetected"] is False
    assert body["desired"]["deleted"] is True
    assert body["observed"] is None


async def test_create_client_invalid_username(client, monkeypatch):
    """Username con espacios o caracteres especiales: retorna 422."""
    monkeypatch.setattr(dynsec_svc, "execute_mosquitto_command", lambda *a, **kw: CMD_OK)
    payload = {"username": "nombre invalido!", "password": "SecurePass123"}
    resp = await client.post("/api/v1/dynsec/clients", json=payload)
    assert resp.status_code == 422


async def test_create_client_short_password(client, monkeypatch):
    """Password menor a 6 caracteres: retorna 422."""
    monkeypatch.setattr(dynsec_svc, "execute_mosquitto_command", lambda *a, **kw: CMD_OK)
    payload = {"username": "sensor-nuevo", "password": "123"}
    resp = await client.post("/api/v1/dynsec/clients", json=payload)
    assert resp.status_code == 422


async def test_create_client_requires_auth(raw_client):
    """Sin autenticacion, crear cliente retorna 401 o 403."""
    payload = {"username": "sensor-nuevo", "password": "SecurePass123"}
    resp = await raw_client.post("/api/v1/dynsec/clients", json=payload)
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /api/v1/dynsec/roles
# ---------------------------------------------------------------------------

async def test_create_role_success(client, monkeypatch):
    """Crear rol con nombre valido: retorna 201."""
    monkeypatch.setattr(dynsec_svc, "execute_mosquitto_command", lambda *a, **kw: CMD_OK)
    dynsec_doc = {**SAMPLE_DYNSEC, "roles": list(SAMPLE_DYNSEC["roles"])}
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: dynsec_doc)
    monkeypatch.setattr(dynsec_svc, "write_dynsec", lambda data: dynsec_doc.update(data))
    payload = {"name": "operadores"}
    resp = await client.post("/api/v1/dynsec/roles", json=payload)
    assert resp.status_code == 201
    status_resp = await client.get("/api/v1/dynsec/roles/operadores/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["desired"]["rolename"] == "operadores"


async def test_add_and_remove_role_acl_updates_control_plane_state(client, monkeypatch):
    """Las ACLs de rol deben persistirse como desired state antes de reconciliar."""
    dynsec_doc = {
        **SAMPLE_DYNSEC,
        "roles": [{"rolename": "sensors", "acls": []}],
    }
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: dynsec_doc)
    monkeypatch.setattr(dynsec_svc, "execute_mosquitto_command", lambda *a, **kw: CMD_OK)
    monkeypatch.setattr(dynsec_svc, "write_dynsec", lambda data: dynsec_doc.update(data))

    add_resp = await client.post(
        "/api/v1/dynsec/roles/sensors/acls",
        json={"topic": "plants/#", "aclType": "publishClientSend", "permission": "allow"},
    )
    assert add_resp.status_code == 200
    add_status = await client.get("/api/v1/dynsec/roles/sensors/status")
    assert add_status.status_code == 200
    assert any(entry["topic"] == "plants/#" for entry in add_status.json()["desired"]["acls"])

    remove_resp = await client.request(
        "DELETE",
        "/api/v1/dynsec/roles/sensors/acls",
        params={"acl_type": "publishClientSend", "topic": "plants/#"},
    )
    assert remove_resp.status_code == 200
    remove_status = await client.get("/api/v1/dynsec/roles/sensors/status")
    assert remove_status.status_code == 200
    assert all(entry["topic"] != "plants/#" for entry in remove_status.json()["desired"]["acls"])


# ---------------------------------------------------------------------------
# GET /api/v1/dynsec/roles
# ---------------------------------------------------------------------------

async def test_list_roles_returns_200(client, monkeypatch):
    """Lista de roles: retorna 200 y campo 'roles'."""
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: SAMPLE_DYNSEC)
    resp = await client.get("/api/v1/dynsec/roles")
    assert resp.status_code == 200
    assert "roles" in resp.json()


# ---------------------------------------------------------------------------
# GET /api/v1/dynsec/groups
# ---------------------------------------------------------------------------

async def test_list_groups_returns_200(client, monkeypatch):
    """Lista de grupos: retorna 200 y campo 'groups'."""
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: SAMPLE_DYNSEC)
    resp = await client.get("/api/v1/dynsec/groups")
    assert resp.status_code == 200
    assert "groups" in resp.json()


async def test_create_group_and_membership_updates_control_plane_state(client, monkeypatch):
    """Create group y sus memberships deben pasar por desired state del grupo."""
    dynsec_doc = {
        **SAMPLE_DYNSEC,
        "groups": [{"groupname": "plantas", "roles": [], "clients": []}],
    }
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: dynsec_doc)
    monkeypatch.setattr(dynsec_svc, "execute_mosquitto_command", lambda *a, **kw: CMD_OK)
    monkeypatch.setattr(dynsec_svc, "write_dynsec", lambda data: dynsec_doc.update(data))

    create_resp = await client.post("/api/v1/dynsec/groups", json={"name": "operacion"})
    assert create_resp.status_code == 201

    add_role_resp = await client.post(
        "/api/v1/dynsec/groups/operacion/roles",
        json={"role_name": "sensors", "priority": 2},
    )
    assert add_role_resp.status_code == 200

    add_client_resp = await client.post(
        "/api/v1/dynsec/groups/operacion/clients",
        json={"username": "sensor-01", "priority": 4},
    )
    assert add_client_resp.status_code == 200

    status_resp = await client.get("/api/v1/dynsec/groups/operacion/status")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert any(role["rolename"] == "sensors" for role in body["desired"]["roles"])
    assert any(entry["username"] == "sensor-01" and entry.get("priority") == 4 for entry in body["desired"]["clients"])
    assert any(entry["username"] == "sensor-01" and entry.get("priority") == 4 for entry in body["observed"]["clients"])


async def test_delete_group_marks_desired_state_as_deleted(client, monkeypatch):
    """Delete group debe dejar desired deleted y observed ausente."""
    dynsec_doc = {
        **SAMPLE_DYNSEC,
        "groups": [{"groupname": "plantas", "roles": [], "clients": []}],
    }
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: dynsec_doc)
    monkeypatch.setattr(dynsec_svc, "execute_mosquitto_command", lambda *a, **kw: CMD_OK)
    monkeypatch.setattr(dynsec_svc, "write_dynsec", lambda data: dynsec_doc.update(data))

    resp = await client.delete("/api/v1/dynsec/groups/plantas")
    assert resp.status_code == 200
    status_resp = await client.get("/api/v1/dynsec/groups/plantas/status")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "applied"
    assert body["driftDetected"] is False
    assert body["desired"]["deleted"] is True
    assert body["observed"] is None
