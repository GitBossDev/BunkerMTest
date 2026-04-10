"""
Router DynSec: gestión de clientes, roles, grupos y ACLs de Mosquitto.
Capa HTTP fina que delega la lógica al servicio dynsec_service.
"""
from __future__ import annotations

import json
import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Security, status
from pydantic import BaseModel

from core.auth import get_api_key
from models.schemas import (
    ACLRequest,
    ACLType,
    ClientCreate,
    GroupCreate,
    RoleAssignment,
    RoleCreate,
    VALID_ACL_TYPES,
)
from services import dynsec_service as dynsec_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dynsec", tags=["dynsec"])

# Incluye el router de importación de contraseñas como sub-ruta
try:
    from dynsec.password_import import router as _password_import_router
    router.include_router(_password_import_router)
except ImportError:
    logger.warning("password_import router no disponible; sub-ruta deshabilitada")


# ---------------------------------------------------------------------------
# Modelos locales que no pertenecen a schemas generales
# ---------------------------------------------------------------------------

class DefaultACLConfig(BaseModel):
    publishClientSend: bool
    publishClientReceive: bool
    subscribe: bool
    unsubscribe: bool


_DEFAULT_ACL_TYPES = ["publishClientSend", "publishClientReceive", "subscribe", "unsubscribe"]


def _normalize_role_names(raw_roles: List[Any]) -> List[str]:
    """Normaliza roles a lista de nombres simple para la UI."""
    result: List[str] = []
    for role in raw_roles:
        if isinstance(role, dict):
            name = role.get("rolename")
        else:
            name = role
        if isinstance(name, str) and name:
            result.append(name)
    return result


def _normalize_group_names(raw_groups: List[Any]) -> List[str]:
    """Normaliza grupos a lista de nombres simple para la UI."""
    result: List[str] = []
    for group in raw_groups:
        if isinstance(group, dict):
            name = group.get("groupname")
        else:
            name = group
        if isinstance(name, str) and name:
            result.append(name)
    return result


def _normalize_role_entries(raw_roles: List[Any]) -> List[Dict[str, Any]]:
    """Normaliza roles preservando compatibilidad con contratos viejos y nuevos."""
    result: List[Dict[str, Any]] = []
    for role in raw_roles:
        if isinstance(role, dict):
            name = role.get("rolename") or role.get("name")
            priority = role.get("priority")
        else:
            name = role
            priority = None
        if isinstance(name, str) and name:
            entry: Dict[str, Any] = {"rolename": name, "name": name}
            if priority is not None:
                entry["priority"] = priority
            result.append(entry)
    return result


def _normalize_group_entries(raw_groups: List[Any]) -> List[Dict[str, Any]]:
    """Normaliza grupos preservando compatibilidad con contratos viejos y nuevos."""
    result: List[Dict[str, Any]] = []
    for group in raw_groups:
        if isinstance(group, dict):
            name = group.get("groupname") or group.get("name")
            priority = group.get("priority")
        else:
            name = group
            priority = None
        if isinstance(name, str) and name:
            entry: Dict[str, Any] = {"groupname": name, "name": name}
            if priority is not None:
                entry["priority"] = priority
            result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _cmd_or_raise(subcommand: List[str], err_code: int = status.HTTP_400_BAD_REQUEST) -> str:
    """Ejecuta mosquitto_ctrl y lanza HTTPException si falla. Devuelve stdout."""
    r = dynsec_svc.execute_mosquitto_command(subcommand)
    if not r["success"]:
        if r.get("timeout"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Broker unreachable: command timed out",
            )
        raise HTTPException(status_code=err_code, detail=r["error_output"])
    return r["output"]


