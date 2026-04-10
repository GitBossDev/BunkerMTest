"""
Tests de regresion para el router DynSec (/api/v1/dynsec).

Cubre los endpoints criticos de gestion de clientes, roles y grupos MQTT.
Los servicios externos (mosquitto_ctrl, dynamic-security.json) se mockean
para que los tests no dependan del broker en ejecucion.
"""
import pytest
import services.dynsec_service as dynsec_svc
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
    payload = {"username": "nuevo-sensor", "password": "SecurePass123"}
    resp = await client.post("/api/v1/dynsec/clients", json=payload)
    assert resp.status_code == 201


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
    payload = {"name": "operadores"}
    resp = await client.post("/api/v1/dynsec/roles", json=payload)
    assert resp.status_code == 201


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
