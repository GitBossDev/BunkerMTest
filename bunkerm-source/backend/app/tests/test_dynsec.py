"""
Tests de regresion para el router DynSec (/api/v1/dynsec).

Cubre los endpoints criticos de gestion de clientes, roles y grupos MQTT.
Los servicios externos (mosquitto_ctrl, dynamic-security.json) se mockean
para que los tests no dependan del broker en ejecucion.
"""
import json

import pytest
import services.dynsec_service as dynsec_svc
from services import broker_desired_state_service as desired_state_svc
import services.broker_reconciler as broker_reconciler
from config.dynsec_config import merge_dynsec_configs

# Estructura minima valida de dynamic-security.json para los mocks
SAMPLE_DYNSEC = {
    "defaultACLAccess": {
        "publishClientSend": True,
        "publishClientReceive": False,
        "subscribe": False,
        "unsubscribe": True,
    },
    "clients": [
        {"username": "sensor-01", "textname": "Sensor de prueba", "groups": [], "roles": [{"rolename": "sensors"}]}
    ],
    "roles": [
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
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: SAMPLE_DYNSEC)
    resp = await client.get("/api/v1/dynsec/clients")
    assert resp.status_code == 200
    body = resp.json()
    assert "clients" in body
    assert any(c["username"] == "sensor-01" for c in body["clients"])
    assert body["total"] == 1


async def test_list_clients_returns_paginated_normalized_shape(client, monkeypatch):
    """El listado normaliza roles/grupos y retorna metadatos de paginación."""
    dynsec = {
        **SAMPLE_DYNSEC,
        "clients": [
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
    }
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: dynsec)
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
            {"username": "sensor-01", "disabled": False},
            {"username": "sensor-02", "disabled": True},
        ],
    }
    monkeypatch.setattr(dynsec_svc, "read_dynsec", lambda: dynsec)
    resp = await client.get("/api/v1/dynsec/clients/disabled-map")
    assert resp.status_code == 200
    body = resp.json()
    assert body["map"] == {"sensor-01": False, "sensor-02": True}
    assert body["usernames"] == ["sensor-01", "sensor-02"]


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
    monkeypatch.setattr(broker_reconciler, "_signal_dynsec_reload", lambda: None)

    resp = await client.post("/api/v1/dynsec/sync-passwd-to-dynsec")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert body["controlPlane"]["scope"] == desired_state_svc.DYNSEC_CONFIG_SCOPE
    assert body["controlPlane"]["status"] == "applied"

    stored = json.loads(dynsec_path.read_text(encoding="utf-8"))
    assert any(client_entry["username"] == "sensor-99" for client_entry in stored["clients"])


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
    assert body["desired"]["deleted"] is True
    assert body["observed"] is None