def _write_or_raise(
    data: Dict[str, Any],
    rollback_cmd: Optional[List[str]],
    context: str,
) -> None:
    """
    Escribe el JSON de DynSec. Si la escritura falla (HIGH-1):
    - Ejecuta rollback_cmd en mosquitto_ctrl para revertir el cambio en el broker
      (solo cuando sea posible invertir la operacion).
    - Lanza HTTP 500 con un mensaje claro al llamador.
    Sin este helper, los fallos del dual-write se ignoraban silenciosamente y el
    broker quedaba en un estado diferente al JSON, causando inconsistencias.
    """
    try:
        dynsec_svc.write_dynsec(data)
    except Exception as exc:
        if rollback_cmd:
            logger.error(
                "Dual-write fallido para %s: %s — ejecutando rollback: %s",
                context, exc, rollback_cmd[0],
            )
            dynsec_svc.execute_mosquitto_command(rollback_cmd)
            detail = (
                "DynSec config write failed. The broker change was reverted. "
                "Retry the operation."
            )
        else:
            logger.error(
                "Dual-write fallido para %s: %s — sin rollback disponible. "
                "El broker y el JSON pueden estar desincronizados.",
                context, exc,
            )
            detail = (
                "DynSec config write failed. The broker and the config file "
                "may be out of sync. Check server logs."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        )


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------

