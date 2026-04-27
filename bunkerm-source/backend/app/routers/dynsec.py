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

from fastapi import APIRouter, Depends, HTTPException, Request, Security, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from clientlogs.activity_storage import client_activity_storage
from core.auth import get_api_key
from core.database import get_db
from models.schemas import (
    ACLRequest,
    ACLType,
    ClientCreate,
    GroupCreate,
    RoleAssignment,
    RoleCreate,
    VALID_ACL_TYPES,
)
from services import broker_desired_state_service as desired_state_svc
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


class TestACLRequest(BaseModel):
    aclType: str
    topic: str


_DEFAULT_ACL_TYPES = ["publishClientSend", "publishClientReceive", "subscribe", "unsubscribe"]


def _get_observed_dynsec_for_read() -> Dict[str, Any]:
    return desired_state_svc.get_cached_observed_dynsec_config()


def _get_observed_dynsec_index_for_read() -> Dict[str, Any]:
    return desired_state_svc.get_cached_observed_dynsec_index()


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


def _mqtt_topic_matches(pattern: str, topic: str) -> bool:
    """
    Implementa el algoritmo de matching de topics de Mosquitto DynSec.

    Reglas:
    - '+' coincide exactamente con un nivel de topic.
    - '#' coincide con cero o más niveles finales.
    - '#' NO coincide con topics que empiecen por '$' (estándar MQTT §4.7.3).
    - '$SYS/...' solo puede ser accedido con patrones que comiencen por '$'.
    """
    # Prevenir que '#' o '+/...' coincidan con topics $SYS
    if topic.startswith("$") and not pattern.startswith("$"):
        return False

    pattern_parts = pattern.split("/")
    topic_parts = topic.split("/")

    def _match(pp: list[str], tp: list[str]) -> bool:
        if not pp and not tp:
            return True
        if not pp:
            return False
        if pp[0] == "#":
            return True  # coincide con el resto (incluido vacío)
        if not tp:
            return False
        if pp[0] == "+" or pp[0] == tp[0]:
            return _match(pp[1:], tp[1:])
        return False

    return _match(pattern_parts, topic_parts)


def _ensure_reconcile_success(state, detail_prefix: str) -> None:
    if state.reconcile_status == "error":
        detail = state.last_error or "Unknown reconciliation error"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{detail_prefix}: {detail}",
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
        index = _get_observed_dynsec_index_for_read()
        raw_clients = index.get("client_summaries", [])

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
                "roles": list(c.get("roles", [])),
                "groups": list(c.get("groups", [])),
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
        index = _get_observed_dynsec_index_for_read()
        return {"map": index.get("disabled_map", {}), "usernames": index.get("usernames", [])}
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
        _get_observed_dynsec_index_for_read()
        client = desired_state_svc.get_observed_client(username)
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


@router.get("/clients/{username}/status")
async def get_client_status(
    username: str,
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await desired_state_svc.get_client_status(db, username)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load client control-plane status: {exc}",
        )