@router.get("/clients")
async def list_clients(
    page: int = 1,
    limit: int = 50,
    search: Optional[str] = None,
    api_key: str = Security(get_api_key),
):
    """Lista clientes desde dynamic-security.json con paginación y búsqueda."""
    try:
        data = dynsec_svc.read_dynsec()
        raw_clients = data.get("clients", [])

        if search:
            q = search.lower()
            raw_clients = [c for c in raw_clients if q in c.get("username", "").lower()]

        limit = max(1, limit)
        page = max(1, page)
        total = len(raw_clients)
        pages = max(1, -(-total // limit))
        start = (page - 1) * limit
        page_clients = raw_clients[start:start + limit]

        clients = [
            {
                "username": c.get("username", ""),
                "disabled": c.get("disabled", False),
                "roles": _normalize_role_names(c.get("roles", [])),
                "groups": _normalize_group_names(c.get("groups", [])),
            }
            for c in page_clients
        ]
        return {
            "clients": clients,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": pages,
        }
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Dynamic security config not found")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=str(exc))


@router.get("/clients/disabled-map")
async def get_clients_disabled_map(api_key: str = Security(get_api_key)):
    """Devuelve el mapa disabled y la lista de usernames para Connected Clients."""
    try:
        data = dynsec_svc.read_dynsec()
        clients = data.get("clients", [])
        disabled_map = {
            c["username"]: c.get("disabled", False)
            for c in clients
            if isinstance(c, dict) and c.get("username")
        }
        return {"map": disabled_map, "usernames": list(disabled_map.keys())}
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Dynamic security config not found")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=str(exc))


@router.get("/clients/{username}")
async def get_client(username: str, api_key: str = Security(get_api_key)):
    """Devuelve los detalles de un cliente específico."""
    try:
        data = dynsec_svc.read_dynsec()
        client = dynsec_svc.find_client(data, username)
        if client is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Client {username} not found")
        return {
            "client": {
                "username": client.get("username", ""),
                "textname": client.get("textname", ""),
                "disabled": client.get("disabled", False),
                "roles": _normalize_role_entries(client.get("roles", [])),
                "groups": _normalize_group_entries(client.get("groups", [])),
            }
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/clients", status_code=status.HTTP_201_CREATED)
async def create_client(client: ClientCreate, api_key: str = Security(get_api_key)):
    """Crea un nuevo cliente MQTT."""
    _cmd_or_raise(["createClient", client.username, "-p", client.password])
    # Dual-write al JSON
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            if not dynsec_svc.find_client(data, client.username):
                data.setdefault("clients", []).append({
                    "username": client.username,
                    "textname": "",
                    "groups": [],
                    "roles": [],
                    "disabled": False,
                })
            _write_or_raise(data, ["deleteClient", client.username], f"create_client:{client.username}")
    except HTTPException:
        raise
    return {"message": f"Client {client.username} created successfully"}


@router.put("/clients/{username}/enable")
async def enable_client(username: str, api_key: str = Security(get_api_key)):
    _cmd_or_raise(["enableClient", username])
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            for c in data.get("clients", []):
                if c.get("username") == username:
                    c["disabled"] = False
                    break
            _write_or_raise(data, ["disableClient", username], f"enable_client:{username}")
    except HTTPException:
        raise
    return {"message": f"Client {username} enabled successfully"}


@router.put("/clients/{username}/disable")
async def disable_client(username: str, api_key: str = Security(get_api_key)):
    _cmd_or_raise(["disableClient", username])
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            for c in data.get("clients", []):
                if c.get("username") == username:
                    c["disabled"] = True
                    break
            _write_or_raise(data, ["enableClient", username], f"disable_client:{username}")
    except HTTPException:
        raise
    return {"message": f"Client {username} disabled successfully"}


@router.delete("/clients/{username}")
async def delete_client(username: str, api_key: str = Security(get_api_key)):
    _cmd_or_raise(["deleteClient", username])
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            data["clients"] = [c for c in data.get("clients", [])
                                if c.get("username") != username]
            # Sin rollback: no es posible recrear el cliente con su password original
            _write_or_raise(data, None, f"delete_client:{username}")
    except HTTPException:
        raise
    return {"message": f"Client {username} removed successfully"}


@router.post("/clients/{username}/roles")
async def add_client_role(username: str, role: RoleAssignment,
                          api_key: str = Security(get_api_key)):
    _cmd_or_raise(["addClientRole", username, role.role_name, str(role.priority or 1)])
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            for c in data.get("clients", []):
                if c.get("username") == username:
                    roles = c.setdefault("roles", [])
                    if not any(r.get("rolename") == role.role_name for r in roles):
                        roles.append({"rolename": role.role_name, "priority": role.priority or 1})
                    break
            _write_or_raise(data, ["removeClientRole", username, role.role_name], f"add_client_role:{username}/{role.role_name}")
    except HTTPException:
        raise
    return {"message": f"Role {role.role_name} assigned to client {username}"}


@router.delete("/clients/{username}/roles/{role_name}")
async def remove_client_role(username: str, role_name: str,
                             api_key: str = Security(get_api_key)):
    _cmd_or_raise(["removeClientRole", username, role_name])
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            for c in data.get("clients", []):
                if c.get("username") == username:
                    c["roles"] = [r for r in c.get("roles", [])
                                  if r.get("rolename") != role_name]
                    break
            _write_or_raise(data, ["addClientRole", username, role_name, "1"], f"remove_client_role:{username}/{role_name}")
    except HTTPException:
        raise
    return {"message": f"Role {role_name} removed from client {username}"}


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

@router.get("/roles")
async def list_roles(api_key: str = Security(get_api_key)):
    try:
        data = dynsec_svc.read_dynsec()
        role_names = [r["rolename"] for r in data.get("roles", []) if "rolename" in r]
        return {"roles": "\n".join(role_names)}
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Dynamic security config not found")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/roles/{role_name}")
async def get_role(role_name: str, api_key: str = Security(get_api_key)):
    try:
        data = dynsec_svc.read_dynsec()
        role_data = dynsec_svc.find_role(data, role_name)
        if role_data is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Role {role_name} not found")
        acls = [
            {
                "topic": a.get("topic", ""),
                "aclType": a.get("acltype", ""),
                "permission": "allow" if a.get("allow", False) else "deny",
                "priority": a.get("priority", -1),
            }
            for a in role_data.get("acls", [])
        ]
        return {"role": role_name, "acls": acls}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(role: RoleCreate, api_key: str = Security(get_api_key)):
    _cmd_or_raise(["createRole", role.name])
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            if not dynsec_svc.find_role(data, role.name):
                data.setdefault("roles", []).append({"rolename": role.name, "acls": []})
            _write_or_raise(data, ["deleteRole", role.name], f"create_role:{role.name}")
    except HTTPException:
        raise
    return {"message": f"Role {role.name} created successfully"}


@router.delete("/roles/{role_name}")
async def delete_role(role_name: str, api_key: str = Security(get_api_key)):
    _cmd_or_raise(["deleteRole", role_name])
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            data["roles"] = [r for r in data.get("roles", [])
                             if r.get("rolename") != role_name]
            # Sin rollback: no es posible recrear el rol con todas sus ACLs originales
            _write_or_raise(data, None, f"delete_role:{role_name}")
    except HTTPException:
        raise
    return {"message": f"Role {role_name} deleted successfully"}


@router.post("/roles/{role_name}/acls")
async def add_role_acl(role_name: str, acl: ACLRequest,
                       api_key: str = Security(get_api_key)):
    if acl.aclType not in VALID_ACL_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid aclType. Must be one of: {', '.join(VALID_ACL_TYPES)}")
    if acl.permission not in ("allow", "deny"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid permission. Must be 'allow' or 'deny'")
    _cmd_or_raise(["addRoleACL", role_name, acl.aclType, acl.topic, acl.permission])
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            for r in data.get("roles", []):
                if r.get("rolename") == role_name:
                    acls_list = r.setdefault("acls", [])
                    if not any(a.get("acltype") == acl.aclType and a.get("topic") == acl.topic
                               for a in acls_list):
                        acls_list.append({
                            "acltype": acl.aclType,
                            "topic": acl.topic,
                            "allow": acl.permission == "allow",
                            "priority": -1,
                        })
                    break
            _write_or_raise(data, ["removeRoleACL", role_name, acl.aclType, acl.topic], f"add_role_acl:{role_name}")
    except HTTPException:
        raise
    return {"message": f"ACL added successfully to role {role_name}",
            "details": {"role": role_name, "topic": acl.topic,
                        "aclType": acl.aclType, "permission": acl.permission}}


@router.delete("/roles/{role_name}/acls")
async def remove_role_acl(role_name: str, acl_type: ACLType, topic: str,
                          api_key: str = Security(get_api_key)):
    _cmd_or_raise(["removeRoleACL", role_name, acl_type.value, topic])
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            for r in data.get("roles", []):
                if r.get("rolename") == role_name:
                    r["acls"] = [a for a in r.get("acls", [])
                                 if not (a.get("acltype") == acl_type.value
                                         and a.get("topic") == topic)]
                    break
            # Sin rollback: no conocemos el permiso original (allow/deny) para recrear la ACL
            _write_or_raise(data, None, f"remove_role_acl:{role_name}")
    except HTTPException:
        raise
    return {"message": f"ACL removed from role {role_name} successfully"}


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------

@router.get("/groups")
async def list_groups(api_key: str = Security(get_api_key)):
    try:
        data = dynsec_svc.read_dynsec()
        group_names = [g["groupname"] for g in data.get("groups", []) if "groupname" in g]
        return {"groups": "\n".join(group_names)}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/groups/{group_name}")
async def get_group(group_name: str, api_key: str = Security(get_api_key)):
    try:
        data = dynsec_svc.read_dynsec()
        group_data = dynsec_svc.find_group(data, group_name)
        if group_data is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Group {group_name} not found")
        info = {
            "name": group_data.get("groupname", ""),
            "roles": [
                {"name": r.get("rolename", ""), "priority": r.get("priority", -1)}
                for r in group_data.get("roles", [])
            ],
            "clients": [
                c.get("username", "") if isinstance(c, dict) else str(c)
                for c in group_data.get("clients", [])
            ],
        }
        return {"group": info}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/groups", status_code=status.HTTP_201_CREATED)
async def create_group(group: GroupCreate, api_key: str = Security(get_api_key)):
    _cmd_or_raise(["createGroup", group.name])
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            if not dynsec_svc.find_group(data, group.name):
                data.setdefault("groups", []).append({
                    "groupname": group.name, "roles": [], "clients": []
                })
            _write_or_raise(data, ["deleteGroup", group.name], f"create_group:{group.name}")
    except HTTPException:
        raise
    return {"message": f"Group {group.name} created successfully"}


@router.delete("/groups/{group_name}")
async def delete_group(group_name: str, api_key: str = Security(get_api_key)):
    _cmd_or_raise(["deleteGroup", group_name])
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            data["groups"] = [g for g in data.get("groups", [])
                              if g.get("groupname") != group_name]
            # Sin rollback: no es posible recrear el grupo con sus miembros y roles originales
            _write_or_raise(data, None, f"delete_group:{group_name}")
    except HTTPException:
        raise
    return {"message": f"Group {group_name} deleted successfully"}


@router.post("/groups/{group_name}/roles")
async def add_group_role(group_name: str, role: RoleAssignment,
                         api_key: str = Security(get_api_key)):
    _cmd_or_raise(["addGroupRole", group_name, role.role_name])
    return {"message": f"Role {role.role_name} assigned to group {group_name}"}


@router.delete("/groups/{group_name}/roles/{role_name}")
async def remove_group_role(group_name: str, role_name: str,
                            api_key: str = Security(get_api_key)):
    _cmd_or_raise(["removeGroupRole", group_name, role_name])
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            for g in data.get("groups", []):
                if g.get("groupname") == group_name:
                    g["roles"] = [r for r in g.get("roles", [])
                                  if r.get("rolename") != role_name]
                    break
            _write_or_raise(data, ["addGroupRole", group_name, role_name], f"remove_group_role:{group_name}/{role_name}")
    except HTTPException:
        raise
    return {"message": f"Role {role_name} removed from group {group_name}"}


@router.post("/groups/{group_name}/clients")
async def add_client_to_group(group_name: str, body: dict,
                              api_key: str = Security(get_api_key)):
    username = body.get("username")
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Username is required")
    priority = body.get("priority")
    cmd = ["addGroupClient", group_name, username]
    if priority:
        cmd.extend(["--priority", str(priority)])
    _cmd_or_raise(cmd)
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            for g in data.get("groups", []):
                if g.get("groupname") == group_name:
                    gc = g.setdefault("clients", [])
                    if not any(
                        (c.get("username") if isinstance(c, dict) else c) == username
                        for c in gc
                    ):
                        gc.append({"username": username})
                    break
            _write_or_raise(data, ["removeGroupClient", group_name, username], f"add_client_to_group:{group_name}/{username}")
    except HTTPException:
        raise
    return {"message": f"Client {username} added to group {group_name} successfully"}


@router.delete("/groups/{group_name}/clients/{username}")
async def remove_client_from_group(group_name: str, username: str,
                                   api_key: str = Security(get_api_key)):
    _cmd_or_raise(["removeGroupClient", group_name, username])
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            for g in data.get("groups", []):
                if g.get("groupname") == group_name:
                    g["clients"] = [
                        c for c in g.get("clients", [])
                        if (c.get("username") if isinstance(c, dict) else c) != username
                    ]
                    break
            _write_or_raise(data, ["addGroupClient", group_name, username], f"remove_client_from_group:{group_name}/{username}")
    except HTTPException:
        raise
    return {"message": f"Client {username} removed from group {group_name} successfully"}


# ---------------------------------------------------------------------------
# Default ACL
# ---------------------------------------------------------------------------

@router.get("/default-acl")
async def get_default_acl(api_key: str = Security(get_api_key)):
    try:
        data = dynsec_svc.read_dynsec()
        raw = data.get("defaultACLAccess", {})
        return {
            "publishClientSend": bool(raw.get("publishClientSend", True)),
            "publishClientReceive": bool(raw.get("publishClientReceive", True)),
            "subscribe": bool(raw.get("subscribe", True)),
            "unsubscribe": bool(raw.get("unsubscribe", True)),
        }
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to load defaultACLAccess: {exc}")


@router.put("/default-acl")
async def set_default_acl(acl_config: DefaultACLConfig,
                          api_key: str = Security(get_api_key)):
    updates = {
        "publishClientSend":    acl_config.publishClientSend,
        "publishClientReceive": acl_config.publishClientReceive,
        "subscribe":            acl_config.subscribe,
        "unsubscribe":          acl_config.unsubscribe,
    }
    errors = []
    for acl_type, allow in updates.items():
        r = dynsec_svc.execute_mosquitto_command(
            ["setDefaultACLAccess", acl_type, "allow" if allow else "deny"]
        )
        if not r["success"]:
            errors.append(f"{acl_type}: {r['error_output']}")
    if errors:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="; ".join(errors))
    try:
        with dynsec_svc._dynsec_lock:
            data = dynsec_svc.read_dynsec()
            data["defaultACLAccess"] = updates
            _write_or_raise(data, None, "set_default_acl")
    except HTTPException:
        raise
    return {"message": "Default ACL access updated successfully", "config": updates}