@router.post("/clients", status_code=status.HTTP_201_CREATED)
async def create_client(
    client: ClientCreate,
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Crea un nuevo cliente MQTT."""
    try:
        state = await desired_state_svc.set_client_desired(
            db,
            {
                "username": client.username,
                "textname": "",
                "groups": [],
                "roles": [],
                "disabled": False,
            },
        )
        if desired_state_svc.is_daemon_reconcile_mode():
            await desired_state_svc.stage_client_creation_secret(db, client.username, state.version, client.password)
            state = await desired_state_svc.reconcile_or_wait(
                state,
                desired_state_svc.reconcile_client,
                db,
                client.username,
            )
        else:
            state = await desired_state_svc.reconcile_or_wait(
                state,
                desired_state_svc.reconcile_client,
                db,
                client.username,
                creation_password=client.password,
            )
        _ensure_reconcile_success(state, "Client reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando desired state de cliente %s: %s", client.username, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Client desired state reconciliation failed: {exc}",
        )
    client_activity_storage.upsert_client(client.username, disabled=False)
    return {
        "message": f"Client {client.username} created successfully",
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


@router.put("/clients/{username}/enable")
async def enable_client(
    username: str,
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    try:
        observed = desired_state_svc.get_observed_client(username)
        payload = observed or {
            "username": username,
            "textname": "",
            "groups": [],
            "roles": [],
            "disabled": False,
        }
        payload["disabled"] = False
        state = await desired_state_svc.set_client_desired(db, payload)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_client,
            db,
            username,
        )
        _ensure_reconcile_success(state, "Client enable reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando enable de cliente %s: %s", username, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Client desired state reconciliation failed: {exc}",
        )
    client_activity_storage.upsert_client(username, disabled=False)
    return {
        "message": f"Client {username} enabled successfully",
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


@router.put("/clients/{username}/disable")
async def disable_client(
    username: str,
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    try:
        observed = desired_state_svc.get_observed_client(username)
        payload = observed or {
            "username": username,
            "textname": "",
            "groups": [],
            "roles": [],
            "disabled": True,
        }
        payload["disabled"] = True
        state = await desired_state_svc.set_client_desired(db, payload)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_client,
            db,
            username,
        )
        _ensure_reconcile_success(state, "Client disable reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando disable de cliente %s: %s", username, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Client desired state reconciliation failed: {exc}",
        )
    client_activity_storage.upsert_client(username, disabled=True)
    return {
        "message": f"Client {username} disabled successfully",
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


@router.delete("/clients/{username}")
async def delete_client(
    username: str,
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    try:
        observed = desired_state_svc.get_observed_client(username)
        payload = observed or {
            "username": username,
            "textname": "",
            "groups": [],
            "roles": [],
            "disabled": True,
        }
        payload["deleted"] = True
        state = await desired_state_svc.set_client_desired(db, payload)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_client,
            db,
            username,
        )
        _ensure_reconcile_success(state, "Client delete reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando delete de cliente %s: %s", username, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Client desired state reconciliation failed: {exc}",
        )
    client_activity_storage.mark_client_deleted(username)
    return {
        "message": f"Client {username} removed successfully",
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


@router.post("/clients/{username}/roles")
async def add_client_role(username: str, role: RoleAssignment,
                          api_key: str = Security(get_api_key),
                          db: AsyncSession = Depends(get_db)):
    try:
        observed = desired_state_svc.get_observed_client(username)
        payload = observed or {
            "username": username,
            "textname": "",
            "groups": [],
            "roles": [],
            "disabled": False,
        }
        roles = payload.setdefault("roles", [])
        if not any(r.get("rolename") == role.role_name for r in roles):
            roles.append({"rolename": role.role_name, "priority": role.priority or 1})
        state = await desired_state_svc.set_client_desired(db, payload)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_client,
            db,
            username,
        )
        _ensure_reconcile_success(state, "Client role reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando rol %s para cliente %s: %s", role.role_name, username, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Client desired state reconciliation failed: {exc}",
        )
    return {
        "message": f"Role {role.role_name} assigned to client {username}",
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


@router.delete("/clients/{username}/roles/{role_name}")
async def remove_client_role(username: str, role_name: str,
                             api_key: str = Security(get_api_key),
                             db: AsyncSession = Depends(get_db)):
    try:
        observed = desired_state_svc.get_observed_client(username)
        payload = observed or {
            "username": username,
            "textname": "",
            "groups": [],
            "roles": [],
            "disabled": False,
        }
        payload["roles"] = [
            role for role in payload.get("roles", [])
            if role.get("rolename") != role_name
        ]
        state = await desired_state_svc.set_client_desired(db, payload)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_client,
            db,
            username,
        )
        _ensure_reconcile_success(state, "Client role reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando remocion de rol %s para cliente %s: %s", role_name, username, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Client desired state reconciliation failed: {exc}",
        )
    return {
        "message": f"Role {role_name} removed from client {username}",
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

@router.get("/roles")
async def list_roles(api_key: str = Security(get_api_key)):
    try:
        index = desired_state_svc.get_cached_observed_dynsec_index()
        role_names = sorted(index.get("role_lookup", {}).keys())
        return {
            "roles": role_names,
            "summaries": index.get("role_summaries", []),
        }
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Dynamic security config not found")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/roles/{role_name}")
async def get_role(role_name: str, api_key: str = Security(get_api_key)):
    try:
        role_data = desired_state_svc.get_observed_role(role_name)
        if role_data is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Role {role_name} not found")
        acls = [
            {
                "topic": a.get("topic", ""),
                "aclType": a.get("acltype", ""),
                "permission": "allow" if a.get("allow", False) else "deny",
                "priority": a.get("priority", 0),
            }
            for a in role_data.get("acls", [])
        ]
        return {"role": role_name, "acls": acls}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/roles/{role_name}/status")
async def get_role_status(
    role_name: str,
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await desired_state_svc.get_role_status(db, role_name)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load role control-plane status: {exc}",
        )


@router.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(
    role: RoleCreate,
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    try:
        state = await desired_state_svc.set_role_desired(
            db,
            {"rolename": role.name, "acls": [], "deleted": False},
        )
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_role,
            db,
            role.name,
        )
        _ensure_reconcile_success(state, "Role reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando create role %s: %s", role.name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Role desired state reconciliation failed.",
        )
    return {
        "message": f"Role {role.name} created successfully",
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


@router.delete("/roles/{role_name}")
async def delete_role(
    role_name: str,
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    try:
        observed = desired_state_svc.get_observed_role(role_name)
        payload = observed or {"rolename": role_name, "acls": []}
        payload["deleted"] = True
        state = await desired_state_svc.set_role_desired(db, payload)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_role,
            db,
            role_name,
        )
        _ensure_reconcile_success(state, "Role deletion reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando delete role %s: %s", role_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Role desired state reconciliation failed after broker deletion. Check control-plane status.",
        )
    return {
        "message": f"Role {role_name} deleted successfully",
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


@router.post("/roles/{role_name}/acls")
async def add_role_acl(role_name: str, acl: ACLRequest,
                       api_key: str = Security(get_api_key),
                       db: AsyncSession = Depends(get_db)):
    if acl.aclType not in VALID_ACL_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid aclType. Must be one of: {', '.join(VALID_ACL_TYPES)}")
    if acl.permission not in ("allow", "deny"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid permission. Must be 'allow' or 'deny'")
    try:
        observed = desired_state_svc.get_observed_role(role_name)
        payload = observed or {"rolename": role_name, "acls": []}
        acls_list = payload.setdefault("acls", [])
        if not any(entry.get("acltype") == acl.aclType and entry.get("topic") == acl.topic for entry in acls_list):
            acls_list.append(
                {
                    "acltype": acl.aclType,
                    "topic": acl.topic,
                    "allow": acl.permission == "allow",
                    "priority": 0,
                }
            )
        state = await desired_state_svc.set_role_desired(db, payload)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_role,
            db,
            role_name,
        )
        _ensure_reconcile_success(state, "Role ACL reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando ACL %s/%s para role %s: %s", acl.aclType, acl.topic, role_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Role desired state reconciliation failed.",
        )
    return {"message": f"ACL added successfully to role {role_name}",
            "details": {"role": role_name, "topic": acl.topic,
                        "aclType": acl.aclType, "permission": acl.permission},
            "controlPlane": {
                "scope": state.scope,
                "version": state.version,
                "status": state.reconcile_status,
                "driftDetected": state.drift_detected,
            }}


@router.delete("/roles/{role_name}/acls")
async def remove_role_acl(role_name: str, acl_type: ACLType, topic: str,
                          api_key: str = Security(get_api_key),
                          db: AsyncSession = Depends(get_db)):
    try:
        observed = desired_state_svc.get_observed_role(role_name)
        payload = observed or {"rolename": role_name, "acls": []}
        payload["acls"] = [
            entry for entry in payload.get("acls", [])
            if not (entry.get("acltype") == acl_type.value and entry.get("topic") == topic)
        ]
        state = await desired_state_svc.set_role_desired(db, payload)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_role,
            db,
            role_name,
        )
        _ensure_reconcile_success(state, "Role ACL removal reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando remocion ACL %s/%s para role %s: %s", acl_type.value, topic, role_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Role desired state reconciliation failed after broker mutation. Check control-plane status.",
        )
    return {
        "message": f"ACL removed from role {role_name} successfully",
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


@router.post("/roles/{role_name}/acls/test")
async def test_role_acl(
    role_name: str,
    payload: TestACLRequest,
    api_key: str = Security(get_api_key),
):
    """
    Evalúa si el rol tiene acceso a un topic para un tipo de ACL dado.

    Implementa el algoritmo de matching de Mosquitto:
    - Primero evalúa las ACLs del rol (prioridad descendente).
    - Si ninguna regla del rol coincide, consulta el ACL por defecto.
    - Retorna la primera regla que coincide o la decisión por defecto.

    Nota: '#' no coincide con topics que empiecen por '$' (MQTT §4.7.3).
    """
    acl_type = payload.aclType
    topic = payload.topic.strip()

    if not topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El campo 'topic' no puede estar vacío.",
        )

    # Obtener las ACLs del rol desde el estado observado
    role_data = desired_state_svc.get_observed_role(role_name)
    if role_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rol '{role_name}' no encontrado.",
        )

    acls: list[dict] = role_data.get("acls", [])

    # Filtrar por tipo de ACL y ordenar por prioridad (mayor primero)
    matching_type = [
        entry for entry in acls
        if entry.get("acltype", "").lower() == acl_type.lower()
    ]
    matching_type.sort(key=lambda e: e.get("priority", 0), reverse=True)

    # Evaluar cada regla del rol
    for entry in matching_type:
        pattern = entry.get("topic", "")
        if _mqtt_topic_matches(pattern, topic):
            allowed = bool(entry.get("allow", False))
            return {
                "allowed": allowed,
                "reason": "role_acl",
                "matchedRule": {
                    "topic": pattern,
                    "aclType": entry.get("acltype", acl_type),
                    "allow": allowed,
                    "priority": entry.get("priority", 0),
                },
            }

    # Sin coincidencia en el rol → consultar ACL por defecto
    default_acl = desired_state_svc.get_observed_default_acl()
    default_key_map = {
        "publishClientSend":    "publishClientSend",
        "publishclientsend":    "publishClientSend",
        "publishClientReceive": "publishClientReceive",
        "publishclientreceive": "publishClientReceive",
        "subscribe":            "subscribe",
        "subscribeliteral":     "subscribe",
        "subscribepattern":     "subscribe",
        "unsubscribe":          "unsubscribe",
        "unsubscriteliteral":   "unsubscribe",
        "unsubscribepattern":   "unsubscribe",
    }
    default_key = default_key_map.get(acl_type.lower())
    default_allowed = False
    if default_acl and default_key:
        default_allowed = bool(default_acl.get(default_key, False))

    return {
        "allowed": default_allowed,
        "reason": "default_acl",
        "matchedRule": None,
        "defaultKey": default_key,
    }


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------

@router.get("/groups")
async def list_groups(api_key: str = Security(get_api_key)):
    try:
        index = desired_state_svc.get_cached_observed_dynsec_index()
        group_names = sorted(index.get("group_lookup", {}).keys())
        return {
            "groups": group_names,
            "summaries": index.get("group_summaries", []),
        }
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/groups/{group_name}")
async def get_group(group_name: str, api_key: str = Security(get_api_key)):
    try:
        group_data = desired_state_svc.get_observed_group(group_name)
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


@router.get("/groups/{group_name}/status")
async def get_group_status(
    group_name: str,
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await desired_state_svc.get_group_status(db, group_name)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load group control-plane status: {exc}",
        )


@router.post("/groups", status_code=status.HTTP_201_CREATED)
async def create_group(
    group: GroupCreate,
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    try:
        state = await desired_state_svc.set_group_desired(
            db,
            {"groupname": group.name, "roles": [], "clients": [], "deleted": False},
        )
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_group,
            db,
            group.name,
        )
        _ensure_reconcile_success(state, "Group reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando create group %s: %s", group.name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Group desired state reconciliation failed.",
        )
    return {
        "message": f"Group {group.name} created successfully",
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


@router.delete("/groups/{group_name}")
async def delete_group(
    group_name: str,
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    try:
        observed = desired_state_svc.get_observed_group(group_name)
        payload = observed or {"groupname": group_name, "roles": [], "clients": []}
        payload["deleted"] = True
        state = await desired_state_svc.set_group_desired(db, payload)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_group,
            db,
            group_name,
        )
        _ensure_reconcile_success(state, "Group deletion reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando delete group %s: %s", group_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Group desired state reconciliation failed after broker deletion. Check control-plane status.",
        )
    return {
        "message": f"Group {group_name} deleted successfully",
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


@router.post("/groups/{group_name}/roles")
async def add_group_role(group_name: str, role: RoleAssignment,
                         api_key: str = Security(get_api_key),
                         db: AsyncSession = Depends(get_db)):
    try:
        observed = desired_state_svc.get_observed_group(group_name)
        payload = observed or {"groupname": group_name, "roles": [], "clients": []}
        roles = payload.setdefault("roles", [])
        if not any(entry.get("rolename") == role.role_name for entry in roles):
            roles.append({"rolename": role.role_name, "priority": role.priority or 1})
        state = await desired_state_svc.set_group_desired(db, payload)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_group,
            db,
            group_name,
        )
        _ensure_reconcile_success(state, "Group role reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando addGroupRole %s/%s: %s", group_name, role.role_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Group desired state reconciliation failed.",
        )
    return {
        "message": f"Role {role.role_name} assigned to group {group_name}",
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


@router.delete("/groups/{group_name}/roles/{role_name}")
async def remove_group_role(group_name: str, role_name: str,
                            api_key: str = Security(get_api_key),
                            db: AsyncSession = Depends(get_db)):
    try:
        observed = desired_state_svc.get_observed_group(group_name)
        payload = observed or {"groupname": group_name, "roles": [], "clients": []}
        payload["roles"] = [
            entry for entry in payload.get("roles", [])
            if entry.get("rolename") != role_name
        ]
        state = await desired_state_svc.set_group_desired(db, payload)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_group,
            db,
            group_name,
        )
        _ensure_reconcile_success(state, "Group role removal reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando removeGroupRole %s/%s: %s", group_name, role_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Group desired state reconciliation failed after broker mutation. Check control-plane status.",
        )
    return {
        "message": f"Role {role_name} removed from group {group_name}",
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


@router.post("/groups/{group_name}/clients")
async def add_client_to_group(group_name: str, body: dict,
                              api_key: str = Security(get_api_key),
                              db: AsyncSession = Depends(get_db)):
    username = body.get("username")
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Username is required")
    priority = body.get("priority")
    try:
        observed = desired_state_svc.get_observed_group(group_name)
        payload = observed or {"groupname": group_name, "roles": [], "clients": []}
        clients = payload.setdefault("clients", [])
        if not any(entry.get("username") == username for entry in clients):
            client_entry: Dict[str, Any] = {"username": username}
            if priority is not None:
                client_entry["priority"] = int(priority)
            clients.append(client_entry)
        state = await desired_state_svc.set_group_desired(db, payload)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_group,
            db,
            group_name,
        )
        _ensure_reconcile_success(state, "Group membership reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando addGroupClient %s/%s: %s", group_name, username, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Group desired state reconciliation failed: {exc}",
        )
    return {
        "message": f"Client {username} added to group {group_name} successfully",
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


@router.delete("/groups/{group_name}/clients/{username}")
async def remove_client_from_group(group_name: str, username: str,
                                   api_key: str = Security(get_api_key),
                                   db: AsyncSession = Depends(get_db)):
    try:
        observed = desired_state_svc.get_observed_group(group_name)
        payload = observed or {"groupname": group_name, "roles": [], "clients": []}
        payload["clients"] = [
            entry for entry in payload.get("clients", [])
            if entry.get("username") != username
        ]
        state = await desired_state_svc.set_group_desired(db, payload)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_group,
            db,
            group_name,
        )
        _ensure_reconcile_success(state, "Group membership reconciliation failed")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciliando removeGroupClient %s/%s: %s", group_name, username, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Group desired state reconciliation failed: {exc}",
        )
    return {
        "message": f"Client {username} removed from group {group_name} successfully",
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


# ---------------------------------------------------------------------------
# Default ACL
# ---------------------------------------------------------------------------

@router.get("/default-acl")
async def get_default_acl(api_key: str = Security(get_api_key)):
    try:
        raw = desired_state_svc.get_observed_default_acl()
        return {
            "publishClientSend": bool(raw.get("publishClientSend", True)),
            "publishClientReceive": bool(raw.get("publishClientReceive", True)),
            "subscribe": bool(raw.get("subscribe", True)),
            "unsubscribe": bool(raw.get("unsubscribe", True)),
        }
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to load defaultACLAccess: {exc}")


@router.get("/default-acl/status")
async def get_default_acl_status(
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await desired_state_svc.get_default_acl_status(db)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load default ACL status: {exc}",
        )


@router.put("/default-acl")
async def set_default_acl(acl_config: DefaultACLConfig,
                          api_key: str = Security(get_api_key),
                          db: AsyncSession = Depends(get_db)):
    updates = {
        "publishClientSend":    acl_config.publishClientSend,
        "publishClientReceive": acl_config.publishClientReceive,
        "subscribe":            acl_config.subscribe,
        "unsubscribe":          acl_config.unsubscribe,
    }
    try:
        state = await desired_state_svc.set_default_acl_desired(db, updates)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_default_acl,
            db,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reconcile default ACL access: {exc}",
        )

    _ensure_reconcile_success(state, "Default ACL reconciliation failed")

    return {
        "message": "Default ACL access updated successfully",
        "config": desired_state_svc.normalize_default_acl(updates),
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }
